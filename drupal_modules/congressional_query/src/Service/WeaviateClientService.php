<?php

namespace Drupal\congressional_query\Service;

use Drupal\Core\Cache\CacheBackendInterface;
use Drupal\Core\Config\ConfigFactoryInterface;
use Psr\Log\LoggerInterface;

/**
 * Service for communicating with Weaviate vector database.
 *
 * This service provides vector search functionality for congressional data
 * stored in Weaviate. All communication with Weaviate and Ollama happens
 * through the SSHTunnelService using remote curl execution.
 *
 * Key features:
 * - Vector similarity search with multiple filters
 * - Embedding generation via Ollama (snowflake-arctic-embed:l)
 * - Member listing with aggregation
 * - Collection statistics (party, state, chamber)
 * - Query result caching for performance
 * - Comprehensive health monitoring
 */
class WeaviateClientService {

  /**
   * Expected embedding dimension for snowflake-arctic-embed:l.
   */
  const EMBEDDING_DIMENSION = 1024;

  /**
   * Cache TTL for embeddings (1 hour).
   */
  const EMBEDDING_CACHE_TTL = 3600;

  /**
   * Cache TTL for search results (15 minutes).
   */
  const SEARCH_CACHE_TTL = 900;

  /**
   * Cache TTL for member list (1 hour).
   */
  const MEMBER_LIST_CACHE_TTL = 3600;

  /**
   * Cache TTL for statistics (30 minutes).
   */
  const STATS_CACHE_TTL = 1800;

  /**
   * Cache TTL for collection existence check (5 minutes).
   */
  const COLLECTION_CHECK_CACHE_TTL = 300;

  /**
   * The SSH tunnel service.
   *
   * @var \Drupal\congressional_query\Service\SSHTunnelService
   */
  protected $sshTunnel;

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
   * The cache backend.
   *
   * @var \Drupal\Core\Cache\CacheBackendInterface
   */
  protected $cache;

  /**
   * Constructs the WeaviateClientService.
   *
   * @param \Drupal\congressional_query\Service\SSHTunnelService $ssh_tunnel
   *   The SSH tunnel service.
   * @param \Drupal\Core\Config\ConfigFactoryInterface $config_factory
   *   The config factory.
   * @param \Psr\Log\LoggerInterface $logger
   *   The logger.
   * @param \Drupal\Core\Cache\CacheBackendInterface $cache
   *   The cache backend.
   */
  public function __construct(
    SSHTunnelService $ssh_tunnel,
    ConfigFactoryInterface $config_factory,
    LoggerInterface $logger,
    CacheBackendInterface $cache
  ) {
    $this->sshTunnel = $ssh_tunnel;
    $this->configFactory = $config_factory;
    $this->logger = $logger;
    $this->cache = $cache;
  }

  /**
   * Get configuration.
   *
   * @return \Drupal\Core\Config\ImmutableConfig
   *   The configuration object.
   */
  protected function getConfig() {
    return $this->configFactory->get('congressional_query.settings');
  }

  /**
   * Get the collection name from configuration.
   *
   * @return string
   *   The collection name.
   */
  protected function getCollectionName(): string {
    return $this->getConfig()->get('weaviate.collection') ?: 'CongressionalData';
  }

  // ===========================================================================
  // Connection Validation
  // ===========================================================================

  /**
   * Validate SSH tunnel connection before operations.
   *
   * Performs comprehensive connection validation including:
   * - Basic connection state check
   * - Deeper health status from SSHTunnelService
   * - Recent error detection
   *
   * @throws \Exception
   *   If SSH tunnel is not connected or healthy, with descriptive error message.
   */
  protected function validateConnection(): void {
    // First check basic connection state.
    if (!$this->sshTunnel->isConnected()) {
      throw new \Exception('SSH tunnel is not connected. Please check connection status in the admin dashboard.');
    }

    // Check deeper health status from SSH tunnel service.
    $healthCheck = $this->sshTunnel->getLastHealthCheck();
    if ($healthCheck !== NULL) {
      // Check overall status from health check.
      $overallStatus = $healthCheck['overall_status'] ?? $healthCheck['status'] ?? NULL;

      if ($overallStatus !== NULL && !in_array($overallStatus, ['ok', 'healthy', 'connected'], TRUE)) {
        // Connection is degraded or unhealthy.
        $reason = $healthCheck['message'] ?? $healthCheck['error'] ?? 'Unknown connectivity issue';
        throw new \Exception('SSH tunnel is unhealthy: ' . $reason . '. Please check the admin dashboard.');
      }

      // Check for recent errors recorded in health state.
      if (!empty($healthCheck['error'])) {
        throw new \Exception('SSH tunnel has recent errors: ' . $healthCheck['error']);
      }

      // Check services health if available.
      if (isset($healthCheck['services'])) {
        foreach ($healthCheck['services'] as $serviceName => $serviceStatus) {
          $status = $serviceStatus['status'] ?? 'unknown';
          if ($status === 'error') {
            $serviceError = $serviceStatus['message'] ?? 'Service unavailable';
            throw new \Exception("SSH tunnel service '$serviceName' is unhealthy: $serviceError");
          }
        }
      }
    }
  }

