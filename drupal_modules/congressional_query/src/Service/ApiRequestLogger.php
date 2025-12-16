<?php

namespace Drupal\congressional_query\Service;

use Drupal\Core\Config\ConfigFactoryInterface;
use Drupal\Core\Database\Connection;
use Psr\Log\LoggerInterface;

/**
 * Service for logging API requests.
 */
class ApiRequestLogger {

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
   * Constructs an ApiRequestLogger.
   *
   * @param \Drupal\Core\Database\Connection $database
   *   The database connection.
   * @param \Drupal\Core\Config\ConfigFactoryInterface $config_factory
   *   The config factory.
   * @param \Psr\Log\LoggerInterface $logger
   *   The logger.
   */
  public function __construct(
    Connection $database,
    ConfigFactoryInterface $config_factory,
    LoggerInterface $logger
  ) {
    $this->database = $database;
    $this->configFactory = $config_factory;
    $this->logger = $logger;
  }

  /**
   * Logs an API request.
   *
   * @param array $data
   *   Request data with keys: api_key_id, endpoint, method, status_code,
   *   response_time_ms, ip_address, user_agent, request_body_size,
   *   response_body_size, error_message.
   *
   * @return int|null
   *   The log entry ID or NULL on failure.
   */
  public function logRequest(array $data): ?int {
    try {
      $data['timestamp'] = $data['timestamp'] ?? time();

      $this->database->insert('congressional_query_api_logs')
        ->fields([
          'api_key_id' => $data['api_key_id'] ?? NULL,
          'endpoint' => $data['endpoint'],
          'method' => $data['method'],
          'status_code' => $data['status_code'],
          'response_time_ms' => $data['response_time_ms'] ?? NULL,
          'ip_address' => $data['ip_address'],
          'user_agent' => substr($data['user_agent'] ?? '', 0, 512),
          'request_body_size' => $data['request_body_size'] ?? NULL,
          'response_body_size' => $data['response_body_size'] ?? NULL,
          'error_message' => $data['error_message'] ?? NULL,
          'timestamp' => $data['timestamp'],
        ])
        ->execute();

      return (int) $this->database->lastInsertId();
    }
    catch (\Exception $e) {
      $this->logger->error('Failed to log API request: @message', [
        '@message' => $e->getMessage(),
      ]);
      return NULL;
    }
  }

  /**
   * Gets recent API requests.
   *
   * @param int $limit
   *   Maximum number of requests.
   * @param int|null $api_key_id
   *   Optional filter by API key.
   * @param string|null $endpoint
   *   Optional filter by endpoint.
   *
   * @return array
   *   Array of request logs.
   */
  public function getRecentRequests(int $limit = 50, ?int $api_key_id = NULL, ?string $endpoint = NULL): array {
    $query = $this->database->select('congressional_query_api_logs', 'l')
      ->fields('l')
      ->orderBy('timestamp', 'DESC')
      ->range(0, $limit);

    if ($api_key_id !== NULL) {
      $query->condition('api_key_id', $api_key_id);
    }

    if ($endpoint !== NULL) {
      $query->condition('endpoint', $endpoint);
    }

    return $query->execute()->fetchAll(\PDO::FETCH_ASSOC);
  }

