<?php

namespace Drupal\congressional_query\Plugin\Block;

use Drupal\congressional_query\Service\OllamaLLMService;
use Drupal\congressional_query\Service\SSHTunnelService;
use Drupal\congressional_query\Service\WeaviateClientService;
use Drupal\Core\Block\BlockBase;
use Drupal\Core\Form\FormStateInterface;
use Drupal\Core\Plugin\ContainerFactoryPluginInterface;
use Symfony\Component\DependencyInjection\ContainerInterface;

/**
 * Provides a connection status block.
 *
 * @Block(
 *   id = "congressional_query_connection_status",
 *   admin_label = @Translation("Congressional Query Connection Status"),
 *   category = @Translation("Congressional Query")
 * )
 */
class ConnectionStatusBlock extends BlockBase implements ContainerFactoryPluginInterface {

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
   * Constructs a ConnectionStatusBlock object.
   *
   * @param array $configuration
   *   A configuration array containing information about the plugin instance.
   * @param string $plugin_id
   *   The plugin_id for the plugin instance.
   * @param mixed $plugin_definition
   *   The plugin implementation definition.
   * @param \Drupal\congressional_query\Service\SSHTunnelService $ssh_tunnel
   *   The SSH tunnel service.
   * @param \Drupal\congressional_query\Service\OllamaLLMService $ollama_service
   *   The Ollama LLM service.
   * @param \Drupal\congressional_query\Service\WeaviateClientService $weaviate_client
   *   The Weaviate client service.
   */
  public function __construct(
    array $configuration,
    $plugin_id,
    $plugin_definition,
    SSHTunnelService $ssh_tunnel,
    OllamaLLMService $ollama_service,
    WeaviateClientService $weaviate_client
  ) {
    parent::__construct($configuration, $plugin_id, $plugin_definition);
    $this->sshTunnel = $ssh_tunnel;
    $this->ollamaService = $ollama_service;
    $this->weaviateClient = $weaviate_client;
  }

  /**
   * {@inheritdoc}
   */
  public static function create(ContainerInterface $container, array $configuration, $plugin_id, $plugin_definition) {
    return new static(
      $configuration,
      $plugin_id,
      $plugin_definition,
      $container->get('congressional_query.ssh_tunnel'),
      $container->get('congressional_query.ollama_llm'),
      $container->get('congressional_query.weaviate_client')
    );
  }

  /**
   * {@inheritdoc}
   */
  public function defaultConfiguration() {
    return [
      'refresh_interval' => 30,
      'show_details' => FALSE,
      'auto_refresh' => TRUE,
    ];
  }

  /**
   * {@inheritdoc}
   */
  public function blockForm($form, FormStateInterface $form_state) {
    $form['refresh_interval'] = [
      '#type' => 'number',
      '#title' => $this->t('Refresh Interval (seconds)'),
      '#description' => $this->t('How often to refresh the status display.'),
      '#default_value' => $this->configuration['refresh_interval'],
      '#min' => 10,
      '#max' => 300,
    ];

    $form['show_details'] = [
      '#type' => 'checkbox',
      '#title' => $this->t('Show detailed status'),
      '#description' => $this->t('Display extended status information.'),
      '#default_value' => $this->configuration['show_details'],
    ];

    $form['auto_refresh'] = [
      '#type' => 'checkbox',
      '#title' => $this->t('Enable auto-refresh'),
      '#description' => $this->t('Automatically refresh status at the specified interval.'),
      '#default_value' => $this->configuration['auto_refresh'],
    ];

    return $form;
  }

  /**
   * {@inheritdoc}
   */
  public function blockSubmit($form, FormStateInterface $form_state) {
    $this->configuration['refresh_interval'] = $form_state->getValue('refresh_interval');
    $this->configuration['show_details'] = $form_state->getValue('show_details');
    $this->configuration['auto_refresh'] = $form_state->getValue('auto_refresh');
  }