  // ===========================================================================
  // Collection Management
  // ===========================================================================

  /**
   * Check if the CongressionalData collection exists.
   *
   * @return bool
   *   TRUE if collection exists, FALSE otherwise.
   */
  public function collectionExists(): bool {
    $cacheKey = 'congressional_query:collection_exists';
    $cached = $this->cache->get($cacheKey);

    // Correctly check for cache hit: $cached is an object with 'data' property
    // on cache hit, or FALSE on cache miss. We must check for object existence
    // before accessing ->data to avoid confusing FALSE (miss) with cached FALSE value.
    if ($cached && is_object($cached) && property_exists($cached, 'data')) {
      return (bool) $cached->data;
    }

    try {
      $this->validateConnection();
      $weaviateUrl = $this->sshTunnel->getWeaviateUrl();
      $collection = $this->getCollectionName();

      $url = rtrim($weaviateUrl, '/') . '/v1/schema/' . $collection;
      $response = $this->sshTunnel->makeHttpRequest('GET', $url, [], NULL, 10);

      $exists = ($response['status'] === 200);

      // Cache for 5 minutes. Always store as boolean to ensure consistent type.
      $this->cache->set($cacheKey, (bool) $exists, time() + self::COLLECTION_CHECK_CACHE_TTL);

      return (bool) $exists;
    }
    catch (\Exception $e) {
      $this->logger->error('Failed to check collection existence: @error', [
        '@error' => $e->getMessage(),
      ]);
      return FALSE;
    }
  }

  // ===========================================================================
  // Embedding Generation
  // ===========================================================================

  /**
   * Generate embedding vector for text using Ollama.
   *
   * Uses the /api/embeddings endpoint with the configured embedding model
   * (default: snowflake-arctic-embed:l which produces 1024-dimension vectors).
   *
   * IMPORTANT: Empty or whitespace-only text will return a zero vector.
   * Callers should validate and trim user input before calling this method
   * to provide better user-facing error messages. This method handles empty
   * text gracefully by returning a deterministic zero vector rather than
   * throwing an exception, to avoid breaking batch operations or cases where
   * empty text might occur in automated pipelines.
   *
   * @param string $text
   *   The text to embed. Empty or whitespace-only text will return a zero vector.
   *
   * @return array
   *   The embedding vector (1024 floats for snowflake-arctic-embed:l).
   *   Returns a zero vector if input is empty or whitespace-only.
   *
   * @throws \Exception
   *   If embedding generation fails (network error, Ollama error, etc.).
   */
  public function generateEmbedding(string $text): array {
    $startTime = microtime(TRUE);

    // Handle empty or whitespace-only text by returning a zero vector.
    // This provides a consistent, deterministic result for empty input
    // rather than throwing an exception that would break batch operations.
    if (empty(trim($text))) {
      $this->logger->debug('Empty text provided to generateEmbedding(), returning zero vector');
      return array_fill(0, self::EMBEDDING_DIMENSION, 0.0);
    }

    // Check cache first.
    $cacheKey = 'congressional_query:embedding:' . md5($text);
    $cached = $this->cache->get($cacheKey);

    if ($cached) {
      $this->logger->debug('Returning cached embedding (cache hit)');
      return $cached->data;
    }

    $this->validateConnection();

    $config = $this->getConfig();
    $ollamaEndpoint = $this->sshTunnel->getOllamaEndpoint();
    $embeddingModel = $config->get('ollama.embedding_model') ?: 'snowflake-arctic-embed:l';

    // FIXED: Use correct endpoint /api/embeddings (not /api/embed).
    $url = rtrim($ollamaEndpoint, '/') . '/api/embeddings';

    // FIXED: Use correct request format with 'prompt' (not 'input').
    $payload = json_encode([
      'model' => $embeddingModel,
      'prompt' => $text,
    ]);

    $this->logger->debug('Generating embedding with model @model for text of length @length', [
      '@model' => $embeddingModel,
      '@length' => strlen($text),
    ]);

    try {
      $response = $this->sshTunnel->makeHttpRequest(
        'POST',
        $url,
        ['Content-Type' => 'application/json'],
        $payload,
        60
      );

      if ($response['status'] !== 200) {
        $this->logger->error('Ollama embedding request failed. Status: @status, Body: @body', [
          '@status' => $response['status'],
          '@body' => substr($response['body'] ?? '', 0, 500),
        ]);
        throw new \Exception('Ollama embedding request failed with status ' . $response['status']);
      }

      $data = json_decode($response['body'], TRUE);

      if (json_last_error() !== JSON_ERROR_NONE) {
        throw new \Exception('Failed to parse Ollama embedding response: ' . json_last_error_msg());
      }

      // FIXED: Ollama returns {"embedding": [...]} format.
      if (!isset($data['embedding'])) {
        $this->logger->error('Invalid Ollama embedding response format: @body', [
          '@body' => substr($response['body'], 0, 500),
        ]);
        throw new \Exception('Invalid embedding response: expected "embedding" key not found');
      }

      $embedding = $data['embedding'];

      // Validate embedding dimension.
      $dimension = count($embedding);
      if ($dimension !== self::EMBEDDING_DIMENSION) {
        $this->logger->warning('Unexpected embedding dimension: @actual (expected @expected)', [
          '@actual' => $dimension,
          '@expected' => self::EMBEDDING_DIMENSION,
        ]);
      }

      // Cache embedding for 1 hour.
      $this->cache->set($cacheKey, $embedding, time() + self::EMBEDDING_CACHE_TTL);

      $duration = microtime(TRUE) - $startTime;
      $this->logger->info('Embedding generated in @duration seconds (dimension: @dim)', [
        '@duration' => number_format($duration, 3),
        '@dim' => $dimension,
      ]);

      return $embedding;
    }
    catch (\Exception $e) {
      $this->logger->error('Embedding generation failed: @error. URL: @url, Model: @model', [
        '@error' => $e->getMessage(),
        '@url' => $url,
        '@model' => $embeddingModel,
      ]);
      throw new \Exception('Failed to generate embedding: ' . $e->getMessage(), 0, $e);
    }
  }

