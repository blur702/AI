<?php

namespace Drupal\page_password_protect\Service;

use Drupal\Core\Config\ConfigFactoryInterface;
use Drupal\Core\Database\Connection;
use Drupal\Core\Password\PasswordInterface;
use Drupal\Core\Session\AccountInterface;
use Drupal\Core\Session\AccountProxyInterface;
use Drupal\Core\Session\SessionManagerInterface;
use Drupal\node\NodeInterface;
use Psr\Log\LoggerInterface;
use Symfony\Component\HttpFoundation\RequestStack;
use Symfony\Component\HttpFoundation\Session\SessionInterface;
use Throwable;

/**
 * Encapsulates password protection logic for the Page Password Protect module.
 */
class PasswordProtectionService {

  protected const DEFAULT_MAX_ATTEMPTS = 5;
  protected const DEFAULT_SESSION_TIMEOUT = 3600;

  protected Connection $database;
  protected PasswordInterface $passwordHasher;
  protected RequestStack $requestStack;
  protected SessionManagerInterface $sessionManager;
  protected AccountProxyInterface $currentUser;
  protected ConfigFactoryInterface $configFactory;
  protected LoggerInterface $logger;

  public function __construct(Connection $database, PasswordInterface $password_hasher, RequestStack $request_stack, SessionManagerInterface $session_manager, AccountProxyInterface $current_user, ConfigFactoryInterface $config_factory, LoggerInterface $logger) {
    $this->database = $database;
    $this->passwordHasher = $password_hasher;
    $this->requestStack = $request_stack;
    $this->sessionManager = $session_manager;
    $this->currentUser = $current_user;
    $this->configFactory = $config_factory;
    $this->logger = $logger;
  }

  public function setPassword(NodeInterface $node, string $plain_password, string $hint = ''): bool {
    $timestamp = time();
    $nid = (int) $node->id();

    try {
      $hash = $this->passwordHasher->hash($plain_password);

      // Use insert/update pattern instead of merge for better compatibility.
      $existing = $this->database->select('page_password_protect', 'pp')
        ->fields('pp', ['nid'])
        ->condition('nid', $nid)
        ->execute()
        ->fetchField();

      if ($existing) {
        $this->database->update('page_password_protect')
          ->fields([
            'password_hash' => $hash,
            'hint' => $hint,
            'changed' => $timestamp,
          ])
          ->condition('nid', $nid)
          ->execute();
      }
      else {
        $this->database->insert('page_password_protect')
          ->fields([
            'nid' => $nid,
            'password_hash' => $hash,
            'hint' => $hint,
            'created' => $timestamp,
            'changed' => $timestamp,
          ])
          ->execute();
      }

      $this->logger->info('Stored password hash for node @nid.', ['@nid' => $nid]);
      return TRUE;
    }
    catch (Throwable $exception) {
      $this->logger->error('Failed to set password for node @nid: @message', [
        '@nid' => $nid,
        '@message' => $exception->getMessage(),
      ]);
      return FALSE;
    }
  }

  public function removePassword(NodeInterface $node): bool {
    try {
      $this->database->delete('page_password_protect')
        ->condition('nid', $node->id())
        ->execute();

      $this->revokeAccess($node);
      $this->logger->info('Removed password protection for node @nid.', ['@nid' => $node->id()]);
      return TRUE;
    }
    catch (Throwable $exception) {
      $this->logger->error('Failed to remove password for node @nid: @message', [
        '@nid' => $node->id(),
        '@message' => $exception->getMessage(),
      ]);
      return FALSE;
    }
  }

  public function validatePassword(NodeInterface $node, string $plain_password): bool {
    $data = $this->getPasswordData($node);
    if (empty($data) || empty($data['password_hash'])) {
      return FALSE;
    }

    $ip = $this->getCurrentRequestIp();
    if ($this->isRateLimited($node)) {
      $this->logger->warning('Rate limit reached for node @nid from @ip.', ['@nid' => $node->id(), '@ip' => $ip]);
      return FALSE;
    }

    $valid = $this->passwordHasher->check($plain_password, $data['password_hash']);
    if ($valid) {
      $this->resetAttempts($node);
      $this->grantAccess($node);
      $this->logger->info('Password validated for node @nid from @ip.', ['@nid' => $node->id(), '@ip' => $ip]);
      return TRUE;
    }

    $this->incrementAttempts($node);
    $this->logger->notice('Failed password attempt for node @nid from @ip.', ['@nid' => $node->id(), '@ip' => $ip]);
    return FALSE;
  }

  public function grantAccess(NodeInterface $node): void {
    $session = $this->getCurrentSession();
    if (!$session) {
      $this->logger->warning('Unable to grant access because no session is available.');
      return;
    }

    $authorized = $this->getAuthorizedNodes($session);
    if (!in_array($node->id(), $authorized, TRUE)) {
      $authorized[] = $node->id();
      $session->set('page_password_protect.authorized_nodes', $authorized);
    }

    $timeout = $this->getValidatedSessionTimeout();
    if ($timeout !== null) {
      $session->set('page_password_protect.timeout.' . $node->id(), time() + $timeout);
    }
    $this->logger->info('Granted session access to node @nid.', ['@nid' => $node->id()]);
  }

