<?php

namespace Drupal\congressional_query\Form;

use Drupal\congressional_query\Service\WeaviateClientService;
use Drupal\Core\Form\ConfirmFormBase;
use Drupal\Core\Form\FormStateInterface;
use Drupal\Core\Url;
use Symfony\Component\DependencyInjection\ContainerInterface;

/**
 * Form for managing Congressional Query caches.
 */
class CongressionalCacheManagementForm extends ConfirmFormBase {

  /**
   * The Weaviate client service.
   *
   * @var \Drupal\congressional_query\Service\WeaviateClientService
   */
  protected $weaviateClient;

  /**
   * Constructs the form.
   *
   * @param \Drupal\congressional_query\Service\WeaviateClientService $weaviate_client
   *   The Weaviate client service.
   */
  public function __construct(WeaviateClientService $weaviate_client) {
    $this->weaviateClient = $weaviate_client;
  }

  /**
   * {@inheritdoc}
   */
  public static function create(ContainerInterface $container) {
    return new static(
      $container->get('congressional_query.weaviate_client')
    );
  }

  /**
   * {@inheritdoc}
   */
  public function getFormId() {
    return 'congressional_cache_management_form';
  }

  /**
   * {@inheritdoc}
   */
  public function getQuestion() {
    return $this->t('Clear Congressional Query Caches');
  }

  /**
   * {@inheritdoc}
   */
  public function getDescription() {
    return $this->t('Select which caches to clear. This operation cannot be undone.');
  }

  /**
   * {@inheritdoc}
   */
  public function getCancelUrl() {
    return new Url('congressional_query.admin_dashboard');
  }

  /**
   * {@inheritdoc}
   */
  public function getConfirmText() {
    return $this->t('Clear Selected Caches');
  }

  /**
   * {@inheritdoc}
   */
  public function buildForm(array $form, FormStateInterface $form_state) {
    $form = parent::buildForm($form, $form_state);

    $form['cache_types'] = [
      '#type' => 'checkboxes',
      '#title' => $this->t('Cache Types'),
      '#options' => [
        'collection' => $this->t('Collection Cache - Cached collection metadata and schema'),
        'member' => $this->t('Member Cache - Cached member data from Weaviate'),
        'stats' => $this->t('Statistics Cache - Cached query statistics'),
        'all' => $this->t('All Caches - Clear all Congressional Query caches'),
      ],
      '#required' => TRUE,
    ];

    $form['warning'] = [
      '#type' => 'markup',
      '#markup' => '<div class="messages messages--warning">' .
        $this->t('Clearing caches may temporarily slow down queries while the cache is rebuilt.') .
        '</div>',
    ];

    return $form;
  }

  /**
   * {@inheritdoc}
   */
  public function submitForm(array &$form, FormStateInterface $form_state) {
    $cacheTypes = array_filter($form_state->getValue('cache_types'));
    $clearedCaches = [];

    try {
      if (in_array('all', $cacheTypes)) {
        $this->weaviateClient->clearCache();
        $clearedCaches[] = $this->t('All caches');
      }
      else {
        foreach ($cacheTypes as $type) {
          switch ($type) {
            case 'collection':
              $this->weaviateClient->invalidateCollectionCache();
              $clearedCaches[] = $this->t('Collection cache');
              break;

            case 'member':
              $this->weaviateClient->clearCache();
              $clearedCaches[] = $this->t('Member cache');
              break;

            case 'stats':
              $this->weaviateClient->clearCache();
              $clearedCaches[] = $this->t('Statistics cache');
              break;
          }
        }
      }

      $this->messenger()->addStatus($this->t('Successfully cleared: @caches', [
        '@caches' => implode(', ', $clearedCaches),
      ]));

      $this->logger('congressional_query')->info('Cache cleared: @caches', [
        '@caches' => implode(', ', $clearedCaches),
      ]);
    }
    catch (\Exception $e) {
      $this->messenger()->addError($this->t('Failed to clear cache: @error', [
        '@error' => $e->getMessage(),
      ]));

      $this->logger('congressional_query')->error('Cache clear failed: @error', [
        '@error' => $e->getMessage(),
      ]);
    }

    $form_state->setRedirectUrl($this->getCancelUrl());
  }

}
