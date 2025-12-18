<?php

namespace Drupal\congressional_query\Form;

use Drupal\congressional_query\Service\ApiKeyManager;
use Drupal\Core\Datetime\DateFormatterInterface;
use Drupal\Core\Form\FormBase;
use Drupal\Core\Form\FormStateInterface;
use Drupal\Core\Url;
use Drupal\user\Entity\User;
use Symfony\Component\DependencyInjection\ContainerInterface;

/**
 * Form for managing API keys.
 */
class ApiKeyManagementForm extends FormBase {

  /**
   * The API key manager.
   *
   * @var \Drupal\congressional_query\Service\ApiKeyManager
   */
  protected $apiKeyManager;

  /**
   * The date formatter.
   *
   * @var \Drupal\Core\Datetime\DateFormatterInterface
   */
  protected $dateFormatter;

  /**
   * Constructs the form.
   *
   * @param \Drupal\congressional_query\Service\ApiKeyManager $api_key_manager
   *   The API key manager.
   * @param \Drupal\Core\Datetime\DateFormatterInterface $date_formatter
   *   The date formatter.
   */
  public function __construct(ApiKeyManager $api_key_manager, DateFormatterInterface $date_formatter) {
    $this->apiKeyManager = $api_key_manager;
    $this->dateFormatter = $date_formatter;
  }

  /**
   * {@inheritdoc}
   */
  public static function create(ContainerInterface $container) {
    return new static(
      $container->get('congressional_query.api_key_manager'),
      $container->get('date.formatter')
    );
  }

  /**
   * {@inheritdoc}
   */
  public function getFormId() {
    return 'congressional_query_api_key_management';
  }

  /**
   * {@inheritdoc}
   */
  public function buildForm(array $form, FormStateInterface $form_state) {
    // Statistics summary.
    $stats = $this->apiKeyManager->getStatistics();

    $form['stats'] = [
      '#type' => 'container',
      '#attributes' => ['class' => ['api-key-stats']],
    ];

    $form['stats']['summary'] = [
      '#markup' => $this->t('<div class="stats-grid">
        <div class="stat-item"><strong>@total</strong> Total Keys</div>
        <div class="stat-item"><strong>@active</strong> Active</div>
        <div class="stat-item"><strong>@inactive</strong> Inactive</div>
        <div class="stat-item"><strong>@used_today</strong> Used Today</div>
      </div>', [
        '@total' => $stats['total_keys'],
        '@active' => $stats['active_keys'],
        '@inactive' => $stats['inactive_keys'],
        '@used_today' => $stats['used_today'],
      ]),
    ];

    // Actions.
    $form['actions_top'] = [
      '#type' => 'container',
      '#attributes' => ['class' => ['form-actions-top']],
    ];

    $form['actions_top']['generate'] = [
      '#type' => 'link',
      '#title' => $this->t('Generate New API Key'),
      '#url' => Url::fromRoute('congressional_query.api_key_generate'),
      '#attributes' => ['class' => ['button', 'button--primary']],
    ];

    // Filters.
    $form['filters'] = [
      '#type' => 'details',
      '#title' => $this->t('Filters'),
      '#open' => FALSE,
    ];

    $form['filters']['status'] = [
      '#type' => 'select',
      '#title' => $this->t('Status'),
      '#options' => [
        '' => $this->t('- All -'),
        'active' => $this->t('Active'),
        'inactive' => $this->t('Inactive'),
      ],
      '#default_value' => $form_state->getValue('status', ''),
    ];

    $form['filters']['apply'] = [
      '#type' => 'submit',
      '#value' => $this->t('Apply'),
      '#submit' => ['::filterSubmit'],
    ];

    // API Keys table.
    $activeOnly = NULL;
    $statusFilter = $form_state->getValue('status');
    if ($statusFilter === 'active') {
      $activeOnly = TRUE;
    }
    elseif ($statusFilter === 'inactive') {
      $activeOnly = FALSE;
    }

    $keys = $this->apiKeyManager->listKeys(NULL, $activeOnly);

    $header = [
      'prefix' => $this->t('Key Prefix'),
      'name' => $this->t('Name'),
      'owner' => $this->t('Owner'),
      'created' => $this->t('Created'),
      'last_used' => $this->t('Last Used'),
      'status' => $this->t('Status'),
      'rate_limit' => $this->t('Rate Limit'),
      'operations' => $this->t('Operations'),
    ];

