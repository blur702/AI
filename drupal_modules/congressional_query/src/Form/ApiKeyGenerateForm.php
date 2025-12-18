<?php

namespace Drupal\congressional_query\Form;

use Drupal\congressional_query\Service\ApiKeyManager;
use Drupal\Core\Form\FormBase;
use Drupal\Core\Form\FormStateInterface;
use Drupal\user\Entity\User;
use Symfony\Component\DependencyInjection\ContainerInterface;

/**
 * Form for generating a new API key.
 */
class ApiKeyGenerateForm extends FormBase {

  /**
   * The API key manager.
   *
   * @var \Drupal\congressional_query\Service\ApiKeyManager
   */
  protected $apiKeyManager;

  /**
   * Constructs the form.
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
   * {@inheritdoc}
   */
  public function getFormId() {
    return 'congressional_query_api_key_generate';
  }

  /**
   * {@inheritdoc}
   */
  public function buildForm(array $form, FormStateInterface $form_state) {
    // Check if we just generated a key.
    $generatedKey = $form_state->get('generated_key');

    if ($generatedKey) {
      $form['success'] = [
        '#type' => 'container',
        '#attributes' => ['class' => ['messages', 'messages--status']],
      ];

      $form['success']['message'] = [
        '#markup' => '<h3>' . $this->t('API Key Generated Successfully') . '</h3>',
      ];

      $form['success']['key'] = [
        '#type' => 'textfield',
        '#title' => $this->t('Your API Key'),
        '#value' => $generatedKey,
        '#attributes' => [
          'readonly' => 'readonly',
          'onclick' => 'this.select();',
          'class' => ['api-key-display'],
        ],
        '#description' => $this->t('<strong>Important:</strong> Copy this key now. It will not be shown again.'),
      ];

      $form['success']['warning'] = [
        '#markup' => '<div class="messages messages--warning">' .
          $this->t('Save this key securely. For security reasons, the full key cannot be retrieved later.') .
          '</div>',
      ];

      $form['actions'] = [
        '#type' => 'actions',
      ];

      $form['actions']['back'] = [
        '#type' => 'link',
        '#title' => $this->t('Back to API Keys'),
        '#url' => \Drupal\Core\Url::fromRoute('congressional_query.api_keys'),
        '#attributes' => ['class' => ['button']],
      ];

      return $form;
    }

    $form['name'] = [
      '#type' => 'textfield',
      '#title' => $this->t('Key Name'),
      '#description' => $this->t('A descriptive name for this API key (e.g., "Production Server", "Development").'),
      '#required' => TRUE,
      '#maxlength' => 255,
    ];

    $form['uid'] = [
      '#type' => 'entity_autocomplete',
      '#title' => $this->t('Owner'),
      '#target_type' => 'user',
      '#default_value' => User::load($this->currentUser()->id()),
      '#description' => $this->t('The user who owns this API key.'),
      '#required' => TRUE,
    ];

    $form['rate_limit_override'] = [
      '#type' => 'number',
      '#title' => $this->t('Rate Limit Override'),
      '#description' => $this->t('Custom rate limit (requests per hour). Leave empty to use the default (@default/hr).', [
        '@default' => $this->apiKeyManager->getDefaultRateLimit(),
      ]),
      '#min' => 1,
      '#max' => 10000,
    ];

    $form['allowed_ips'] = [
      '#type' => 'textarea',
      '#title' => $this->t('Allowed IP Addresses'),
      '#description' => $this->t('One IP address per line. Leave empty to allow all IPs.'),
      '#rows' => 3,
    ];

    $form['actions'] = [
      '#type' => 'actions',
    ];

    $form['actions']['submit'] = [
      '#type' => 'submit',
      '#value' => $this->t('Generate Key'),
      '#button_type' => 'primary',
    ];

    $form['actions']['cancel'] = [
      '#type' => 'link',
      '#title' => $this->t('Cancel'),
      '#url' => \Drupal\Core\Url::fromRoute('congressional_query.api_keys'),
      '#attributes' => ['class' => ['button']],
    ];

    return $form;
  }

  /**
   * {@inheritdoc}
   */
  public function validateForm(array &$form, FormStateInterface $form_state) {
    $name = trim($form_state->getValue('name'));
    if (strlen($name) < 3) {
      $form_state->setErrorByName('name', $this->t('Name must be at least 3 characters.'));
    }

    // Validate IP addresses.
    $ips = $form_state->getValue('allowed_ips');
    if (!empty($ips)) {
      $ipList = array_filter(array_map('trim', explode("\n", $ips)));
      foreach ($ipList as $ip) {
        if (!filter_var($ip, FILTER_VALIDATE_IP)) {
          $form_state->setErrorByName('allowed_ips', $this->t('Invalid IP address: @ip', ['@ip' => $ip]));
          break;
        }
      }
    }
  }

  /**
   * {@inheritdoc}
   */
  public function submitForm(array &$form, FormStateInterface $form_state) {
    $name = trim($form_state->getValue('name'));
    $uid = $form_state->getValue('uid');
    $rateLimitOverride = $form_state->getValue('rate_limit_override');
    $allowedIps = [];

    $ipsInput = $form_state->getValue('allowed_ips');
    if (!empty($ipsInput)) {
      $allowedIps = array_filter(array_map('trim', explode("\n", $ipsInput)));
    }

    $result = $this->apiKeyManager->generateKey(
      $name,
      $uid,
      $rateLimitOverride ?: NULL,
      $allowedIps
    );

    // Store the generated key for display.
    $form_state->set('generated_key', $result['key']);
    $form_state->setRebuild();

    $this->messenger()->addStatus($this->t('API key "@name" has been generated.', ['@name' => $name]));
  }

}
