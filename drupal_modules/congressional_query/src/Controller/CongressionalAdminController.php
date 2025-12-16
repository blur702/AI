<?php

namespace Drupal\congressional_query\Controller;

use Drupal\congressional_query\Service\ConversationManager;
use Drupal\congressional_query\Service\OllamaLLMService;
use Drupal\congressional_query\Service\SSHTunnelService;
use Drupal\congressional_query\Service\WeaviateClientService;
use Drupal\Core\Ajax\AjaxResponse;
use Drupal\Core\Ajax\MessageCommand;
use Drupal\Core\Ajax\RemoveCommand;
use Drupal\Core\Controller\ControllerBase;
use Drupal\Core\Datetime\DateFormatterInterface;
use Drupal\Core\Url;
use Symfony\Component\DependencyInjection\ContainerInterface;
use Symfony\Component\HttpFoundation\JsonResponse;
use Symfony\Component\HttpFoundation\RequestStack;
use Symfony\Component\HttpFoundation\Response;

/**
 * Controller for admin dashboard.
 */
class CongressionalAdminController extends ControllerBase {

  /**
   * The conversation manager.
   *
   * @var \Drupal\congressional_query\Service\ConversationManager
   */
  protected $conversationManager;

  /**
   * The SSH tunnel service.
   *
   * @var \Drupal\congressional_query\Service\SSHTunnelService
   */
  protected $sshTunnel;

  /**
   * The Ollama LLM service.
   *
   * @var \Drupal\congressional_query\Service\OllamaLLMService
   */
  protected $ollamaService;

  /**
   * The Weaviate client service.
   *
   * @var \Drupal\congressional_query\Service\WeaviateClientService
   */
  protected $weaviateClient;

  /**
   * The date formatter.
   *
   * @var \Drupal\Core\Datetime\DateFormatterInterface
   */
  protected $dateFormatter;

  /**
   * The request stack.
   *
   * @var \Symfony\Component\HttpFoundation\RequestStack
   */
  protected $requestStack;

  /**
   * Constructs the controller.
   *
   * @param \Drupal\congressional_query\Service\ConversationManager $conversation_manager
   *   The conversation manager.
   * @param \Drupal\congressional_query\Service\SSHTunnelService $ssh_tunnel
   *   The SSH tunnel service.
   * @param \Drupal\congressional_query\Service\OllamaLLMService $ollama_service
   *   The Ollama LLM service.
   * @param \Drupal\congressional_query\Service\WeaviateClientService $weaviate_client
   *   The Weaviate client service.
   * @param \Drupal\Core\Datetime\DateFormatterInterface $date_formatter
   *   The date formatter.
   * @param \Symfony\Component\HttpFoundation\RequestStack $request_stack
   *   The request stack.
   */
  public function __construct(
    ConversationManager $conversation_manager,
    SSHTunnelService $ssh_tunnel,
    OllamaLLMService $ollama_service,
    WeaviateClientService $weaviate_client,
    DateFormatterInterface $date_formatter,
    RequestStack $request_stack
  ) {
    $this->conversationManager = $conversation_manager;
    $this->sshTunnel = $ssh_tunnel;
    $this->ollamaService = $ollama_service;
    $this->weaviateClient = $weaviate_client;
    $this->dateFormatter = $date_formatter;
    $this->requestStack = $request_stack;
  }

  /**
   * {@inheritdoc}
   */
  public static function create(ContainerInterface $container) {
    return new static(
      $container->get('congressional_query.conversation_manager'),
      $container->get('congressional_query.ssh_tunnel'),
      $container->get('congressional_query.ollama_llm'),
      $container->get('congressional_query.weaviate_client'),
      $container->get('date.formatter'),
      $container->get('request_stack')
    );
  }

