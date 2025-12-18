<?php

namespace Drupal\congressional_query\Controller;

use Drupal\congressional_query\Service\ApiKeyManager;
use Drupal\congressional_query\Service\ApiRequestLogger;
use Drupal\Core\Controller\ControllerBase;
use Drupal\Core\Datetime\DateFormatterInterface;
use Drupal\user\Entity\User;
use Symfony\Component\DependencyInjection\ContainerInterface;
use Symfony\Component\HttpFoundation\JsonResponse;
use Symfony\Component\HttpFoundation\Request;

/**
 * Controller for API analytics.
 */
class ApiAnalyticsController extends ControllerBase {

  /**
   * The API request logger.
   *
   * @var \Drupal\congressional_query\Service\ApiRequestLogger
   */
  protected $requestLogger;

  /**
   * The API key manager.
   *
   * @var \Drupal\congressional_query\Service\ApiKeyManager
   */
  protected $apiKeyManager;

  /**
   * The date formatter.
   *
   * @var \Drupal\Core\Datetime\DateFormatterInterface
   */
  protected $dateFormatter;

  /**
   * Constructs the controller.
   *
   * @param \Drupal\congressional_query\Service\ApiRequestLogger $request_logger
   *   The API request logger.
   * @param \Drupal\congressional_query\Service\ApiKeyManager $api_key_manager
   *   The API key manager.
   * @param \Drupal\Core\Datetime\DateFormatterInterface $date_formatter
   *   The date formatter.
   */
  public function __construct(
    ApiRequestLogger $request_logger,
    ApiKeyManager $api_key_manager,
    DateFormatterInterface $date_formatter
  ) {
    $this->requestLogger = $request_logger;
    $this->apiKeyManager = $api_key_manager;
    $this->dateFormatter = $date_formatter;
  }

  /**
   * {@inheritdoc}
   */
  public static function create(ContainerInterface $container) {
    return new static(
      $container->get('congressional_query.api_request_logger'),
      $container->get('congressional_query.api_key_manager'),
      $container->get('date.formatter')
    );
  }

  /**
   * Displays API analytics page.
   *
   * @return array
   *   Render array.
   */
  public function analytics(): array {
    $now = time();
    $dayAgo = $now - 86400;
    $weekAgo = $now - 604800;

    // Get usage stats.
    $todayStats = $this->requestLogger->getUsageStats($dayAgo, $now);
    $weekStats = $this->requestLogger->getUsageStats($weekAgo, $now);

    // Get hourly distribution.
    $hourlyDistribution = $this->requestLogger->getHourlyDistribution(24);

    // Get top API keys.
    $topKeys = $this->requestLogger->getTopApiKeys(10, $dayAgo);

    // Load key names.
    foreach ($topKeys as &$keyData) {
      $key = $this->apiKeyManager->getKey($keyData['api_key_id']);
      $keyData['name'] = $key ? $key->getName() : 'Unknown';
      $keyData['prefix'] = $key ? $key->getKeyPrefix() : '???';
    }

    // Get recent requests.
    $recentRequests = $this->requestLogger->getRecentRequests(20);

    // Format recent requests.
    $formattedRequests = [];
    foreach ($recentRequests as $request) {
      $key = $request['api_key_id'] ? $this->apiKeyManager->getKey($request['api_key_id']) : NULL;

      $formattedRequests[] = [
        'endpoint' => $request['endpoint'],
        'method' => $request['method'],
        'status_code' => $request['status_code'],
        'response_time_ms' => $request['response_time_ms'],
        'ip_address' => $request['ip_address'],
        'key_name' => $key ? $key->getName() : 'Anonymous',
        'timestamp' => $this->dateFormatter->format($request['timestamp'], 'short'),
        'has_error' => !empty($request['error_message']),
      ];
    }

    // API key stats.
    $keyStats = $this->apiKeyManager->getStatistics();

    return [
      '#theme' => 'congressional_api_analytics',
      '#today_stats' => $todayStats,
      '#week_stats' => $weekStats,
      '#hourly_distribution' => $hourlyDistribution,
      '#top_keys' => $topKeys,
      '#recent_requests' => $formattedRequests,
      '#key_stats' => $keyStats,
      '#attached' => [
        'library' => ['congressional_query/api_analytics'],
        'drupalSettings' => [
          'congressionalApiAnalytics' => [
            'hourlyDistribution' => $hourlyDistribution,
            'requestsByEndpoint' => $todayStats['requests_by_endpoint'],
            'requestsByStatus' => $todayStats['requests_by_status'],
          ],
        ],
      ],
    ];
  }

  /**
   * Returns API analytics data as JSON.
   *
   * @param \Symfony\Component\HttpFoundation\Request $request
   *   The request.
   *
   * @return \Symfony\Component\HttpFoundation\JsonResponse
   *   JSON response.
   */
  public function analyticsData(Request $request): JsonResponse {
    $period = $request->query->get('period', 'day');

    $now = time();
    switch ($period) {
      case 'hour':
        $startTime = $now - 3600;
        break;

      case 'week':
        $startTime = $now - 604800;
        break;

      case 'month':
        $startTime = $now - 2592000;
        break;

      default:
        $startTime = $now - 86400;
    }

    $stats = $this->requestLogger->getUsageStats($startTime, $now);
    $hourlyDistribution = $this->requestLogger->getHourlyDistribution(24);
    $topKeys = $this->requestLogger->getTopApiKeys(10, $startTime);

    return new JsonResponse([
      'stats' => $stats,
      'hourly_distribution' => $hourlyDistribution,
      'top_keys' => $topKeys,
    ]);
  }

}
