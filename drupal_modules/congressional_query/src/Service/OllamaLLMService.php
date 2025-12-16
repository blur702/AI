<?php

namespace Drupal\congressional_query\Service;

use Drupal\Core\Cache\CacheBackendInterface;
use Drupal\Core\Config\ConfigFactoryInterface;
use Drupal\Core\Session\AccountProxyInterface;
use Drupal\Core\State\StateInterface;
use Psr\Log\LoggerInterface;

/**
 * Service for LLM inference using Ollama with enhanced features.
 *
 * Provides RAG (Retrieval-Augmented Generation) pipeline for congressional
 * queries with:
 * - Streaming response support
 * - Multi-turn conversation history
 * - Response caching
 * - Advanced Ollama configuration options
 * - Retry logic with exponential backoff
 * - Token usage tracking
 * - Model validation with fallback
 * - Context window management
 * - Enhanced health checks
 * - Comprehensive logging and debugging
 */
class OllamaLLMService {

  /**
   * System prompt for congressional queries.
   */
  const SYSTEM_PROMPT = <<<PROMPT
You are a knowledgeable assistant specializing in U.S. congressional information. You have access to information about congressional members, their press releases, positions, and voting records.

When answering questions:
1. Base your answers on the provided context from congressional sources
2. Cite specific members and their positions when relevant
3. Be objective and present multiple viewpoints when discussing policy issues
4. If the context doesn't contain enough information to fully answer, say so
5. Include relevant details like state, party, and specific quotes when available

Format your responses clearly with:
- Direct answers to questions
- Supporting evidence from the sources
- Attribution to specific members when quoting or paraphrasing
PROMPT;

  /**
   * Default context window size for most models.
   */
  const DEFAULT_CONTEXT_WINDOW = 8192;

  /**
   * Tokens per character estimate (conservative).
   */
  const TOKENS_PER_CHAR = 0.25;

  /**
   * Maximum retry attempts.
   */
  const MAX_RETRY_ATTEMPTS = 3;

  /**
   * Base delay for exponential backoff (milliseconds).
   */
  const BASE_RETRY_DELAY_MS = 1000;

  /**
   * Cache key prefix for model validation.
   */
  const CACHE_KEY_MODELS = 'congressional_query:ollama:models';

  /**
   * Cache key prefix for responses.
   */
  const CACHE_KEY_RESPONSE_PREFIX = 'congressional_query:ollama:response:';

  /**
   * State key for conversation history.
   */
  const STATE_KEY_CONVERSATIONS = 'congressional_query.conversations';

  /**
   * State key for tracking response cache keys.
   */
  const STATE_KEY_RESPONSE_CACHE_KEYS = 'congressional_query.ollama_response_cache_keys';

  /**
   * Cache tag for Ollama responses.
   */
  const CACHE_TAG_RESPONSES = 'congressional_query:ollama_responses';

  /**
   * Known model context windows.
   *
   * @var array
   */
  protected static $modelContextWindows = [
    'qwen3-coder-roo' => 32768,
    'qwen3' => 32768,
    'llama3' => 8192,
    'llama3.1' => 131072,
    'llama3.2' => 131072,
    'mistral' => 32768,
    'mixtral' => 32768,
    'phi3' => 128000,
    'gemma2' => 8192,
    'codellama' => 16384,
  ];

  /**
   * The SSH tunnel service.
   *
   * @var \Drupal\congressional_query\Service\SSHTunnelService
   */
  protected $sshTunnel;

  /**
   * The Weaviate client service.
   *
   * @var \Drupal\congressional_query\Service\WeaviateClientService
   */
  protected $weaviateClient;

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
   * The state service.
   *
   * @var \Drupal\Core\State\StateInterface
   */
  protected $state;

  /**
   * The current user.
   *
   * @var \Drupal\Core\Session\AccountProxyInterface
   */
  protected $currentUser;

  /**
   * Token usage statistics for current session.
   *
   * @var array
   */
  protected $tokenUsage = [
    'prompt_tokens' => 0,
    'completion_tokens' => 0,
    'total_tokens' => 0,
    'tokens_per_second' => 0.0,
    'requests' => 0,
  ];

  /**
   * Validated models cache (in-memory).
   *
   * @var array
   */
  protected $validatedModels = [];

  /**
   * Debug mode flag.
   *
   * @var bool
   */
  protected $debugMode = FALSE;

