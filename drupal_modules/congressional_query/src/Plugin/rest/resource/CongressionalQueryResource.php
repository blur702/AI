<?php

namespace Drupal\congressional_query\Plugin\rest\resource;

use Drupal\congressional_query\Entity\ApiKey;
use Drupal\congressional_query\Exception\RateLimitExceededException;
use Drupal\congressional_query\Exception\ValidationException;
use Drupal\congressional_query\Service\ApiRequestLogger;
use Drupal\congressional_query\Service\ApiResponseFormatter;
use Drupal\congressional_query\Service\ConversationManager;
use Drupal\congressional_query\Service\OllamaLLMService;
use Drupal\congressional_query\Service\RateLimitService;
use Drupal\Core\Session\AccountProxyInterface;
use Drupal\rest\ModifiedResourceResponse;
use Drupal\rest\Plugin\ResourceBase;
use Psr\Log\LoggerInterface;
use Symfony\Component\DependencyInjection\ContainerInterface;
use Symfony\Component\HttpFoundation\Request;
use Symfony\Component\HttpKernel\Exception\AccessDeniedHttpException;
use Symfony\Component\HttpKernel\Exception\HttpException;
use Symfony\Component\HttpKernel\Exception\TooManyRequestsHttpException;

/**
 * REST resource for congressional queries.
 *
 * @RestResource(
 *   id = "congressional_query",
 *   label = @Translation("Congressional Query"),
 *   uri_paths = {
 *     "create" = "/api/congressional/query"
 *   }
 * )
 */
class CongressionalQueryResource extends ResourceBase {

  /**
   * The Ollama LLM service.
   *
   * @var \Drupal\congressional_query\Service\OllamaLLMService
   */
  protected $ollamaService;

  /**
   * The conversation manager.
   *
   * @var \Drupal\congressional_query\Service\ConversationManager
   */
  protected $conversationManager;

  /**
   * The current user.
   *
   * @var \Drupal\Core\Session\AccountProxyInterface
   */
  protected $currentUser;

  /**
   * The rate limit service.
   *
   * @var \Drupal\congressional_query\Service\RateLimitService
   */
  protected $rateLimitService;

  /**
   * The API response formatter.
   *
   * @var \Drupal\congressional_query\Service\ApiResponseFormatter
   */
  protected $responseFormatter;

  /**
   * The API request logger.
   *
   * @var \Drupal\congressional_query\Service\ApiRequestLogger
   */
  protected $requestLogger;

  /**
   * Constructs a CongressionalQueryResource object.
   *
   * @param array $configuration
   *   A configuration array containing information about the plugin instance.
   * @param string $plugin_id
   *   The plugin_id for the plugin instance.
   * @param mixed $plugin_definition
   *   The plugin implementation definition.
   * @param array $serializer_formats
   *   The available serialization formats.
   * @param \Psr\Log\LoggerInterface $logger
   *   A logger instance.
   * @param \Drupal\congressional_query\Service\OllamaLLMService $ollama_service
   *   The Ollama LLM service.
   * @param \Drupal\congressional_query\Service\ConversationManager $conversation_manager
   *   The conversation manager.
   * @param \Drupal\Core\Session\AccountProxyInterface $current_user
   *   The current user.
   * @param \Drupal\congressional_query\Service\RateLimitService $rate_limit_service
   *   The rate limit service.
   * @param \Drupal\congressional_query\Service\ApiResponseFormatter $response_formatter
   *   The API response formatter.
   * @param \Drupal\congressional_query\Service\ApiRequestLogger $request_logger
   *   The API request logger.
   */
  public function __construct(
    array $configuration,
    $plugin_id,
    $plugin_definition,
    array $serializer_formats,
    LoggerInterface $logger,
    OllamaLLMService $ollama_service,
    ConversationManager $conversation_manager,
    AccountProxyInterface $current_user,
    RateLimitService $rate_limit_service,
    ApiResponseFormatter $response_formatter,
    ApiRequestLogger $request_logger
  ) {
    parent::__construct($configuration, $plugin_id, $plugin_definition, $serializer_formats, $logger);
    $this->ollamaService = $ollama_service;
    $this->conversationManager = $conversation_manager;
    $this->currentUser = $current_user;
    $this->rateLimitService = $rate_limit_service;
    $this->responseFormatter = $response_formatter;
    $this->requestLogger = $request_logger;
  }

