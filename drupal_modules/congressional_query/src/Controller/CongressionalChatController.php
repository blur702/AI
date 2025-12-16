<?php

namespace Drupal\congressional_query\Controller;

use Drupal\congressional_query\Service\ConversationManager;
use Drupal\congressional_query\Service\OllamaLLMService;
use Drupal\Core\Controller\ControllerBase;
use Drupal\Core\Flood\FloodInterface;
use Symfony\Component\DependencyInjection\ContainerInterface;
use Symfony\Component\HttpFoundation\JsonResponse;
use Symfony\Component\HttpFoundation\Request;
use Symfony\Component\HttpFoundation\Response;
use Symfony\Component\HttpFoundation\StreamedResponse;

/**
 * Controller for chat interface.
 */
class CongressionalChatController extends ControllerBase {

  /**
   * Rate limit: messages per minute.
   */
  const RATE_LIMIT_MESSAGES = 10;

  /**
   * Rate limit window in seconds.
   */
  const RATE_LIMIT_WINDOW = 60;

  /**
   * Maximum message length.
   */
  const MAX_MESSAGE_LENGTH = 2000;

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
   * The flood service for rate limiting.
   *
   * @var \Drupal\Core\Flood\FloodInterface
   */
  protected $flood;

  /**
   * Constructs the controller.
   *
   * @param \Drupal\congressional_query\Service\OllamaLLMService $ollama_service
   *   The Ollama LLM service.
   * @param \Drupal\congressional_query\Service\ConversationManager $conversation_manager
   *   The conversation manager.
   * @param \Drupal\Core\Flood\FloodInterface $flood
   *   The flood service.
   */
  public function __construct(
    OllamaLLMService $ollama_service,
    ConversationManager $conversation_manager,
    FloodInterface $flood
  ) {
    $this->ollamaService = $ollama_service;
    $this->conversationManager = $conversation_manager;
    $this->flood = $flood;
  }

  /**
   * {@inheritdoc}
   */
  public static function create(ContainerInterface $container) {
    return new static(
      $container->get('congressional_query.ollama_llm'),
      $container->get('congressional_query.conversation_manager'),
      $container->get('flood')
    );
  }

  /**
   * Render the chat page.
   *
   * @param \Symfony\Component\HttpFoundation\Request $request
   *   The request object.
   *
   * @return array
   *   Render array.
   */
  public function chatPage(Request $request): array {
    // Get or create conversation ID.
    $conversationId = $request->query->get('conversation_id');
    $memberFilter = $request->query->get('member_filter');

    $messages = [];
    if ($conversationId) {
      $messages = $this->conversationManager->getConversation($conversationId);
    }
    else {
      $conversationId = $this->conversationManager->createConversation($memberFilter);
    }

    $exampleQuestions = congressional_query_get_example_questions();

    return [
      '#theme' => 'congressional_query_chat',
      '#conversation_id' => $conversationId,
      '#messages' => $messages,
      '#member_filter' => $memberFilter,
      '#example_questions' => $exampleQuestions,
      '#attached' => [
        'library' => ['congressional_query/chat'],
        'drupalSettings' => [
          'congressionalQuery' => [
            'conversationId' => $conversationId,
            'memberFilter' => $memberFilter,
            'sendUrl' => '/congressional/chat/send',
            'historyUrl' => '/congressional/chat/history/' . $conversationId,
          ],
        ],
      ],
    ];
  }

