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
 *
 * This service hashes/validates passwords, tracks session authorization states,
 * enforces rate limiting, and persists metadata in the `page_password_protect`
 * table. Admin users bypass protection via permissions, while visitor sessions
 * are granted timed access upon successful validation. All interactions use
 * injectable Drupal services so unit testing becomes practical in later phases.
 */
class PasswordProtectionService {

  protected const DEFAULT_MAX_ATTEMPTS = 5;
  protected const DEFAULT_SESSION_TIMEOUT = 3600;

  /**
   * The database connection used to read and write password records.
   *
   * @var \Drupal\Core\Database\Connection
   */
  protected Connection $database;

  /**
   * Drupal's password hasher (bcrypt).
   *
   * @var \Drupal\Core\Password\PasswordInterface
   */
  protected PasswordInterface $passwordHasher;

  /**
   * Stack of HTTP requests to access the current session.
   *
   * @var \Symfony\Component\HttpFoundation\RequestStack
   */
  protected RequestStack $requestStack;

  /**
   * Manages PHP session lifecycle to ensure anonymous sessions start.
   *
   * @var \Drupal\Core\Session\SessionManagerInterface
   */
  protected SessionManagerInterface $sessionManager;

  /**
   * Represents the current user with permission helpers.
   *
   * @var \Drupal\Core\Session\AccountProxyInterface
   */
  protected AccountProxyInterface $currentUser;

  /**
   * Provides access to configuration such as max_attempts/session_timeout.
   *
   * @var \Drupal\Core\Config\ConfigFactoryInterface
   */
  protected ConfigFactoryInterface $configFactory;

  /**
   * Logger for the page_password_protect channel.
   *
   * @var \Psr\Log\LoggerInterface
   */
  protected LoggerInterface $logger;

  /**
   * Constructs a PasswordProtectionService instance.
   *
   * @param \Drupal\Core\Database\Connection $database
   *   The active database connection.
   * @param \Drupal\Core\Password\PasswordInterface $password_hasher
   *   The Drupal password hashing service.
   * @param \Symfony\Component\HttpFoundation\RequestStack $request_stack
   *   Request stack for session retrieval.
   * @param \Drupal\Core\Session\SessionManagerInterface $session_manager
   *   Ensures anonymous sessions exist when needed.
   * @param \Drupal\Core\Session\AccountProxyInterface $current_user
   *   The current account proxy used for permission checks.
   * @param \Drupal\Core\Config\ConfigFactoryInterface $config_factory
   *   Access to configurable module settings.
   * @param \Psr\Log\LoggerInterface $logger
   *   Module-specific logger channel.
   */
  public function __construct(Connection $database, PasswordInterface $password_hasher, RequestStack $request_stack, SessionManagerInterface $session_manager, AccountProxyInterface $current_user, ConfigFactoryInterface $config_factory, LoggerInterface $logger) {
    $this->database = $database;
    $this->passwordHasher = $password_hasher;
    $this->requestStack = $request_stack;
    $this->sessionManager = $session_manager;
    $this->currentUser = $current_user;
    $this->configFactory = $config_factory;
    $this->logger = $logger;
  }

  /**
   * Hashes and stores a password for the provided node.
   *
   * @param \Drupal\node\NodeInterface $node
   *   Node whose password is being set.
   * @param string $plain_password
   *   Plain-text password provided by the administrator.
   * @param string $hint
   *   Optional hint shown to visitors.
   *
   * @return bool
   *   TRUE on success, FALSE on failure.
   */
  public function setPassword(NodeInterface $node, string $plain_password, string $hint = ''): bool {
    $timestamp = time();

    try {
      $hash = $this->passwordHasher->hash($plain_password);
      $this->database->merge('page_password_protect')
        ->key(['nid' => $node->id()])
        ->fields([
          'password_hash' => $hash,
          'hint' => $hint,
          'changed' => $timestamp,
        ])
        ->insertFields([
          'created' => $timestamp,
        ])
        ->execute();

      $this->logger->info('Stored password hash for node @nid.', ['@nid' => $node->id()]);
      return TRUE;
    }
    catch (Throwable $exception) {
      $this->logger->error('Failed to set password for node @nid: @message', [
        '@nid' => $node->id(),
        '@message' => $exception->getMessage(),
      ]);
      return FALSE;
    }
  }

