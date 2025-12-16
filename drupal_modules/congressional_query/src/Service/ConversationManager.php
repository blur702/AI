<?php

namespace Drupal\congressional_query\Service;

use Drupal\Component\Datetime\TimeInterface;
use Drupal\Core\Database\Connection;
use Drupal\Core\Session\AccountProxyInterface;
use Symfony\Component\HttpFoundation\Session\SessionInterface;

/**
 * Service for managing conversation history and query logs.
 */
class ConversationManager {

  /**
   * The session.
   *
   * @var \Symfony\Component\HttpFoundation\Session\SessionInterface
   */
  protected $session;

  /**
   * The database connection.
   *
   * @var \Drupal\Core\Database\Connection
   */
  protected $database;

  /**
   * The current user.
   *
   * @var \Drupal\Core\Session\AccountProxyInterface
   */
  protected $currentUser;

  /**
   * The time service.
   *
   * @var \Drupal\Component\Datetime\TimeInterface
   */
  protected $time;

  /**
   * Constructs the ConversationManager.
   *
   * @param \Symfony\Component\HttpFoundation\Session\SessionInterface $session
   *   The session.
   * @param \Drupal\Core\Database\Connection $database
   *   The database connection.
   * @param \Drupal\Core\Session\AccountProxyInterface $current_user
   *   The current user.
   * @param \Drupal\Component\Datetime\TimeInterface $time
   *   The time service.
   */
  public function __construct(
    SessionInterface $session,
    Connection $database,
    AccountProxyInterface $current_user,
    TimeInterface $time
  ) {
    $this->session = $session;
    $this->database = $database;
    $this->currentUser = $current_user;
    $this->time = $time;
  }

  /**
   * Create a new conversation.
   *
   * @param string|null $memberFilter
   *   Optional member filter for this conversation.
   *
   * @return string
   *   The conversation ID.
   */
  public function createConversation(?string $memberFilter = NULL): string {
    $conversationId = $this->generateUuid();
    $now = $this->time->getRequestTime();

    $this->database->insert('congressional_query_conversations')
      ->fields([
        'conversation_id' => $conversationId,
        'uid' => $this->currentUser->id(),
        'member_filter' => $memberFilter,
        'message_count' => 0,
        'created' => $now,
        'updated' => $now,
      ])
      ->execute();

    // Initialize session storage for messages.
    $sessionKey = 'congressional_query_messages_' . $conversationId;
    $this->session->set($sessionKey, []);

    return $conversationId;
  }

  /**
   * Add a message to a conversation.
   *
   * @param string $conversationId
   *   The conversation ID.
   * @param string $role
   *   Message role ('user' or 'assistant').
   * @param string $content
   *   Message content.
   * @param array $sources
   *   Source documents (for assistant messages).
   * @param array $metadata
   *   Additional metadata (model, response_time, etc.).
   *
   * @return int
   *   The query log ID.
   */
  public function addMessage(
    string $conversationId,
    string $role,
    string $content,
    array $sources = [],
    array $metadata = []
  ): int {
    $now = $this->time->getRequestTime();

    // Store in session for quick access.
    $sessionKey = 'congressional_query_messages_' . $conversationId;
    $messages = $this->session->get($sessionKey, []);
    $messages[] = [
      'role' => $role,
      'content' => $content,
      'sources' => $sources,
      'metadata' => $metadata,
      'timestamp' => $now,
    ];
    $this->session->set($sessionKey, $messages);

    // Log to database (only for user questions and assistant answers).
    $logId = 0;
    if ($role === 'user') {
      // Just update the conversation timestamp.
      $this->updateConversationTimestamp($conversationId);
    }
    elseif ($role === 'assistant') {
      // Get the last user message for logging.
      $userMessages = array_filter($messages, fn($m) => $m['role'] === 'user');
      $lastUserMessage = end($userMessages);
      $question = $lastUserMessage['content'] ?? '';

      $logId = $this->database->insert('congressional_query_logs')
        ->fields([
          'uid' => $this->currentUser->id(),
          'question' => $question,
          'answer' => $content,
          'model' => $metadata['model'] ?? NULL,
          'member_filter' => $metadata['member_filter'] ?? NULL,
          'num_sources' => count($sources),
          'sources_json' => json_encode($sources),
          'response_time_ms' => $metadata['response_time_ms'] ?? NULL,
          'conversation_id' => $conversationId,
          'created' => $now,
        ])
        ->execute();
    }

    // Update conversation message count.
    $this->database->update('congressional_query_conversations')
      ->fields([
        'message_count' => count($messages),
        'updated' => $now,
      ])
      ->condition('conversation_id', $conversationId)
      ->execute();

    // Set title from first user message if not set.
    $this->setConversationTitleIfEmpty($conversationId, $messages);

    return $logId;
  }