  /**
   * Generate embeddings for multiple texts.
   *
   * @param array $texts
   *   Array of text strings to embed.
   *
   * @return array
   *   Array of embedding vectors (same order as input).
   *
   * @throws \Exception
   *   If embedding generation fails.
   */
  public function generateEmbeddingsBatch(array $texts): array {
    $embeddings = [];

    foreach ($texts as $text) {
      // Each call checks cache first, so this is efficient for repeated texts.
      $embeddings[] = $this->generateEmbedding($text);
    }

    return $embeddings;
  }

  // ===========================================================================
  // Vector Search
  // ===========================================================================

  /**
   * Escape a string value for GraphQL.
   *
   * @param string $value
   *   The value to escape.
   *
   * @return string
   *   The escaped string (without surrounding quotes).
   */
  protected function escapeGraphQLString(string $value): string {
    // Escape backslashes first, then double quotes, then newlines.
    $escaped = str_replace('\\', '\\\\', $value);
    $escaped = str_replace('"', '\\"', $escaped);
    $escaped = str_replace("\n", '\\n', $escaped);
    $escaped = str_replace("\r", '\\r', $escaped);
    $escaped = str_replace("\t", '\\t', $escaped);
    return $escaped;
  }

  /**
   * Build a GraphQL where filter object as a string.
   *
   * Constructs proper GraphQL input object syntax rather than using json_encode(),
   * which can produce invalid GraphQL with escaped quotes.
   *
   * @param array $filter
   *   Filter array with 'path', 'operator', and value keys.
   *
   * @return string
   *   GraphQL filter object string.
   */
  protected function buildGraphQLFilter(array $filter): string {
    $parts = [];

    // Path is always an array of strings.
    if (isset($filter['path'])) {
      $pathItems = array_map(function ($p) {
        return '"' . $this->escapeGraphQLString($p) . '"';
      }, $filter['path']);
      $parts[] = 'path: [' . implode(', ', $pathItems) . ']';
    }

    // Operator is an enum (no quotes).
    if (isset($filter['operator'])) {
      $parts[] = 'operator: ' . $filter['operator'];
    }

    // Value fields - handle different types.
    if (isset($filter['valueText'])) {
      $parts[] = 'valueText: "' . $this->escapeGraphQLString($filter['valueText']) . '"';
    }

    if (isset($filter['valueInt'])) {
      $parts[] = 'valueInt: ' . (int) $filter['valueInt'];
    }

    if (isset($filter['valueNumber'])) {
      $parts[] = 'valueNumber: ' . (float) $filter['valueNumber'];
    }

    if (isset($filter['valueBoolean'])) {
      $parts[] = 'valueBoolean: ' . ($filter['valueBoolean'] ? 'true' : 'false');
    }

    // valueTextArray for ContainsAny operator - render as GraphQL array literal.
    if (isset($filter['valueTextArray']) && is_array($filter['valueTextArray'])) {
      $arrayItems = array_map(function ($item) {
        return '"' . $this->escapeGraphQLString($item) . '"';
      }, $filter['valueTextArray']);
      $parts[] = 'valueTextArray: [' . implode(', ', $arrayItems) . ']';
    }

    // Handle nested operands for And/Or operators.
    if (isset($filter['operands']) && is_array($filter['operands'])) {
      $operandStrings = array_map(function ($operand) {
        return $this->buildGraphQLFilter($operand);
      }, $filter['operands']);
      $parts[] = 'operands: [' . implode(', ', $operandStrings) . ']';
    }

    return '{ ' . implode(', ', $parts) . ' }';
  }

  /**
   * Build the complete where clause for GraphQL query.
   *
   * @param array $filters
   *   Array of filter definitions.
   *
   * @return string
   *   GraphQL where clause string (empty string if no filters).
   */
  protected function buildWhereClause(array $filters): string {
    if (empty($filters)) {
      return '';
    }

    if (count($filters) === 1) {
      return ', where: ' . $this->buildGraphQLFilter($filters[0]);
    }

    // Multiple filters: wrap in And operator.
    $combinedFilter = [
      'operator' => 'And',
      'operands' => $filters,
    ];
    return ', where: ' . $this->buildGraphQLFilter($combinedFilter);
  }

