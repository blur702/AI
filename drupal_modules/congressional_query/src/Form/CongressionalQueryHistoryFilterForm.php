<?php

namespace Drupal\congressional_query\Form;

use Drupal\Core\Form\FormBase;
use Drupal\Core\Form\FormStateInterface;
use Drupal\Core\Url;
use Symfony\Component\HttpFoundation\RequestStack;
use Symfony\Component\DependencyInjection\ContainerInterface;

/**
 * Provides a filter form for query history.
 */
class CongressionalQueryHistoryFilterForm extends FormBase {

  /**
   * The request stack.
   *
   * @var \Symfony\Component\HttpFoundation\RequestStack
   */
  protected $requestStack;

  /**
   * Constructs the form.
   *
   * @param \Symfony\Component\HttpFoundation\RequestStack $request_stack
   *   The request stack.
   */
  public function __construct(RequestStack $request_stack) {
    $this->requestStack = $request_stack;
  }

  /**
   * {@inheritdoc}
   */
  public static function create(ContainerInterface $container) {
    return new static(
      $container->get('request_stack')
    );
  }

  /**
   * {@inheritdoc}
   */
  public function getFormId() {
    return 'congressional_query_history_filter_form';
  }

  /**
   * {@inheritdoc}
   */
  public function buildForm(array $form, FormStateInterface $form_state) {
    $request = $this->requestStack->getCurrentRequest();

    $form['#method'] = 'get';
    $form['#attributes']['class'][] = 'query-history-filter-form';

    $form['filters'] = [
      '#type' => 'details',
      '#title' => $this->t('Filter Options'),
      '#open' => $this->hasActiveFilters($request),
      '#attributes' => ['class' => ['filter-options']],
    ];

    $form['filters']['date_from'] = [
      '#type' => 'date',
      '#title' => $this->t('Date From'),
      '#default_value' => $request->query->get('date_from', ''),
    ];

    $form['filters']['date_to'] = [
      '#type' => 'date',
      '#title' => $this->t('Date To'),
      '#default_value' => $request->query->get('date_to', ''),
    ];

    $form['filters']['uid'] = [
      '#type' => 'entity_autocomplete',
      '#title' => $this->t('User'),
      '#target_type' => 'user',
      '#default_value' => $this->loadUserFromId($request->query->get('uid')),
      '#description' => $this->t('Filter by user who asked the question.'),
    ];

    $form['filters']['member_filter'] = [
      '#type' => 'textfield',
      '#title' => $this->t('Member Filter'),
      '#default_value' => $request->query->get('member_filter', ''),
      '#description' => $this->t('Filter by congressional member name.'),
      '#maxlength' => 255,
    ];

    $form['filters']['model'] = [
      '#type' => 'textfield',
      '#title' => $this->t('Model'),
      '#default_value' => $request->query->get('model', ''),
      '#description' => $this->t('Filter by LLM model name.'),
      '#maxlength' => 128,
    ];

    $form['filters']['response_time'] = [
      '#type' => 'container',
      '#attributes' => ['class' => ['response-time-range']],
    ];

    $form['filters']['response_time']['min_response_time'] = [
      '#type' => 'number',
      '#title' => $this->t('Min Response Time (ms)'),
      '#default_value' => $request->query->get('min_response_time', ''),
      '#min' => 0,
    ];

    $form['filters']['response_time']['max_response_time'] = [
      '#type' => 'number',
      '#title' => $this->t('Max Response Time (ms)'),
      '#default_value' => $request->query->get('max_response_time', ''),
      '#min' => 0,
    ];

    $form['filters']['search_text'] = [
      '#type' => 'textfield',
      '#title' => $this->t('Search Text'),
      '#default_value' => $request->query->get('search_text', ''),
      '#description' => $this->t('Search in questions and answers.'),
      '#maxlength' => 255,
    ];

    $form['filters']['actions'] = [
      '#type' => 'actions',
    ];

    $form['filters']['actions']['submit'] = [
      '#type' => 'submit',
      '#value' => $this->t('Apply Filters'),
      '#attributes' => ['class' => ['button--primary']],
    ];

    $form['filters']['actions']['reset'] = [
      '#type' => 'link',
      '#title' => $this->t('Reset'),
      '#url' => Url::fromRoute('congressional_query.query_history'),
      '#attributes' => ['class' => ['button']],
    ];

    return $form;
  }

  /**
   * {@inheritdoc}
   */
  public function submitForm(array &$form, FormStateInterface $form_state) {
    // Form uses GET method, so submission is handled automatically.
    // This method is required by FormBase but doesn't need to do anything.
  }

  /**
   * Check if any filters are active.
   *
   * @param \Symfony\Component\HttpFoundation\Request $request
   *   The current request.
   *
   * @return bool
   *   TRUE if filters are active.
   */
  protected function hasActiveFilters($request): bool {
    $filterParams = [
      'date_from', 'date_to', 'uid', 'member_filter',
      'model', 'min_response_time', 'max_response_time', 'search_text',
    ];

    foreach ($filterParams as $param) {
      if ($request->query->get($param)) {
        return TRUE;
      }
    }

    return FALSE;
  }

  /**
   * Load user entity from ID.
   *
   * @param int|null $uid
   *   User ID.
   *
   * @return \Drupal\user\UserInterface|null
   *   User entity or NULL.
   */
  protected function loadUserFromId($uid) {
    if ($uid) {
      return \Drupal::entityTypeManager()->getStorage('user')->load($uid);
    }
    return NULL;
  }

}