  /**
   * Get conversation messages.
   *
   * @param string $conversationId
   *   The conversation ID.
   *
   * @return array
   *   Array of messages.
   */
  public function getConversation(string $conversationId): array {
    $sessionKey = 'congressional_query_messages_' . $conversationId;
    return $this->session->get($sessionKey, []);
  }

  /**
   * Get conversation metadata.
   *
   * @param string $conversationId
   *   The conversation ID.
   *
   * @return array|null
   *   Conversation metadata or NULL if not found.
   */
  public function getConversationMetadata(string $conversationId): ?array {
    $result = $this->database->select('congressional_query_conversations', 'c')
      ->fields('c')
      ->condition('conversation_id', $conversationId)
      ->execute()
      ->fetchAssoc();

    return $result ?: NULL;
  }

  /**
   * Clear a conversation.
   *
   * @param string $conversationId
   *   The conversation ID.
   */
  public function clearConversation(string $conversationId): void {
    $sessionKey = 'congressional_query_messages_' . $conversationId;
    $this->session->remove($sessionKey);
  }

  /**
   * Delete a conversation and its logs.
   *
   * @param string $conversationId
   *   The conversation ID.
   */
  public function deleteConversation(string $conversationId): void {
    $this->clearConversation($conversationId);

    $this->database->delete('congressional_query_logs')
      ->condition('conversation_id', $conversationId)
      ->execute();

    $this->database->delete('congressional_query_conversations')
      ->condition('conversation_id', $conversationId)
      ->execute();
  }

  /**
   * Get user's recent conversations.
   *
   * @param int $limit
   *   Maximum number of conversations to return.
   *
   * @return array
   *   Array of conversation metadata.
   */
  public function getUserConversations(int $limit = 10): array {
    $results = $this->database->select('congressional_query_conversations', 'c')
      ->fields('c')
      ->condition('uid', $this->currentUser->id())
      ->orderBy('updated', 'DESC')
      ->range(0, $limit)
      ->execute()
      ->fetchAll();

    return array_map(fn($row) => (array) $row, $results);
  }

  /**
   * Log a query (for simple form submissions without conversation).
   *
   * @param string $question
   *   The question asked.
   * @param string $answer
   *   The generated answer.
   * @param array $metadata
   *   Additional metadata.
   *
   * @return int
   *   The query log ID.
   */
  public function logQuery(string $question, string $answer, array $metadata = []): int {
    return $this->database->insert('congressional_query_logs')
      ->fields([
        'uid' => $this->currentUser->id(),
        'question' => $question,
        'answer' => $answer,
        'model' => $metadata['model'] ?? NULL,
        'member_filter' => $metadata['member_filter'] ?? NULL,
        'num_sources' => $metadata['num_sources'] ?? 0,
        'sources_json' => json_encode($metadata['sources'] ?? []),
        'response_time_ms' => $metadata['response_time_ms'] ?? NULL,
        'conversation_id' => $metadata['conversation_id'] ?? NULL,
        'created' => $this->time->getRequestTime(),
      ])
      ->execute();
  }

  /**
   * Get query log by ID.
   *
   * @param int $queryId
   *   The query log ID.
   *
   * @return array|null
   *   Query log data or NULL if not found.
   */
  public function getQueryLog(int $queryId): ?array {
    $result = $this->database->select('congressional_query_logs', 'l')
      ->fields('l')
      ->condition('id', $queryId)
      ->execute()
      ->fetchAssoc();

    if ($result) {
      $result['sources'] = json_decode($result['sources_json'] ?? '[]', TRUE);
    }

    return $result ?: NULL;
  }