  /**
   * Render admin dashboard.
   *
   * @return array
   *   Render array.
   */
  public function dashboard(): array {
    // Get statistics.
    $stats = $this->conversationManager->getStatistics();

    // Get recent queries.
    $recentQueries = $this->conversationManager->getRecentQueries(20);

    // Format recent queries for display.
    $formattedQueries = [];
    foreach ($recentQueries as $query) {
      $formattedQueries[] = [
        'id' => $query['id'],
        'question' => $this->truncateText($query['question'], 80),
        'member_filter' => $query['member_filter'] ?: 'All',
        'model' => $query['model'],
        'response_time' => $query['response_time_ms'] ? $query['response_time_ms'] . 'ms' : 'N/A',
        'num_sources' => $query['num_sources'],
        'created' => $this->dateFormatter->format($query['created'], 'short'),
        'view_url' => Url::fromRoute('congressional_query.results', ['query_id' => $query['id']])->toString(),
      ];
    }

    // Get system status.
    $systemStatus = $this->getSystemStatus();

    // Get Weaviate collection stats.
    try {
      $collectionStats = $this->weaviateClient->getCollectionStats();
    }
    catch (\Exception $e) {
      $this->logger->error('Failed to get Weaviate collection stats: @message', ['@message' => $e->getMessage()]);
      $collectionStats = ['count' => 'N/A'];
    }

    $build = [
      '#theme' => 'congressional_admin_dashboard',
      '#stats' => [
        'total_queries' => $stats['total_queries'],
        'queries_today' => $stats['queries_today'],
        'queries_this_week' => $stats['queries_this_week'],
        'unique_users' => $stats['unique_users'],
        'avg_response_time' => $stats['avg_response_time_ms'] ? $stats['avg_response_time_ms'] . 'ms' : 'N/A',
        'top_filters' => $stats['top_member_filters'],
        'collection_count' => $collectionStats['count'] ?? 0,
      ],
      '#recent_queries' => $formattedQueries,
      '#system_status' => $systemStatus,
      '#attached' => [
        'library' => ['congressional_query/admin'],
      ],
    ];

    // Add quick links.
    $build['quick_links'] = [
      '#type' => 'container',
      '#attributes' => ['class' => ['admin-quick-links']],
      'settings' => [
        '#type' => 'link',
        '#title' => $this->t('Configure Settings'),
        '#url' => Url::fromRoute('congressional_query.admin'),
        '#attributes' => ['class' => ['button']],
      ],
      'query_form' => [
        '#type' => 'link',
        '#title' => $this->t('Query Form'),
        '#url' => Url::fromRoute('congressional_query.query_form'),
        '#attributes' => ['class' => ['button']],
      ],
      'chat' => [
        '#type' => 'link',
        '#title' => $this->t('Chat Interface'),
        '#url' => Url::fromRoute('congressional_query.chat'),
        '#attributes' => ['class' => ['button']],
      ],
    ];

    return $build;
  }

  /**
   * Get system status for all services.
   *
   * @return array
   *   System status array.
   */
  protected function getSystemStatus(): array {
    $status = [];

    // Check SSH.
    try {
      $sshHealth = $this->sshTunnel->checkTunnelHealth();
      $status['ssh'] = [
        'name' => 'SSH Tunnel',
        'status' => $sshHealth['status'],
        'message' => $sshHealth['message'],
        'details' => $sshHealth['details'] ?? [],
      ];
    }
    catch (\Exception $e) {
      $status['ssh'] = [
        'name' => 'SSH Tunnel',
        'status' => 'error',
        'message' => $e->getMessage(),
        'details' => [],
      ];
    }

    // Check Ollama.
    try {
      $ollamaHealth = $this->ollamaService->checkHealth();
      $status['ollama'] = [
        'name' => 'Ollama LLM',
        'status' => $ollamaHealth['status'],
        'message' => $ollamaHealth['message'],
        'details' => [
          'models' => $ollamaHealth['models'] ?? [],
        ],
      ];
    }
    catch (\Exception $e) {
      $status['ollama'] = [
        'name' => 'Ollama LLM',
        'status' => 'error',
        'message' => $e->getMessage(),
        'details' => [],
      ];
    }

    // Check Weaviate.
    try {
      $weaviateHealth = $this->weaviateClient->checkHealth();
      $status['weaviate'] = [
        'name' => 'Weaviate DB',
        'status' => $weaviateHealth['status'],
        'message' => $weaviateHealth['message'],
        'details' => $weaviateHealth['details'] ?? [],
      ];
    }
    catch (\Exception $e) {
      $status['weaviate'] = [
        'name' => 'Weaviate DB',
        'status' => 'error',
        'message' => $e->getMessage(),
        'details' => [],
      ];
    }

    return $status;
  }

