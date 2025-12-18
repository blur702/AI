<?php

namespace Drupal\page_password_protect\EventSubscriber;

use Drupal\Core\Entity\EntityTypeManagerInterface;
use Drupal\Core\Routing\CurrentRouteMatch;
use Drupal\page_password_protect\Service\PasswordProtectionService;
use Drupal\node\NodeInterface;
use Symfony\Component\EventDispatcher\EventSubscriberInterface;
use Symfony\Component\HttpFoundation\RedirectResponse;
use Symfony\Component\HttpKernel\Event\ExceptionEvent;
use Symfony\Component\HttpKernel\Exception\AccessDeniedHttpException;
use Symfony\Component\HttpKernel\KernelEvents;
use Symfony\Component\Security\Core\Exception\AccessDeniedException;
use Drupal\Core\Url;

/**
 * Redirects denied access to protected nodes to the password form.
 */
class PasswordProtectRedirectSubscriber implements EventSubscriberInterface {

  /**
   * @var \Drupal\page_password_protect\Service\PasswordProtectionService
   */
  protected PasswordProtectionService $protectionService;

  /**
   * @var \Drupal\Core\Entity\EntityTypeManagerInterface
   */
  protected EntityTypeManagerInterface $entityTypeManager;

  /**
   * @var \Drupal\Core\Routing\CurrentRouteMatch
   */
  protected CurrentRouteMatch $routeMatch;

  /**
   * Constructs subscriber.
   */
  public function __construct(PasswordProtectionService $protection_service, EntityTypeManagerInterface $entity_type_manager, CurrentRouteMatch $route_match) {
    $this->protectionService = $protection_service;
    $this->entityTypeManager = $entity_type_manager;
    $this->routeMatch = $route_match;
  }

  /**
   * {@inheritdoc}
   */
  public static function getSubscribedEvents() {
    return [
      KernelEvents::EXCEPTION => ['onException', 50],
    ];
  }

  /**
   * Redirects to the password form when access is denied on protected nodes.
   */
  public function onException(ExceptionEvent $event) {
    $exception = $event->getThrowable();
    if (!($exception instanceof AccessDeniedHttpException) && !($exception instanceof AccessDeniedException)) {
      return;
    }

    $route_name = $this->routeMatch->getRouteName();
    if (!in_array($route_name, ['entity.node.canonical'], TRUE)) {
      return;
    }
    if (in_array($route_name, ['page_password_protect.access_form', 'page_password_protect.validate_password'], TRUE)) {
      return;
    }

    $node = $this->routeMatch->getParameter('node');
    if (!$node instanceof NodeInterface) {
      return;
    }

    if ($this->protectionService->isProtected($node) && !$this->protectionService->checkAccess($node)) {
      $url = Url::fromRoute('page_password_protect.access_form', ['node' => $node->id()])->toString();
      $event->setResponse(new RedirectResponse($url));
    }
  }

}