  /**
   * Get query statistics.
   *
   * @return array
   *   Statistics array.
   */
  public function getStatistics(): array {
    $now = $this->time->getRequestTime();
    $todayStart = strtotime('today midnight');
    $weekStart = strtotime('-7 days');

    // Total queries.
    $totalQueries = $this->database->select('congressional_query_logs', 'l')
      ->countQuery()
      ->execute()
      ->fetchField();

    // Queries today.
    $queriesToday = $this->database->select('congressional_query_logs', 'l')
      ->condition('created', $todayStart, '>=')
      ->countQuery()
      ->execute()
      ->fetchField();

    // Queries this week.
    $queriesThisWeek = $this->database->select('congressional_query_logs', 'l')
      ->condition('created', $weekStart, '>=')
      ->countQuery()
      ->execute()
      ->fetchField();

    // Unique users.
    $uniqueUsers = $this->database->select('congressional_query_logs', 'l')
      ->distinct()
      ->fields('l', ['uid'])
      ->countQuery()
      ->execute()
      ->fetchField();

    // Average response time.
    $avgResponseTime = $this->database->select('congressional_query_logs', 'l')
      ->where('response_time_ms IS NOT NULL')
      ->addExpression('AVG(response_time_ms)', 'avg_time')
      ->execute()
      ->fetchField();

    // Top member filters.
    $topFilters = $this->database->select('congressional_query_logs', 'l')
      ->fields('l', ['member_filter'])
      ->addExpression('COUNT(*)', 'count')
      ->groupBy('member_filter')
      ->orderBy('count', 'DESC')
      ->range(0, 5)
      ->execute()
      ->fetchAll();

    return [
      'total_queries' => (int) $totalQueries,
      'queries_today' => (int) $queriesToday,
      'queries_this_week' => (int) $queriesThisWeek,
      'unique_users' => (int) $uniqueUsers,
      'avg_response_time_ms' => $avgResponseTime ? round($avgResponseTime) : NULL,
      'top_member_filters' => array_map(fn($row) => [
        'filter' => $row->member_filter ?: 'All',
        'count' => $row->count,
      ], $topFilters),
    ];
  }

  /**
   * Get recent queries for admin dashboard.
   *
   * @param int $limit
   *   Maximum number of queries to return.
   *
   * @return array
   *   Array of recent queries.
   */
  public function getRecentQueries(int $limit = 20): array {
    $results = $this->database->select('congressional_query_logs', 'l')
      ->fields('l')
      ->orderBy('created', 'DESC')
      ->range(0, $limit)
      ->execute()
      ->fetchAll();

    return array_map(function ($row) {
      $data = (array) $row;
      $data['sources'] = json_decode($data['sources_json'] ?? '[]', TRUE);
      unset($data['sources_json']);
      return $data;
    }, $results);
  }

  /**
   * Update a message in a conversation.
   *
   * @param string $conversationId
   *   The conversation ID.
   * @param int $messageIndex
   *   The message index (0-based).
   * @param string $newContent
   *   The new message content.
   *
   * @return bool
   *   TRUE if successful, FALSE otherwise.
   */
  public function updateMessage(string $conversationId, int $messageIndex, string $newContent): bool {
    $sessionKey = 'congressional_query_messages_' . $conversationId;
    $messages = $this->session->get($sessionKey, []);

    if (!isset($messages[$messageIndex])) {
      return FALSE;
    }

    // Only allow editing user messages.
    if ($messages[$messageIndex]['role'] !== 'user') {
      return FALSE;
    }

    $messages[$messageIndex]['content'] = $newContent;
    $messages[$messageIndex]['edited'] = TRUE;
    $messages[$messageIndex]['edited_at'] = $this->time->getRequestTime();

    $this->session->set($sessionKey, $messages);
    $this->updateConversationTimestamp($conversationId);

    return TRUE;
  }

  /**
   * Delete a message from a conversation.
   *
   * @param string $conversationId
   *   The conversation ID.
   * @param int $messageIndex
   *   The message index (0-based).
   *
   * @return bool
   *   TRUE if successful, FALSE otherwise.
   */
  public function deleteMessage(string $conversationId, int $messageIndex): bool {
    $sessionKey = 'congressional_query_messages_' . $conversationId;
    $messages = $this->session->get($sessionKey, []);

    if (!isset($messages[$messageIndex])) {
      return FALSE;
    }

    // Only allow deleting user messages.
    if ($messages[$messageIndex]['role'] !== 'user') {
      return FALSE;
    }

    // Remove the message and re-index.
    array_splice($messages, $messageIndex, 1);

    $this->session->set($sessionKey, $messages);

    // Update message count in database.
    $this->database->update('congressional_query_conversations')
      ->fields([
        'message_count' => count($messages),
        'updated' => $this->time->getRequestTime(),
      ])
      ->condition('conversation_id', $conversationId)
      ->execute();

    return TRUE;
  }