  /**
   * Truncate text to a maximum length.
   *
   * @param string $text
   *   Text to truncate.
   * @param int $maxLength
   *   Maximum length.
   *
   * @return string
   *   Truncated text.
   */
  protected function truncateText(string $text, int $maxLength): string {
    if (strlen($text) <= $maxLength) {
      return $text;
    }
    return substr($text, 0, $maxLength) . '...';
  }

  /**
   * Render query history page.
   *
   * @return array
   *   Render array.
   */
  public function queryHistory(): array {
    $request = $this->requestStack->getCurrentRequest();

    // Get filter parameters.
    $filters = [
      'date_from' => $request->query->get('date_from'),
      'date_to' => $request->query->get('date_to'),
      'uid' => $request->query->get('uid'),
      'member_filter' => $request->query->get('member_filter'),
      'model' => $request->query->get('model'),
      'min_response_time' => $request->query->get('min_response_time'),
      'max_response_time' => $request->query->get('max_response_time'),
      'search_text' => $request->query->get('search_text'),
    ];

    // Remove empty filters.
    $filters = array_filter($filters, fn($v) => $v !== NULL && $v !== '');

    // Pagination.
    $page = (int) $request->query->get('page', 0);
    $limit = 50;

    // Sorting.
    $sort = $request->query->get('sort', 'created');
    $order = $request->query->get('order', 'DESC');

    // Get filtered results.
    $result = $this->conversationManager->getFilteredQueryLogs($filters, $page, $limit, $sort, $order);

    // Format queries for display.
    $formattedQueries = [];
    foreach ($result['results'] as $query) {
      $formattedQueries[] = [
        'id' => $query['id'],
        'uid' => $query['uid'],
        'username' => $this->getUserName($query['uid']),
        'question' => $query['question'],
        'question_truncated' => $this->truncateText($query['question'], 80),
        'member_filter' => $query['member_filter'] ?: 'All',
        'model' => $query['model'] ?: 'N/A',
        'response_time' => $query['response_time_ms'] ? $query['response_time_ms'] . 'ms' : 'N/A',
        'num_sources' => $query['num_sources'],
        'created' => $this->dateFormatter->format($query['created'], 'short'),
        'created_timestamp' => $query['created'],
        'view_url' => Url::fromRoute('congressional_query.results', ['query_id' => $query['id']])->toString(),
      ];
    }

    // Build active filters for display.
    $activeFilters = [];
    foreach ($filters as $key => $value) {
      if ($value) {
        $label = str_replace('_', ' ', ucfirst($key));
        if ($key === 'uid') {
          $value = $this->getUserName($value);
        }
        $activeFilters[] = ['label' => $label, 'value' => $value];
      }
    }

    // Get filter form.
    $filterForm = $this->formBuilder()->getForm('Drupal\congressional_query\Form\CongressionalQueryHistoryFilterForm');

    // Calculate pagination info.
    $totalPages = ceil($result['total'] / $limit);

    return [
      '#theme' => 'congressional_query_history',
      '#filter_form' => $filterForm,
      '#queries' => $formattedQueries,
      '#total' => $result['total'],
      '#page' => $page,
      '#limit' => $limit,
      '#total_pages' => $totalPages,
      '#active_filters' => $activeFilters,
      '#sort' => $sort,
      '#order' => $order,
      '#export_csv_url' => Url::fromRoute('congressional_query.export_history', ['format' => 'csv'], ['query' => $filters])->toString(),
      '#export_json_url' => Url::fromRoute('congressional_query.export_history', ['format' => 'json'], ['query' => $filters])->toString(),
      '#attached' => [
        'library' => ['congressional_query/query_history'],
      ],
    ];
  }

