<?php

namespace Drupal\congressional_query\Service;

use Drupal\congressional_query\Entity\ApiKey;
use Drupal\Core\Config\ConfigFactoryInterface;
use Drupal\Core\Database\Connection;
use Drupal\Core\Datetime\DateFormatterInterface;
use Psr\Log\LoggerInterface;

/**
 * Service for managing API keys.
 */
class ApiKeyManager {

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
   * The date formatter.
   *
   * @var \Drupal\Core\Datetime\DateFormatterInterface
   */
  protected $dateFormatter;

  /**
   * Constructs an ApiKeyManager.
   *
   * @param \Drupal\Core\Database\Connection $database
   *   The database connection.
   * @param \Drupal\Core\Config\ConfigFactoryInterface $config_factory
   *   The config factory.
   * @param \Psr\Log\LoggerInterface $logger
   *   The logger.
   * @param \Drupal\Core\Datetime\DateFormatterInterface $date_formatter
   *   The date formatter.
   */
  public function __construct(
    Connection $database,
    ConfigFactoryInterface $config_factory,
    LoggerInterface $logger,
    DateFormatterInterface $date_formatter
  ) {
    $this->database = $database;
    $this->configFactory = $config_factory;
    $this->logger = $logger;
    $this->dateFormatter = $date_formatter;
  }

  /**
   * Generates a new API key.
   *
   * @param string $name
   *   The key name.
   * @param int $uid
   *   The owner user ID.
   * @param int|null $rate_limit_override
   *   Optional custom rate limit.
   * @param array $allowed_ips
   *   Optional allowed IP addresses.
   *
   * @return array
   *   Array with 'key' (plaintext, shown once) and 'entity' (ApiKey object).
   */
  public function generateKey(string $name, int $uid, ?int $rate_limit_override = NULL, array $allowed_ips = []): array {
    // Generate a secure random key (32 bytes = 256 bits).
    $rawKey = random_bytes(32);
    $plaintextKey = 'cq_' . rtrim(strtr(base64_encode($rawKey), '+/', '-_'), '=');

    // Store the hash, not the plaintext.
    $hashedKey = hash('sha256', $plaintextKey);

    // Extract prefix for identification.
    $keyPrefix = substr($plaintextKey, 0, 8);

    $data = [
      'api_key' => $hashedKey,
      'key_prefix' => $keyPrefix,
      'name' => $name,
      'uid' => $uid,
      'created' => time(),
      'is_active' => 1,
      'rate_limit_override' => $rate_limit_override,
      'allowed_ips' => !empty($allowed_ips) ? json_encode($allowed_ips) : NULL,
    ];

    $this->database->insert('congressional_query_api_keys')
      ->fields($data)
      ->execute();

    $id = $this->database->select('congressional_query_api_keys', 'k')
      ->fields('k', ['id'])
      ->condition('api_key', $hashedKey)
      ->execute()
      ->fetchField();

    $data['id'] = $id;

    $this->logger->notice('API key generated: @name (prefix: @prefix) for user @uid', [
      '@name' => $name,
      '@prefix' => $keyPrefix,
      '@uid' => $uid,
    ]);

    return [
      'key' => $plaintextKey,
      'entity' => new ApiKey($data),
    ];
  }

  /**
   * Validates an API key.
   *
   * @param string $key
   *   The plaintext API key.
   *
   * @return \Drupal\congressional_query\Entity\ApiKey|null
   *   The ApiKey entity if valid, NULL otherwise.
   */
  public function validateKey(string $key): ?ApiKey {
    if (empty($key)) {
      return NULL;
    }

    $hashedKey = hash('sha256', $key);

    $result = $this->database->select('congressional_query_api_keys', 'k')
      ->fields('k')
      ->condition('api_key', $hashedKey)
      ->condition('is_active', 1)
      ->execute()
      ->fetchAssoc();

    if (!$result) {
      return NULL;
    }

    return new ApiKey($result);
  }

  /**
   * Updates the last_used timestamp for a key.
   *
   * @param int $key_id
   *   The key ID.
   */
  public function updateLastUsed(int $key_id): void {
    $this->database->update('congressional_query_api_keys')
      ->fields(['last_used' => time()])
      ->condition('id', $key_id)
      ->execute();
  }

  /**
   * Revokes an API key.
   *
   * @param int $key_id
   *   The key ID.
   *
   * @return bool
   *   TRUE if successful.
   */
  public function revokeKey(int $key_id): bool {
    $updated = $this->database->update('congressional_query_api_keys')
      ->fields(['is_active' => 0])
      ->condition('id', $key_id)
      ->execute();

    if ($updated) {
      $this->logger->notice('API key revoked: ID @id', ['@id' => $key_id]);
    }

    return $updated > 0;
  }