  /**
   * Get extended statistics for analytics.
   *
   * @return array
   *   Extended statistics array.
   */
  public function getExtendedStatistics(): array {
    $baseStats = $this->getStatistics();
    $now = $this->time->getRequestTime();

    // Hourly distribution (last 24 hours).
    // For i=0: most recent hour (now - 1 hour to now).
    // For i=23: oldest hour (now - 24 hours to now - 23 hours).
    $hourlyDistribution = [];
    for ($i = 0; $i < 24; $i++) {
      $hourStart = $now - (($i + 1) * 3600);
      $hourEnd = $now - ($i * 3600);

      $count = $this->database->select('congressional_query_logs', 'l')
        ->condition('created', $hourStart, '>=')
        ->condition('created', $hourEnd, '<')
        ->countQuery()
        ->execute()
        ->fetchField();

      $hourlyDistribution[24 - $i] = (int) $count;
    }

    // Daily distribution (last 7 days).
    // For i=0: today (midnight to now).
    // For i=6: 6 days ago (midnight to next midnight).
    $dailyDistribution = [];
    for ($i = 0; $i < 7; $i++) {
      $dayStart = strtotime("-{$i} days midnight", $now);
      $dayEnd = ($i === 0) ? $now : strtotime("-" . ($i - 1) . " days midnight", $now);

      $count = $this->database->select('congressional_query_logs', 'l')
        ->condition('created', $dayStart, '>=')
        ->condition('created', $dayEnd, '<')
        ->countQuery()
        ->execute()
        ->fetchField();

      $dailyDistribution[date('Y-m-d', $dayStart)] = (int) $count;
    }

    // Average conversation length.
    $avgConvLength = $this->database->select('congressional_query_conversations', 'c')
      ->addExpression('AVG(message_count)', 'avg_length')
      ->execute()
      ->fetchField();

    // Top questions (word frequency analysis).
    $recentQuestions = $this->database->select('congressional_query_logs', 'l')
      ->fields('l', ['question'])
      ->orderBy('created', 'DESC')
      ->range(0, 100)
      ->execute()
      ->fetchCol();

    $wordCounts = [];
    $stopWords = ['what', 'the', 'is', 'are', 'how', 'does', 'do', 'a', 'an', 'of', 'in', 'to', 'and', 'for', 'on', 'about'];
    foreach ($recentQuestions as $question) {
      $words = preg_split('/\s+/', strtolower($question));
      foreach ($words as $word) {
        $word = trim($word, '.,!?');
        if (strlen($word) > 3 && !in_array($word, $stopWords)) {
          $wordCounts[$word] = ($wordCounts[$word] ?? 0) + 1;
        }
      }
    }
    arsort($wordCounts);
    $topWords = array_slice($wordCounts, 0, 10, TRUE);

    // Response time percentiles.
    $responseTimes = $this->database->select('congressional_query_logs', 'l')
      ->fields('l', ['response_time_ms'])
      ->condition('response_time_ms', NULL, 'IS NOT NULL')
      ->orderBy('response_time_ms')
      ->range(0, 1000)
      ->execute()
      ->fetchCol();

    $p50 = $p90 = $p99 = NULL;
    if (count($responseTimes) > 0) {
      sort($responseTimes);
      $p50 = $responseTimes[(int) (count($responseTimes) * 0.5)] ?? NULL;
      $p90 = $responseTimes[(int) (count($responseTimes) * 0.9)] ?? NULL;
      $p99 = $responseTimes[(int) (count($responseTimes) * 0.99)] ?? NULL;
    }

    return array_merge($baseStats, [
      'hourly_distribution' => $hourlyDistribution,
      'daily_distribution' => $dailyDistribution,
      'avg_conversation_length' => $avgConvLength ? round($avgConvLength, 1) : 0,
      'top_words' => $topWords,
      'response_time_percentiles' => [
        'p50' => $p50,
        'p90' => $p90,
        'p99' => $p99,
      ],
    ]);
  }

