<?php

namespace Drupal\congressional_query\Form;

use Drupal\congressional_query\Service\OllamaLLMService;
use Drupal\congressional_query\Service\SSHTunnelService;
use Drupal\congressional_query\Service\WeaviateClientService;
use Drupal\Core\Form\ConfigFormBase;
use Drupal\Core\Form\FormStateInterface;
use Symfony\Component\DependencyInjection\ContainerInterface;

/**
 * Configuration form for Congressional Query module.
 */
class CongressionalConfigForm extends ConfigFormBase {

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
   * Constructs the form.
   *
   * @param \Drupal\congressional_query\Service\SSHTunnelService $ssh_tunnel
   *   The SSH tunnel service.
   * @param \Drupal\congressional_query\Service\OllamaLLMService $ollama_service
   *   The Ollama LLM service.
   * @param \Drupal\congressional_query\Service\WeaviateClientService $weaviate_client
   *   The Weaviate client service.
   */
  public function __construct(
    SSHTunnelService $ssh_tunnel,
    OllamaLLMService $ollama_service,
    WeaviateClientService $weaviate_client
  ) {
    $this->sshTunnel = $ssh_tunnel;
    $this->ollamaService = $ollama_service;
    $this->weaviateClient = $weaviate_client;
  }

  /**
   * {@inheritdoc}
   */
  public static function create(ContainerInterface $container) {
    return new static(
      $container->get('congressional_query.ssh_tunnel'),
      $container->get('congressional_query.ollama_llm'),
      $container->get('congressional_query.weaviate_client')
    );
  }

  /**
   * {@inheritdoc}
   */
  protected function getEditableConfigNames() {
    return ['congressional_query.settings'];
  }

  /**
   * {@inheritdoc}
   */
  public function getFormId() {
    return 'congressional_query_config_form';
  }