  /**
   * Search congressional data using vector similarity.
   *
   * @param array $queryVector
   *   The query embedding vector.
   * @param int $limit
   *   Maximum number of results.
   * @param string|null $memberFilter
   *   Optional member name filter (partial match).
   * @param string|null $stateFilter
   *   Optional state filter (e.g., "TX").
   * @param string|null $partyFilter
   *   Optional party filter (e.g., "Republican", "Democrat").
   * @param string|null $topicFilter
   *   Optional topic filter (partial match).
   * @param string|null $dateFrom
   *   Optional start date filter (ISO format: YYYY-MM-DD).
   * @param string|null $dateTo
   *   Optional end date filter (ISO format: YYYY-MM-DD).
   * @param array|null $policyTopicsFilter
   *   Optional policy topics filter (array of topics).
   *
   * @return array
   *   Array of search results with member info, content, and distance scores.
   *
   * @throws \Exception
   *   If search fails.
   */
  public function searchCongressionalData(
    array $queryVector,
    int $limit = 8,
    ?string $memberFilter = NULL,
    ?string $stateFilter = NULL,
    ?string $partyFilter = NULL,
    ?string $topicFilter = NULL,
    ?string $dateFrom = NULL,
    ?string $dateTo = NULL,
    ?array $policyTopicsFilter = NULL
  ): array {
    $startTime = microtime(TRUE);

    // Generate cache key from query parameters.
    $cacheParams = [
      'vector' => md5(json_encode($queryVector)),
      'limit' => $limit,
      'member' => $memberFilter,
      'state' => $stateFilter,
      'party' => $partyFilter,
      'topic' => $topicFilter,
      'date_from' => $dateFrom,
      'date_to' => $dateTo,
      'policy_topics' => $policyTopicsFilter,
    ];
    $cacheKey = 'congressional_query:search:' . md5(json_encode($cacheParams));

    // Check cache first.
    $cached = $this->cache->get($cacheKey);
    if ($cached && is_object($cached) && property_exists($cached, 'data')) {
      $this->logger->debug('Returning cached search results (cache hit)');
      return $cached->data;
    }

    $this->validateConnection();

    // Check collection exists.
    if (!$this->collectionExists()) {
      $this->logger->warning('CongressionalData collection does not exist');
      return [];
    }

    $weaviateUrl = $this->sshTunnel->getWeaviateUrl();
    $collection = $this->getCollectionName();

    // Build GraphQL where filters using proper GraphQL syntax.
    $whereFilters = [];

    if ($memberFilter && $memberFilter !== 'all') {
      $whereFilters[] = [
        'path' => ['member_name'],
        'operator' => 'Like',
        'valueText' => '*' . $memberFilter . '*',
      ];
    }

    if ($stateFilter) {
      $whereFilters[] = [
        'path' => ['state'],
        'operator' => 'Equal',
        'valueText' => strtoupper($stateFilter),
      ];
    }

    if ($partyFilter) {
      $whereFilters[] = [
        'path' => ['party'],
        'operator' => 'Like',
        'valueText' => '*' . $partyFilter . '*',
      ];
    }

    if ($topicFilter) {
      $whereFilters[] = [
        'path' => ['topic'],
        'operator' => 'Like',
        'valueText' => '*' . $topicFilter . '*',
      ];
    }

    // Date range filters.
    if ($dateFrom) {
      $whereFilters[] = [
        'path' => ['scraped_at'],
        'operator' => 'GreaterThanEqual',
        'valueText' => $dateFrom,
      ];
    }

    if ($dateTo) {
      $whereFilters[] = [
        'path' => ['scraped_at'],
        'operator' => 'LessThanEqual',
        'valueText' => $dateTo,
      ];
    }

    // Policy topics filter (ContainsAny for array field).
    if ($policyTopicsFilter && !empty($policyTopicsFilter)) {
      $whereFilters[] = [
        'path' => ['policy_topics'],
        'operator' => 'ContainsAny',
        'valueTextArray' => $policyTopicsFilter,
      ];
    }

    // Build where clause using proper GraphQL syntax (not json_encode).
    $whereClause = $this->buildWhereClause($whereFilters);

    // Format vector for GraphQL.
    $vectorStr = '[' . implode(',', $queryVector) . ']';

    $graphqlQuery = <<<GRAPHQL
{
  Get {
    $collection(
      limit: $limit,
      nearVector: {
        vector: $vectorStr,
        certainty: 0.5
      }
      $whereClause
    ) {
      member_name
      title
      content_text
      url
      party
      state
      district
      topic
      policy_topics
      chamber
      scraped_at
      website_url
      rss_feed_url
      _additional {
        distance
        certainty
      }
    }
  }
}
GRAPHQL;

    $url = rtrim($weaviateUrl, '/') . '/v1/graphql';
    $payload = json_encode(['query' => $graphqlQuery]);

    $this->logger->debug('Executing Weaviate search with @filters filters', [
      '@filters' => count($whereFilters),
    ]);

    try {
      $response = $this->sshTunnel->makeHttpRequest(
        'POST',
        $url,
        ['Content-Type' => 'application/json'],
        $payload,
        60
      );

      if ($response['status'] !== 200) {
        $this->logger->error('Weaviate search failed. Status: @status, Body: @body', [
          '@status' => $response['status'],
          '@body' => substr($response['body'] ?? '', 0, 500),
        ]);
        throw new \Exception('Weaviate search failed with status ' . $response['status']);
      }

      $data = json_decode($response['body'], TRUE);

      if (json_last_error() !== JSON_ERROR_NONE) {
        throw new \Exception('Failed to parse Weaviate response: ' . json_last_error_msg());
      }

      if (isset($data['errors'])) {
        $errorMsg = is_array($data['errors']) ? json_encode($data['errors']) : $data['errors'];
        $this->logger->error('Weaviate GraphQL error: @error', ['@error' => $errorMsg]);
        throw new \Exception('Weaviate query error: ' . $errorMsg);
      }

      $results = $data['data']['Get'][$collection] ?? [];

      // Process results.
      $processed = [];
      foreach ($results as $result) {
        $processed[] = [
          'member_name' => $result['member_name'] ?? 'Unknown',
          'title' => $result['title'] ?? 'Untitled',
          'content_text' => $result['content_text'] ?? '',
          'url' => $result['url'] ?? '',
          'party' => $result['party'] ?? '',
          'state' => $result['state'] ?? '',
          'district' => $result['district'] ?? '',
          'topic' => $result['topic'] ?? '',
          'policy_topics' => $result['policy_topics'] ?? [],
          'chamber' => $result['chamber'] ?? 'House',
          'scraped_at' => $result['scraped_at'] ?? '',
          'website_url' => $result['website_url'] ?? '',
          'rss_feed_url' => $result['rss_feed_url'] ?? '',
          'distance' => $result['_additional']['distance'] ?? NULL,
          'certainty' => $result['_additional']['certainty'] ?? NULL,
        ];
      }

      // Cache results for 15 minutes.
      $this->cache->set($cacheKey, $processed, time() + self::SEARCH_CACHE_TTL);

      $duration = microtime(TRUE) - $startTime;
      $this->logger->info('Weaviate search completed in @duration seconds, returned @count results', [
        '@duration' => number_format($duration, 3),
        '@count' => count($processed),
      ]);

      return $processed;
    }
    catch (\Exception $e) {
      $this->logger->error('Weaviate search failed: @error. URL: @url, Filters: @filters', [
        '@error' => $e->getMessage(),
        '@url' => $url,
        '@filters' => json_encode($whereFilters),
      ]);
      throw new \Exception('Failed to search congressional data: ' . $e->getMessage(), 0, $e);
    }
  }

