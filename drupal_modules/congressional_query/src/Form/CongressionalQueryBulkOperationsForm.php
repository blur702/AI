<?php

namespace Drupal\congressional_query\Form;

use Drupal\congressional_query\Service\ConversationManager;
use Drupal\Core\Config\ConfigFactoryInterface;
use Drupal\Core\Form\ConfirmFormBase;
use Drupal\Core\Form\FormStateInterface;
use Drupal\Core\Url;
use Symfony\Component\DependencyInjection\ContainerInterface;

/**
 * Form for bulk operations on query logs.
 */
class CongressionalQueryBulkOperationsForm extends ConfirmFormBase {

  /**
   * The conversation manager.
   *
   * @var \Drupal\congressional_query\Service\ConversationManager
   */
  protected $conversationManager;

  /**
   * The config factory.
   *
   * @var \Drupal\Core\Config\ConfigFactoryInterface
   */
  protected $configFactory;

  /**
   * Constructs the form.
   *
   * @param \Drupal\congressional_query\Service\ConversationManager $conversation_manager
   *   The conversation manager.
   * @param \Drupal\Core\Config\ConfigFactoryInterface $config_factory
   *   The config factory.
   */
  public function __construct(
    ConversationManager $conversation_manager,
    ConfigFactoryInterface $config_factory
  ) {
    $this->conversationManager = $conversation_manager;
    $this->configFactory = $config_factory;
  }

  /**
   * {@inheritdoc}
   */
  public static function create(ContainerInterface $container) {
    return new static(
      $container->get('congressional_query.conversation_manager'),
      $container->get('config.factory')
    );
  }

  /**
   * {@inheritdoc}
   */
  public function getFormId() {
    return 'congressional_query_bulk_operations_form';
  }

  /**
   * {@inheritdoc}
   */
  public function getQuestion() {
    return $this->t('Bulk Query Operations');
  }

  /**
   * {@inheritdoc}
   */
  public function getDescription() {
    return $this->t('Select an operation to perform on query logs. These operations cannot be undone.');
  }

  /**
   * {@inheritdoc}
   */
  public function getCancelUrl() {
    return new Url('congressional_query.query_history');
  }

  /**
   * {@inheritdoc}
   */
  public function getConfirmText() {
    return $this->t('Execute Operation');
  }

  /**
   * {@inheritdoc}
   */
  public function buildForm(array $form, FormStateInterface $form_state) {
    $form = parent::buildForm($form, $form_state);

    $config = $this->configFactory->get('congressional_query.settings');
    $retentionDays = $config->get('query.log_retention_days') ?? 90;

    $form['operation'] = [
      '#type' => 'select',
      '#title' => $this->t('Operation'),
      '#options' => [
        '' => $this->t('- Select an operation -'),
        'retention' => $this->t('Apply retention policy (delete queries older than @days days)', ['@days' => $retentionDays]),
        'date_range' => $this->t('Delete queries by date range'),
        'user' => $this->t('Delete queries by user'),
        'member_filter' => $this->t('Delete queries by member filter'),
        'all' => $this->t('Delete ALL queries (use with caution!)'),
      ],
      '#required' => TRUE,
    ];

    $form['date_range'] = [
      '#type' => 'container',
      '#states' => [
        'visible' => [
          ':input[name="operation"]' => ['value' => 'date_range'],
        ],
      ],
    ];

    $form['date_range']['date_from'] = [
      '#type' => 'date',
      '#title' => $this->t('From Date'),
    ];

    $form['date_range']['date_to'] = [
      '#type' => 'date',
      '#title' => $this->t('To Date'),
    ];

    $form['user_id'] = [
      '#type' => 'entity_autocomplete',
      '#title' => $this->t('User'),
      '#target_type' => 'user',
      '#states' => [
        'visible' => [
          ':input[name="operation"]' => ['value' => 'user'],
        ],
      ],
    ];

    $form['member_filter'] = [
      '#type' => 'textfield',
      '#title' => $this->t('Member Filter'),
      '#description' => $this->t('Enter the exact member filter value to delete.'),
      '#states' => [
        'visible' => [
          ':input[name="operation"]' => ['value' => 'member_filter'],
        ],
      ],
    ];

    $form['confirm_all'] = [
      '#type' => 'checkbox',
      '#title' => $this->t('I understand this will delete ALL query logs'),
      '#states' => [
        'visible' => [
          ':input[name="operation"]' => ['value' => 'all'],
        ],
        'required' => [
          ':input[name="operation"]' => ['value' => 'all'],
        ],
      ],
    ];

    $form['warning'] = [
      '#type' => 'markup',
      '#markup' => '<div class="messages messages--warning">' .
        '<strong>' . $this->t('Warning:') . '</strong> ' .
        $this->t('Bulk delete operations cannot be undone. Make sure you have a backup if needed.') .
        '</div>',
    ];

    return $form;
  }