  /**
   * {@inheritdoc}
   */
  public function buildForm(array $form, FormStateInterface $form_state) {
    $config = $this->config('congressional_query.settings');

    // SSH Configuration.
    $form['ssh'] = [
      '#type' => 'details',
      '#title' => $this->t('SSH Configuration'),
      '#open' => TRUE,
    ];

    $form['ssh']['ssh_host'] = [
      '#type' => 'textfield',
      '#title' => $this->t('SSH Host'),
      '#description' => $this->t('Remote server hostname or IP address.'),
      '#default_value' => $config->get('ssh.host'),
      '#required' => TRUE,
    ];

    $form['ssh']['ssh_port'] = [
      '#type' => 'number',
      '#title' => $this->t('SSH Port'),
      '#description' => $this->t('SSH port (default: 22).'),
      '#default_value' => $config->get('ssh.port') ?: 22,
      '#min' => 1,
      '#max' => 65535,
    ];

    $form['ssh']['ssh_username'] = [
      '#type' => 'textfield',
      '#title' => $this->t('SSH Username'),
      '#default_value' => $config->get('ssh.username'),
      '#required' => TRUE,
    ];

    $form['ssh']['ssh_password'] = [
      '#type' => 'password',
      '#title' => $this->t('SSH Password'),
      '#description' => $this->t('Leave blank to keep existing password. Use private key for better security.'),
    ];

    $form['ssh']['ssh_private_key_path'] = [
      '#type' => 'textfield',
      '#title' => $this->t('Private Key Path'),
      '#description' => $this->t('Optional path to SSH private key file on this server.'),
      '#default_value' => $config->get('ssh.private_key_path'),
    ];

    $form['ssh']['ssh_connection_timeout'] = [
      '#type' => 'number',
      '#title' => $this->t('Connection Timeout (seconds)'),
      '#description' => $this->t('Timeout for establishing SSH connections.'),
      '#default_value' => $config->get('ssh.connection_timeout') ?: 30,
      '#min' => 5,
      '#max' => 120,
    ];

    $form['ssh']['ssh_command_timeout'] = [
      '#type' => 'number',
      '#title' => $this->t('Command Timeout (seconds)'),
      '#description' => $this->t('Timeout for executing remote commands.'),
      '#default_value' => $config->get('ssh.command_timeout') ?: 120,
      '#min' => 10,
      '#max' => 600,
    ];

    $form['ssh']['ssh_max_retries'] = [
      '#type' => 'number',
      '#title' => $this->t('Max Connection Retries'),
      '#description' => $this->t('Maximum number of connection retry attempts.'),
      '#default_value' => $config->get('ssh.max_retries') ?: 3,
      '#min' => 1,
      '#max' => 10,
    ];

    $form['ssh']['ssh_health_check_interval'] = [
      '#type' => 'number',
      '#title' => $this->t('Health Check Interval (seconds)'),
      '#description' => $this->t('How often to run automatic health checks via cron.'),
      '#default_value' => $config->get('ssh.health_check_interval') ?: 300,
      '#min' => 60,
      '#max' => 3600,
    ];

    $form['ssh']['ssh_remote_os'] = [
      '#type' => 'select',
      '#title' => $this->t('Remote OS Type'),
      '#description' => $this->t('Operating system of the SSH target. Affects command syntax for curl requests.'),
      '#default_value' => $config->get('ssh.remote_os') ?: 'windows',
      '#options' => [
        'linux' => $this->t('Linux/POSIX'),
        'windows' => $this->t('Windows'),
      ],
    ];

    $form['ssh']['test_ssh'] = [
      '#type' => 'submit',
      '#value' => $this->t('Test SSH Connection'),
      '#submit' => ['::testSshConnection'],
      '#ajax' => [
        'callback' => '::testConnectionAjax',
        'wrapper' => 'ssh-test-result',
      ],
      '#limit_validation_errors' => [],
    ];

    $form['ssh']['ssh_test_result'] = [
      '#type' => 'container',
      '#attributes' => ['id' => 'ssh-test-result'],
    ];

    // Ollama Configuration.
    $form['ollama'] = [
      '#type' => 'details',
      '#title' => $this->t('Ollama LLM Configuration'),
      '#open' => TRUE,
    ];

    $form['ollama']['ollama_endpoint'] = [
      '#type' => 'textfield',
      '#title' => $this->t('Ollama Endpoint'),
      '#description' => $this->t('Ollama API endpoint on the remote server.'),
      '#default_value' => $config->get('ollama.endpoint') ?: 'http://localhost:11434',
    ];

    $form['ollama']['ollama_model'] = [
      '#type' => 'textfield',
      '#title' => $this->t('LLM Model'),
      '#description' => $this->t('Model to use for answer generation.'),
      '#default_value' => $config->get('ollama.model') ?: 'qwen3-coder-roo:latest',
    ];

    $form['ollama']['ollama_embedding_model'] = [
      '#type' => 'textfield',
      '#title' => $this->t('Embedding Model'),
      '#description' => $this->t('Model to use for generating embeddings.'),
      '#default_value' => $config->get('ollama.embedding_model') ?: 'snowflake-arctic-embed:l',
    ];

    $form['ollama']['ollama_temperature'] = [
      '#type' => 'number',
      '#title' => $this->t('Temperature'),
      '#description' => $this->t('Generation temperature (0.0-2.0). Lower = more focused.'),
      '#default_value' => $config->get('ollama.temperature') ?: 0.3,
      '#min' => 0,
      '#max' => 2,
      '#step' => 0.1,
    ];

    $form['ollama']['ollama_fallback_model'] = [
      '#type' => 'textfield',
      '#title' => $this->t('Fallback Model'),
      '#description' => $this->t('Fallback model to use if primary model is unavailable.'),
      '#default_value' => $config->get('ollama.fallback_model') ?: '',
    ];

    // Advanced Ollama Options.
    $form['ollama']['advanced'] = [
      '#type' => 'details',
      '#title' => $this->t('Advanced Options'),
      '#open' => FALSE,
    ];

    $form['ollama']['advanced']['ollama_num_predict'] = [
      '#type' => 'number',
      '#title' => $this->t('Max Tokens to Generate'),
      '#description' => $this->t('Maximum number of tokens to generate in a response.'),
      '#default_value' => $config->get('ollama.num_predict') ?: 2048,
      '#min' => 128,
      '#max' => 8192,
    ];

    $form['ollama']['advanced']['ollama_top_p'] = [
      '#type' => 'number',
      '#title' => $this->t('Top P (Nucleus Sampling)'),
      '#description' => $this->t('Top P value for nucleus sampling (0.0-1.0). Leave empty to use model default.'),
      '#default_value' => $config->get('ollama.top_p'),
      '#min' => 0,
      '#max' => 1,
      '#step' => 0.05,
    ];

    $form['ollama']['advanced']['ollama_top_k'] = [
      '#type' => 'number',
      '#title' => $this->t('Top K'),
      '#description' => $this->t('Limit choices to top K tokens. Leave empty to use model default.'),
      '#default_value' => $config->get('ollama.top_k'),
      '#min' => 1,
      '#max' => 100,
    ];

    $form['ollama']['advanced']['ollama_repeat_penalty'] = [
      '#type' => 'number',
      '#title' => $this->t('Repeat Penalty'),
      '#description' => $this->t('Penalty for repeating tokens (1.0 = no penalty). Leave empty to use model default.'),
      '#default_value' => $config->get('ollama.repeat_penalty'),
      '#min' => 0.5,
      '#max' => 2,
      '#step' => 0.1,
    ];

    $form['ollama']['advanced']['ollama_seed'] = [
      '#type' => 'number',
      '#title' => $this->t('Random Seed'),
      '#description' => $this->t('Fixed seed for reproducible results. Leave empty for random.'),
      '#default_value' => $config->get('ollama.seed'),
    ];

    $form['ollama']['advanced']['ollama_generation_timeout'] = [
      '#type' => 'number',
      '#title' => $this->t('Generation Timeout (seconds)'),
      '#description' => $this->t('Maximum time to wait for LLM response.'),
      '#default_value' => $config->get('ollama.generation_timeout') ?: 120,
      '#min' => 30,
      '#max' => 600,
    ];

    $form['ollama']['advanced']['ollama_response_cache_ttl'] = [
      '#type' => 'number',
      '#title' => $this->t('Response Cache TTL (seconds)'),
      '#description' => $this->t('How long to cache identical query responses.'),
      '#default_value' => $config->get('ollama.response_cache_ttl') ?: 3600,
      '#min' => 0,
      '#max' => 86400,
    ];

    $form['ollama']['advanced']['ollama_debug_mode'] = [
      '#type' => 'checkbox',
      '#title' => $this->t('Enable Debug Mode'),
      '#description' => $this->t('Log detailed debug information for Ollama operations.'),
      '#default_value' => $config->get('ollama.debug_mode') ?: FALSE,
    ];

    $form['ollama']['test_ollama'] = [
      '#type' => 'submit',
      '#value' => $this->t('Test Ollama Connection'),
      '#submit' => ['::testOllamaConnection'],
      '#ajax' => [
        'callback' => '::testConnectionAjax',
        'wrapper' => 'ollama-test-result',
      ],
      '#limit_validation_errors' => [],
    ];

    $form['ollama']['ollama_test_result'] = [
      '#type' => 'container',
      '#attributes' => ['id' => 'ollama-test-result'],
    ];

    // Weaviate Configuration.
    $form['weaviate'] = [
      '#type' => 'details',
      '#title' => $this->t('Weaviate Configuration'),
      '#open' => TRUE,
    ];

    $form['weaviate']['weaviate_url'] = [
      '#type' => 'textfield',
      '#title' => $this->t('Weaviate URL'),
      '#description' => $this->t('Weaviate HTTP endpoint on the remote server.'),
      '#default_value' => $config->get('weaviate.url') ?: 'http://localhost:8080',
    ];

    $form['weaviate']['weaviate_grpc_port'] = [
      '#type' => 'number',
      '#title' => $this->t('Weaviate gRPC Port'),
      '#default_value' => $config->get('weaviate.grpc_port') ?: 50051,
    ];

    $form['weaviate']['weaviate_collection'] = [
      '#type' => 'textfield',
      '#title' => $this->t('Collection Name'),
      '#description' => $this->t('Weaviate collection containing congressional data.'),
      '#default_value' => $config->get('weaviate.collection') ?: 'CongressionalData',
    ];

    $form['weaviate']['test_weaviate'] = [
      '#type' => 'submit',
      '#value' => $this->t('Test Weaviate Connection'),
      '#submit' => ['::testWeaviateConnection'],
      '#ajax' => [
        'callback' => '::testConnectionAjax',
        'wrapper' => 'weaviate-test-result',
      ],
      '#limit_validation_errors' => [],
    ];

    $form['weaviate']['weaviate_test_result'] = [
      '#type' => 'container',
      '#attributes' => ['id' => 'weaviate-test-result'],
    ];

    // Query Settings.
    $form['query'] = [
      '#type' => 'details',
      '#title' => $this->t('Query Settings'),
      '#open' => FALSE,
    ];

    $form['query']['query_default_num_sources'] = [
      '#type' => 'number',
      '#title' => $this->t('Default Number of Sources'),
      '#description' => $this->t('Default number of source documents to retrieve.'),
      '#default_value' => $config->get('query.default_num_sources') ?: 8,
      '#min' => 1,
      '#max' => 20,
    ];

    $form['query']['query_max_context_length'] = [
      '#type' => 'number',
      '#title' => $this->t('Max Context Length'),
      '#description' => $this->t('Maximum characters per source document in context.'),
      '#default_value' => $config->get('query.max_context_length') ?: 1500,
      '#min' => 100,
      '#max' => 5000,
    ];

    $form['query']['query_log_retention_days'] = [
      '#type' => 'number',
      '#title' => $this->t('Log Retention (Days)'),
      '#description' => $this->t('Number of days to retain query logs.'),
      '#default_value' => $config->get('query.log_retention_days') ?: 90,
      '#min' => 1,
      '#max' => 365,
    ];

    $form['query']['query_session_timeout_hours'] = [
      '#type' => 'number',
      '#title' => $this->t('Session Timeout (Hours)'),
      '#description' => $this->t('Hours before conversation sessions expire.'),
      '#default_value' => $config->get('query.session_timeout_hours') ?: 24,
      '#min' => 1,
      '#max' => 168,
    ];

    $form['query']['query_max_stored_turns'] = [
      '#type' => 'number',
      '#title' => $this->t('Max Conversation Turns to Store'),
      '#description' => $this->t('Maximum number of conversation turns to store per session.'),
      '#default_value' => $config->get('query.max_stored_turns') ?: 20,
      '#min' => 5,
      '#max' => 100,
    ];

    return parent::buildForm($form, $form_state);
  }

