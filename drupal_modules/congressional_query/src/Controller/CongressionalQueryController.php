<?php

namespace Drupal\congressional_query\Controller;

use Drupal\congressional_query\Service\ConversationManager;
use Drupal\Core\Controller\ControllerBase;
use Drupal\Core\Datetime\DateFormatterInterface;
use Symfony\Component\DependencyInjection\ContainerInterface;
use Symfony\Component\HttpKernel\Exception\AccessDeniedHttpException;
use Symfony\Component\HttpKernel\Exception\NotFoundHttpException;

/**
 * Controller for displaying query results.
 */
class CongressionalQueryController extends ControllerBase {

  /**
   * The conversation manager.
   *
   * @var \Drupal\congressional_query\Service\ConversationManager
   */
  protected $conversationManager;

  /**
   * The date formatter.
   *
   * @var \Drupal\Core\Datetime\DateFormatterInterface
   */
  protected $dateFormatter;

  /**
   * Constructs the controller.
   *
   * @param \Drupal\congressional_query\Service\ConversationManager $conversation_manager
   *   The conversation manager.
   * @param \Drupal\Core\Datetime\DateFormatterInterface $date_formatter
   *   The date formatter.
   */
  public function __construct(
    ConversationManager $conversation_manager,
    DateFormatterInterface $date_formatter
  ) {
    $this->conversationManager = $conversation_manager;
    $this->dateFormatter = $date_formatter;
  }

  /**
   * {@inheritdoc}
   */
  public static function create(ContainerInterface $container) {
    return new static(
      $container->get('congressional_query.conversation_manager'),
      $container->get('date.formatter')
    );
  }

  /**
   * Display query results.
   *
   * @param int $query_id
   *   The query log ID.
   *
   * @return array
   *   Render array.
   */
  public function resultsPage(int $query_id): array {
    $queryLog = $this->conversationManager->getQueryLog($query_id);

    if (!$queryLog) {
      throw new NotFoundHttpException('Query not found.');
    }

    // Check access - user must own the query or have admin permissions.
    $currentUser = $this->currentUser();
    $hasAdminAccess = $currentUser->hasPermission('view congressional query logs')
      || $currentUser->hasPermission('administer congressional query');

    if (($queryLog['uid'] ?? 0) != $currentUser->id() && !$hasAdminAccess) {
      throw new AccessDeniedHttpException('You do not have permission to view this query.');
    }

    // Process sources for display.
    // Pass full content - preprocess will handle truncation.
    $sources = [];
    foreach ($queryLog['sources'] ?? [] as $source) {
      $sources[] = [
        '#theme' => 'congressional_query_source',
        '#member_name' => $source['member_name'] ?? 'Unknown',
        '#title' => $source['title'] ?? 'Untitled',
        '#content' => $source['content_text'] ?? '',
        '#url' => $source['url'] ?? '',
        '#party' => $source['party'] ?? '',
        '#state' => $source['state'] ?? '',
        '#topic' => $source['topic'] ?? '',
        '#distance' => $source['distance'] ?? NULL,
      ];
    }

    return [
      '#theme' => 'congressional_query_results',
      '#question' => $queryLog['question'],
      '#answer' => $queryLog['answer'],
      '#sources' => $sources,
      '#model' => $queryLog['model'],
      '#timestamp' => $this->dateFormatter->format($queryLog['created'], 'medium'),
      '#query_id' => $query_id,
      '#member_filter' => $queryLog['member_filter'] ?? NULL,
      '#party_filter' => $queryLog['party_filter'] ?? NULL,
      '#state_filter' => $queryLog['state_filter'] ?? NULL,
      '#response_time_ms' => $queryLog['response_time_ms'] ?? NULL,
      '#num_sources_requested' => $queryLog['num_sources'] ?? NULL,
      '#conversation_id' => $queryLog['conversation_id'] ?? NULL,
      '#attached' => [
        'library' => [
          'congressional_query/base',
          'congressional_query/query-results',
        ],
        'drupalSettings' => [
          'congressionalQuery' => [
            'queryId' => $query_id,
            'conversationId' => $queryLog['conversation_id'] ?? NULL,
          ],
        ],
      ],
    ];
  }

  /**
   * Truncate content to a maximum length.
   *
   * @param string $content
   *   The content to truncate.
   * @param int $maxLength
   *   Maximum length.
   *
   * @return string
   *   Truncated content.
   */
  protected function truncateContent(string $content, int $maxLength): string {
    if (strlen($content) <= $maxLength) {
      return $content;
    }

    $truncated = substr($content, 0, $maxLength);
    $lastSpace = strrpos($truncated, ' ');

    if ($lastSpace !== FALSE) {
      $truncated = substr($truncated, 0, $lastSpace);
    }

    return $truncated . '...';
  }

}
