<?php

namespace Drupal\page_password_protect\Form;

use Drupal\Core\Render\Markup;
use Drupal\Core\Config\ConfigFactoryInterface;
use Drupal\Core\Entity\EntityTypeManagerInterface;
use Drupal\Core\Form\FormBase;
use Drupal\Core\Form\FormStateInterface;
use Drupal\Core\Messenger\MessengerInterface;
use Drupal\Core\Url;
use Drupal\page_password_protect\Service\PasswordProtectionService;
use Drupal\node\NodeInterface;
use Drupal\Core\Datetime\DateFormatterInterface;
use Symfony\Component\DependencyInjection\ContainerInterface;

/**
 * Provides the admin form for managing node-level passwords.
 *
 * This form is exposed via the /node/{node}/password-protect route and reuses
 * the same PasswordProtectionService used elsewhere in the module so all
 * password, session, and rate-limiting logic stays centralized.
 */
class PasswordProtectionForm extends FormBase {

  /**
   * The password protection service.
   *
   * @var \Drupal\page_password_protect\Service\PasswordProtectionService
   */
  protected PasswordProtectionService $protectionService;

  /**
   * The entity type manager.
   *
   * @var \Drupal\Core\Entity\EntityTypeManagerInterface
   */
  protected EntityTypeManagerInterface $entityTypeManager;

  /**
   * Date formatter service.
   *
   * @var \Drupal\Core\Datetime\DateFormatterInterface
   */
  protected DateFormatterInterface $dateFormatter;

  /**
   * Constructs a PasswordProtectionForm.
   *
   * @param \Drupal\page_password_protect\Service\PasswordProtectionService $protection_service
   *   The password protection service.
   * @param \Drupal\Core\Entity\EntityTypeManagerInterface $entity_type_manager
   *   Entity type manager for node loading.
   * @param \Drupal\Core\Config\ConfigFactoryInterface $config_factory
   *   Configuration factory for module settings.
   * @param \Drupal\Core\Messenger\MessengerInterface $messenger
   *   Messenger service.
   * @param \Drupal\Core\Datetime\DateFormatterInterface $date_formatter
   *   Date formatter service.
   */
  public function __construct(PasswordProtectionService $protection_service, EntityTypeManagerInterface $entity_type_manager, ConfigFactoryInterface $config_factory, MessengerInterface $messenger, DateFormatterInterface $date_formatter) {
    $this->protectionService = $protection_service;
    $this->entityTypeManager = $entity_type_manager;
    $this->configFactory = $config_factory;
    $this->messenger = $messenger;
    $this->dateFormatter = $date_formatter;
  }

  /**
   * {@inheritdoc}
   */
  public static function create(ContainerInterface $container) {
    return new static(
      $container->get('page_password_protect.password_protection'),
      $container->get('entity_type.manager'),
      $container->get('config.factory'),
      $container->get('messenger'),
      $container->get('date.formatter')
    );
  }

  /**
   * {@inheritdoc}
   */
  public function getFormId() {
    return 'page_password_protect_admin_form';
  }

  /**
   * {@inheritdoc}
   */
  public function buildForm(array $form, FormStateInterface $form_state, NodeInterface $node = NULL) {
    if (!$node) {
      throw new \InvalidArgumentException('A node parameter is required.');
    }

    $node = $this->entityTypeManager->getStorage('node')->load($node->id()) ?? $node;
    $form_state->set('node', $node);
    $is_protected = $this->protectionService->isProtected($node);
    $password_data = $this->protectionService->getPasswordData($node);
    $has_password_record = !empty($password_data);
    $config = $this->configFactory->get('page_password_protect.settings');

    $form['#attached']['library'][] = 'core/drupal.password';

    $form['current_status'] = [
      '#type' => 'markup',
      '#markup' => $this->buildStatusMarkup($node, $is_protected, $password_data),
    ];

    $form['protection_enabled'] = [
      '#type' => 'checkbox',
      '#title' => $this->t('Enable password protection for this page'),
      '#default_value' => $is_protected,
    ];

    $form['password'] = [
      '#type' => 'password_confirm',
      '#title' => $this->t('Password'),
      '#description' => $this->t('Leave blank to keep the existing password when protection remains enabled.'),
      '#required' => FALSE,
      '#states' => [
        'visible' => [
          ':input[name="protection_enabled"]' => ['checked' => TRUE],
        ],
      ],
    ];

    $form['hint'] = [
      '#type' => 'textfield',
      '#title' => $this->t('Password hint'),
      '#maxlength' => 255,
      '#description' => $this->t('Optional hint shown to visitors when entering the password.'),
      '#default_value' => $node->hasField('field_page_password_hint') ? $node->get('field_page_password_hint')->value : '',
      '#states' => [
        'visible' => [
          ':input[name="protection_enabled"]' => ['checked' => TRUE],
        ],
      ],
    ];

    $custom_message_default = $node->hasField('field_page_password_custom_message') ? $node->get('field_page_password_custom_message')->value : $config->get('custom_message');
    $form['custom_message'] = [
      '#type' => 'textarea',
      '#title' => $this->t('Custom access message'),
      '#description' => $this->t('Message displayed above the password form when access is denied.'),
      '#default_value' => $custom_message_default,
      '#states' => [
        'visible' => [
          ':input[name="protection_enabled"]' => ['checked' => TRUE],
        ],
      ],
    ];

    $form['actions'] = [
      '#type' => 'actions',
    ];

    $form['actions']['submit'] = [
      '#type' => 'submit',
      '#value' => $this->t('Save password protection settings'),
    ];

    $form['actions']['cancel'] = [
      '#type' => 'link',
      '#title' => $this->t('Cancel'),
      '#url' => Url::fromRoute('entity.node.canonical', ['node' => $node->id()]),
    ];

    $form_state->set('has_password_record', $has_password_record);

    return $form;
  }