  /**
   * {@inheritdoc}
   */
  public function submitForm(array &$form, FormStateInterface $form_state) {
    $config = $this->configFactory->getEditable('congressional_query.settings');

    // SSH settings.
    $config->set('ssh.host', $form_state->getValue('ssh_host'))
      ->set('ssh.port', (int) $form_state->getValue('ssh_port'))
      ->set('ssh.username', $form_state->getValue('ssh_username'))
      ->set('ssh.private_key_path', $form_state->getValue('ssh_private_key_path'))
      ->set('ssh.connection_timeout', (int) $form_state->getValue('ssh_connection_timeout'))
      ->set('ssh.command_timeout', (int) $form_state->getValue('ssh_command_timeout'))
      ->set('ssh.max_retries', (int) $form_state->getValue('ssh_max_retries'))
      ->set('ssh.health_check_interval', (int) $form_state->getValue('ssh_health_check_interval'))
      ->set('ssh.remote_os', $form_state->getValue('ssh_remote_os'));

    // Only update password if a new one was provided.
    $newPassword = $form_state->getValue('ssh_password');
    if (!empty($newPassword)) {
      $config->set('ssh.password', $newPassword);
    }

    // Ollama settings.
    $config->set('ollama.endpoint', $form_state->getValue('ollama_endpoint'))
      ->set('ollama.model', $form_state->getValue('ollama_model'))
      ->set('ollama.fallback_model', $form_state->getValue('ollama_fallback_model'))
      ->set('ollama.embedding_model', $form_state->getValue('ollama_embedding_model'))
      ->set('ollama.temperature', (float) $form_state->getValue('ollama_temperature'))
      ->set('ollama.num_predict', (int) $form_state->getValue('ollama_num_predict'))
      ->set('ollama.generation_timeout', (int) $form_state->getValue('ollama_generation_timeout'))
      ->set('ollama.response_cache_ttl', (int) $form_state->getValue('ollama_response_cache_ttl'))
      ->set('ollama.debug_mode', (bool) $form_state->getValue('ollama_debug_mode'));

    // Optional Ollama advanced settings (only set if provided).
    $topP = $form_state->getValue('ollama_top_p');
    if ($topP !== '' && $topP !== NULL) {
      $config->set('ollama.top_p', (float) $topP);
    }
    else {
      $config->set('ollama.top_p', NULL);
    }

    $topK = $form_state->getValue('ollama_top_k');
    if ($topK !== '' && $topK !== NULL) {
      $config->set('ollama.top_k', (int) $topK);
    }
    else {
      $config->set('ollama.top_k', NULL);
    }

    $repeatPenalty = $form_state->getValue('ollama_repeat_penalty');
    if ($repeatPenalty !== '' && $repeatPenalty !== NULL) {
      $config->set('ollama.repeat_penalty', (float) $repeatPenalty);
    }
    else {
      $config->set('ollama.repeat_penalty', NULL);
    }

    $seed = $form_state->getValue('ollama_seed');
    if ($seed !== '' && $seed !== NULL) {
      $config->set('ollama.seed', (int) $seed);
    }
    else {
      $config->set('ollama.seed', NULL);
    }

    // Weaviate settings.
    $config->set('weaviate.url', $form_state->getValue('weaviate_url'))
      ->set('weaviate.grpc_port', (int) $form_state->getValue('weaviate_grpc_port'))
      ->set('weaviate.collection', $form_state->getValue('weaviate_collection'));

    // Query settings.
    $config->set('query.default_num_sources', (int) $form_state->getValue('query_default_num_sources'))
      ->set('query.max_context_length', (int) $form_state->getValue('query_max_context_length'))
      ->set('query.log_retention_days', (int) $form_state->getValue('query_log_retention_days'))
      ->set('query.session_timeout_hours', (int) $form_state->getValue('query_session_timeout_hours'))
      ->set('query.max_stored_turns', (int) $form_state->getValue('query_max_stored_turns'));

    $config->save();

    parent::submitForm($form, $form_state);
  }

