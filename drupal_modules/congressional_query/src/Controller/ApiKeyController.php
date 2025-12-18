<?php

namespace Drupal\congressional_query\Controller;

use Drupal\congressional_query\Service\ApiKeyManager;
use Drupal\Core\Controller\ControllerBase;
use Symfony\Component\DependencyInjection\ContainerInterface;
use Symfony\Component\HttpFoundation\RedirectResponse;

/**
 * Controller for API key operations.
 */
class ApiKeyController extends ControllerBase {

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
   * Revokes an API key.
   *
   * @param int $key_id
   *   The key ID.
   *
   * @return \Symfony\Component\HttpFoundation\RedirectResponse
   *   Redirect response.
   */
  public function revoke(int $key_id): RedirectResponse {
    $key = $this->apiKeyManager->getKey($key_id);

    if (!$key) {
      $this->messenger()->addError($this->t('API key not found.'));
      return $this->redirect('congressional_query.api_keys');
    }

    if ($this->apiKeyManager->revokeKey($key_id)) {
      $this->messenger()->addStatus($this->t('API key "@name" has been revoked.', [
        '@name' => $key->getName(),
      ]));
    }
    else {
      $this->messenger()->addError($this->t('Failed to revoke API key.'));
    }

    return $this->redirect('congressional_query.api_keys');
  }

  /**
   * Reactivates an API key.
   *
   * @param int $key_id
   *   The key ID.
   *
   * @return \Symfony\Component\HttpFoundation\RedirectResponse
   *   Redirect response.
   */
  public function reactivate(int $key_id): RedirectResponse {
    $key = $this->apiKeyManager->getKey($key_id);

    if (!$key) {
      $this->messenger()->addError($this->t('API key not found.'));
      return $this->redirect('congressional_query.api_keys');
    }

    if ($this->apiKeyManager->reactivateKey($key_id)) {
      $this->messenger()->addStatus($this->t('API key "@name" has been reactivated.', [
        '@name' => $key->getName(),
      ]));
    }
    else {
      $this->messenger()->addError($this->t('Failed to reactivate API key.'));
    }

    return $this->redirect('congressional_query.api_keys');
  }

  /**
   * Deletes an API key.
   *
   * @param int $key_id
   *   The key ID.
   *
   * @return \Symfony\Component\HttpFoundation\RedirectResponse
   *   Redirect response.
   */
  public function delete(int $key_id): RedirectResponse {
    $key = $this->apiKeyManager->getKey($key_id);

    if (!$key) {
      $this->messenger()->addError($this->t('API key not found.'));
      return $this->redirect('congressional_query.api_keys');
    }

    if ($this->apiKeyManager->deleteKey($key_id)) {
      $this->messenger()->addStatus($this->t('API key "@name" has been deleted.', [
        '@name' => $key->getName(),
      ]));
    }
    else {
      $this->messenger()->addError($this->t('Failed to delete API key.'));
    }

    return $this->redirect('congressional_query.api_keys');
  }

}