  /**
   * Export query history.
   *
   * @param string $format
   *   Export format (csv or json).
   *
   * @return \Symfony\Component\HttpFoundation\Response
   *   File download response.
   */
  public function exportQueryHistory(string $format): Response {
    $request = $this->requestStack->getCurrentRequest();

    // Get filter parameters.
    $filters = [
      'date_from' => $request->query->get('date_from'),
      'date_to' => $request->query->get('date_to'),
      'uid' => $request->query->get('uid'),
      'member_filter' => $request->query->get('member_filter'),
      'model' => $request->query->get('model'),
      'min_response_time' => $request->query->get('min_response_time'),
      'max_response_time' => $request->query->get('max_response_time'),
      'search_text' => $request->query->get('search_text'),
    ];

    $filters = array_filter($filters, fn($v) => $v !== NULL && $v !== '');

    // Get all matching results (no pagination for export).
    $result = $this->conversationManager->getFilteredQueryLogs($filters, 0, 10000);
    $queries = $result['results'];

    $filename = 'congressional_query_history_' . date('Y-m-d_H-i-s');

    if ($format === 'csv') {
      $output = fopen('php://temp', 'r+');

      // Header row.
      fputcsv($output, [
        'ID', 'User', 'Question', 'Answer (Truncated)', 'Model',
        'Member Filter', 'Response Time (ms)', 'Sources Count', 'Date',
      ]);

      // Data rows.
      foreach ($queries as $query) {
        fputcsv($output, [
          $query['id'],
          $this->getUserName($query['uid']),
          $query['question'],
          $this->truncateText($query['answer'] ?? '', 500),
          $query['model'] ?: 'N/A',
          $query['member_filter'] ?: 'All',
          $query['response_time_ms'] ?: 'N/A',
          $query['num_sources'],
          date('Y-m-d H:i:s', $query['created']),
        ]);
      }

      rewind($output);
      $content = stream_get_contents($output);
      fclose($output);

      return new Response($content, 200, [
        'Content-Type' => 'text/csv',
        'Content-Disposition' => 'attachment; filename="' . $filename . '.csv"',
      ]);
    }
    else {
      // JSON format.
      $exportData = array_map(function ($query) {
        return [
          'id' => $query['id'],
          'user' => $this->getUserName($query['uid']),
          'question' => $query['question'],
          'answer' => $query['answer'] ?? '',
          'model' => $query['model'],
          'member_filter' => $query['member_filter'],
          'response_time_ms' => $query['response_time_ms'],
          'num_sources' => $query['num_sources'],
          'sources' => $query['sources'] ?? [],
          'created' => date('c', $query['created']),
        ];
      }, $queries);

      $content = json_encode($exportData, JSON_PRETTY_PRINT);

      return new Response($content, 200, [
        'Content-Type' => 'application/json',
        'Content-Disposition' => 'attachment; filename="' . $filename . '.json"',
      ]);
    }
  }

  /**
   * Render analytics page.
   *
   * @return array
   *   Render array.
   */
  public function analytics(): array {
    // Get extended statistics.
    $stats = $this->conversationManager->getExtendedStatistics();

    // Get additional analytics data.
    $queriesByModel = $this->conversationManager->getQueriesByModel(10);
    $queriesByUser = $this->conversationManager->getQueriesByUser(10);

    // Load usernames for top users.
    foreach ($queriesByUser as &$userStat) {
      $userStat['username'] = $this->getUserName($userStat['uid']);
    }

    // Calculate trends (week over week).
    $lastWeekTotal = $stats['queries_this_week'] ?? 0;
    $previousWeekQueries = $this->getPreviousWeekQueries();
    $growthRate = $previousWeekQueries > 0
      ? round((($lastWeekTotal - $previousWeekQueries) / $previousWeekQueries) * 100, 1)
      : 0;

    return [
      '#theme' => 'congressional_analytics',
      '#stats' => $stats,
      '#queries_by_model' => $queriesByModel,
      '#queries_by_user' => $queriesByUser,
      '#growth_rate' => $growthRate,
      '#attached' => [
        'library' => ['congressional_query/analytics'],
        'drupalSettings' => [
          'congressionalAnalytics' => [
            'hourlyDistribution' => $stats['hourly_distribution'] ?? [],
            'dailyDistribution' => $stats['daily_distribution'] ?? [],
            'topWords' => $stats['top_words'] ?? [],
            'responseTimePercentiles' => $stats['response_time_percentiles'] ?? [],
            'topFilters' => $stats['top_member_filters'] ?? [],
            'queriesByModel' => $queriesByModel,
          ],
        ],
      ],
    ];
  }