  /**
   * Deletes the password record for a node.
   *
   * @param \Drupal\node\NodeInterface $node
   *   Node whose password is being removed.
   *
   * @return bool
   *   TRUE when removal succeeds or the record did not exist.
   */
  /**
   * Deletes the password record for a node.
   *
   * Removes the stored hash and revokes access for the current session only.
   *
   * @param \Drupal\node\NodeInterface $node
   *   Node whose password is being removed.
   *
   * @return bool
   *   TRUE when the operation succeeds, FALSE if the database interaction fails.
   */
  public function removePassword(NodeInterface $node): bool {
    try {
      $this->database->delete('page_password_protect')
        ->condition('nid', $node->id())
        ->execute();

      $this->revokeAccess($node);
      $this->logger->info('Removed password protection for node @nid (current session only).', ['@nid' => $node->id()]);
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

  /**
   * Validates a password attempt for a protected node.
   *
   * Performs rate limiting and updates session metadata upon success.
   *
   * @param \Drupal\node\NodeInterface $node
   *   Target node for validation.
   * @param string $plain_password
   *   Submitted plain-text password.
   *
   * @return bool
   *   TRUE if the password matches, FALSE otherwise.
   */
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

  /**
   * Grants the current session access to the provided node.
   *
   * @param \Drupal\node\NodeInterface $node
   *   Node to grant access for.
   */
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
    $this->logger->info('Granted session {sid} access to node @nid.', ['@nid' => $node->id(), '{sid}' => $session->getId()]);
  }

  /**
   * Revokes the current session's access to the given node.
   *
   * @param \Drupal\node\NodeInterface $node
   *   Node to revoke access for.
   */
  public function revokeAccess(NodeInterface $node): void {
    $session = $this->getCurrentSession();
    if (!$session) {
      return;
    }

    $authorized = $this->getAuthorizedNodes($session);
    $updated = array_diff($authorized, [$node->id()]);
    $session->set('page_password_protect.authorized_nodes', array_values($updated));
    $session->remove('page_password_protect.timeout.' . $node->id());
    $this->logger->info('Revoked session {sid} access for node @nid.', ['@nid' => $node->id(), '{sid}' => $session->getId()]);
  }

  /**
   * Determines whether the provided node is protected.
   *
   * @param \Drupal\node\NodeInterface $node
   *   Candidate node.
   *
   * @return bool
   *   TRUE if the node has Password Protect enabled.
   */
  public function isProtected(NodeInterface $node): bool {
    if (!$node->hasField('field_page_password_protected')) {
      return FALSE;
    }

    $field = $node->get('field_page_password_protected');
    return !$field->isEmpty() && (bool) $field->value;
  }

  /**
   * Returns password metadata for a node.
   *
   * @param \Drupal\node\NodeInterface $node
   *   Target node.
   *
   * @return array|null
   *   Database row or NULL when no record exists.
   */
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

  /**
   * Checks whether the current session or user may view a protected node.
   *
   * @param \Drupal\node\NodeInterface $node
   *   Node being accessed.
   * @param \Drupal\Core\Session\AccountInterface|null $account
   *   Optional account to check; defaults to the current user.
   *
   * @return bool
   *   TRUE if the node is accessible.
   */
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

  /**
   * Returns the number of password attempts stored in the current session.
   *
   * @param \Drupal\node\NodeInterface $node
   *   Node being protected.
   *
   * @return int
   *   Number of attempts used so far.
   */
  public function getAttemptCount(NodeInterface $node): int {
    $session = $this->getCurrentSession();
    if (!$session) {
      return 0;
    }
    return (int) $session->get($this->getAttemptKey($node), 0);
  }

  /**
   * Resets the attempt counter stored in the session.
   *
   * @param \Drupal\node\NodeInterface $node
   *   Node whose counter should be reset.
   */
  public function resetAttempts(NodeInterface $node): void {
    $session = $this->getCurrentSession();
    if (!$session) {
      return;
    }

    $session->remove($this->getAttemptKey($node));
    $this->logger->debug('Attempt counter reset for node @nid.', ['@nid' => $node->id()]);
  }

  /**
   * Determines if the current session has exceeded max attempts.
   *
   * @param \Drupal\node\NodeInterface $node
   *   Node being protected.
   *
   * @return bool
   *   TRUE when the attempt counter meets or exceeds the configured max.
   */
  public function isRateLimited(NodeInterface $node): bool {
    $max_attempts = $this->getNormalizedMaxAttempts();
    return $this->getAttemptCount($node) >= $max_attempts;
  }

  /**
   * Returns the number of attempts remaining for the given node.
   *
   * @param \Drupal\node\NodeInterface $node
   *   Node being protected.
   *
   * @return int
   *   Attempts left before hitting rate limit.
   */
  public function getRemainingAttempts(NodeInterface $node): int {
    $remaining = $this->getNormalizedMaxAttempts() - $this->getAttemptCount($node);
    return $remaining > 0 ? $remaining : 0;
  }

  /**
   * Returns the normalized max attempts.
   *
   * @return int
   *   A safe, positive attempt count.
   */
  protected function getNormalizedMaxAttempts(): int {
    $value = $this->getSettings()->get('max_attempts');
    if (!is_numeric($value)) {
      return self::DEFAULT_MAX_ATTEMPTS;
    }
    $attempts = (int) $value;
    return $attempts > 0 ? $attempts : self::DEFAULT_MAX_ATTEMPTS;
  }

  /**
   * Returns the validated session timeout in seconds or NULL when sessions never expire.
   *
   * @return int|null
   *   Number of seconds until expiration or NULL for none.
   */
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

  /**
   * Increments the attempt counter for the node.
   *
   * @param \Drupal\node\NodeInterface $node
   *   Node being accessed.
   */
  protected function incrementAttempts(NodeInterface $node): void {
    $session = $this->getCurrentSession();
    if (!$session) {
      return;
    }

    $count = $this->getAttemptCount($node) + 1;
    $session->set($this->getAttemptKey($node), $count);
  }

  /**
   * Returns the key used for storing attempt counters in the session.
   *
   * @param \Drupal\node\NodeInterface $node
   *   Node being accessed.
   *
   * @return string
   *   Cache key string.
   */
  protected function getAttemptKey(NodeInterface $node): string {
    return 'page_password_protect.attempts.' . $node->id();
  }

  /**
   * Reads the current session, starting it when necessary.
   *
   * @return \Symfony\Component\HttpFoundation\Session\SessionInterface|null
   *   Active session or NULL when unavailable.
   */
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

  /**
   * Retrieves the list of authorized node IDs from session storage.
   *
   * @param \Symfony\Component\HttpFoundation\Session\SessionInterface $session
   *   Session object.
   *
   * @return int[]
   *   Node IDs granted access.
   */
  protected function getAuthorizedNodes(SessionInterface $session): array {
    $authorized = $session->get('page_password_protect.authorized_nodes', []);
    return is_array($authorized) ? $authorized : [];
  }

  /**
   * Returns the IP address of the current request for logging.
   *
   * @return string
   *   Client IP or 'unknown'.
   */
  protected function getCurrentRequestIp(): string {
    $request = $this->requestStack->getCurrentRequest();
    if (!$request) {
      return 'unknown';
    }

    $ip = $request->getClientIp();
    return $ip ? $ip : 'unknown';
  }

  /**
   * Retrieves the module settings config object.
   *
   * @return \\Drupal\\Core\\Config\\ImmutableConfig
   *   Settings for page_password_protect.
   */
  protected function getSettings() {
    return $this->configFactory->get('page_password_protect.settings');
  }
}