  /**
   * Handle chat message submission.
   *
   * @param \Symfony\Component\HttpFoundation\Request $request
   *   The request object.
   *
   * @return \Symfony\Component\HttpFoundation\JsonResponse
   *   JSON response with answer.
   */
  public function sendMessage(Request $request): JsonResponse {
    // Rate limiting check.
    $rateLimitResult = $this->checkRateLimit($request);
    if ($rateLimitResult !== TRUE) {
      return $rateLimitResult;
    }

    $content = json_decode($request->getContent(), TRUE);

    if (json_last_error() !== JSON_ERROR_NONE) {
      return new JsonResponse([
        'error' => 'Invalid JSON',
      ], 400);
    }

    // Validate and sanitize inputs.
    $validationResult = $this->validateMessageInput($content);
    if ($validationResult !== TRUE) {
      return $validationResult;
    }

    $message = $this->sanitizeMessage($content['message']);
    $conversationId = $this->sanitizeConversationId($content['conversation_id'] ?? NULL);
    $memberFilter = $this->sanitizeMemberFilter($content['member_filter'] ?? NULL);

    // Create conversation if needed.
    if (empty($conversationId)) {
      $conversationId = $this->conversationManager->createConversation($memberFilter);
    }
    else {
      // Verify conversation ownership.
      if (!$this->verifyConversationOwnership($conversationId)) {
        return new JsonResponse([
          'error' => 'Access denied to this conversation',
        ], 403);
      }
    }

    // Register rate limit event.
    $this->registerRateLimitEvent($request);

    try {
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

      return new JsonResponse([
        'answer' => $result['answer'],
        'sources' => $this->formatSourcesForJson($result['sources']),
        'conversation_id' => $conversationId,
        'model' => $result['model'],
        'response_time_ms' => $result['response_time_ms'],
      ]);
    }
    catch (\Exception $e) {
      $this->getLogger('congressional_query')->error('Chat error: @message', [
        '@message' => $e->getMessage(),
      ]);

      return new JsonResponse([
        'error' => 'Failed to generate response. Please try again.',
      ], 500);
    }
  }

  /**
   * Handle streaming chat message submission.
   *
   * @param \Symfony\Component\HttpFoundation\Request $request
   *   The request object.
   *
   * @return \Symfony\Component\HttpFoundation\Response
   *   SSE streaming response.
   */
  public function sendMessageStream(Request $request): Response {
    // Rate limiting check.
    $rateLimitResult = $this->checkRateLimit($request);
    if ($rateLimitResult !== TRUE) {
      return $rateLimitResult;
    }

    $content = json_decode($request->getContent(), TRUE);

    if (json_last_error() !== JSON_ERROR_NONE) {
      return new JsonResponse(['error' => 'Invalid JSON'], 400);
    }

    // Validate and sanitize inputs.
    $validationResult = $this->validateMessageInput($content);
    if ($validationResult !== TRUE) {
      return $validationResult;
    }

    $message = $this->sanitizeMessage($content['message']);
    $conversationId = $this->sanitizeConversationId($content['conversation_id'] ?? NULL);
    $memberFilter = $this->sanitizeMemberFilter($content['member_filter'] ?? NULL);

    // Create conversation if needed.
    if (empty($conversationId)) {
      $conversationId = $this->conversationManager->createConversation($memberFilter);
    }
    else {
      if (!$this->verifyConversationOwnership($conversationId)) {
        return new JsonResponse(['error' => 'Access denied'], 403);
      }
    }

    // Register rate limit event.
    $this->registerRateLimitEvent($request);

    // Store user message before streaming.
    $this->conversationManager->addMessage($conversationId, 'user', $message);

    $ollamaService = $this->ollamaService;
    $conversationManager = $this->conversationManager;
    $logger = $this->getLogger('congressional_query');

    $response = new StreamedResponse(function () use (
      $message,
      $memberFilter,
      $conversationId,
      $ollamaService,
      $conversationManager,
      $logger
    ) {
      // Set up SSE headers are already set on response object.
      $fullAnswer = '';

      try {
        // Stream callback receives chunks.
        $callback = function (string $chunk, bool $done) use (&$fullAnswer) {
          $fullAnswer .= $chunk;

          // Send SSE event.
          echo "data: " . json_encode([
            'type' => 'chunk',
            'content' => $chunk,
            'done' => $done,
          ]) . "\n\n";

          // Flush output.
          if (ob_get_level() > 0) {
            ob_flush();
          }
          flush();
        };

        // Generate streaming answer.
        $result = $ollamaService->answerQuestionStream(
          $message,
          $callback,
          $memberFilter,
          NULL,
          $conversationId
        );

        // Store assistant message with full answer.
        $conversationManager->addMessage(
          $conversationId,
          'assistant',
          $fullAnswer,
          $result['sources'],
          [
            'model' => $result['model'],
            'member_filter' => $memberFilter,
            'response_time_ms' => $result['response_time_ms'],
          ]
        );

        // Send final event with metadata.
        echo "data: " . json_encode([
          'type' => 'complete',
          'sources' => array_map(function ($source) {
            return [
              'member_name' => $source['member_name'] ?? 'Unknown',
              'title' => $source['title'] ?? 'Untitled',
              'content' => substr($source['content_text'] ?? '', 0, 200),
              'url' => $source['url'] ?? '',
              'party' => $source['party'] ?? '',
              'state' => $source['state'] ?? '',
              'party_class' => congressional_query_get_party_class($source['party'] ?? ''),
            ];
          }, $result['sources']),
          'model' => $result['model'],
          'conversation_id' => $conversationId,
          'response_time_ms' => $result['response_time_ms'],
        ]) . "\n\n";

        if (ob_get_level() > 0) {
          ob_flush();
        }
        flush();
      }
      catch (\Exception $e) {
        $logger->error('Streaming chat error: @message', [
          '@message' => $e->getMessage(),
        ]);

        echo "data: " . json_encode([
          'type' => 'error',
          'error' => 'Failed to generate response. Please try again.',
        ]) . "\n\n";

        if (ob_get_level() > 0) {
          ob_flush();
        }
        flush();
      }
    });

    // Set SSE headers.
    $response->headers->set('Content-Type', 'text/event-stream');
    $response->headers->set('Cache-Control', 'no-cache');
    $response->headers->set('Connection', 'keep-alive');
    $response->headers->set('X-Accel-Buffering', 'no');

    return $response;
  }

