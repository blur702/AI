<?php

namespace Drupal\congressional_query\Authentication;

use Drupal\congressional_query\Service\ApiKeyManager;
use Drupal\Core\Authentication\AuthenticationProviderInterface;
use Drupal\Core\Session\AccountInterface;
use Drupal\Core\Session\UserSession;
use Drupal\user\Entity\User;
use Psr\Log\LoggerInterface;
use Symfony\Component\HttpFoundation\Request;

/**
 * Authentication provider for API key authentication.
 */
class ApiKeyAuth implements AuthenticationProviderInterface {

  /**
   * The API key manager.
   *
   * @var \Drupal\congressional_query\Service\ApiKeyManager
   */
  protected $apiKeyManager;

  /**
   * The logger.
   *
   * @var \Psr\Log\LoggerInterface
   */
  protected $logger;

  /**
   * Constructs an ApiKeyAuth provider.
   *
   * @param \Drupal\congressional_query\Service\ApiKeyManager $api_key_manager
   *   The API key manager.
   * @param \Psr\Log\LoggerInterface $logger
   *   The logger.
   */
  public function __construct(ApiKeyManager $api_key_manager, LoggerInterface $logger) {
    $this->apiKeyManager = $api_key_manager;
    $this->logger = $logger;
  }

  /**
   * {@inheritdoc}
   */
  public function applies(Request $request) {
    // Check if this is an API endpoint.
    $path = $request->getPathInfo();

    // Only apply to congressional API endpoints.
    if (!str_starts_with($path, '/api/congressional/')) {
      return FALSE;
    }

    // Skip public endpoints.
    $publicPaths = [
      '/api/congressional/docs',
      '/api/congressional/documentation',
    ];

    foreach ($publicPaths as $publicPath) {
      if (str_starts_with($path, $publicPath)) {
        return FALSE;
      }
    }

    // Apply if X-API-Key header is present.
    return $request->headers->has('X-API-Key');
  }

  /**
   * {@inheritdoc}
   */
  public function authenticate(Request $request) {
    $apiKey = $request->headers->get('X-API-Key');

    if (empty($apiKey)) {
      return NULL;
    }

    // Validate the key.
    $keyEntity = $this->apiKeyManager->validateKey($apiKey);

    if (!$keyEntity) {
      $this->logger->warning('Invalid API key attempt from @ip', [
        '@ip' => $request->getClientIp(),
      ]);
      return NULL;
    }

    // Check IP restrictions.
    $clientIp = $request->getClientIp();
    if (!$keyEntity->isIpAllowed($clientIp)) {
      $this->logger->warning('API key @prefix denied for IP @ip', [
        '@prefix' => $keyEntity->getKeyPrefix(),
        '@ip' => $clientIp,
      ]);
      return NULL;
    }

    // Update last used timestamp.
    $this->apiKeyManager->updateLastUsed($keyEntity->getId());

    // Store the key entity in the request for later use.
    $request->attributes->set('_congressional_api_key', $keyEntity);

    // Load the user associated with this key.
    $uid = $keyEntity->getUid();
    if ($uid > 0) {
      $user = User::load($uid);
      if ($user) {
        return $user;
      }
    }

    // If no user associated, return anonymous with API access.
    return new UserSession([
      'uid' => 0,
      'roles' => ['anonymous'],
    ]);
  }

  /**
   * {@inheritdoc}
   */
  public function cleanup(Request $request) {
    // Nothing to clean up.
  }

  /**
   * {@inheritdoc}
   */
  public function handleException(\Exception $exception, Request $request) {
    return TRUE;
  }

}