  // ===========================================================================
  // Member Management
  // ===========================================================================

  /**
   * List all unique congressional members in the collection.
   *
   * @return array
   *   Array of member info arrays with keys:
   *   - name: Member name
   *   - state: State code (e.g., "TX")
   *   - district: District number
   *   - party: Party affiliation
   *   - chamber: House or Senate
   *   - website_url: Official website
   *   - rss_feed_url: RSS feed URL
   *   - document_count: Number of documents for this member
   *
   * @throws \Exception
   *   If query fails.
   */
  public function listMembers(): array {
    $cacheKey = 'congressional_query:members_list';
    $cached = $this->cache->get($cacheKey);

    if ($cached) {
      $this->logger->debug('Returning cached member list (cache hit)');
      return $cached->data;
    }

    $this->validateConnection();

    // Check collection exists.
    if (!$this->collectionExists()) {
      $this->logger->warning('CongressionalData collection does not exist');
      return [];
    }

    $startTime = microtime(TRUE);
    $weaviateUrl = $this->sshTunnel->getWeaviateUrl();
    $collection = $this->getCollectionName();

    // Step 1: Get unique member names with counts using Aggregate.
    $aggregateQuery = <<<GRAPHQL
{
  Aggregate {
    $collection(groupBy: ["member_name"]) {
      groupedBy {
        value
      }
      meta {
        count
      }
    }
  }
}
GRAPHQL;

    $url = rtrim($weaviateUrl, '/') . '/v1/graphql';

    try {
      $response = $this->sshTunnel->makeHttpRequest(
        'POST',
        $url,
        ['Content-Type' => 'application/json'],
        json_encode(['query' => $aggregateQuery]),
        60
      );

      if ($response['status'] !== 200) {
        throw new \Exception('Aggregate query failed with status ' . $response['status']);
      }

      $data = json_decode($response['body'], TRUE);

      if (isset($data['errors'])) {
        throw new \Exception('GraphQL error: ' . json_encode($data['errors']));
      }

      $aggregateResults = $data['data']['Aggregate'][$collection] ?? [];
      $members = [];

      // Step 2: For each member, fetch one document to get metadata.
      foreach ($aggregateResults as $item) {
        $memberName = $item['groupedBy']['value'] ?? NULL;
        $documentCount = $item['meta']['count'] ?? 0;

        if (!$memberName) {
          continue;
        }

        // Fetch one document to get member metadata.
        $memberQuery = <<<GRAPHQL
{
  Get {
    $collection(
      limit: 1,
      where: {
        path: ["member_name"],
        operator: Equal,
        valueText: "$memberName"
      }
    ) {
      member_name
      party
      state
      district
      chamber
      website_url
      rss_feed_url
    }
  }
}
GRAPHQL;

        $memberResponse = $this->sshTunnel->makeHttpRequest(
          'POST',
          $url,
          ['Content-Type' => 'application/json'],
          json_encode(['query' => $memberQuery]),
          30
        );

        if ($memberResponse['status'] === 200) {
          $memberData = json_decode($memberResponse['body'], TRUE);
          $memberDoc = $memberData['data']['Get'][$collection][0] ?? [];

          $members[] = [
            'name' => $memberName,
            'state' => $memberDoc['state'] ?? '',
            'district' => $memberDoc['district'] ?? '',
            'party' => $memberDoc['party'] ?? '',
            'chamber' => $memberDoc['chamber'] ?? 'House',
            'website_url' => $memberDoc['website_url'] ?? '',
            'rss_feed_url' => $memberDoc['rss_feed_url'] ?? '',
            'document_count' => $documentCount,
          ];
        }
      }

      // Sort by name.
      usort($members, function ($a, $b) {
        return strcmp($a['name'], $b['name']);
      });

      // Cache for 1 hour.
      $this->cache->set($cacheKey, $members, time() + self::MEMBER_LIST_CACHE_TTL);

      $duration = microtime(TRUE) - $startTime;
      $this->logger->info('Member list retrieved in @duration seconds, found @count members', [
        '@duration' => number_format($duration, 3),
        '@count' => count($members),
      ]);

      return $members;
    }
    catch (\Exception $e) {
      $this->logger->error('Failed to list members: @error', [
        '@error' => $e->getMessage(),
      ]);
      throw new \Exception('Failed to list congressional members: ' . $e->getMessage(), 0, $e);
    }
  }