  /**
   * Export conversation in various formats.
   *
   * @param string $conversation_id
   *   The conversation ID.
   * @param string $format
   *   Export format (json, markdown, html).
   *
   * @return \Symfony\Component\HttpFoundation\Response
   *   The export response.
   */
  public function exportConversation(string $conversation_id, string $format = 'json'): Response {
    // Verify ownership.
    if (!$this->verifyConversationOwnership($conversation_id)) {
      return new JsonResponse(['error' => 'Access denied'], 403);
    }

    $messages = $this->conversationManager->getConversation($conversation_id);
    $metadata = $this->conversationManager->getConversationMetadata($conversation_id);

    if (!$metadata) {
      return new JsonResponse(['error' => 'Conversation not found'], 404);
    }

    $exportData = [
      'conversation_id' => $conversation_id,
      'title' => $metadata['title'] ?? 'Congressional Chat',
      'member_filter' => $metadata['member_filter'] ?? NULL,
      'created' => date('Y-m-d H:i:s', $metadata['created']),
      'updated' => date('Y-m-d H:i:s', $metadata['updated']),
      'messages' => array_map(function ($msg) {
        return [
          'role' => $msg['role'],
          'content' => $msg['content'],
          'sources' => $msg['sources'] ?? [],
          'timestamp' => date('Y-m-d H:i:s', $msg['timestamp']),
        ];
      }, $messages),
    ];

    switch ($format) {
      case 'markdown':
        return $this->exportAsMarkdown($exportData);

      case 'html':
        return $this->exportAsHtml($exportData);

      case 'json':
      default:
        return $this->exportAsJson($exportData);
    }
  }

  /**
   * Export as JSON.
   */
  protected function exportAsJson(array $data): Response {
    $response = new JsonResponse($data);
    $response->headers->set('Content-Disposition', 'attachment; filename="conversation-' . $data['conversation_id'] . '.json"');
    return $response;
  }

  /**
   * Export as Markdown.
   */
  protected function exportAsMarkdown(array $data): Response {
    $markdown = "# Congressional Chat - " . ($data['title'] ?: 'Conversation') . "\n\n";
    $markdown .= "**Date:** " . $data['created'] . "\n";

    if ($data['member_filter']) {
      $markdown .= "**Member Filter:** " . $data['member_filter'] . "\n";
    }

    $markdown .= "\n---\n\n";

    foreach ($data['messages'] as $msg) {
      $role = ucfirst($msg['role']);
      $markdown .= "## {$role}\n\n";
      $markdown .= $msg['content'] . "\n\n";

      if (!empty($msg['sources'])) {
        $markdown .= "**Sources:**\n\n";
        foreach ($msg['sources'] as $i => $source) {
          $memberInfo = sprintf(
            "[%s] %s",
            $source['party'] ?? '?',
            $source['member_name'] ?? 'Unknown'
          );
          $markdown .= ($i + 1) . ". {$memberInfo} - " . ($source['title'] ?? 'Untitled');
          if (!empty($source['url'])) {
            $markdown .= "\n   " . $source['url'];
          }
          $markdown .= "\n";
        }
        $markdown .= "\n";
      }

      $markdown .= "---\n\n";
    }

    $markdown .= "\n\n*Exported from Congressional Query on " . date('Y-m-d H:i:s') . "*\n";

    $response = new Response($markdown);
    $response->headers->set('Content-Type', 'text/markdown; charset=utf-8');
    $response->headers->set('Content-Disposition', 'attachment; filename="conversation-' . $data['conversation_id'] . '.md"');
    return $response;
  }