  public function revokeAccess(NodeInterface $node): void {
    $session = $this->getCurrentSession();
    if (!$session) {
      return;
    }

    $authorized = $this->getAuthorizedNodes($session);
    $updated = array_diff($authorized, [$node->id()]);
    $session->set('page_password_protect.authorized_nodes', array_values($updated));
    $session->remove('page_password_protect.timeout.' . $node->id());
    $this->logger->info('Revoked session access for node @nid.', ['@nid' => $node->id()]);
  }

  public function isProtected(NodeInterface $node): bool {
    if (!$node->hasField('field_page_password_protected')) {
      return FALSE;
    }

    $field = $node->get('field_page_password_protected');
    return !$field->isEmpty() && (bool) $field->value;
  }

  public function getPasswordData(NodeInterface $node): ?array {
    try {
      $result = $this->database->select('page_password_protect', 'pp')
        ->fields('pp')
        ->condition('nid', $node->id())
        ->execute()
        ->fetchAssoc();
      return $result ?: NULL;
    }
    catch (Throwable $exception) {
      $this->logger->error('Failed to load password data for node @nid: @message', [
        '@nid' => $node->id(),
        '@message' => $exception->getMessage(),
      ]);
      return NULL;
    }
  }

  public function checkAccess(NodeInterface $node, AccountInterface $account = NULL): bool {
    $user = $account ?? $this->currentUser;
    if ($user->hasPermission('bypass page password') || $user->hasPermission('administer page passwords')) {
      return TRUE;
    }

    if (!$this->isProtected($node)) {
      return TRUE;
    }

    $session = $this->getCurrentSession();
    if (!$session) {
      return FALSE;
    }

    $authorized = $this->getAuthorizedNodes($session);
    if (!in_array($node->id(), $authorized, TRUE)) {
      return FALSE;
    }

    $timeout = $session->get('page_password_protect.timeout.' . $node->id(), 0);
    if ($timeout && time() > $timeout) {
      $this->revokeAccess($node);
      return FALSE;
    }

    return TRUE;
  }

  public function getAttemptCount(NodeInterface $node): int {
    $session = $this->getCurrentSession();
    if (!$session) {
      return 0;
    }
    return (int) $session->get($this->getAttemptKey($node), 0);
  }

  public function resetAttempts(NodeInterface $node): void {
    $session = $this->getCurrentSession();
    if (!$session) {
      return;
    }

    $session->remove($this->getAttemptKey($node));
  }

  public function isRateLimited(NodeInterface $node): bool {
    $max_attempts = $this->getNormalizedMaxAttempts();
    return $this->getAttemptCount($node) >= $max_attempts;
  }

  public function getRemainingAttempts(NodeInterface $node): int {
    $remaining = $this->getNormalizedMaxAttempts() - $this->getAttemptCount($node);
    return $remaining > 0 ? $remaining : 0;
  }

  protected function getNormalizedMaxAttempts(): int {
    $value = $this->getSettings()->get('max_attempts');
    if (!is_numeric($value)) {
      return self::DEFAULT_MAX_ATTEMPTS;
    }
    $attempts = (int) $value;
    return $attempts > 0 ? $attempts : self::DEFAULT_MAX_ATTEMPTS;
  }

  protected function getValidatedSessionTimeout(): ?int {
    $value = $this->getSettings()->get('session_timeout');
    if (!is_numeric($value)) {
      return self::DEFAULT_SESSION_TIMEOUT;
    }
    $seconds = (int) $value;
    if ($seconds <= 0) {
      return null;
    }
    return $seconds;
  }

  protected function incrementAttempts(NodeInterface $node): void {
    $session = $this->getCurrentSession();
    if (!$session) {
      return;
    }

    $count = $this->getAttemptCount($node) + 1;
    $session->set($this->getAttemptKey($node), $count);
  }

  protected function getAttemptKey(NodeInterface $node): string {
    return 'page_password_protect.attempts.' . $node->id();
  }

  protected function getCurrentSession(): ?SessionInterface {
    $request = $this->requestStack->getCurrentRequest();
    if (!$request) {
      return NULL;
    }

    $session = $request->getSession();
    if (!$session) {
      return NULL;
    }

    if (!$session->isStarted()) {
      $this->sessionManager->start();
    }

    return $session;
  }

  protected function getAuthorizedNodes(SessionInterface $session): array {
    $authorized = $session->get('page_password_protect.authorized_nodes', []);
    return is_array($authorized) ? $authorized : [];
  }

  protected function getCurrentRequestIp(): string {
    $request = $this->requestStack->getCurrentRequest();
    if (!$request) {
      return 'unknown';
    }

    $ip = $request->getClientIp();
    return $ip ? $ip : 'unknown';
  }

  protected function getSettings() {
    return $this->configFactory->get('page_password_protect.settings');
  }
}
