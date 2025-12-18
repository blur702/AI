<?php

namespace Drupal\page_password_protect\Form;

use Drupal\Component\Utility\Html;
use Drupal\Core\Render\Markup;
use Drupal\Core\Config\ConfigFactoryInterface;
use Drupal\Core\Entity\EntityTypeManagerInterface;
use Drupal\Core\Form\FormBase;
use Drupal\Core\Form\FormStateInterface;
use Drupal\Core\Messenger\MessengerInterface;
use Drupal\Core\Url;
use Drupal\page_password_protect\Service\PasswordProtectionService;
use Drupal\node\NodeInterface;
use Symfony\Component\DependencyInjection\ContainerInterface;

/**
 * Handles visitor password entry for protected nodes.
 */
class PasswordAccessForm extends FormBase {

  /**
   * Password protection service.
   *
   * @var \Drupal\page_password_protect\Service\PasswordProtectionService
   */
  protected PasswordProtectionService $protectionService;

  /**
   * Entity type manager.
   *
   * @var \Drupal\Core\Entity\EntityTypeManagerInterface
   */
  protected EntityTypeManagerInterface $entityTypeManager;

  /**
   * Constructs the form.
   */
  public function __construct(PasswordProtectionService $protection_service, ConfigFactoryInterface $config_factory, MessengerInterface $messenger, EntityTypeManagerInterface $entity_type_manager) {
    $this->protectionService = $protection_service;
    $this->configFactory = $config_factory;
    $this->messenger = $messenger;
    $this->entityTypeManager = $entity_type_manager;
  }

  /**
   * {@inheritdoc}
   */
  public static function create(ContainerInterface $container) {
    return new static(
      $container->get('page_password_protect.password_protection'),
      $container->get('config.factory'),
      $container->get('messenger'),
      $container->get('entity_type.manager')
    );
  }

  /**
   * {@inheritdoc}
   */
  public function getFormId() {
    return 'page_password_protect_access_form';
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

    $config = $this->configFactory->get('page_password_protect.settings');
    $custom_message = $node->hasField('field_page_password_custom_message') && !$node->get('field_page_password_custom_message')->isEmpty()
      ? $node->get('field_page_password_custom_message')->value
      : $config->get('custom_message');

    $show_hints = (bool) $config->get('show_hints');
    $hint = '';
    if ($show_hints && $node->hasField('field_page_password_hint') && !$node->get('field_page_password_hint')->isEmpty()) {
      $hint = $node->get('field_page_password_hint')->value;
    }

    $remaining = $this->protectionService->getRemainingAttempts($node);

    $form['custom_message'] = [
      '#type' => 'markup',
      '#markup' => $custom_message ? Markup::create(Html::escape($custom_message)) : '',
      '#prefix' => '<div class="page-password-protect-message">',
      '#suffix' => '</div>',
    ];

    $form['password'] = [
      '#type' => 'password',
      '#title' => $this->t('Password'),
      '#required' => TRUE,
    ];

    if ($hint) {
      $form['hint'] = [
        '#type' => 'markup',
        '#markup' => Markup::create('<p class="page-password-protect-hint">' . Html::escape($hint) . '</p>'),
      ];
    }

    $form['attempts'] = [
      '#type' => 'markup',
      '#markup' => $this->t('You have @attempts attempts remaining.', ['@attempts' => $remaining]),
      '#prefix' => '<div class="page-password-protect-attempts">',
      '#suffix' => '</div>',
    ];

    $form['actions'] = [
      '#type' => 'actions',
    ];

    $form['actions']['submit'] = [
      '#type' => 'submit',
      '#value' => $this->t('Submit'),
    ];

    $form['actions']['cancel'] = [
      '#type' => 'link',
      '#title' => $this->t('Cancel'),
      '#url' => Url::fromRoute('<front>'),
      '#attributes' => [
        'class' => ['button', 'button--secondary'],
      ],
    ];

    $form['#attached']['library'][] = 'core/drupal.password';

    return $form;
  }

  /**
   * {@inheritdoc}
   */
  public function validateForm(array &$form, FormStateInterface $form_state) {
    $node = $form_state->get('node');
    if ($this->protectionService->isRateLimited($node)) {
      $form_state->setErrorByName('password', $this->t('Too many failed password attempts. Please try again later.'));
    }
  }

  /**
   * {@inheritdoc}
   */
  public function submitForm(array &$form, FormStateInterface $form_state) {
    $node = $form_state->get('node');
    $password = $form_state->getValue('password');
    $success = $this->protectionService->validatePassword($node, $password);

    if ($success) {
      $this->messenger->addStatus($this->t('Access granted to %title.', ['%title' => $node->label()]));
      $form_state->setRedirect('entity.node.canonical', ['node' => $node->id()]);
      return;
    }

    $remaining = $this->protectionService->getRemainingAttempts($node);
    if ($this->protectionService->isRateLimited($node)) {
      $this->messenger->addError($this->t('Too many failed attempts. Access denied.'));
    }
    else {
      $this->messenger->addError($this->t('Incorrect password. You have @attempts attempts remaining.', ['@attempts' => $remaining]));
    }

    $form_state->setRebuild();
  }

}