  /**
   * {@inheritdoc}
   */
  public function validateForm(array &$form, FormStateInterface $form_state) {
    parent::validateForm($form, $form_state);

    $operation = $form_state->getValue('operation');

    switch ($operation) {
      case 'date_range':
        if (empty($form_state->getValue('date_from')) || empty($form_state->getValue('date_to'))) {
          $form_state->setErrorByName('date_from', $this->t('Both From and To dates are required for date range deletion.'));
        }
        break;

      case 'user':
        if (empty($form_state->getValue('user_id'))) {
          $form_state->setErrorByName('user_id', $this->t('Please select a user.'));
        }
        break;

      case 'member_filter':
        if (empty($form_state->getValue('member_filter'))) {
          $form_state->setErrorByName('member_filter', $this->t('Please enter a member filter value.'));
        }
        break;

      case 'all':
        if (!$form_state->getValue('confirm_all')) {
          $form_state->setErrorByName('confirm_all', $this->t('You must confirm you understand this will delete all queries.'));
        }
        break;
    }
  }

  /**
   * {@inheritdoc}
   */
  public function submitForm(array &$form, FormStateInterface $form_state) {
    $operation = $form_state->getValue('operation');
    $deleted = 0;

    try {
      switch ($operation) {
        case 'retention':
          $config = $this->configFactory->get('congressional_query.settings');
          $retentionDays = $config->get('query.log_retention_days') ?? 90;
          $deleted = $this->conversationManager->applyRetentionPolicy($retentionDays);
          $this->messenger()->addStatus($this->t('Deleted @count queries older than @days days.', [
            '@count' => $deleted,
            '@days' => $retentionDays,
          ]));
          break;

        case 'date_range':
          $dateFrom = $form_state->getValue('date_from');
          $dateTo = $form_state->getValue('date_to');
          $deleted = $this->conversationManager->deleteQueriesByDateRange($dateFrom, $dateTo);
          $this->messenger()->addStatus($this->t('Deleted @count queries from @from to @to.', [
            '@count' => $deleted,
            '@from' => $dateFrom,
            '@to' => $dateTo,
          ]));
          break;

        case 'user':
          $uid = $form_state->getValue('user_id');
          $deleted = $this->conversationManager->deleteQueriesByUser($uid);
          $this->messenger()->addStatus($this->t('Deleted @count queries for user.', [
            '@count' => $deleted,
          ]));
          break;

        case 'member_filter':
          $memberFilter = $form_state->getValue('member_filter');
          $deleted = $this->conversationManager->deleteQueriesByMemberFilter($memberFilter);
          $this->messenger()->addStatus($this->t('Deleted @count queries with member filter "@filter".', [
            '@count' => $deleted,
            '@filter' => $memberFilter,
          ]));
          break;

        case 'all':
          // Delete all by using a very old date range.
          $deleted = $this->conversationManager->deleteQueriesByDateRange('2000-01-01', date('Y-m-d'));
          $this->messenger()->addStatus($this->t('Deleted @count queries.', [
            '@count' => $deleted,
          ]));
          break;
      }

      $this->logger('congressional_query')->notice('Bulk operation @op: deleted @count queries', [
        '@op' => $operation,
        '@count' => $deleted,
      ]);
    }
    catch (\Exception $e) {
      $this->messenger()->addError($this->t('Bulk operation failed: @error', [
        '@error' => $e->getMessage(),
      ]));

      $this->logger('congressional_query')->error('Bulk operation @op failed: @error', [
        '@op' => $operation,
        '@error' => $e->getMessage(),
      ]);
    }

    $form_state->setRedirectUrl($this->getCancelUrl());
  }

}