  /**
   * Constructs the OllamaLLMService.
   *
   * @param \Drupal\congressional_query\Service\SSHTunnelService $ssh_tunnel
   *   The SSH tunnel service.
   * @param \Drupal\congressional_query\Service\WeaviateClientService $weaviate_client
   *   The Weaviate client service.
   * @param \Drupal\Core\Config\ConfigFactoryInterface $config_factory
   *   The config factory.
   * @param \Psr\Log\LoggerInterface $logger
   *   The logger.
   * @param \Drupal\Core\Cache\CacheBackendInterface $cache
   *   The cache backend.
   * @param \Drupal\Core\State\StateInterface $state
   *   The state service.
   * @param \Drupal\Core\Session\AccountProxyInterface $current_user
   *   The current user.
   */
  public function __construct(
    SSHTunnelService $ssh_tunnel,
    WeaviateClientService $weaviate_client,
    ConfigFactoryInterface $config_factory,
    LoggerInterface $logger,
    CacheBackendInterface $cache,
    StateInterface $state,
    AccountProxyInterface $current_user
  ) {
    $this->sshTunnel = $ssh_tunnel;
    $this->weaviateClient = $weaviate_client;
    $this->configFactory = $config_factory;
    $this->logger = $logger;
    $this->cache = $cache;
    $this->state = $state;
    $this->currentUser = $current_user;

    // Check if debug mode is enabled.
    $this->debugMode = (bool) $this->getConfig()->get('ollama.debug_mode');
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
   * Answer a question using RAG pipeline.
   *
   * @param string $question
   *   The user's question.
   * @param string|null $memberFilter
   *   Optional member name filter.
   * @param int|null $numSources
   *   Number of sources to retrieve.
   * @param string|null $conversationId
   *   Optional conversation ID for context.
   * @param array $options
   *   Additional options:
   *   - use_cache: Whether to use response caching (default: TRUE).
   *   - include_history: Whether to include conversation history (default: TRUE).
   *
   * @return array
   *   Response array with 'answer', 'sources', 'model', 'conversation_id',
   *   'token_usage', 'response_time_ms', 'cache_hit'.
   *
   * @throws \Exception
   *   If answer generation fails.
   */
  public function answerQuestion(
    string $question,
    ?string $memberFilter = NULL,
    ?int $numSources = NULL,
    ?string $conversationId = NULL,
    array $options = []
  ): array {
    $startTime = microtime(TRUE);
    $config = $this->getConfig();

    $useCache = $options['use_cache'] ?? TRUE;
    $includeHistory = $options['include_history'] ?? TRUE;

    $numSources = $numSources ?? $config->get('query.default_num_sources') ?? 8;
    $model = $config->get('ollama.model') ?? 'qwen3-coder-roo:latest';

    // Generate or use existing conversation ID (always generate fresh for this request).
    $conversationId = $conversationId ?? $this->generateConversationId();

    $this->debugLog('Processing question', [
      'question' => substr($question, 0, 100),
      'filter' => $memberFilter ?? 'none',
      'conversation_id' => $conversationId,
    ]);

    // Determine if we have existing conversation history that would affect the response.
    // If so, disable caching to avoid stale answers.
    $conversationHistory = [];
    if ($includeHistory) {
      $conversationHistory = $this->getConversationHistory($conversationId);
    }
    $hasConversationContext = !empty($conversationHistory);

    // Disable caching when conversation history is present, as the response
    // depends on prior context that won't match cache keys.
    $effectiveUseCache = $useCache && !$hasConversationContext;

    // Check response cache only for stateless queries.
    if ($effectiveUseCache) {
      $cacheKey = $this->buildResponseCacheKey($question, $memberFilter, $model);
      $cached = $this->cache->get($cacheKey);
      if ($cached && is_object($cached) && property_exists($cached, 'data')) {
        $this->debugLog('Cache hit for question');
        $cachedResponse = $cached->data;
        $cachedResponse['cache_hit'] = TRUE;
        $cachedResponse['response_time_ms'] = (int) ((microtime(TRUE) - $startTime) * 1000);
        // Always regenerate conversation_id on cache hit to avoid leaking
        // another user's conversation context.
        $cachedResponse['conversation_id'] = $this->generateConversationId();
        return $cachedResponse;
      }
    }

    // Validate model before use.
    $model = $this->validateModel($model);

    // Step 1: Generate embedding for the question.
    $queryVector = $this->weaviateClient->generateEmbedding($question);

    // Step 2: Search Weaviate for relevant documents.
    $sources = $this->weaviateClient->searchCongressionalData(
      $queryVector,
      $numSources,
      $memberFilter
    );

    // Step 3: Format context from sources.
    $maxContextLength = $config->get('query.max_context_length') ?? 1500;
    $context = $this->formatContext($sources, $maxContextLength);

    // Step 4: Build prompt with conversation history (already fetched above).
    $prompt = $this->buildPrompt($question, $context, $conversationHistory);

    // Step 5: Manage context window.
    $prompt = $this->manageContextWindow($prompt, $model);

    // Step 6: Generate answer with retry logic.
    $generationResult = $this->generateCompletionWithRetry($prompt, $model);

    $endTime = microtime(TRUE);
    $responseTimeMs = (int) (($endTime - $startTime) * 1000);

    // Update token usage statistics.
    $tokenUsage = $generationResult['token_usage'] ?? [];
    $this->updateTokenUsage($tokenUsage);

    // Store conversation turn (scoped to user).
    if ($includeHistory) {
      $this->addConversationTurn($conversationId, $question, $generationResult['response']);
    }

    $this->logger->info('Generated answer in @time ms with @count sources', [
      '@time' => $responseTimeMs,
      '@count' => count($sources),
    ]);

    $response = [
      'answer' => $generationResult['response'],
      'sources' => $sources,
      'model' => $model,
      'conversation_id' => $conversationId,
      'response_time_ms' => $responseTimeMs,
      'num_sources' => count($sources),
      'token_usage' => $tokenUsage,
      'cache_hit' => FALSE,
    ];

    // Cache only stateless responses (no conversation history).
    // Do not include conversation_id in cached data to prevent cross-user leakage.
    if ($effectiveUseCache) {
      $cacheTtl = $config->get('ollama.response_cache_ttl') ?? 3600;
      $cacheableResponse = $response;
      // Remove conversation_id from cached data - it will be regenerated on cache hit.
      unset($cacheableResponse['conversation_id']);
      $this->cache->set(
        $cacheKey,
        $cacheableResponse,
        time() + $cacheTtl,
        [self::CACHE_TAG_RESPONSES]
      );
      // Track cache key for targeted invalidation.
      $this->trackCacheKey($cacheKey);
    }

    return $response;
  }

  /**
   * Answer a question with streaming response.
   *
   * @param string $question
   *   The user's question.
   * @param callable $callback
   *   Callback function receiving each chunk: function(string $chunk, bool $done).
   * @param string|null $memberFilter
   *   Optional member name filter.
   * @param int|null $numSources
   *   Number of sources to retrieve.
   * @param string|null $conversationId
   *   Optional conversation ID for context.
   *
   * @return array
   *   Final response metadata (sources, model, token_usage, etc.).
   *
   * @throws \Exception
   *   If streaming generation fails.
   */
  public function answerQuestionStream(
    string $question,
    callable $callback,
    ?string $memberFilter = NULL,
    ?int $numSources = NULL,
    ?string $conversationId = NULL
  ): array {
    $startTime = microtime(TRUE);
    $config = $this->getConfig();

    $numSources = $numSources ?? $config->get('query.default_num_sources') ?? 8;
    $model = $config->get('ollama.model') ?? 'qwen3-coder-roo:latest';
    $conversationId = $conversationId ?? $this->generateConversationId();

    $this->debugLog('Processing streaming question', [
      'question' => substr($question, 0, 100),
      'filter' => $memberFilter ?? 'none',
    ]);

    // Validate model.
    $model = $this->validateModel($model);

    // Step 1: Generate embedding.
    $queryVector = $this->weaviateClient->generateEmbedding($question);

    // Step 2: Search Weaviate.
    $sources = $this->weaviateClient->searchCongressionalData(
      $queryVector,
      $numSources,
      $memberFilter
    );

    // Step 3: Format context.
    $maxContextLength = $config->get('query.max_context_length') ?? 1500;
    $context = $this->formatContext($sources, $maxContextLength);

    // Step 4: Build prompt with history.
    $conversationHistory = $this->getConversationHistory($conversationId);
    $prompt = $this->buildPrompt($question, $context, $conversationHistory);

    // Step 5: Manage context window.
    $prompt = $this->manageContextWindow($prompt, $model);

    // Step 6: Generate streaming response.
    $streamResult = $this->generateCompletionStream($prompt, $model, $callback);

    $endTime = microtime(TRUE);
    $responseTimeMs = (int) (($endTime - $startTime) * 1000);

    // Update token usage.
    $tokenUsage = $streamResult['token_usage'] ?? [];
    $this->updateTokenUsage($tokenUsage);

    // Store conversation turn.
    $this->addConversationTurn($conversationId, $question, $streamResult['full_response']);

    return [
      'sources' => $sources,
      'model' => $model,
      'conversation_id' => $conversationId,
      'response_time_ms' => $responseTimeMs,
      'num_sources' => count($sources),
      'token_usage' => $tokenUsage,
    ];
  }

  /**
   * Generate completion with true incremental streaming support.
   *
   * Uses the SSH tunnel's streaming HTTP request method to deliver chunks
   * as they arrive from Ollama, enabling real-time streaming to the client.
   *
   * @param string $prompt
   *   The prompt to send.
   * @param string $model
   *   The model to use.
   * @param callable $callback
   *   Callback for each chunk: function(string $chunk, bool $done).
   *
   * @return array
   *   Result with 'full_response' and 'token_usage'.
   *
   * @throws \Exception
   *   If streaming generation fails.
   */
  protected function generateCompletionStream(
    string $prompt,
    string $model,
    callable $callback
  ): array {
    $ollamaEndpoint = $this->sshTunnel->getOllamaEndpoint();
    $options = $this->buildOllamaOptions();

    $url = rtrim($ollamaEndpoint, '/') . '/api/generate';

    $payload = json_encode([
      'model' => $model,
      'prompt' => $prompt,
      'system' => self::SYSTEM_PROMPT,
      'stream' => TRUE,
      'options' => $options,
    ]);

    $this->debugLog('Sending true streaming request to Ollama', ['model' => $model]);

    // Use true streaming via SSH tunnel's streaming method.
    // This invokes our callback as data arrives from the remote curl command.
    $fullResponse = '';
    $tokenUsage = [];

    // Wrap the user's callback to parse NDJSON lines and extract token usage.
    $streamCallback = function ($line) use ($callback, &$fullResponse, &$tokenUsage) {
      $line = trim($line);
      if (empty($line)) {
        return;
      }

      $data = json_decode($line, TRUE);
      if (json_last_error() !== JSON_ERROR_NONE) {
        // Not valid JSON, might be partial data - skip.
        return;
      }

      if (isset($data['response'])) {
        $chunk = $data['response'];
        $fullResponse .= $chunk;
        $done = $data['done'] ?? FALSE;

        // Invoke the user's callback with the chunk and done flag.
        $callback($chunk, $done);

        // Capture token usage from final response.
        if ($done && isset($data['total_duration'])) {
          $tokenUsage = [
            'prompt_tokens' => $data['prompt_eval_count'] ?? 0,
            'completion_tokens' => $data['eval_count'] ?? 0,
            'total_duration_ns' => $data['total_duration'] ?? 0,
            'load_duration_ns' => $data['load_duration'] ?? 0,
            'eval_duration_ns' => $data['eval_duration'] ?? 0,
          ];

          // Calculate tokens per second.
          if (!empty($tokenUsage['eval_duration_ns']) && $tokenUsage['eval_duration_ns'] > 0) {
            $evalSeconds = $tokenUsage['eval_duration_ns'] / 1e9;
            $tokenUsage['tokens_per_second'] = $tokenUsage['completion_tokens'] / $evalSeconds;
          }
        }
      }
    };

    // Execute streaming request - callback is invoked as data arrives.
    $statusCode = $this->sshTunnel->makeHttpRequestStreaming(
      'POST',
      $url,
      ['Content-Type' => 'application/json'],
      $payload,
      $streamCallback,
      300 // Longer timeout for generation.
    );

    if ($statusCode !== 200 && $statusCode !== 0) {
      throw new \Exception('Ollama streaming failed with status ' . $statusCode);
    }

    return [
      'full_response' => $fullResponse,
      'token_usage' => $tokenUsage,
    ];
  }

  /**
   * Generate completion with retry logic.
   *
   * @param string $prompt
   *   The prompt to send.
   * @param string $model
   *   The model to use.
   *
   * @return array
   *   Result with 'response' and 'token_usage'.
   *
   * @throws \Exception
   *   If all retry attempts fail.
   */
  protected function generateCompletionWithRetry(string $prompt, string $model): array {
    $attempts = 0;
    $lastException = NULL;

    while ($attempts < self::MAX_RETRY_ATTEMPTS) {
      try {
        return $this->generateCompletion($prompt, $model);
      }
      catch (\Exception $e) {
        $lastException = $e;
        $attempts++;

        if ($attempts < self::MAX_RETRY_ATTEMPTS) {
          // Exponential backoff.
          $delayMs = self::BASE_RETRY_DELAY_MS * pow(2, $attempts - 1);

          // Add jitter (±25%).
          $jitter = $delayMs * (mt_rand(-25, 25) / 100);
          $delayMs = (int) ($delayMs + $jitter);

          $this->logger->warning('Ollama request failed (attempt @attempt/@max), retrying in @delay ms: @error', [
            '@attempt' => $attempts,
            '@max' => self::MAX_RETRY_ATTEMPTS,
            '@delay' => $delayMs,
            '@error' => $e->getMessage(),
          ]);

          usleep($delayMs * 1000);
        }
      }
    }

    $this->logger->error('Ollama request failed after @max attempts: @error', [
      '@max' => self::MAX_RETRY_ATTEMPTS,
      '@error' => $lastException->getMessage(),
    ]);

    throw $lastException;
  }

  /**
   * Generate completion using Ollama.
   *
   * @param string $prompt
   *   The prompt to send.
   * @param string $model
   *   The model to use.
   *
   * @return array
   *   Result with 'response' and 'token_usage'.
   *
   * @throws \Exception
   *   If generation fails.
   */
  protected function generateCompletion(string $prompt, string $model): array {
    $ollamaEndpoint = $this->sshTunnel->getOllamaEndpoint();
    $options = $this->buildOllamaOptions();

    $url = rtrim($ollamaEndpoint, '/') . '/api/generate';

    $payload = json_encode([
      'model' => $model,
      'prompt' => $prompt,
      'system' => self::SYSTEM_PROMPT,
      'stream' => FALSE,
      'options' => $options,
    ]);

    $this->debugLog('Sending generation request to Ollama', ['model' => $model]);

    $config = $this->getConfig();
    $timeout = $config->get('ollama.generation_timeout') ?? 120;

    $response = $this->sshTunnel->makeHttpRequest(
      'POST',
      $url,
      ['Content-Type' => 'application/json'],
      $payload,
      $timeout
    );

    if ($response['status'] !== 200) {
      throw new \Exception('Ollama generation failed with status ' . $response['status']);
    }

    $data = json_decode($response['body'], TRUE);

    if (json_last_error() !== JSON_ERROR_NONE) {
      throw new \Exception('Failed to parse Ollama response: ' . json_last_error_msg());
    }

    if (!isset($data['response'])) {
      throw new \Exception('Invalid Ollama response format');
    }

    // Extract token usage.
    $tokenUsage = [
      'prompt_tokens' => $data['prompt_eval_count'] ?? 0,
      'completion_tokens' => $data['eval_count'] ?? 0,
      'total_duration_ns' => $data['total_duration'] ?? 0,
      'load_duration_ns' => $data['load_duration'] ?? 0,
      'eval_duration_ns' => $data['eval_duration'] ?? 0,
    ];

    // Calculate tokens per second.
    if (!empty($tokenUsage['eval_duration_ns']) && $tokenUsage['eval_duration_ns'] > 0) {
      $evalSeconds = $tokenUsage['eval_duration_ns'] / 1e9;
      $tokenUsage['tokens_per_second'] = $tokenUsage['completion_tokens'] / $evalSeconds;
    }
    else {
      $tokenUsage['tokens_per_second'] = 0;
    }

    return [
      'response' => trim($data['response']),
      'token_usage' => $tokenUsage,
    ];
  }

  /**
   * Build Ollama options from configuration.
   *
   * @return array
   *   Ollama options array.
   */
  protected function buildOllamaOptions(): array {
    $config = $this->getConfig();

    $options = [
      'temperature' => $config->get('ollama.temperature') ?? 0.3,
      'num_predict' => $config->get('ollama.num_predict') ?? 2048,
    ];

    // Optional advanced options.
    if ($topP = $config->get('ollama.top_p')) {
      $options['top_p'] = (float) $topP;
    }

    if ($topK = $config->get('ollama.top_k')) {
      $options['top_k'] = (int) $topK;
    }

    if ($repeatPenalty = $config->get('ollama.repeat_penalty')) {
      $options['repeat_penalty'] = (float) $repeatPenalty;
    }

    if ($seed = $config->get('ollama.seed')) {
      $options['seed'] = (int) $seed;
    }

    // Stop sequences.
    $stopSequences = $config->get('ollama.stop_sequences');
    if (!empty($stopSequences) && is_array($stopSequences)) {
      $options['stop'] = $stopSequences;
    }

    return $options;
  }

  /**
   * Format context from source documents.
   *
   * @param array $sources
   *   Array of source documents.
   * @param int $maxLength
   *   Maximum length per document.
   *
   * @return string
   *   Formatted context string.
   */
  protected function formatContext(array $sources, int $maxLength = 1500): string {
    if (empty($sources)) {
      return "No relevant congressional information found.";
    }

    $contextParts = [];

    foreach ($sources as $i => $source) {
      $content = $source['content_text'] ?? '';

      // Truncate content if too long.
      if (strlen($content) > $maxLength) {
        $content = substr($content, 0, $maxLength) . '...';
      }

      $memberInfo = sprintf(
        "%s (%s-%s)",
        $source['member_name'] ?? 'Unknown',
        $source['party'] ?? '?',
        $source['state'] ?? '??'
      );

      $title = $source['title'] ?? 'Untitled';
      $topic = $source['topic'] ?? '';

      $contextParts[] = sprintf(
        "[Source %d: %s]\nFrom: %s%s\n\n%s",
        $i + 1,
        $title,
        $memberInfo,
        $topic ? "\nTopic: $topic" : '',
        $content
      );
    }

    return implode("\n\n---\n\n", $contextParts);
  }

  /**
   * Build the full prompt with system message, context, and history.
   *
   * @param string $question
   *   The user's question.
   * @param string $context
   *   The formatted context.
   * @param array $conversationHistory
   *   Previous conversation turns.
   *
   * @return string
   *   The complete prompt.
   */
  protected function buildPrompt(
    string $question,
    string $context,
    array $conversationHistory = []
  ): string {
    $promptParts = [];

    // Add context.
    $promptParts[] = "CONTEXT FROM CONGRESSIONAL SOURCES:\n\n" . $context;

    // Add conversation history if present.
    if (!empty($conversationHistory)) {
      $historyText = "PREVIOUS CONVERSATION:\n\n";
      foreach ($conversationHistory as $turn) {
        $historyText .= "User: " . $turn['question'] . "\n";
        $historyText .= "Assistant: " . $turn['answer'] . "\n\n";
      }
      $promptParts[] = $historyText;
    }

    // Add current question.
    $promptParts[] = "USER QUESTION: " . $question;

    // Add instruction.
    $promptParts[] = "Please answer the question based on the congressional sources provided above. Cite specific sources and members when relevant.";

    return implode("\n\n---\n\n", $promptParts);
  }

  /**
   * Manage context window to prevent overflow.
   *
   * @param string $prompt
   *   The full prompt.
   * @param string $model
   *   The model being used.
   *
   * @return string
   *   Potentially truncated prompt.
   */
  protected function manageContextWindow(string $prompt, string $model): string {
    $contextWindow = $this->getModelContextWindow($model);
    $config = $this->getConfig();
    $numPredict = $config->get('ollama.num_predict') ?? 2048;

    // Reserve tokens for response.
    $availableTokens = $contextWindow - $numPredict - 100; // 100 token buffer

    // Estimate current prompt tokens.
    $estimatedTokens = $this->estimateTokens($prompt);

    if ($estimatedTokens <= $availableTokens) {
      return $prompt;
    }

    $this->debugLog('Prompt exceeds context window, truncating', [
      'estimated_tokens' => $estimatedTokens,
      'available_tokens' => $availableTokens,
    ]);

    // Calculate target length.
    $ratio = $availableTokens / $estimatedTokens;
    $targetLength = (int) (strlen($prompt) * $ratio * 0.95); // 5% safety margin

    // Truncate from the middle of context section to preserve question.
    $questionMarker = "USER QUESTION:";
    $questionPos = strrpos($prompt, $questionMarker);

    if ($questionPos !== FALSE) {
      $contextPart = substr($prompt, 0, $questionPos);
      $questionPart = substr($prompt, $questionPos);

      $contextTargetLength = $targetLength - strlen($questionPart);
      if ($contextTargetLength > 0) {
        $contextPart = substr($contextPart, 0, $contextTargetLength);
        $contextPart .= "\n\n[Context truncated due to length...]\n\n";
        return $contextPart . $questionPart;
      }
    }

    // Fallback: simple truncation.
    return substr($prompt, 0, $targetLength) . "\n\n[Truncated...]\n\n" . $questionMarker . " " . substr($prompt, -500);
  }

  /**
   * Get context window size for a model.
   *
   * @param string $model
   *   The model name.
   *
   * @return int
   *   Context window size in tokens.
   */
  protected function getModelContextWindow(string $model): int {
    // Check for exact match first.
    if (isset(self::$modelContextWindows[$model])) {
      return self::$modelContextWindows[$model];
    }

    // Check for partial match (model family).
    $modelBase = preg_replace('/[:\-].*$/', '', $model);
    if (isset(self::$modelContextWindows[$modelBase])) {
      return self::$modelContextWindows[$modelBase];
    }

    // Try fetching from Ollama API.
    $modelInfo = $this->getModelInfo($model);
    if (!empty($modelInfo['context_length'])) {
      return (int) $modelInfo['context_length'];
    }

    return self::DEFAULT_CONTEXT_WINDOW;
  }

  /**
   * Estimate token count for text.
   *
   * @param string $text
   *   The text to estimate.
   *
   * @return int
   *   Estimated token count.
   */
  protected function estimateTokens(string $text): int {
    // Conservative estimate: ~4 characters per token on average.
    return (int) (strlen($text) * self::TOKENS_PER_CHAR);
  }

  /**
   * Validate that a model is available.
   *
   * @param string $model
   *   The model name to validate.
   *
   * @return string
   *   The validated model name (may be fallback).
   */
  protected function validateModel(string $model): string {
    // Check in-memory cache.
    if (in_array($model, $this->validatedModels)) {
      return $model;
    }

    // Check persistent cache.
    $cached = $this->cache->get(self::CACHE_KEY_MODELS);
    if ($cached && is_object($cached) && property_exists($cached, 'data')) {
      $availableModels = $cached->data;
      if (in_array($model, $availableModels)) {
        $this->validatedModels[] = $model;
        return $model;
      }
    }

    // Fetch from API.
    $availableModels = $this->getAvailableModels();
    $this->cache->set(self::CACHE_KEY_MODELS, $availableModels, time() + 3600);

    if (in_array($model, $availableModels)) {
      $this->validatedModels[] = $model;
      return $model;
    }

    // Try fallback model.
    $config = $this->getConfig();
    $fallbackModel = $config->get('ollama.fallback_model');

    if ($fallbackModel && in_array($fallbackModel, $availableModels)) {
      $this->logger->warning('Model @model not available, using fallback @fallback', [
        '@model' => $model,
        '@fallback' => $fallbackModel,
      ]);
      $this->validatedModels[] = $fallbackModel;
      return $fallbackModel;
    }

    // Use first available model.
    if (!empty($availableModels)) {
      $firstModel = $availableModels[0];
      $this->logger->warning('Model @model not available, using first available: @first', [
        '@model' => $model,
        '@first' => $firstModel,
      ]);
      return $firstModel;
    }

    throw new \Exception('No models available on Ollama server');
  }

  /**
   * Get information about a specific model.
   *
   * @param string $model
   *   The model name.
   *
   * @return array
   *   Model information or empty array if not found.
   */
  protected function getModelInfo(string $model): array {
    try {
      $ollamaEndpoint = $this->sshTunnel->getOllamaEndpoint();
      $url = rtrim($ollamaEndpoint, '/') . '/api/show';

      $payload = json_encode(['name' => $model]);

      $response = $this->sshTunnel->makeHttpRequest(
        'POST',
        $url,
        ['Content-Type' => 'application/json'],
        $payload,
        10
      );

      if ($response['status'] === 200) {
        $data = json_decode($response['body'], TRUE);
        return $data ?? [];
      }
    }
    catch (\Exception $e) {
      $this->debugLog('Failed to get model info', ['model' => $model, 'error' => $e->getMessage()]);
    }

    return [];
  }

  /**
   * Build cache key for response caching.
   *
   * @param string $question
   *   The question.
   * @param string|null $memberFilter
   *   Optional member filter.
   * @param string $model
   *   The model name.
   *
   * @return string
   *   Cache key.
   */
  protected function buildResponseCacheKey(
    string $question,
    ?string $memberFilter,
    string $model
  ): string {
    $components = [
      'q' => $question,
      'm' => $memberFilter ?? '',
      'model' => $model,
    ];

    return self::CACHE_KEY_RESPONSE_PREFIX . md5(json_encode($components));
  }

  /**
   * Get user-scoped state key for conversations.
   *
   * Scopes conversation storage per user to prevent cross-user leakage.
   *
   * @return string
   *   The user-scoped state key.
   */
  protected function getUserConversationsKey(): string {
    $userId = $this->currentUser->id();
    return self::STATE_KEY_CONVERSATIONS . ':user:' . $userId;
  }

  /**
   * Get conversation history.
   *
   * Conversation history is scoped per user to prevent cross-user leakage.
   *
   * @param string $conversationId
   *   The conversation ID.
   * @param int $maxTurns
   *   Maximum number of turns to retrieve.
   *
   * @return array
   *   Array of conversation turns.
   */
  protected function getConversationHistory(string $conversationId, int $maxTurns = 5): array {
    $stateKey = $this->getUserConversationsKey();
    $conversations = $this->state->get($stateKey, []);

    if (!isset($conversations[$conversationId])) {
      return [];
    }

    $history = $conversations[$conversationId]['turns'] ?? [];

    // Return only the last N turns.
    if (count($history) > $maxTurns) {
      return array_slice($history, -$maxTurns);
    }

    return $history;
  }

  /**
   * Add a conversation turn.
   *
   * Conversation history is scoped per user to prevent cross-user leakage.
   *
   * @param string $conversationId
   *   The conversation ID.
   * @param string $question
   *   The user's question.
   * @param string $answer
   *   The assistant's answer.
   */
  protected function addConversationTurn(
    string $conversationId,
    string $question,
    string $answer
  ): void {
    $stateKey = $this->getUserConversationsKey();
    $conversations = $this->state->get($stateKey, []);

    if (!isset($conversations[$conversationId])) {
      $conversations[$conversationId] = [
        'created' => time(),
        'turns' => [],
      ];
    }

    $conversations[$conversationId]['updated'] = time();
    $conversations[$conversationId]['turns'][] = [
      'question' => $question,
      'answer' => $answer,
      'timestamp' => time(),
    ];

    // Limit total turns stored per conversation.
    $maxStoredTurns = $this->getConfig()->get('query.max_stored_turns') ?? 20;
    if (count($conversations[$conversationId]['turns']) > $maxStoredTurns) {
      $conversations[$conversationId]['turns'] = array_slice(
        $conversations[$conversationId]['turns'],
        -$maxStoredTurns
      );
    }

    $this->state->set($stateKey, $conversations);
  }

  /**
   * Clear conversation history for current user.
   *
   * Conversation history is scoped per user.
   *
   * @param string|null $conversationId
   *   Optional specific conversation to clear. If NULL, clears all for current user.
   */
  public function clearConversationHistory(?string $conversationId = NULL): void {
    $stateKey = $this->getUserConversationsKey();

    if ($conversationId === NULL) {
      $this->state->delete($stateKey);
      return;
    }

    $conversations = $this->state->get($stateKey, []);
    unset($conversations[$conversationId]);
    $this->state->set($stateKey, $conversations);
  }

  /**
   * Clean up old conversations for current user.
   *
   * Conversation history is scoped per user.
   *
   * @param int|null $maxAgeHours
   *   Maximum age in hours. NULL uses config value.
   *
   * @return int
   *   Number of conversations cleaned up.
   */
  public function cleanupOldConversations(?int $maxAgeHours = NULL): int {
    $maxAgeHours = $maxAgeHours ?? $this->getConfig()->get('query.session_timeout_hours') ?? 24;
    $cutoff = time() - ($maxAgeHours * 3600);

    $stateKey = $this->getUserConversationsKey();
    $conversations = $this->state->get($stateKey, []);
    $originalCount = count($conversations);

    $conversations = array_filter($conversations, function ($conv) use ($cutoff) {
      $updated = $conv['updated'] ?? $conv['created'] ?? 0;
      return $updated > $cutoff;
    });

    $this->state->set($stateKey, $conversations);

    $cleanedCount = $originalCount - count($conversations);
    if ($cleanedCount > 0) {
      $this->logger->info('Cleaned up @count old conversations', ['@count' => $cleanedCount]);
    }

    return $cleanedCount;
  }

  /**
   * Track a cache key for later targeted invalidation.
   *
   * @param string $cacheKey
   *   The cache key to track.
   */
  protected function trackCacheKey(string $cacheKey): void {
    $trackedKeys = $this->state->get(self::STATE_KEY_RESPONSE_CACHE_KEYS, []);

    // Limit tracked keys to prevent unbounded growth.
    if (count($trackedKeys) > 1000) {
      // Remove oldest half when limit reached.
      $trackedKeys = array_slice($trackedKeys, 500, NULL, TRUE);
    }

    $trackedKeys[$cacheKey] = time();
    $this->state->set(self::STATE_KEY_RESPONSE_CACHE_KEYS, $trackedKeys);
  }

  /**
   * Get all tracked cache keys.
   *
   * @return array
   *   Array of cache keys with timestamps.
   */
  protected function getTrackedCacheKeys(): array {
    return $this->state->get(self::STATE_KEY_RESPONSE_CACHE_KEYS, []);
  }

  /**
   * Update token usage statistics.
   *
   * @param array $tokenUsage
   *   Token usage from a single request.
   */
  protected function updateTokenUsage(array $tokenUsage): void {
    $this->tokenUsage['prompt_tokens'] += $tokenUsage['prompt_tokens'] ?? 0;
    $this->tokenUsage['completion_tokens'] += $tokenUsage['completion_tokens'] ?? 0;
    $this->tokenUsage['total_tokens'] = $this->tokenUsage['prompt_tokens'] + $this->tokenUsage['completion_tokens'];
    $this->tokenUsage['requests']++;

    // Update average tokens per second.
    if (!empty($tokenUsage['tokens_per_second'])) {
      $prevAvg = $this->tokenUsage['tokens_per_second'];
      $requests = $this->tokenUsage['requests'];
      $this->tokenUsage['tokens_per_second'] = (($prevAvg * ($requests - 1)) + $tokenUsage['tokens_per_second']) / $requests;
    }
  }

  /**
   * Get current session token usage statistics.
   *
   * @return array
   *   Token usage statistics.
   */
  public function getTokenUsage(): array {
    return $this->tokenUsage;
  }

  /**
   * Reset token usage statistics.
   */
  public function resetTokenUsage(): void {
    $this->tokenUsage = [
      'prompt_tokens' => 0,
      'completion_tokens' => 0,
      'total_tokens' => 0,
      'tokens_per_second' => 0.0,
      'requests' => 0,
    ];
  }

  /**
   * Generate a unique conversation ID.
   *
   * @return string
   *   UUID v4 string.
   */
  protected function generateConversationId(): string {
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
   * Check Ollama connection health with enhanced metrics.
   *
   * @return array
   *   Health status array with extended details.
   */
  public function checkHealth(): array {
    $startTime = microtime(TRUE);

    try {
      $ollamaEndpoint = $this->sshTunnel->getOllamaEndpoint();
      $url = rtrim($ollamaEndpoint, '/') . '/api/tags';

      $response = $this->sshTunnel->makeHttpRequest('GET', $url, [], NULL, 10);

      $latencyMs = (int) ((microtime(TRUE) - $startTime) * 1000);

      if ($response['status'] !== 200) {
        return [
          'status' => 'error',
          'message' => 'Ollama returned status ' . $response['status'],
          'models' => [],
          'details' => [
            'latency_ms' => $latencyMs,
          ],
        ];
      }

      $data = json_decode($response['body'], TRUE);
      $models = [];
      $modelDetails = [];

      if (isset($data['models'])) {
        foreach ($data['models'] as $model) {
          $name = $model['name'] ?? 'unknown';
          $models[] = $name;
          $modelDetails[$name] = [
            'size' => $model['size'] ?? 0,
            'modified_at' => $model['modified_at'] ?? NULL,
            'digest' => $model['digest'] ?? NULL,
          ];
        }
      }

      // Check if configured model is available.
      $configuredModel = $this->getConfig()->get('ollama.model') ?? 'qwen3-coder-roo:latest';
      $modelAvailable = in_array($configuredModel, $models);

      // Check for running models.
      $runningModels = $this->getRunningModels();

      return [
        'status' => $modelAvailable ? 'ok' : 'warning',
        'message' => $modelAvailable ? 'Ollama connected' : 'Configured model not available',
        'models' => $models,
        'details' => [
          'model_count' => count($models),
          'configured_model' => $configuredModel,
          'model_available' => $modelAvailable,
          'running_models' => $runningModels,
          'latency_ms' => $latencyMs,
          'session_stats' => $this->tokenUsage,
        ],
      ];
    }
    catch (\Exception $e) {
      return [
        'status' => 'error',
        'message' => $e->getMessage(),
        'models' => [],
        'details' => [
          'latency_ms' => (int) ((microtime(TRUE) - $startTime) * 1000),
        ],
      ];
    }
  }

  /**
   * Get currently running models.
   *
   * @return array
   *   List of running model names.
   */
  protected function getRunningModels(): array {
    try {
      $ollamaEndpoint = $this->sshTunnel->getOllamaEndpoint();
      $url = rtrim($ollamaEndpoint, '/') . '/api/ps';

      $response = $this->sshTunnel->makeHttpRequest('GET', $url, [], NULL, 5);

      if ($response['status'] === 200) {
        $data = json_decode($response['body'], TRUE);
        $running = [];

        if (isset($data['models'])) {
          foreach ($data['models'] as $model) {
            $running[] = $model['name'] ?? 'unknown';
          }
        }

        return $running;
      }
    }
    catch (\Exception $e) {
      $this->debugLog('Failed to get running models', ['error' => $e->getMessage()]);
    }

    return [];
  }

  /**
   * Get available models from Ollama.
   *
   * @return array
   *   List of available model names.
   */
  public function getAvailableModels(): array {
    $health = $this->checkHealth();
    return $health['models'] ?? [];
  }

  /**
   * Clear response cache.
   *
   * Uses targeted deletion of tracked cache keys instead of clearing
   * the entire cache bin, which would affect unrelated site caches.
   *
   * @param string|null $question
   *   Optional specific question to clear. If NULL, clears all tracked response cache.
   */
  public function clearResponseCache(?string $question = NULL): void {
    if ($question === NULL) {
      // Delete all tracked response cache keys individually.
      $trackedKeys = $this->getTrackedCacheKeys();
      $deletedCount = 0;

      foreach (array_keys($trackedKeys) as $cacheKey) {
        $this->cache->delete($cacheKey);
        $deletedCount++;
      }

      // Also delete the model validation cache.
      $this->cache->delete(self::CACHE_KEY_MODELS);

      // Clear the tracked keys list.
      $this->state->delete(self::STATE_KEY_RESPONSE_CACHE_KEYS);

      $this->logger->info('Cleared @count Ollama response cache entries', [
        '@count' => $deletedCount,
      ]);
      return;
    }

    // Clear specific response for all member filter combinations.
    $model = $this->getConfig()->get('ollama.model') ?? 'qwen3-coder-roo:latest';
    $cacheKey = $this->buildResponseCacheKey($question, NULL, $model);
    $this->cache->delete($cacheKey);

    // Remove from tracked keys.
    $trackedKeys = $this->getTrackedCacheKeys();
    unset($trackedKeys[$cacheKey]);
    $this->state->set(self::STATE_KEY_RESPONSE_CACHE_KEYS, $trackedKeys);
  }

  /**
   * Log debug message if debug mode is enabled.
   *
   * @param string $message
   *   The debug message.
   * @param array $context
   *   Additional context.
   */
  protected function debugLog(string $message, array $context = []): void {
    if ($this->debugMode) {
      $this->logger->debug('[OllamaLLM] ' . $message, $context);
    }
  }

  /**
   * Enable or disable debug mode.
   *
   * @param bool $enabled
   *   Whether to enable debug mode.
   */
  public function setDebugMode(bool $enabled): void {
    $this->debugMode = $enabled;
  }

  /**
   * Check if debug mode is enabled.
   *
   * @return bool
   *   TRUE if debug mode is enabled.
   */
  public function isDebugMode(): bool {
    return $this->debugMode;
  }

}