  /**
   * Builds the status markup for the current password protection state.
   *
   * @param \Drupal\node\NodeInterface $node
   *   The node being edited.
   * @param bool $is_protected
   *   Whether protection is enabled on the node.
   * @param array|null $password_data
   *   Saved password metadata.
   *
   * @return string
   *   Safe markup describing the current state.
   */
  protected function buildStatusMarkup(NodeInterface $node, bool $is_protected, ?array $password_data) {
    $status = $is_protected ? $this->t('Password protection is enabled for this page.') : $this->t('Password protection is disabled.');
    if ($password_data) {
      $created = $this->dateFormatter->format($password_data['created'], 'short');
      $changed = $this->dateFormatter->format($password_data['changed'], 'short');
      $config = $this->configFactory->get('page_password_protect.settings');
      $max_attempts = $config->get('max_attempts') ?? 5;
      $session_timeout = $config->get('session_timeout') ?? 3600;
      $status .= '<br />' . $this->t('Password last changed on @changed (created @created).', ['@changed' => $changed, '@created' => $created]);
      $status .= '<br />' . $this->t('Visitors have @attempts attempts and sessions last @timeout seconds.', ['@attempts' => $max_attempts, '@timeout' => $session_timeout]);
    }
    else {
      $status .= '<br />' . $this->t('No password has been stored yet.');
    }

    return Markup::create($status);
  }

  /**
   * {@inheritdoc}
   */
  public function validateForm(array &$form, FormStateInterface $form_state) {
    $node = $form_state->get('node');
    $enabled = (bool) $form_state->getValue('protection_enabled');
    // password_confirm returns the password string directly, not an array.
    $password = $form_state->getValue('password') ?? '';
    $has_record = $form_state->get('has_password_record');

    if ($enabled && empty($password) && !$has_record) {
      $form_state->setErrorByName('password', $this->t('A password is required when enabling protection for the first time.'));
    }

    $hint = $form_state->getValue('hint');
    if (strlen($hint) > 255) {
      $form_state->setErrorByName('hint', $this->t('Hint must be 255 characters or fewer.'));
    }
  }

  /**
   * {@inheritdoc}
   */
  public function submitForm(array &$form, FormStateInterface $form_state) {
    /** @var \Drupal\node\NodeInterface $node */
    $node = $form_state->get('node');
    $enabled = (bool) $form_state->getValue('protection_enabled');
    // password_confirm returns the password string directly, not an array.
    $password = $form_state->getValue('password') ?? '';
    $hint = $form_state->getValue('hint');
    $custom_message = $form_state->getValue('custom_message');

    if ($node->hasField('field_page_password_protected')) {
      $node->set('field_page_password_protected', $enabled);
    }
    if ($node->hasField('field_page_password_hint')) {
      $node->set('field_page_password_hint', $hint);
    }
    if ($node->hasField('field_page_password_custom_message')) {
      $node->set('field_page_password_custom_message', $custom_message);
    }

    $node->save();

    if ($enabled) {
      if (!empty($password)) {
        // Ensure hint is a string, not an array.
        $hint_str = is_array($hint) ? '' : (string) ($hint ?? '');
        $result = $this->protectionService->setPassword($node, $password, $hint_str);
        $this->messenger->addStatus($this->t('Password protection enabled for %title.', ['%title' => $node->label()]));
      }
      else {
        \Drupal::logger('page_password_protect')->notice('Password empty, skipping setPassword for node @nid', ['@nid' => $node->id()]);
        $this->messenger->addStatus($this->t('Password protection settings saved for %title.', ['%title' => $node->label()]));
      }
    }
    else {
      $this->protectionService->removePassword($node);
      \Drupal::logger('page_password_protect')->notice('Protection disabled, password removed for node @nid', ['@nid' => $node->id()]);
      $this->messenger->addStatus($this->t('Password protection removed from %title.', ['%title' => $node->label()]));
    }

    $form_state->setRedirect('entity.node.canonical', ['node' => $node->id()]);
  }

}