  /**
   * Get all documents for a specific congressional member.
   *
   * @param string $memberName
   *   The member's name.
   * @param int $limit
   *   Maximum number of documents to return.
   * @param int $offset
   *   Offset for pagination.
   *
   * @return array
   *   Array of document objects.
   *
   * @throws \Exception
   *   If query fails.
   */
  public function getMemberDocuments(string $memberName, int $limit = 50, int $offset = 0): array {
    $this->validateConnection();

    if (!$this->collectionExists()) {
      return [];
    }

    $startTime = microtime(TRUE);
    $weaviateUrl = $this->sshTunnel->getWeaviateUrl();
    $collection = $this->getCollectionName();

    // Escape member name for GraphQL.
    $escapedName = addslashes($memberName);

    $graphqlQuery = <<<GRAPHQL
{
  Get {
    $collection(
      limit: $limit,
      offset: $offset,
      where: {
        path: ["member_name"],
        operator: Equal,
        valueText: "$escapedName"
      }
    ) {
      member_name
      title
      content_text
      url
      party
      state
      district
      topic
      policy_topics
      chamber
      scraped_at
      website_url
      rss_feed_url
    }
  }
}
GRAPHQL;

    $url = rtrim($weaviateUrl, '/') . '/v1/graphql';

    try {
      $response = $this->sshTunnel->makeHttpRequest(
        'POST',
        $url,
        ['Content-Type' => 'application/json'],
        json_encode(['query' => $graphqlQuery]),
        60
      );

      if ($response['status'] !== 200) {
        throw new \Exception('Query failed with status ' . $response['status']);
      }

      $data = json_decode($response['body'], TRUE);

      if (isset($data['errors'])) {
        throw new \Exception('GraphQL error: ' . json_encode($data['errors']));
      }

      $results = $data['data']['Get'][$collection] ?? [];

      // Sort by scraped_at descending (most recent first) - in PHP since Weaviate
      // has limited sorting support.
      usort($results, function ($a, $b) {
        return strcmp($b['scraped_at'] ?? '', $a['scraped_at'] ?? '');
      });

      $duration = microtime(TRUE) - $startTime;
      $this->logger->info('Member documents retrieved in @duration seconds for @member, found @count documents', [
        '@duration' => number_format($duration, 3),
        '@member' => $memberName,
        '@count' => count($results),
      ]);

      return $results;
    }
    catch (\Exception $e) {
      $this->logger->error('Failed to get member documents: @error', [
        '@error' => $e->getMessage(),
      ]);
      throw new \Exception('Failed to get member documents: ' . $e->getMessage(), 0, $e);
    }
  }

  // ===========================================================================
  // Statistics
  // ===========================================================================

  /**
   * Get document counts by political party.
   *
   * @return array
   *   Associative array of party => count (e.g., ['Republican' => 200, 'Democrat' => 150]).
   */
  public function getPartyStats(): array {
    return $this->getGroupedStats('party', 'congressional_query:stats:party');
  }

  /**
   * Get document counts by state.
   *
   * @return array
   *   Associative array of state code => count (e.g., ['TX' => 50, 'CA' => 75]).
   */
  public function getStateStats(): array {
    return $this->getGroupedStats('state', 'congressional_query:stats:state');
  }