  /**
   * {@inheritdoc}
   */
  public function build() {
    // Use SSHTunnelService's getStatusForBlock() as the primary data source.
    // This avoids duplicating status aggregation logic in the block.
    $blockStatus = $this->sshTunnel->getStatusForBlock();

    // Build SSH status from the centralized status.
    $sshStatus = [
      'name' => 'SSH Tunnel',
      'status' => $blockStatus['connection']['status'],
      'message' => $blockStatus['overall_message'],
      'class' => $blockStatus['connection']['status_class'],
      'host' => $blockStatus['connection']['host'],
      'uptime' => $blockStatus['connection']['uptime'],
      'details' => [
        'Host' => $blockStatus['connection']['host'] ?: 'Not configured',
        'Uptime' => $blockStatus['connection']['uptime'] ?: 'N/A',
        'Auth Method' => $blockStatus['connection']['auth_method'] ?? 'N/A',
        'Last Activity' => $blockStatus['connection']['last_activity'] ?? 'N/A',
      ],
    ];

    // Build Ollama status from services data.
    $ollamaData = $blockStatus['services']['ollama'] ?? [];
    $ollamaDetails = $ollamaData['details'] ?? [];
    $ollamaStatus = [
      'name' => 'Ollama LLM',
      'status' => $ollamaData['status'] ?? 'unknown',
      'message' => $ollamaData['message'] ?? 'Status unknown',
      'class' => $this->getStatusClass($ollamaData['status'] ?? 'unknown'),
      'models' => count($ollamaDetails['models'] ?? []),
      'details' => [
        'Model Count' => $ollamaDetails['model_count'] ?? 0,
        'Models' => !empty($ollamaDetails['models']) ? implode(', ', array_slice($ollamaDetails['models'], 0, 3)) : 'None',
        'Response Time' => isset($ollamaData['response_time_ms']) ? $ollamaData['response_time_ms'] . 'ms' : 'N/A',
      ],
    ];

    // Build Weaviate status from services data.
    $weaviateData = $blockStatus['services']['weaviate'] ?? [];
    $weaviateDetails = $weaviateData['details'] ?? [];
    $weaviateStatus = [
      'name' => 'Weaviate DB',
      'status' => $weaviateData['status'] ?? 'unknown',
      'message' => $weaviateData['message'] ?? 'Status unknown',
      'class' => $this->getStatusClass($weaviateData['status'] ?? 'unknown'),
      'documents' => $weaviateDetails['document_count'] ?? 0,
      'details' => [
        'Version' => $weaviateDetails['version'] ?? 'Unknown',
        'Documents' => $weaviateDetails['document_count'] ?? 0,
        'Response Time' => isset($weaviateData['response_time_ms']) ? $weaviateData['response_time_ms'] . 'ms' : 'N/A',
      ],
    ];

    // Use configurable health check interval for cache max-age.
    $cacheMaxAge = $this->sshTunnel->getHealthCheckInterval();

    return [
      '#theme' => 'connection_status_block',
      '#ssh_status' => $sshStatus,
      '#ollama_status' => $ollamaStatus,
      '#weaviate_status' => $weaviateStatus,
      '#last_check' => $blockStatus['last_check'] ?? time(),
      '#show_details' => $this->configuration['show_details'],
      '#attached' => [
        'library' => ['congressional_query/connection-status'],
        'drupalSettings' => [
          'congressionalQueryStatus' => [
            'healthUrl' => '/congressional/health',
            'refreshInterval' => $this->configuration['refresh_interval'] * 1000,
            'autoRefresh' => $this->configuration['auto_refresh'],
          ],
        ],
      ],
      '#cache' => [
        'max-age' => $cacheMaxAge,
      ],
    ];
  }

  /**
   * Get CSS class for status.
   *
   * @param string $status
   *   The status value.
   *
   * @return string
   *   CSS class.
   */
  protected function getStatusClass(string $status): string {
    switch ($status) {
      case 'ok':
        return 'status-ok';

      case 'warning':
        return 'status-warning';

      case 'error':
        return 'status-error';

      default:
        return 'status-unknown';
    }
  }

}