  /**
   * Update conversation timestamp.
   *
   * @param string $conversationId
   *   The conversation ID.
   */
  protected function updateConversationTimestamp(string $conversationId): void {
    $this->database->update('congressional_query_conversations')
      ->fields(['updated' => $this->time->getRequestTime()])
      ->condition('conversation_id', $conversationId)
      ->execute();
  }

  /**
   * Set conversation title from first user message if empty.
   *
   * @param string $conversationId
   *   The conversation ID.
   * @param array $messages
   *   The messages array.
   */
  protected function setConversationTitleIfEmpty(string $conversationId, array $messages): void {
    // Check if title is already set.
    $existing = $this->database->select('congressional_query_conversations', 'c')
      ->fields('c', ['title'])
      ->condition('conversation_id', $conversationId)
      ->execute()
      ->fetchField();

    if (empty($existing)) {
      // Get first user message.
      $userMessages = array_filter($messages, fn($m) => $m['role'] === 'user');
      if (!empty($userMessages)) {
        $firstMessage = reset($userMessages);
        $title = substr($firstMessage['content'], 0, 100);
        if (strlen($firstMessage['content']) > 100) {
          $title .= '...';
        }

        $this->database->update('congressional_query_conversations')
          ->fields(['title' => $title])
          ->condition('conversation_id', $conversationId)
          ->execute();
      }
    }
  }

  /**
   * Generate a UUID v4.
   *
   * @return string
   *   UUID string.
   */
  protected function generateUuid(): string {
    return sprintf(
      '%04x%04x-%04x-%04x-%04x-%04x%04x%04x',
      mt_rand(0, 0xffff),
      mt_rand(0, 0xffff),
      mt_rand(0, 0xffff),
      mt_rand(0, 0x0fff) | 0x4000,
      mt_rand(0, 0x3fff) | 0x8000,
      mt_rand(0, 0xffff),
      mt_rand(0, 0xffff),
      mt_rand(0, 0xffff)
    );
  }

  /**
   * Get filtered query logs with pagination.
   *
   * @param array $filters
   *   Filter parameters (date_from, date_to, uid, member_filter, model,
   *   min_response_time, max_response_time, search_text).
   * @param int $page
   *   Page number (0-indexed).
   * @param int $limit
   *   Items per page.
   * @param string $sort
   *   Sort field (created, response_time_ms, uid).
   * @param string $order
   *   Sort order (ASC or DESC).
   *
   * @return array
   *   Array with 'results' and 'total' keys.
   */
  public function getFilteredQueryLogs(
    array $filters = [],
    int $page = 0,
    int $limit = 50,
    string $sort = 'created',
    string $order = 'DESC'
  ): array {
    $query = $this->database->select('congressional_query_logs', 'l')
      ->fields('l');

    // Apply filters.
    if (!empty($filters['date_from'])) {
      $dateFrom = strtotime($filters['date_from'] . ' 00:00:00');
      $query->condition('created', $dateFrom, '>=');
    }

    if (!empty($filters['date_to'])) {
      $dateTo = strtotime($filters['date_to'] . ' 23:59:59');
      $query->condition('created', $dateTo, '<=');
    }

    if (!empty($filters['uid'])) {
      $query->condition('uid', $filters['uid']);
    }

    if (!empty($filters['member_filter'])) {
      $query->condition('member_filter', '%' . $this->database->escapeLike($filters['member_filter']) . '%', 'LIKE');
    }

    if (!empty($filters['model'])) {
      $query->condition('model', '%' . $this->database->escapeLike($filters['model']) . '%', 'LIKE');
    }

    if (!empty($filters['min_response_time'])) {
      $query->condition('response_time_ms', $filters['min_response_time'], '>=');
    }

    if (!empty($filters['max_response_time'])) {
      $query->condition('response_time_ms', $filters['max_response_time'], '<=');
    }

    if (!empty($filters['search_text'])) {
      $searchTerm = '%' . $this->database->escapeLike($filters['search_text']) . '%';
      $group = $query->orConditionGroup()
        ->condition('question', $searchTerm, 'LIKE')
        ->condition('answer', $searchTerm, 'LIKE');
      $query->condition($group);
    }

    // Get total count.
    $countQuery = clone $query;
    $total = $countQuery->countQuery()->execute()->fetchField();

    // Apply sorting and pagination.
    $validSortFields = ['created', 'response_time_ms', 'uid', 'id'];
    if (!in_array($sort, $validSortFields)) {
      $sort = 'created';
    }
    $order = strtoupper($order) === 'ASC' ? 'ASC' : 'DESC';

    $query->orderBy($sort, $order)
      ->range($page * $limit, $limit);

    $results = $query->execute()->fetchAll();

    // Format results.
    $formattedResults = array_map(function ($row) {
      $data = (array) $row;
      $data['sources'] = json_decode($data['sources_json'] ?? '[]', TRUE);
      unset($data['sources_json']);
      return $data;
    }, $results);

    return [
      'results' => $formattedResults,
      'total' => (int) $total,
    ];
  }