  /**
   * Get document counts by chamber.
   *
   * @return array
   *   Associative array of chamber => count (e.g., ['House' => 400, 'Senate' => 100]).
   */
  public function getChamberStats(): array {
    return $this->getGroupedStats('chamber', 'congressional_query:stats:chamber');
  }

  /**
   * Get grouped statistics for a given field.
   *
   * @param string $field
   *   The field to group by.
   * @param string $cacheKey
   *   The cache key to use.
   *
   * @return array
   *   Associative array of value => count.
   */
  protected function getGroupedStats(string $field, string $cacheKey): array {
    $cached = $this->cache->get($cacheKey);

    if ($cached) {
      return $cached->data;
    }

    try {
      $this->validateConnection();

      if (!$this->collectionExists()) {
        return [];
      }

      $weaviateUrl = $this->sshTunnel->getWeaviateUrl();
      $collection = $this->getCollectionName();

      $graphqlQuery = <<<GRAPHQL
{
  Aggregate {
    $collection(groupBy: ["$field"]) {
      groupedBy {
        value
      }
      meta {
        count
      }
    }
  }
}
GRAPHQL;

      $url = rtrim($weaviateUrl, '/') . '/v1/graphql';

      $response = $this->sshTunnel->makeHttpRequest(
        'POST',
        $url,
        ['Content-Type' => 'application/json'],
        json_encode(['query' => $graphqlQuery]),
        30
      );

      if ($response['status'] !== 200) {
        $this->logger->error('Stats query failed for field @field: @status', [
          '@field' => $field,
          '@status' => $response['status'],
        ]);
        return [];
      }

      $data = json_decode($response['body'], TRUE);

      if (isset($data['errors'])) {
        $this->logger->error('Stats query error for field @field: @error', [
          '@field' => $field,
          '@error' => json_encode($data['errors']),
        ]);
        return [];
      }

      $results = $data['data']['Aggregate'][$collection] ?? [];
      $stats = [];

      foreach ($results as $item) {
        $value = $item['groupedBy']['value'] ?? NULL;
        $count = $item['meta']['count'] ?? 0;

        if ($value !== NULL) {
          $stats[$value] = $count;
        }
      }

      // Sort by count descending.
      arsort($stats);

      // Cache for 30 minutes.
      $this->cache->set($cacheKey, $stats, time() + self::STATS_CACHE_TTL);

      return $stats;
    }
    catch (\Exception $e) {
      $this->logger->error('Failed to get @field stats: @error', [
        '@field' => $field,
        '@error' => $e->getMessage(),
      ]);
      return [];
    }
  }

  /**
   * Get collection statistics.
   *
   * @return array
   *   Collection stats including count.
   */
  public function getCollectionStats(): array {
    try {
      $this->validateConnection();

      $weaviateUrl = $this->sshTunnel->getWeaviateUrl();
      $collection = $this->getCollectionName();

      $graphqlQuery = <<<GRAPHQL
{
  Aggregate {
    $collection {
      meta {
        count
      }
    }
  }
}
GRAPHQL;

      $url = rtrim($weaviateUrl, '/') . '/v1/graphql';

      $response = $this->sshTunnel->makeHttpRequest(
        'POST',
        $url,
        ['Content-Type' => 'application/json'],
        json_encode(['query' => $graphqlQuery]),
        30
      );

      if ($response['status'] !== 200) {
        return [
          'collection' => $collection,
          'count' => 0,
          'error' => 'Request failed with status ' . $response['status'],
        ];
      }

      $data = json_decode($response['body'], TRUE);
      $count = $data['data']['Aggregate'][$collection][0]['meta']['count'] ?? 0;

      return [
        'collection' => $collection,
        'count' => $count,
      ];
    }
    catch (\Exception $e) {
      return [
        'collection' => $this->getCollectionName(),
        'count' => 0,
        'error' => $e->getMessage(),
      ];
    }
  }

  // ===========================================================================
  // Health Checks
  // ===========================================================================

