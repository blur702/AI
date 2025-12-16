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
use Drupal\Core\Cache\CacheableMetadata;
use Drupal\Core\Session\AccountProxyInterface;
use Drupal\rest\ModifiedResourceResponse;
use Drupal\rest\Plugin\ResourceBase;
use Drupal\rest\ResourceResponse;
use Psr\Log\LoggerInterface;
use Symfony\Component\DependencyInjection\ContainerInterface;
use Symfony\Component\HttpFoundation\Request;
use Symfony\Component\HttpKernel\Exception\AccessDeniedHttpException;
use Symfony\Component\HttpKernel\Exception\NotFoundHttpException;

/**
 * REST resource for congressional chat.
 *
 * @RestResource(
 *   id = "congressional_chat",
 *   label = @Translation("Congressional Chat"),
 *   uri_paths = {
 *     "canonical" = "/api/congressional/chat/{conversation_id}",
 *     "create" = "/api/congressional/chat"
 *   }
 * )
 */
class CongressionalChatResource extends ResourceBase {

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
   * Constructs a CongressionalChatResource object.
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
   * Responds to GET requests - get conversation history.
   *
   * @param \Symfony\Component\HttpFoundation\Request $request
   *   The request object.
   * @param string $conversation_id
   *   The conversation ID.
   *
   * @return \Drupal\rest\ResourceResponse
   *   The response.
   */
  public function get(Request $request, string $conversation_id) {
    $startTime = microtime(TRUE);
    $statusCode = 200;
    $errorMessage = NULL;

    $apiKey = $request->attributes->get('_congressional_api_key');
    $apiKeyId = $apiKey instanceof ApiKey ? $apiKey->getId() : NULL;
    $identifier = $apiKeyId ? 'key:' . $apiKeyId : 'ip:' . $request->getClientIp();

    try {
      // Check rate limit.
      $limitInfo = $this->rateLimitService->checkLimit($identifier, 'chat_read', $apiKey);

      if (!$limitInfo['allowed']) {
        $retryAfter = $limitInfo['reset'] - time();
        throw new RateLimitExceededException($retryAfter);
      }

      $this->rateLimitService->registerRequest($identifier, 'chat_read');

      $metadata = $this->conversationManager->getConversationMetadata($conversation_id);

      if (!$metadata) {
        throw new NotFoundHttpException('Conversation not found');
      }

      // Check ownership.
      if ($this->currentUser->isAuthenticated() && $metadata['uid'] != $this->currentUser->id()) {
        // Allow if user has admin permission.
        if (!$this->currentUser->hasPermission('view congressional query logs')) {
          throw new AccessDeniedHttpException('Access denied to this conversation');
        }
      }

      $messages = $this->conversationManager->getConversation($conversation_id);

      $formattedMessages = array_map(function ($message) {
        return [
          'role' => $message['role'],
          'content' => $message['content'],
          'sources' => $this->formatSources($message['sources'] ?? []),
          'timestamp' => $message['timestamp'],
        ];
      }, $messages);

      $responseData = [
        'conversation_id' => $conversation_id,
        'title' => $metadata['title'] ?? '',
        'member_filter' => $metadata['member_filter'],
        'message_count' => count($formattedMessages),
        'created' => $metadata['created'],
        'updated' => $metadata['updated'],
        'messages' => $formattedMessages,
      ];

      $response = new ResourceResponse($this->responseFormatter->success($responseData));

      $response->addCacheableDependency(CacheableMetadata::createFromRenderArray([
        '#cache' => ['max-age' => 0],
      ]));

      // Add rate limit headers.
      foreach ($this->rateLimitService->getHeaders($limitInfo) as $name => $value) {
        $response->headers->set($name, $value);
      }

      return $response;
    }
    catch (RateLimitExceededException $e) {
      $statusCode = 429;
      $errorMessage = $e->getMessage();

      $response = new ResourceResponse($this->responseFormatter->rateLimitError($e->getRetryAfter()), 429);
      $response->headers->set('Retry-After', $e->getRetryAfter());
      return $response;
    }
    catch (NotFoundHttpException $e) {
      $statusCode = 404;
      $errorMessage = $e->getMessage();

      return new ResourceResponse(
        $this->responseFormatter->notFoundError('conversation', $conversation_id),
        404
      );
    }
    catch (AccessDeniedHttpException $e) {
      $statusCode = 403;
      $errorMessage = $e->getMessage();

      return new ResourceResponse(
        $this->responseFormatter->error('ACCESS_DENIED', $e->getMessage()),
        403
      );
    }
    catch (\Exception $e) {
      $statusCode = 500;
      $errorMessage = $e->getMessage();

      $this->logger->error('Chat API GET failed: @message', [
        '@message' => $e->getMessage(),
      ]);

      return new ResourceResponse(
        $this->responseFormatter->serverError('Failed to retrieve conversation'),
        500
      );
    }
    finally {
      $responseTime = (int) ((microtime(TRUE) - $startTime) * 1000);
      $this->requestLogger->logRequest([
        'api_key_id' => $apiKeyId,
        'endpoint' => '/api/congressional/chat/' . $conversation_id,
        'method' => 'GET',
        'status_code' => $statusCode,
        'response_time_ms' => $responseTime,
        'ip_address' => $request->getClientIp(),
        'user_agent' => $request->headers->get('User-Agent'),
        'error_message' => $errorMessage,
      ]);
    }
  }