  /**
   * Delete queries by date range.
   *
   * @param string $dateFrom
   *   Start date (Y-m-d format).
   * @param string $dateTo
   *   End date (Y-m-d format).
   *
   * @return int
   *   Number of deleted records.
   */
  public function deleteQueriesByDateRange(string $dateFrom, string $dateTo): int {
    $from = strtotime($dateFrom . ' 00:00:00');
    $to = strtotime($dateTo . ' 23:59:59');

    return $this->database->delete('congressional_query_logs')
      ->condition('created', $from, '>=')
      ->condition('created', $to, '<=')
      ->execute();
  }

  /**
   * Delete queries by user.
   *
   * @param int $uid
   *   User ID.
   *
   * @return int
   *   Number of deleted records.
   */
  public function deleteQueriesByUser(int $uid): int {
    return $this->database->delete('congressional_query_logs')
      ->condition('uid', $uid)
      ->execute();
  }

  /**
   * Delete queries by member filter.
   *
   * @param string $memberFilter
   *   Member filter value.
   *
   * @return int
   *   Number of deleted records.
   */
  public function deleteQueriesByMemberFilter(string $memberFilter): int {
    return $this->database->delete('congressional_query_logs')
      ->condition('member_filter', $memberFilter)
      ->execute();
  }

  /**
   * Delete query by ID.
   *
   * @param int $queryId
   *   Query log ID.
   *
   * @return bool
   *   TRUE if deleted, FALSE otherwise.
   */
  public function deleteQueryLog(int $queryId): bool {
    $deleted = $this->database->delete('congressional_query_logs')
      ->condition('id', $queryId)
      ->execute();

    return $deleted > 0;
  }

  /**
   * Apply retention policy - delete queries older than configured days.
   *
   * @param int $retentionDays
   *   Number of days to retain queries.
   *
   * @return int
   *   Number of deleted records.
   */
  public function applyRetentionPolicy(int $retentionDays): int {
    $cutoff = $this->time->getRequestTime() - ($retentionDays * 86400);

    return $this->database->delete('congressional_query_logs')
      ->condition('created', $cutoff, '<')
      ->execute();
  }

  /**
   * Get queries by model for analytics.
   *
   * @param int $limit
   *   Maximum results.
   *
   * @return array
   *   Array of model stats.
   */
  public function getQueriesByModel(int $limit = 10): array {
    $results = $this->database->select('congressional_query_logs', 'l')
      ->fields('l', ['model'])
      ->addExpression('COUNT(*)', 'count')
      ->addExpression('AVG(response_time_ms)', 'avg_response_time')
      ->groupBy('model')
      ->orderBy('count', 'DESC')
      ->range(0, $limit)
      ->execute()
      ->fetchAll();

    return array_map(fn($row) => [
      'model' => $row->model ?: 'Unknown',
      'count' => (int) $row->count,
      'avg_response_time' => round($row->avg_response_time ?? 0),
    ], $results);
  }

  /**
   * Get queries by user for analytics.
   *
   * @param int $limit
   *   Maximum results.
   *
   * @return array
   *   Array of user stats.
   */
  public function getQueriesByUser(int $limit = 10): array {
    $results = $this->database->select('congressional_query_logs', 'l')
      ->fields('l', ['uid'])
      ->addExpression('COUNT(*)', 'count')
      ->groupBy('uid')
      ->orderBy('count', 'DESC')
      ->range(0, $limit)
      ->execute()
      ->fetchAll();

    return array_map(fn($row) => [
      'uid' => (int) $row->uid,
      'count' => (int) $row->count,
    ], $results);
  }

}

