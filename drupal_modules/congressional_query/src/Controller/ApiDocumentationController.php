<?php

namespace Drupal\congressional_query\Controller;

use Drupal\congressional_query\Service\ApiKeyManager;
use Drupal\Core\Controller\ControllerBase;
use Drupal\Core\Url;
use Symfony\Component\DependencyInjection\ContainerInterface;

/**
 * Controller for API documentation.
 */
class ApiDocumentationController extends ControllerBase {

  /**
   * The API key manager.
   *
   * @var \Drupal\congressional_query\Service\ApiKeyManager
   */
  protected $apiKeyManager;

  /**
   * Constructs the controller.
   *
   * @param \Drupal\congressional_query\Service\ApiKeyManager $api_key_manager
   *   The API key manager.
   */
  public function __construct(ApiKeyManager $api_key_manager) {
    $this->apiKeyManager = $api_key_manager;
  }

  /**
   * {@inheritdoc}
   */
  public static function create(ContainerInterface $container) {
    return new static(
      $container->get('congressional_query.api_key_manager')
    );
  }

  /**
   * Displays API documentation page.
   *
   * @return array
   *   Render array.
   */
  public function documentation(): array {
    $baseUrl = \Drupal::request()->getSchemeAndHttpHost();
    $rateLimit = $this->apiKeyManager->getDefaultRateLimit();
    $rateLimitWindow = $this->apiKeyManager->getRateLimitWindow();

    $endpoints = [
      [
        'method' => 'POST',
        'path' => '/api/congressional/query',
        'description' => $this->t('Submit a question about congressional members.'),
        'auth_required' => TRUE,
        'request_body' => [
          'question' => ['type' => 'string', 'required' => TRUE, 'description' => 'The question to ask (10-2000 characters)'],
          'member_filter' => ['type' => 'string', 'required' => FALSE, 'description' => 'Filter by member name'],
          'party_filter' => ['type' => 'string', 'required' => FALSE, 'description' => 'Republican, Democrat, or Independent'],
          'state_filter' => ['type' => 'string', 'required' => FALSE, 'description' => 'Two-letter state code'],
          'num_sources' => ['type' => 'integer', 'required' => FALSE, 'description' => 'Number of sources (1-20)'],
        ],
        'response' => [
          'query_id' => 'Unique query identifier',
          'answer' => 'Generated answer text',
          'sources' => 'Array of source documents',
          'model' => 'LLM model used',
          'response_time_ms' => 'Response time in milliseconds',
        ],
      ],
      [
        'method' => 'POST',
        'path' => '/api/congressional/chat',
        'description' => $this->t('Send a message in a conversation.'),
        'auth_required' => TRUE,
        'request_body' => [
          'message' => ['type' => 'string', 'required' => TRUE, 'description' => 'The message to send (5-2000 characters)'],
          'conversation_id' => ['type' => 'string', 'required' => FALSE, 'description' => 'Existing conversation UUID'],
          'member_filter' => ['type' => 'string', 'required' => FALSE, 'description' => 'Filter by member name'],
        ],
        'response' => [
          'conversation_id' => 'Conversation UUID',
          'answer' => 'Generated answer text',
          'sources' => 'Array of source documents',
          'model' => 'LLM model used',
          'response_time_ms' => 'Response time in milliseconds',
        ],
      ],
      [
        'method' => 'GET',
        'path' => '/api/congressional/chat/{conversation_id}',
        'description' => $this->t('Retrieve conversation history.'),
        'auth_required' => TRUE,
        'request_body' => NULL,
        'response' => [
          'conversation_id' => 'Conversation UUID',
          'title' => 'Conversation title',
          'member_filter' => 'Active member filter',
          'message_count' => 'Number of messages',
          'messages' => 'Array of messages with role, content, sources, timestamp',
        ],
      ],
      [
        'method' => 'GET',
        'path' => '/congressional/health',
        'description' => $this->t('Check service health status.'),
        'auth_required' => FALSE,
        'request_body' => NULL,
        'response' => [
          'status' => 'Overall status (ok, degraded, error)',
          'services' => 'Individual service statuses',
        ],
      ],
    ];

    $errorCodes = [
      ['code' => 'VALIDATION_ERROR', 'status' => 400, 'description' => $this->t('Request validation failed')],
      ['code' => 'INVALID_API_KEY', 'status' => 401, 'description' => $this->t('API key is invalid or missing')],
      ['code' => 'ACCESS_DENIED', 'status' => 403, 'description' => $this->t('Insufficient permissions')],
      ['code' => 'NOT_FOUND', 'status' => 404, 'description' => $this->t('Resource not found')],
      ['code' => 'RATE_LIMIT_EXCEEDED', 'status' => 429, 'description' => $this->t('Too many requests')],
      ['code' => 'SERVER_ERROR', 'status' => 500, 'description' => $this->t('Internal server error')],
    ];

    return [
      '#theme' => 'congressional_api_documentation',
      '#base_url' => $baseUrl,
      '#endpoints' => $endpoints,
      '#error_codes' => $errorCodes,
      '#rate_limit' => $rateLimit,
      '#rate_limit_window' => $rateLimitWindow / 60,
      '#api_key_url' => Url::fromRoute('congressional_query.api_keys')->toString(),
      '#attached' => [
        'library' => ['congressional_query/base'],
      ],
    ];
  }

}