  /**
   * Check Weaviate and Ollama connection health.
   *
   * @return array
   *   Comprehensive health status array with keys:
   *   - status: 'ok', 'warning', or 'error'
   *   - message: Human-readable status message
   *   - details: Detailed status for each component
   */
  public function checkHealth(): array {
    $startTime = microtime(TRUE);
    $details = [
      'weaviate' => ['status' => 'unknown'],
      'ollama' => ['status' => 'unknown'],
      'collection' => ['status' => 'unknown'],
    ];
    $overallStatus = 'ok';
    $messages = [];

    // Check Weaviate.
    try {
      $weaviateUrl = $this->sshTunnel->getWeaviateUrl();
      $url = rtrim($weaviateUrl, '/') . '/v1/meta';

      $response = $this->sshTunnel->makeHttpRequest('GET', $url, [], NULL, 10);

      if ($response['status'] === 200) {
        $data = json_decode($response['body'], TRUE);
        $details['weaviate'] = [
          'status' => 'ok',
          'version' => $data['version'] ?? 'unknown',
          'hostname' => $data['hostname'] ?? 'unknown',
        ];
      }
      else {
        $details['weaviate'] = [
          'status' => 'error',
          'message' => 'Weaviate returned status ' . $response['status'],
        ];
        $overallStatus = 'error';
        $messages[] = 'Weaviate connection failed';
      }
    }
    catch (\Exception $e) {
      $details['weaviate'] = [
        'status' => 'error',
        'message' => $e->getMessage(),
      ];
      $overallStatus = 'error';
      $messages[] = 'Weaviate error: ' . $e->getMessage();
    }

    // Check Ollama.
    try {
      $ollamaEndpoint = $this->sshTunnel->getOllamaEndpoint();
      $url = rtrim($ollamaEndpoint, '/') . '/api/tags';

      $response = $this->sshTunnel->makeHttpRequest('GET', $url, [], NULL, 10);

      if ($response['status'] === 200) {
        $data = json_decode($response['body'], TRUE);
        $models = [];
        if (isset($data['models'])) {
          foreach ($data['models'] as $model) {
            $models[] = $model['name'] ?? 'unknown';
          }
        }
        $details['ollama'] = [
          'status' => 'ok',
          'models' => $models,
          'model_count' => count($models),
        ];
      }
      else {
        $details['ollama'] = [
          'status' => 'error',
          'message' => 'Ollama returned status ' . $response['status'],
        ];
        $overallStatus = ($overallStatus === 'error') ? 'error' : 'warning';
        $messages[] = 'Ollama connection failed';
      }
    }
    catch (\Exception $e) {
      $details['ollama'] = [
        'status' => 'error',
        'message' => $e->getMessage(),
      ];
      $overallStatus = ($overallStatus === 'error') ? 'error' : 'warning';
      $messages[] = 'Ollama error: ' . $e->getMessage();
    }

    // Check collection existence and stats.
    try {
      $collectionName = $this->getCollectionName();
      $exists = $this->collectionExists();

      if ($exists) {
        $stats = $this->getCollectionStats();
        $details['collection'] = [
          'status' => 'ok',
          'exists' => TRUE,
          'name' => $collectionName,
          'document_count' => $stats['count'] ?? 0,
        ];
      }
      else {
        $details['collection'] = [
          'status' => 'warning',
          'exists' => FALSE,
          'name' => $collectionName,
          'message' => 'Collection does not exist',
        ];
        if ($overallStatus === 'ok') {
          $overallStatus = 'warning';
        }
        $messages[] = 'Collection not found';
      }
    }
    catch (\Exception $e) {
      $details['collection'] = [
        'status' => 'error',
        'message' => $e->getMessage(),
      ];
      if ($overallStatus === 'ok') {
        $overallStatus = 'warning';
      }
    }

    $duration = microtime(TRUE) - $startTime;

    // Build overall message.
    if (empty($messages)) {
      $message = 'All services healthy';
    }
    else {
      $message = implode('; ', $messages);
    }

    return [
      'status' => $overallStatus,
      'message' => $message,
      'details' => $details,
      'response_time_ms' => (int) ($duration * 1000),
    ];
  }

  // ===========================================================================
  // Cache Management
  // ===========================================================================

  /**
   * List of well-known cache key prefixes used by this service.
   *
   * @return array
   *   Array of cache key prefixes.
   */
  protected function getCacheKeyPrefixes(): array {
    return [
      'congressional_query:collection_exists',
      'congressional_query:members_list',
      'congressional_query:stats:party',
      'congressional_query:stats:state',
      'congressional_query:stats:chamber',
    ];
  }

  /**
   * Clear all cached data for this service.
   *
   * Deletes well-known cache keys (collection existence, member list, stats).
   * Note: Embedding caches and search result caches use dynamic keys based on
   * content hashes, so they cannot be deleted by key prefix. These will expire
   * naturally based on their TTLs until cache tags are implemented.
   *
   * Useful when collection data has been updated and cached results
   * should be invalidated.
   */
  public function clearCache(): void {
    $deletedCount = 0;

    // Delete all well-known cache keys.
    foreach ($this->getCacheKeyPrefixes() as $cacheKey) {
      $this->cache->delete($cacheKey);
      $deletedCount++;
    }

    $this->logger->info('Cache cleared for WeaviateClientService. Deleted @count well-known cache entries. Note: Search result and embedding caches use dynamic keys and will expire via TTL.', [
      '@count' => $deletedCount,
    ]);
  }

  /**
   * Invalidate collection-related caches.
   *
   * Call this when the collection structure changes (e.g., schema update).
   */
  public function invalidateCollectionCache(): void {
    $this->cache->delete('congressional_query:collection_exists');
    $this->logger->info('Collection existence cache invalidated');
  }

  /**
   * Invalidate member-related caches.
   *
   * Call this when member data changes (e.g., new members added).
   */
  public function invalidateMemberCache(): void {
    $this->cache->delete('congressional_query:members_list');
    $this->logger->info('Member list cache invalidated');
  }

  /**
   * Invalidate statistics caches.
   *
   * Call this when document counts change significantly.
   */
  public function invalidateStatsCache(): void {
    $this->cache->delete('congressional_query:stats:party');
    $this->cache->delete('congressional_query:stats:state');
    $this->cache->delete('congressional_query:stats:chamber');
    $this->logger->info('Statistics caches invalidated');
  }

}