    $rows = [];
    foreach ($keys as $key) {
      $owner = User::load($key->getUid());
      $ownerName = $owner ? $owner->getDisplayName() : $this->t('Unknown');

      $rows[$key->getId()] = [
        'prefix' => $key->getKeyPrefix() . '...',
        'name' => $key->getName(),
        'owner' => $ownerName,
        'created' => $this->dateFormatter->format($key->getCreated(), 'short'),
        'last_used' => $key->getLastUsed()
          ? $this->dateFormatter->format($key->getLastUsed(), 'short')
          : $this->t('Never'),
        'status' => $key->isActive() ? $this->t('Active') : $this->t('Inactive'),
        'rate_limit' => $key->getRateLimitOverride()
          ? $key->getRateLimitOverride() . '/hr'
          : $this->t('Default'),
        'operations' => [
          'data' => [
            '#type' => 'operations',
            '#links' => $this->getOperations($key),
          ],
        ],
      ];
    }

    $form['keys'] = [
      '#type' => 'tableselect',
      '#header' => $header,
      '#options' => $rows,
      '#empty' => $this->t('No API keys found.'),
    ];

    // Bulk operations.
    $form['bulk'] = [
      '#type' => 'details',
      '#title' => $this->t('Bulk Operations'),
      '#open' => FALSE,
    ];

    $form['bulk']['operation'] = [
      '#type' => 'select',
      '#title' => $this->t('Operation'),
      '#options' => [
        '' => $this->t('- Select -'),
        'revoke' => $this->t('Revoke selected'),
        'reactivate' => $this->t('Reactivate selected'),
        'delete' => $this->t('Delete selected'),
      ],
    ];

    $form['bulk']['submit'] = [
      '#type' => 'submit',
      '#value' => $this->t('Apply to selected'),
      '#submit' => ['::bulkSubmit'],
    ];

    $form['#attached']['library'][] = 'congressional_query/admin';

    return $form;
  }

  /**
   * Gets operations for a key.
   *
   * @param \Drupal\congressional_query\Entity\ApiKey $key
   *   The API key.
   *
   * @return array
   *   Operations links.
   */
  protected function getOperations($key): array {
    $operations = [];

    if ($key->isActive()) {
      $operations['revoke'] = [
        'title' => $this->t('Revoke'),
        'url' => Url::fromRoute('congressional_query.api_key_revoke', ['key_id' => $key->getId()]),
      ];
    }
    else {
      $operations['reactivate'] = [
        'title' => $this->t('Reactivate'),
        'url' => Url::fromRoute('congressional_query.api_key_reactivate', ['key_id' => $key->getId()]),
      ];
    }

    $operations['delete'] = [
      'title' => $this->t('Delete'),
      'url' => Url::fromRoute('congressional_query.api_key_delete', ['key_id' => $key->getId()]),
    ];

    return $operations;
  }

  /**
   * Filter submit handler.
   */
  public function filterSubmit(array &$form, FormStateInterface $form_state) {
    $form_state->setRebuild();
  }

  /**
   * Bulk operations submit handler.
   */
  public function bulkSubmit(array &$form, FormStateInterface $form_state) {
    $operation = $form_state->getValue('operation');
    $selected = array_filter($form_state->getValue('keys'));

    if (empty($operation) || empty($selected)) {
      $this->messenger()->addWarning($this->t('Please select an operation and at least one key.'));
      return;
    }

    $count = 0;
    foreach ($selected as $key_id) {
      switch ($operation) {
        case 'revoke':
          if ($this->apiKeyManager->revokeKey($key_id)) {
            $count++;
          }
          break;

        case 'reactivate':
          if ($this->apiKeyManager->reactivateKey($key_id)) {
            $count++;
          }
          break;

        case 'delete':
          if ($this->apiKeyManager->deleteKey($key_id)) {
            $count++;
          }
          break;
      }
    }

    $this->messenger()->addStatus($this->t('@count keys processed.', ['@count' => $count]));
  }

  /**
   * {@inheritdoc}
   */
  public function submitForm(array &$form, FormStateInterface $form_state) {
    // Default submit does nothing.
  }

}