  /**
   * {@inheritdoc}
   */
  public static function create(ContainerInterface $container, array $configuration, $plugin_id, $plugin_definition) {
    return new static(
      $configuration,
      $plugin_id,
      $plugin_definition,
      $container->getParameter('serializer.formats'),
      $container->get('logger.channel.congressional_query'),
      $container->get('congressional_query.ollama_llm'),
      $container->get('congressional_query.conversation_manager'),
      $container->get('current_user'),
      $container->get('congressional_query.rate_limit_service'),
      $container->get('congressional_query.api_response_formatter'),
      $container->get('congressional_query.api_request_logger')
    );
  }

  /**
   * Responds to POST requests.
   *
   * @param \Symfony\Component\HttpFoundation\Request $request
   *   The request object.
   *
   * @return \Drupal\rest\ModifiedResourceResponse
   *   The response.
   */
  public function post(Request $request) {
    $startTime = microtime(TRUE);
    $statusCode = 200;
    $errorMessage = NULL;

    // Get API key from request attributes (set by authentication provider).
    $apiKey = $request->attributes->get('_congressional_api_key');
    $apiKeyId = $apiKey instanceof ApiKey ? $apiKey->getId() : NULL;

    // Determine rate limit identifier.
    $identifier = $apiKeyId ? 'key:' . $apiKeyId : 'ip:' . $request->getClientIp();

    try {
      // Check rate limit.
      $limitInfo = $this->rateLimitService->checkLimit($identifier, 'query', $apiKey);

      if (!$limitInfo['allowed']) {
        $retryAfter = $limitInfo['reset'] - time();
        throw new RateLimitExceededException($retryAfter);
      }

      // Register the request for rate limiting.
      $this->rateLimitService->registerRequest($identifier, 'query');

      // Parse and validate request.
      $data = $this->parseAndValidateRequest($request);

      $question = $data['question'];
      $memberFilter = $data['member_filter'];
      $partyFilter = $data['party_filter'];
      $stateFilter = $data['state_filter'];
      $numSources = $data['num_sources'];

      // Generate answer.
      $result = $this->ollamaService->answerQuestion(
        $question,
        $memberFilter,
        $numSources,
        NULL,
        $partyFilter,
        $stateFilter
      );

      // Log the query.
      $queryId = $this->conversationManager->logQuery(
        $question,
        $result['answer'],
        [
          'model' => $result['model'],
          'member_filter' => $memberFilter,
          'party_filter' => $partyFilter,
          'state_filter' => $stateFilter,
          'num_sources' => $result['num_sources'],
          'sources' => $result['sources'],
          'response_time_ms' => $result['response_time_ms'],
          'conversation_id' => $result['conversation_id'],
        ]
      );

      // Format sources for response.
      $sources = $this->formatSources($result['sources']);

      $responseData = [
        'query_id' => $queryId,
        'answer' => $result['answer'],
        'sources' => $sources,
        'model' => $result['model'],
        'response_time_ms' => $result['response_time_ms'],
      ];

      $response = new ModifiedResourceResponse(
        $this->responseFormatter->success($responseData),
        200
      );

      // Add rate limit headers.
      foreach ($this->rateLimitService->getHeaders($limitInfo) as $name => $value) {
        $response->headers->set($name, $value);
      }

      return $response;
    }
    catch (RateLimitExceededException $e) {
      $statusCode = 429;
      $errorMessage = $e->getMessage();

      $response = new ModifiedResourceResponse(
        $this->responseFormatter->rateLimitError($e->getRetryAfter()),
        429
      );
      $response->headers->set('Retry-After', $e->getRetryAfter());

      return $response;
    }
    catch (ValidationException $e) {
      $statusCode = 400;
      $errorMessage = $e->getMessage();

      return new ModifiedResourceResponse(
        $this->responseFormatter->validationError($e->getFieldErrors()),
        400
      );
    }
    catch (AccessDeniedHttpException $e) {
      $statusCode = 403;
      $errorMessage = $e->getMessage();

      return new ModifiedResourceResponse(
        $this->responseFormatter->error('ACCESS_DENIED', $e->getMessage()),
        403
      );
    }
    catch (\Exception $e) {
      $statusCode = 500;
      $errorMessage = $e->getMessage();

      $this->logger->error('API query failed: @message', [
        '@message' => $e->getMessage(),
      ]);

      return new ModifiedResourceResponse(
        $this->responseFormatter->serverError('Query processing failed'),
        500
      );
    }
    finally {
      // Log the request.
      $responseTime = (int) ((microtime(TRUE) - $startTime) * 1000);
      $this->requestLogger->logRequest([
        'api_key_id' => $apiKeyId,
        'endpoint' => '/api/congressional/query',
        'method' => 'POST',
        'status_code' => $statusCode,
        'response_time_ms' => $responseTime,
        'ip_address' => $request->getClientIp(),
        'user_agent' => $request->headers->get('User-Agent'),
        'request_body_size' => strlen($request->getContent()),
        'error_message' => $errorMessage,
      ]);
    }
  }