  /**
   * Export as HTML.
   */
  protected function exportAsHtml(array $data): Response {
    $html = '<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Congressional Chat - ' . htmlspecialchars($data['title'] ?: 'Conversation') . '</title>
  <style>
    body { font-family: system-ui, -apple-system, sans-serif; max-width: 800px; margin: 0 auto; padding: 20px; line-height: 1.6; }
    h1 { color: #333; border-bottom: 2px solid #0071b8; padding-bottom: 10px; }
    .meta { color: #666; font-size: 14px; margin-bottom: 20px; }
    .message { margin: 20px 0; padding: 15px; border-radius: 8px; }
    .message-user { background: #e8f4fc; }
    .message-assistant { background: #f5f5f5; }
    .role { font-weight: 600; margin-bottom: 10px; color: #333; }
    .content { white-space: pre-wrap; }
    .sources { margin-top: 15px; padding-top: 15px; border-top: 1px solid #ddd; }
    .sources h4 { margin: 0 0 10px 0; font-size: 14px; color: #666; }
    .source-item { padding: 8px; background: #fff; border-radius: 4px; margin-bottom: 8px; border: 1px solid #eee; }
    .party-r { color: #c62828; }
    .party-d { color: #1565c0; }
    .footer { margin-top: 40px; padding-top: 20px; border-top: 1px solid #ddd; font-size: 12px; color: #888; text-align: center; }
  </style>
</head>
<body>
  <h1>' . htmlspecialchars($data['title'] ?: 'Congressional Chat') . '</h1>
  <div class="meta">
    <p><strong>Date:</strong> ' . $data['created'] . '</p>';

    if ($data['member_filter']) {
      $html .= '<p><strong>Member Filter:</strong> ' . htmlspecialchars($data['member_filter']) . '</p>';
    }

    $html .= '</div>';

    foreach ($data['messages'] as $msg) {
      $roleClass = 'message-' . $msg['role'];
      $html .= '<div class="message ' . $roleClass . '">
        <div class="role">' . ucfirst($msg['role']) . '</div>
        <div class="content">' . htmlspecialchars($msg['content']) . '</div>';

      if (!empty($msg['sources'])) {
        $html .= '<div class="sources"><h4>Sources</h4>';
        foreach ($msg['sources'] as $source) {
          $partyClass = '';
          if (stripos($source['party'] ?? '', 'republican') !== FALSE) {
            $partyClass = 'party-r';
          }
          elseif (stripos($source['party'] ?? '', 'democrat') !== FALSE) {
            $partyClass = 'party-d';
          }

          $html .= '<div class="source-item">
            <span class="' . $partyClass . '">[' . htmlspecialchars($source['party'] ?? '?') . ']</span>
            <strong>' . htmlspecialchars($source['member_name'] ?? 'Unknown') . '</strong> -
            ' . htmlspecialchars($source['title'] ?? 'Untitled');

          if (!empty($source['url'])) {
            $html .= ' <a href="' . htmlspecialchars($source['url']) . '" target="_blank">View source</a>';
          }

          $html .= '</div>';
        }
        $html .= '</div>';
      }

      $html .= '</div>';
    }

    $html .= '<div class="footer">Exported from Congressional Query on ' . date('Y-m-d H:i:s') . '</div>
</body>
</html>';

    $response = new Response($html);
    $response->headers->set('Content-Type', 'text/html; charset=utf-8');
    $response->headers->set('Content-Disposition', 'attachment; filename="conversation-' . $data['conversation_id'] . '.html"');
    return $response;
  }

  /**
   * Edit a message in a conversation.
   *
   * @param string $conversation_id
   *   The conversation ID.
   * @param int $message_index
   *   The message index.
   * @param \Symfony\Component\HttpFoundation\Request $request
   *   The request.
   *
   * @return \Symfony\Component\HttpFoundation\JsonResponse
   *   JSON response.
   */
  public function editMessage(string $conversation_id, int $message_index, Request $request): JsonResponse {
    if (!$this->verifyConversationOwnership($conversation_id)) {
      return new JsonResponse(['error' => 'Access denied'], 403);
    }

    $content = json_decode($request->getContent(), TRUE);
    $newContent = trim($content['content'] ?? '');

    if (empty($newContent)) {
      return new JsonResponse(['error' => 'Content is required'], 400);
    }

    if (strlen($newContent) > self::MAX_MESSAGE_LENGTH) {
      return new JsonResponse(['error' => 'Message too long'], 400);
    }

    $result = $this->conversationManager->updateMessage(
      $conversation_id,
      $message_index,
      $this->sanitizeMessage($newContent)
    );

    if (!$result) {
      return new JsonResponse(['error' => 'Failed to update message'], 400);
    }

    return new JsonResponse([
      'success' => TRUE,
      'message_index' => $message_index,
    ]);
  }

  /**
   * Delete a message from a conversation.
   *
   * @param string $conversation_id
   *   The conversation ID.
   * @param int $message_index
   *   The message index.
   *
   * @return \Symfony\Component\HttpFoundation\JsonResponse
   *   JSON response.
   */
  public function deleteMessage(string $conversation_id, int $message_index): JsonResponse {
    if (!$this->verifyConversationOwnership($conversation_id)) {
      return new JsonResponse(['error' => 'Access denied'], 403);
    }

    $result = $this->conversationManager->deleteMessage($conversation_id, $message_index);

    if (!$result) {
      return new JsonResponse(['error' => 'Failed to delete message'], 400);
    }

    return new JsonResponse([
      'success' => TRUE,
      'message_index' => $message_index,
    ]);
  }

  /**
   * Create a new conversation.
   *
   * @param \Symfony\Component\HttpFoundation\Request $request
   *   The request.
   *
   * @return \Symfony\Component\HttpFoundation\JsonResponse
   *   JSON response with new conversation ID.
   */
  public function newConversation(Request $request): JsonResponse {
    $content = json_decode($request->getContent(), TRUE);
    $memberFilter = $this->sanitizeMemberFilter($content['member_filter'] ?? NULL);

    $conversationId = $this->conversationManager->createConversation($memberFilter);

    return new JsonResponse([
      'conversation_id' => $conversationId,
      'member_filter' => $memberFilter,
    ]);
  }

  /**
   * Check rate limit.
   *
   * @param \Symfony\Component\HttpFoundation\Request $request
   *   The request.
   *
   * @return bool|\Symfony\Component\HttpFoundation\JsonResponse
   *   TRUE if allowed, JsonResponse if rate limited.
   */
  protected function checkRateLimit(Request $request) {
    $identifier = $this->currentUser()->id() . '-' . $request->getClientIp();

    if (!$this->flood->isAllowed('congressional_chat_send', self::RATE_LIMIT_MESSAGES, self::RATE_LIMIT_WINDOW, $identifier)) {
      return new JsonResponse([
        'error' => 'Rate limit exceeded. Please wait before sending more messages.',
      ], 429);
    }

    return TRUE;
  }

  /**
   * Register rate limit event.
   *
   * @param \Symfony\Component\HttpFoundation\Request $request
   *   The request.
   */
  protected function registerRateLimitEvent(Request $request): void {
    $identifier = $this->currentUser()->id() . '-' . $request->getClientIp();
    $this->flood->register('congressional_chat_send', self::RATE_LIMIT_WINDOW, $identifier);
  }

  /**
   * Validate message input.
   *
   * @param array|null $content
   *   The request content.
   *
   * @return bool|\Symfony\Component\HttpFoundation\JsonResponse
   *   TRUE if valid, JsonResponse with error otherwise.
   */
  protected function validateMessageInput($content) {
    if (!is_array($content)) {
      return new JsonResponse(['error' => 'Invalid request format'], 400);
    }

    $message = trim($content['message'] ?? '');

    if (empty($message)) {
      return new JsonResponse(['error' => 'Message is required'], 400);
    }

    if (strlen($message) > self::MAX_MESSAGE_LENGTH) {
      return new JsonResponse([
        'error' => 'Message exceeds maximum length of ' . self::MAX_MESSAGE_LENGTH . ' characters',
      ], 400);
    }

    return TRUE;
  }

  /**
   * Sanitize message content.
   *
   * @param string $message
   *   The message.
   *
   * @return string
   *   Sanitized message.
   */
  protected function sanitizeMessage(string $message): string {
    // Remove HTML tags.
    $message = strip_tags($message);
    // Trim whitespace.
    $message = trim($message);
    // Normalize whitespace.
    $message = preg_replace('/\s+/', ' ', $message);
    // Limit length.
    return substr($message, 0, self::MAX_MESSAGE_LENGTH);
  }

  /**
   * Sanitize conversation ID.
   *
   * @param string|null $id
   *   The conversation ID.
   *
   * @return string|null
   *   Sanitized ID or NULL.
   */
  protected function sanitizeConversationId(?string $id): ?string {
    if ($id === NULL) {
      return NULL;
    }

    // Validate UUID format.
    if (preg_match('/^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/i', $id)) {
      return strtolower($id);
    }

    return NULL;
  }

  /**
   * Sanitize member filter.
   *
   * @param string|null $filter
   *   The member filter.
   *
   * @return string|null
   *   Sanitized filter or NULL.
   */
  protected function sanitizeMemberFilter(?string $filter): ?string {
    if ($filter === NULL || $filter === '') {
      return NULL;
    }

    // Remove HTML tags.
    $filter = strip_tags($filter);
    // Trim whitespace.
    $filter = trim($filter);
    // Limit length.
    return substr($filter, 0, 200);
  }

  /**
   * Verify conversation ownership.
   *
   * @param string $conversationId
   *   The conversation ID.
   *
   * @return bool
   *   TRUE if user owns the conversation.
   */
  protected function verifyConversationOwnership(string $conversationId): bool {
    $metadata = $this->conversationManager->getConversationMetadata($conversationId);

    if (!$metadata) {
      return FALSE;
    }

    // Check if current user owns this conversation.
    return (int) $metadata['uid'] === (int) $this->currentUser()->id();
  }

  /**
   * Get conversation history.
   *
   * @param string $conversation_id
   *   The conversation ID.
   *
   * @return \Symfony\Component\HttpFoundation\JsonResponse
   *   JSON response with messages.
   */
  public function getHistory(string $conversation_id): JsonResponse {
    $messages = $this->conversationManager->getConversation($conversation_id);
    $metadata = $this->conversationManager->getConversationMetadata($conversation_id);

    if (!$metadata) {
      return new JsonResponse([
        'error' => 'Conversation not found',
      ], 404);
    }

    // Verify ownership before returning conversation data.
    if (!$this->verifyConversationOwnership($conversation_id)) {
      return new JsonResponse([
        'error' => 'Access denied to this conversation',
      ], 403);
    }

    // Format messages for JSON.
    $formattedMessages = [];
    foreach ($messages as $message) {
      $formattedMessages[] = [
        'role' => $message['role'],
        'content' => $message['content'],
        'sources' => $this->formatSourcesForJson($message['sources'] ?? []),
        'timestamp' => $message['timestamp'],
      ];
    }

    return new JsonResponse([
      'conversation_id' => $conversation_id,
      'title' => $metadata['title'] ?? '',
      'member_filter' => $metadata['member_filter'],
      'messages' => $formattedMessages,
    ]);
  }

  /**
   * Format sources for JSON response.
   *
   * @param array $sources
   *   Raw sources array.
   *
   * @return array
   *   Formatted sources.
   */
  protected function formatSourcesForJson(array $sources): array {
    return array_map(function ($source) {
      return [
        'member_name' => $source['member_name'] ?? 'Unknown',
        'title' => $source['title'] ?? 'Untitled',
        'content' => $this->truncateContent($source['content_text'] ?? '', 200),
        'url' => $source['url'] ?? '',
        'party' => $source['party'] ?? '',
        'state' => $source['state'] ?? '',
        'topic' => $source['topic'] ?? '',
        'party_class' => congressional_query_get_party_class($source['party'] ?? ''),
      ];
    }, $sources);
  }

  /**
   * Truncate content.
   *
   * @param string $content
   *   Content to truncate.
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
    return substr($content, 0, $maxLength) . '...';
  }

}