  /**
   * Clear cache via AJAX.
   *
   * @param string $type
   *   Cache type (collection, member, stats, all).
   *
   * @return \Symfony\Component\HttpFoundation\JsonResponse
   *   JSON response.
   */
  public function clearCacheAjax(string $type): JsonResponse {
    try {
      $cleared = 0;

      switch ($type) {
        case 'collection':
          $this->weaviateClient->invalidateCollectionCache();
          $message = $this->t('Collection cache cleared.');
          break;

        case 'member':
          $this->weaviateClient->clearCache();
          $message = $this->t('Member cache cleared.');
          break;

        case 'stats':
          $this->weaviateClient->clearCache();
          $message = $this->t('Statistics cache cleared.');
          break;

        case 'all':
          $this->weaviateClient->clearCache();
          $message = $this->t('All caches cleared.');
          break;

        default:
          return new JsonResponse([
            'success' => FALSE,
            'message' => $this->t('Invalid cache type.'),
          ], 400);
      }

      return new JsonResponse([
        'success' => TRUE,
        'message' => $message,
        'timestamp' => date('Y-m-d H:i:s'),
      ]);
    }
    catch (\Exception $e) {
      return new JsonResponse([
        'success' => FALSE,
        'message' => $this->t('Failed to clear cache: @error', ['@error' => $e->getMessage()]),
      ], 500);
    }
  }

  /**
   * Delete query via AJAX.
   *
   * @param int $query_id
   *   Query ID.
   *
   * @return \Drupal\Core\Ajax\AjaxResponse
   *   AJAX response.
   */
  public function deleteQueryAjax(int $query_id): AjaxResponse {
    $response = new AjaxResponse();

    try {
      $deleted = $this->conversationManager->deleteQueryLog($query_id);

      if ($deleted) {
        $response->addCommand(new RemoveCommand('#query-row-' . $query_id));
        $response->addCommand(new MessageCommand(
          $this->t('Query @id deleted successfully.', ['@id' => $query_id]),
          NULL,
          ['type' => 'status']
        ));
      }
      else {
        $response->addCommand(new MessageCommand(
          $this->t('Query not found.'),
          NULL,
          ['type' => 'error']
        ));
      }
    }
    catch (\Exception $e) {
      $response->addCommand(new MessageCommand(
        $this->t('Failed to delete query: @error', ['@error' => $e->getMessage()]),
        NULL,
        ['type' => 'error']
      ));
    }

    return $response;
  }

  /**
   * Get username from user ID.
   *
   * @param int $uid
   *   User ID.
   *
   * @return string
   *   Username.
   */
  protected function getUserName(int $uid): string {
    if ($uid === 0) {
      return 'Anonymous';
    }

    $user = $this->entityTypeManager()->getStorage('user')->load($uid);
    return $user ? $user->getDisplayName() : 'Unknown';
  }

  /**
   * Get previous week query count.
   *
   * @return int
   *   Number of queries from previous week.
   */
  protected function getPreviousWeekQueries(): int {
    $weekAgo = strtotime('-7 days');
    $twoWeeksAgo = strtotime('-14 days');

    $result = $this->conversationManager->getFilteredQueryLogs([
      'date_from' => date('Y-m-d', $twoWeeksAgo),
      'date_to' => date('Y-m-d', $weekAgo),
    ], 0, 1);

    return $result['total'];
  }

}