  /**
   * Responds to POST requests - send a message.
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

    $apiKey = $request->attributes->get('_congressional_api_key');
    $apiKeyId = $apiKey instanceof ApiKey ? $apiKey->getId() : NULL;
    $identifier = $apiKeyId ? 'key:' . $apiKeyId : 'ip:' . $request->getClientIp();

    try {
      // Check rate limit.
      $limitInfo = $this->rateLimitService->checkLimit($identifier, 'chat', $apiKey);

      if (!$limitInfo['allowed']) {
        $retryAfter = $limitInfo['reset'] - time();
        throw new RateLimitExceededException($retryAfter);
      }

      $this->rateLimitService->registerRequest($identifier, 'chat');

      // Parse and validate request.
      $data = $this->parseAndValidateRequest($request);

      $message = $data['message'];
      $conversationId = $data['conversation_id'];
      $memberFilter = $data['member_filter'];

      // Create or verify conversation.
      if (empty($conversationId)) {
        $conversationId = $this->conversationManager->createConversation($memberFilter);
      }
      else {
        $metadata = $this->conversationManager->getConversationMetadata($conversationId);
        if (!$metadata) {
          throw new NotFoundHttpException('Conversation not found');
        }
      }

      // Store user message.
      $this->conversationManager->addMessage($conversationId, 'user', $message);

      // Generate answer.
      $result = $this->ollamaService->answerQuestion(
        $message,
        $memberFilter,
        NULL,
        $conversationId
      );

      // Store assistant message.
      $this->conversationManager->addMessage(
        $conversationId,
        'assistant',
        $result['answer'],
        $result['sources'],
        [
          'model' => $result['model'],
          'member_filter' => $memberFilter,
          'response_time_ms' => $result['response_time_ms'],
        ]
      );

      $responseData = [
        'conversation_id' => $conversationId,
        'answer' => $result['answer'],
        'sources' => $this->formatSources($result['sources']),
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
    catch (NotFoundHttpException $e) {
      $statusCode = 404;
      $errorMessage = $e->getMessage();

      return new ModifiedResourceResponse(
        $this->responseFormatter->notFoundError('conversation'),
        404
      );
    }
    catch (\Exception $e) {
      $statusCode = 500;
      $errorMessage = $e->getMessage();

      $this->logger->error('Chat API POST failed: @message', [
        '@message' => $e->getMessage(),
      ]);

      return new ModifiedResourceResponse(
        $this->responseFormatter->serverError('Failed to process message'),
        500
      );
    }
    finally {
      $responseTime = (int) ((microtime(TRUE) - $startTime) * 1000);
      $this->requestLogger->logRequest([
        'api_key_id' => $apiKeyId,
        'endpoint' => '/api/congressional/chat',
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

    // Validate message.
    if (empty($data['message'])) {
      $errors['message'] = 'Message is required';
    }
    else {
      $message = trim($data['message']);
      if (strlen($message) < 5) {
        $errors['message'] = 'Message must be at least 5 characters';
      }
      elseif (strlen($message) > 2000) {
        $errors['message'] = 'Message must be less than 2000 characters';
      }
    }

    // Validate conversation_id format if provided.
    if (!empty($data['conversation_id'])) {
      if (!preg_match('/^[a-f0-9-]{36}$/i', $data['conversation_id'])) {
        $errors['conversation_id'] = 'Invalid conversation ID format';
      }
    }

    if (!empty($errors)) {
      throw new ValidationException($errors);
    }

    return [
      'message' => trim($data['message']),
      'conversation_id' => $data['conversation_id'] ?? NULL,
      'member_filter' => !empty($data['member_filter']) ? trim($data['member_filter']) : NULL,
    ];
  }

  /**
   * Format sources for API response.
   *
   * @param array $sources
   *   Raw sources array.
   *
   * @return array
   *   Formatted sources.
   */
  protected function formatSources(array $sources): array {
    return array_map(function ($source) {
      return [
        'member_name' => $source['member_name'] ?? 'Unknown',
        'title' => $source['title'] ?? 'Untitled',
        'content' => substr($source['content_text'] ?? '', 0, 200),
        'url' => $source['url'] ?? '',
        'party' => $source['party'] ?? '',
        'state' => $source['state'] ?? '',
        'topic' => $source['topic'] ?? '',
      ];
    }, $sources);
  }

}