  /**
   * Test SSH connection.
   */
  public function testSshConnection(array &$form, FormStateInterface $form_state) {
    try {
      $health = $this->sshTunnel->checkTunnelHealth();
      if ($health['status'] === 'ok') {
        $this->messenger()->addStatus($this->t('SSH connection successful: @message', [
          '@message' => $health['message'],
        ]));
      }
      else {
        $this->messenger()->addError($this->t('SSH connection failed: @message', [
          '@message' => $health['message'],
        ]));
      }
    }
    catch (\Exception $e) {
      $this->messenger()->addError($this->t('SSH connection error: @error', [
        '@error' => $e->getMessage(),
      ]));
    }

    $form_state->setRebuild();
  }

  /**
   * Test Ollama connection.
   */
  public function testOllamaConnection(array &$form, FormStateInterface $form_state) {
    try {
      $health = $this->ollamaService->checkHealth();
      if ($health['status'] === 'ok') {
        $models = implode(', ', array_slice($health['models'], 0, 5));
        $this->messenger()->addStatus($this->t('Ollama connection successful. Available models: @models', [
          '@models' => $models ?: 'none listed',
        ]));
      }
      else {
        $this->messenger()->addError($this->t('Ollama connection failed: @message', [
          '@message' => $health['message'],
        ]));
      }
    }
    catch (\Exception $e) {
      $this->messenger()->addError($this->t('Ollama connection error: @error', [
        '@error' => $e->getMessage(),
      ]));
    }

    $form_state->setRebuild();
  }

  /**
   * Test Weaviate connection.
   */
  public function testWeaviateConnection(array &$form, FormStateInterface $form_state) {
    try {
      $health = $this->weaviateClient->checkHealth();
      if ($health['status'] === 'ok') {
        $stats = $this->weaviateClient->getCollectionStats();
        $this->messenger()->addStatus($this->t('Weaviate connection successful. Collection "@collection" has @count documents.', [
          '@collection' => $stats['collection'],
          '@count' => $stats['count'],
        ]));
      }
      else {
        $this->messenger()->addError($this->t('Weaviate connection failed: @message', [
          '@message' => $health['message'],
        ]));
      }
    }
    catch (\Exception $e) {
      $this->messenger()->addError($this->t('Weaviate connection error: @error', [
        '@error' => $e->getMessage(),
      ]));
    }

    $form_state->setRebuild();
  }

  /**
   * AJAX callback for connection tests.
   */
  public function testConnectionAjax(array &$form, FormStateInterface $form_state) {
    return $form;
  }

}