  /**
   * Gets API usage statistics.
   *
   * @param int $start_time
   *   Start timestamp.
   * @param int $end_time
   *   End timestamp.
   *
   * @return array
   *   Statistics array.
   */
  public function getUsageStats(int $start_time, int $end_time): array {
    // Total requests.
    $total = $this->database->select('congressional_query_api_logs', 'l')
      ->condition('timestamp', $start_time, '>=')
      ->condition('timestamp', $end_time, '<')
      ->countQuery()
      ->execute()
      ->fetchField();

    // Successful requests (2xx).
    $successful = $this->database->select('congressional_query_api_logs', 'l')
      ->condition('timestamp', $start_time, '>=')
      ->condition('timestamp', $end_time, '<')
      ->condition('status_code', 200, '>=')
      ->condition('status_code', 300, '<')
      ->countQuery()
      ->execute()
      ->fetchField();

    // Failed requests (4xx, 5xx).
    $failed = $this->database->select('congressional_query_api_logs', 'l')
      ->condition('timestamp', $start_time, '>=')
      ->condition('timestamp', $end_time, '<')
      ->condition('status_code', 400, '>=')
      ->countQuery()
      ->execute()
      ->fetchField();

    // Average response time.
    $avgTime = $this->database->select('congressional_query_api_logs', 'l')
      ->condition('timestamp', $start_time, '>=')
      ->condition('timestamp', $end_time, '<')
      ->condition('response_time_ms', NULL, 'IS NOT NULL');
    $avgTime->addExpression('AVG(response_time_ms)', 'avg_time');
    $avgTime = $avgTime->execute()->fetchField();

    // Requests by endpoint.
    $byEndpoint = $this->database->select('congressional_query_api_logs', 'l')
      ->fields('l', ['endpoint'])
      ->condition('timestamp', $start_time, '>=')
      ->condition('timestamp', $end_time, '<')
      ->groupBy('endpoint');
    $byEndpoint->addExpression('COUNT(*)', 'count');
    $byEndpoint = $byEndpoint->execute()->fetchAllKeyed();

    // Requests by status code.
    $byStatus = $this->database->select('congressional_query_api_logs', 'l')
      ->fields('l', ['status_code'])
      ->condition('timestamp', $start_time, '>=')
      ->condition('timestamp', $end_time, '<')
      ->groupBy('status_code');
    $byStatus->addExpression('COUNT(*)', 'count');
    $byStatus = $byStatus->execute()->fetchAllKeyed();

    // Unique IPs.
    $uniqueIps = $this->database->select('congressional_query_api_logs', 'l')
      ->condition('timestamp', $start_time, '>=')
      ->condition('timestamp', $end_time, '<')
      ->distinct();
    $uniqueIps->addField('l', 'ip_address');
    $uniqueIps = $uniqueIps->execute()->rowCount();

    return [
      'total_requests' => (int) $total,
      'successful_requests' => (int) $successful,
      'failed_requests' => (int) $failed,
      'success_rate' => $total > 0 ? round(($successful / $total) * 100, 2) : 0,
      'avg_response_time_ms' => $avgTime ? round((float) $avgTime, 2) : NULL,
      'requests_by_endpoint' => $byEndpoint,
      'requests_by_status' => $byStatus,
      'unique_ips' => $uniqueIps,
    ];
  }

  /**
   * Gets hourly request distribution.
   *
   * @param int $hours
   *   Number of hours to look back.
   *
   * @return array
   *   Array of hour => count.
   */
  public function getHourlyDistribution(int $hours = 24): array {
    $now = time();
    $distribution = [];

    for ($i = 0; $i < $hours; $i++) {
      $hourStart = $now - (($i + 1) * 3600);
      $hourEnd = $now - ($i * 3600);

      $count = $this->database->select('congressional_query_api_logs', 'l')
        ->condition('timestamp', $hourStart, '>=')
        ->condition('timestamp', $hourEnd, '<')
        ->countQuery()
        ->execute()
        ->fetchField();

      $distribution[$hours - $i] = (int) $count;
    }

    return $distribution;
  }

  /**
   * Gets top API keys by usage.
   *
   * @param int $limit
   *   Maximum number of keys.
   * @param int $since
   *   Start timestamp.
   *
   * @return array
   *   Array of key stats.
   */
  public function getTopApiKeys(int $limit = 10, int $since = 0): array {
    if ($since === 0) {
      $since = time() - 86400; // Default to last 24 hours.
    }

    $query = $this->database->select('congressional_query_api_logs', 'l')
      ->fields('l', ['api_key_id'])
      ->condition('timestamp', $since, '>=')
      ->condition('api_key_id', NULL, 'IS NOT NULL')
      ->groupBy('api_key_id')
      ->orderBy('count', 'DESC')
      ->range(0, $limit);
    $query->addExpression('COUNT(*)', 'count');

    return $query->execute()->fetchAll(\PDO::FETCH_ASSOC);
  }

  /**
   * Cleans up old log entries.
   *
   * @param int $retention_days
   *   Number of days to retain logs.
   *
   * @return int
   *   Number of deleted entries.
   */
  public function cleanup(int $retention_days = 90): int {
    $cutoff = time() - ($retention_days * 86400);

    try {
      return $this->database->delete('congressional_query_api_logs')
        ->condition('timestamp', $cutoff, '<')
        ->execute();
    }
    catch (\Exception $e) {
      $this->logger->error('Failed to cleanup API logs: @message', [
        '@message' => $e->getMessage(),
      ]);
      return 0;
    }
  }

}
