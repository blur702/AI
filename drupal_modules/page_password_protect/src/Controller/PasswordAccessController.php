<?php

namespace Drupal\page_password_protect\Controller;

use Drupal\Core\Config\ConfigFactoryInterface;
use Drupal\Core\Controller\ControllerBase;
use Drupal\Core\Entity\EntityTypeManagerInterface;
use Drupal\Core\Form\FormBuilderInterface;
use Drupal\page_password_protect\Form\PasswordAccessForm;
use Drupal\page_password_protect\Form\PasswordProtectionForm;
use Drupal\page_password_protect\Service\PasswordProtectionService;
use Drupal\node\NodeInterface;
use Symfony\Component\DependencyInjection\ContainerInterface;
use Symfony\Component\HttpFoundation\JsonResponse;
use Symfony\Component\HttpFoundation\RedirectResponse;
use Symfony\Component\HttpFoundation\RequestStack;
use Symfony\Component\HttpFoundation\Response;

/**
 * Handles rendering the password entry form for visitors.
 */
class PasswordAccessController extends ControllerBase {

  /**
   * Password protection service.
   *
   * @var \Drupal\page_password_protect\Service\PasswordProtectionService
   */
  protected PasswordProtectionService $protectionService;

  /**
   * Request stack for JSON validation.
   *
   * @var \Symfony\Component\HttpFoundation\RequestStack
   */
  protected RequestStack $requestStack;

  /**
   * Constructs the controller.
   */
  public function __construct(FormBuilderInterface $form_builder, PasswordProtectionService $protection_service, EntityTypeManagerInterface $entity_type_manager, RequestStack $request_stack, ConfigFactoryInterface $config_factory) {
    $this->formBuilder = $form_builder;
    $this->protectionService = $protection_service;
    $this->entityTypeManager = $entity_type_manager;
    $this->requestStack = $request_stack;
    $this->configFactory = $config_factory;
  }

  /**
   * {@inheritdoc}
   */
  public static function create(ContainerInterface $container) {
    return new static(
      $container->get('form_builder'),
      $container->get('page_password_protect.password_protection'),
      $container->get('entity_type.manager'),
      $container->get('request_stack'),
      $container->get('config.factory')
    );
  }

  /**
   * Displays the password entry form.
   */
  public function accessForm(NodeInterface $node) {
    $node = $this->entityTypeManager->getStorage('node')->load($node->id()) ?? $node;

    if (!$this->protectionService->isProtected($node)) {
      return $this->redirectToNode($node);
    }

    if ($this->protectionService->checkAccess($node)) {
      return $this->redirectToNode($node);
    }

    if ($this->protectionService->isRateLimited($node)) {
      return [
        '#theme' => 'page_password_protect_denied',
        '#custom_message' => $this->getCustomMessage($node, $this->t('Too many failed attempts. Please try again later.')),
      ];
    }

    return $this->formBuilder->getForm(PasswordAccessForm::class, $node);
  }

  /**
   * Provides a JSON endpoint for password validation.
   */
  public function validatePassword(NodeInterface $node) {
    $password = $this->requestStack->getCurrentRequest()->request->get('password', '');
    $node = $this->entityTypeManager->getStorage('node')->load($node->id()) ?? $node;
    if (!$this->protectionService->isProtected($node)) {
      return new JsonResponse([
        'success' => FALSE,
        'message' => $this->t('This content is not password protected.'),
      ], Response::HTTP_BAD_REQUEST);
    }

    if ($this->protectionService->isRateLimited($node)) {
      return new JsonResponse([
        'success' => FALSE,
        'message' => $this->t('Too many attempts. Please try again later.'),
      ], Response::HTTP_TOO_MANY_REQUESTS);
    }

    $success = $this->protectionService->validatePassword($node, $password);
    $status = $success ? Response::HTTP_OK : Response::HTTP_UNAUTHORIZED;
    return new JsonResponse([
      'success' => $success,
      'message' => $success ? $this->t('Password accepted.') : $this->t('Incorrect password.'),
    ], $status);
  }

  /**
   * Redirects to the node canonical route.
   */
  protected function redirectToNode(NodeInterface $node): RedirectResponse {
    $url = $node->toUrl('canonical')->toString();
    return new RedirectResponse($url);
  }

  /**
   * Retrieves the custom access message.
   */
  protected function getCustomMessage(NodeInterface $node, string $fallback = ''): string {
    if ($node->hasField('field_page_password_custom_message') && !$node->get('field_page_password_custom_message')->isEmpty()) {
      return $node->get('field_page_password_custom_message')->value;
    }
    $message = $this->configFactory->get('page_password_protect.settings')->get('custom_message');
    return $message ?: $fallback;
  }

  /**
   * Displays the admin password protection form.
   */
  public function adminForm(NodeInterface $node) {
    $node = $this->entityTypeManager->getStorage('node')->load($node->id()) ?? $node;
    return $this->formBuilder->getForm(PasswordProtectionForm::class, $node);
  }

}
