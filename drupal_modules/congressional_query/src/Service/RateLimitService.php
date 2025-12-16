<?php

namespace Drupal\congressional_query\Service;

use Drupal\congressional_query\Entity\ApiKey;
use Drupal\Core\Config\ConfigFactoryInterface;
use Drupal\Core\Database\Connection;
use Drupal\Core\Flood\FloodInterface;
use Psr\Log\LoggerInterface;

/**
 * Service for rate limiting API requests.
 */
class RateLimitService {

  /**
   * The flood service.
   *
   * @var \Drupal\Core\Flood\FloodInterface
   */
  protected $flood;

  /**
   * The database connection.
   *
   * @var \Drupal\Core\Database\Connection
   */
  protected $database;

  /**
   * The config factory.
   *
   * @var \Drupal\Core\Config\ConfigFactoryInterface
   */
  protected $configFactory;

  /**
   * The logger.
   *
   * @var \Psr\Log\LoggerInterface
   */
  protected $logger;

  /**
   * Constructs a RateLimitService.
   *
   * @param \Drupal\Core\Flood\FloodInterface $flood
   *   The flood service.
   * @param \Drupal\Core\Database\Connection $database
   *   The database connection.
   * @param \Drupal\Core\Config\ConfigFactoryInterface $config_factory
   *   The config factory.
   * @param \Psr\Log\LoggerInterface $logger
   *   The logger.
   */
  public function __construct(
    FloodInterface $flood,
    Connection $database,
    ConfigFactoryInterface $config_factory,
    LoggerInterface $logger
  ) {
    $this->flood = $flood;
    $this->database = $database;
    $this->configFactory = $config_factory;
    $this->logger = $logger;
  }

  /**
   * Checks if a request is within rate limits.
   *
   * @param string $identifier
   *   The identifier (API key ID, IP address, etc.).
   * @param string $endpoint
   *   The API endpoint.
   * @param \Drupal\congressional_query\Entity\ApiKey|null $api_key
   *   Optional API key entity for custom limits.
   *
   * @return array
   *   Array with 'allowed' (bool), 'limit', 'remaining', 'reset' (timestamp).
   */
  public function checkLimit(string $identifier, string $endpoint, ?ApiKey $api_key = NULL): array {
    $config = $this->configFactory->get('congressional_query.api_settings');

    // Determine the rate limit.
    $limit = $config->get('default_rate_limit') ?: 100;
    $window = $config->get('rate_limit_window') ?: 3600;

    // Check for API key override.
    if ($api_key && $api_key->getRateLimitOverride()) {
      $limit = $api_key->getRateLimitOverride();
    }

    // Use a combination of endpoint and identifier for granular limiting.
    $name = 'congressional_api:' . $endpoint;

    // Check if within limit.
    $allowed = $this->flood->isAllowed($name, $limit, $window, $identifier);

    // Get remaining count.
    $remaining = $this->getRemainingRequests($identifier, $name, $limit, $window);

    // Calculate reset time.
    $reset = $this->getResetTime($identifier, $name, $window);

    return [
      'allowed' => $allowed,
      'limit' => $limit,
      'remaining' => max(0, $remaining - 1),
      'reset' => $reset,
      'window' => $window,
    ];
  }

  /**
   * Registers a request for rate limiting.
   *
   * @param string $identifier
   *   The identifier.
   * @param string $endpoint
   *   The API endpoint.
   */
  public function registerRequest(string $identifier, string $endpoint): void {
    $config = $this->configFactory->get('congressional_query.api_settings');
    $window = $config->get('rate_limit_window') ?: 3600;

    $name = 'congressional_api:' . $endpoint;
    $this->flood->register($name, $window, $identifier);
  }

  /**
   * Gets the remaining request count.
   *
   * @param string $identifier
   *   The identifier.
   * @param string $name
   *   The flood event name.
   * @param int $limit
   *   The rate limit.
   * @param int $window
   *   The time window in seconds.
   *
   * @return int
   *   Remaining requests.
   */
  protected function getRemainingRequests(string $identifier, string $name, int $limit, int $window): int {
    // Count existing events in the window.
    $cutoff = time() - $window;

    try {
      $count = $this->database->select('flood', 'f')
        ->condition('event', $name)
        ->condition('identifier', $identifier)
        ->condition('timestamp', $cutoff, '>')
        ->countQuery()
        ->execute()
        ->fetchField();

      return $limit - (int) $count;
    }
    catch (\Exception $e) {
      // If flood table doesn't exist or query fails, assume full limit.
      return $limit;
    }
  }

  /**
   * Gets the reset timestamp.
   *
   * @param string $identifier
   *   The identifier.
   * @param string $name
   *   The flood event name.
   * @param int $window
   *   The time window in seconds.
   *
   * @return int
   *   Reset timestamp.
   */
  protected function getResetTime(string $identifier, string $name, int $window): int {
    // Get the oldest event in the current window.
    $cutoff = time() - $window;

    try {
      $oldest = $this->database->select('flood', 'f')
        ->fields('f', ['timestamp'])
        ->condition('event', $name)
        ->condition('identifier', $identifier)
        ->condition('timestamp', $cutoff, '>')
        ->orderBy('timestamp', 'ASC')
        ->range(0, 1)
        ->execute()
        ->fetchField();

      if ($oldest) {
        return (int) $oldest + $window;
      }
    }
    catch (\Exception $e) {
      // Ignore errors.
    }

    return time() + $window;
  }

  /**
   * Clears rate limit for an identifier.
   *
   * @param string $identifier
   *   The identifier.
   * @param string|null $endpoint
   *   Optional specific endpoint.
   */
  public function clearLimit(string $identifier, ?string $endpoint = NULL): void {
    if ($endpoint) {
      $name = 'congressional_api:' . $endpoint;
      $this->flood->clear($name, $identifier);
    }
    else {
      // Clear all congressional API limits for this identifier.
      try {
        $this->database->delete('flood')
          ->condition('event', 'congressional_api:%', 'LIKE')
          ->condition('identifier', $identifier)
          ->execute();
      }
      catch (\Exception $e) {
        $this->logger->error('Failed to clear rate limits: @message', [
          '@message' => $e->getMessage(),
        ]);
      }
    }
  }

  /**
   * Gets rate limit headers for a response.
   *
   * @param array $limit_info
   *   The limit info from checkLimit().
   *
   * @return array
   *   Array of headers.
   */
  public function getHeaders(array $limit_info): array {
    return [
      'X-RateLimit-Limit' => $limit_info['limit'],
      'X-RateLimit-Remaining' => $limit_info['remaining'],
      'X-RateLimit-Reset' => $limit_info['reset'],
    ];
  }

}