  /**
   * Deletes an API key permanently.
   *
   * @param int $key_id
   *   The key ID.
   *
   * @return bool
   *   TRUE if successful.
   */
  public function deleteKey(int $key_id): bool {
    $deleted = $this->database->delete('congressional_query_api_keys')
      ->condition('id', $key_id)
      ->execute();

    if ($deleted) {
      $this->logger->notice('API key deleted: ID @id', ['@id' => $key_id]);
    }

    return $deleted > 0;
  }

  /**
   * Reactivates a revoked API key.
   *
   * @param int $key_id
   *   The key ID.
   *
   * @return bool
   *   TRUE if successful.
   */
  public function reactivateKey(int $key_id): bool {
    $updated = $this->database->update('congressional_query_api_keys')
      ->fields(['is_active' => 1])
      ->condition('id', $key_id)
      ->execute();

    if ($updated) {
      $this->logger->notice('API key reactivated: ID @id', ['@id' => $key_id]);
    }

    return $updated > 0;
  }

  /**
   * Gets an API key by ID.
   *
   * @param int $key_id
   *   The key ID.
   *
   * @return \Drupal\congressional_query\Entity\ApiKey|null
   *   The ApiKey entity or NULL.
   */
  public function getKey(int $key_id): ?ApiKey {
    $result = $this->database->select('congressional_query_api_keys', 'k')
      ->fields('k')
      ->condition('id', $key_id)
      ->execute()
      ->fetchAssoc();

    return $result ? new ApiKey($result) : NULL;
  }

  /**
   * Lists API keys.
   *
   * @param int|null $uid
   *   Optional filter by user ID.
   * @param bool|null $active_only
   *   Optional filter by active status.
   * @param int $limit
   *   Maximum number of keys to return.
   * @param int $offset
   *   Offset for pagination.
   *
   * @return array
   *   Array of ApiKey entities.
   */
  public function listKeys(?int $uid = NULL, ?bool $active_only = NULL, int $limit = 50, int $offset = 0): array {
    $query = $this->database->select('congressional_query_api_keys', 'k')
      ->fields('k')
      ->orderBy('created', 'DESC')
      ->range($offset, $limit);

    if ($uid !== NULL) {
      $query->condition('uid', $uid);
    }

    if ($active_only !== NULL) {
      $query->condition('is_active', $active_only ? 1 : 0);
    }

    $results = $query->execute()->fetchAll(\PDO::FETCH_ASSOC);

    return array_map(function ($row) {
      return new ApiKey($row);
    }, $results);
  }

  /**
   * Counts API keys.
   *
   * @param int|null $uid
   *   Optional filter by user ID.
   * @param bool|null $active_only
   *   Optional filter by active status.
   *
   * @return int
   *   The count.
   */
  public function countKeys(?int $uid = NULL, ?bool $active_only = NULL): int {
    $query = $this->database->select('congressional_query_api_keys', 'k');
    $query->addExpression('COUNT(*)', 'count');

    if ($uid !== NULL) {
      $query->condition('uid', $uid);
    }

    if ($active_only !== NULL) {
      $query->condition('is_active', $active_only ? 1 : 0);
    }

    return (int) $query->execute()->fetchField();
  }

  /**
   * Gets API key statistics.
   *
   * @return array
   *   Statistics array.
   */
  public function getStatistics(): array {
    $now = time();
    $dayAgo = $now - 86400;
    $weekAgo = $now - 604800;

    $totalKeys = $this->countKeys();
    $activeKeys = $this->countKeys(NULL, TRUE);

    // Keys used in last 24 hours.
    $usedToday = $this->database->select('congressional_query_api_keys', 'k')
      ->condition('last_used', $dayAgo, '>=')
      ->countQuery()
      ->execute()
      ->fetchField();

    // Keys used in last week.
    $usedThisWeek = $this->database->select('congressional_query_api_keys', 'k')
      ->condition('last_used', $weekAgo, '>=')
      ->countQuery()
      ->execute()
      ->fetchField();

    // Keys created this week.
    $createdThisWeek = $this->database->select('congressional_query_api_keys', 'k')
      ->condition('created', $weekAgo, '>=')
      ->countQuery()
      ->execute()
      ->fetchField();

    return [
      'total_keys' => $totalKeys,
      'active_keys' => $activeKeys,
      'inactive_keys' => $totalKeys - $activeKeys,
      'used_today' => (int) $usedToday,
      'used_this_week' => (int) $usedThisWeek,
      'created_this_week' => (int) $createdThisWeek,
    ];
  }

  /**
   * Gets the default rate limit.
   *
   * @return int
   *   Requests per hour.
   */
  public function getDefaultRateLimit(): int {
    $config = $this->configFactory->get('congressional_query.api_settings');
    return (int) ($config->get('default_rate_limit') ?: 100);
  }

  /**
   * Gets the rate limit window.
   *
   * @return int
   *   Window in seconds.
   */
  public function getRateLimitWindow(): int {
    $config = $this->configFactory->get('congressional_query.api_settings');
    return (int) ($config->get('rate_limit_window') ?: 3600);
  }

}