  /**
   * Parses and validates the request.
   *
   * @param \Symfony\Component\HttpFoundation\Request $request
   *   The request.
   *
   * @return array
   *   Validated data.
   *
   * @throws \Drupal\congressional_query\Exception\ValidationException
   */
  protected function parseAndValidateRequest(Request $request): array {
    $data = json_decode($request->getContent(), TRUE);
    $errors = [];

    if (json_last_error() !== JSON_ERROR_NONE) {
      throw new ValidationException(['body' => 'Invalid JSON payload']);
    }

    // Validate question.
    if (empty($data['question'])) {
      $errors['question'] = 'Question is required';
    }
    else {
      $question = trim($data['question']);
      if (strlen($question) < 10) {
        $errors['question'] = 'Question must be at least 10 characters';
      }
      elseif (strlen($question) > 2000) {
        $errors['question'] = 'Question must be less than 2000 characters';
      }
    }

    // Validate num_sources.
    $numSources = NULL;
    if (isset($data['num_sources'])) {
      $numSources = (int) $data['num_sources'];
      if ($numSources < 1 || $numSources > 20) {
        $errors['num_sources'] = 'num_sources must be between 1 and 20';
      }
    }

    // Validate party_filter.
    $partyFilter = NULL;
    if (!empty($data['party_filter'])) {
      $partyFilter = trim($data['party_filter']);
      $validParties = ['Republican', 'Democrat', 'Independent'];
      if (!in_array($partyFilter, $validParties, TRUE)) {
        $errors['party_filter'] = 'party_filter must be Republican, Democrat, or Independent';
      }
    }

    // Validate state_filter.
    $stateFilter = NULL;
    if (!empty($data['state_filter'])) {
      $stateFilter = strtoupper(trim($data['state_filter']));
      if (!preg_match('/^[A-Z]{2}$/', $stateFilter)) {
        $errors['state_filter'] = 'state_filter must be a 2-letter state code';
      }
    }

    if (!empty($errors)) {
      throw new ValidationException($errors);
    }

    return [
      'question' => trim($data['question']),
      'member_filter' => !empty($data['member_filter']) ? trim($data['member_filter']) : NULL,
      'party_filter' => $partyFilter,
      'state_filter' => $stateFilter,
      'num_sources' => $numSources,
    ];
  }

  /**
   * Formats sources for the API response.
   *
   * @param array $sources
   *   Raw sources.
   *
   * @return array
   *   Formatted sources.
   */
  protected function formatSources(array $sources): array {
    return array_map(function ($source) {
      return [
        'member_name' => $source['member_name'] ?? 'Unknown',
        'title' => $source['title'] ?? 'Untitled',
        'content' => substr($source['content_text'] ?? '', 0, 300),
        'url' => $source['url'] ?? '',
        'party' => $source['party'] ?? '',
        'state' => $source['state'] ?? '',
        'topic' => $source['topic'] ?? '',
        'distance' => $source['distance'] ?? NULL,
      ];
    }, $sources);
  }

}
