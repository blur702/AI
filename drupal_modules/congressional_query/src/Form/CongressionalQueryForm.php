<?php

namespace Drupal\congressional_query\Form;

use Drupal\congressional_query\Service\ConversationManager;
use Drupal\congressional_query\Service\OllamaLLMService;
use Drupal\Core\Ajax\AjaxResponse;
use Drupal\Core\Ajax\HtmlCommand;
use Drupal\Core\Ajax\InvokeCommand;
use Drupal\Core\Ajax\RedirectCommand;
use Drupal\Core\Form\FormBase;
use Drupal\Core\Form\FormStateInterface;
use Drupal\Core\Url;
use Symfony\Component\DependencyInjection\ContainerInterface;

/**
 * Form for submitting congressional queries.
 */
class CongressionalQueryForm extends FormBase {

  /**
   * The Ollama LLM service.
   *
   * @var \Drupal\congressional_query\Service\OllamaLLMService
   */
  protected $ollamaService;

  /**
   * The conversation manager.
   *
   * @var \Drupal\congressional_query\Service\ConversationManager
   */
  protected $conversationManager;

  /**
   * Constructs the form.
   *
   * @param \Drupal\congressional_query\Service\OllamaLLMService $ollama_service
   *   The Ollama LLM service.
   * @param \Drupal\congressional_query\Service\ConversationManager $conversation_manager
   *   The conversation manager.
   */
  public function __construct(
    OllamaLLMService $ollama_service,
    ConversationManager $conversation_manager
  ) {
    $this->ollamaService = $ollama_service;
    $this->conversationManager = $conversation_manager;
  }

  /**
   * {@inheritdoc}
   */
  public static function create(ContainerInterface $container) {
    return new static(
      $container->get('congressional_query.ollama_llm'),
      $container->get('congressional_query.conversation_manager')
    );
  }

  /**
   * {@inheritdoc}
   */
  public function getFormId() {
    return 'congressional_query_form';
  }

  /**
   * {@inheritdoc}
   */
  public function buildForm(array $form, FormStateInterface $form_state) {
    $form['#theme'] = 'congressional_query_form';
    $form['#attached']['library'][] = 'congressional_query/base';
    $form['#attached']['library'][] = 'congressional_query/query-form';

    $form['question'] = [
      '#type' => 'textarea',
      '#title' => $this->t('Your Question'),
      '#description' => $this->t('Ask a question about congressional members, their positions, or voting records.'),
      '#required' => TRUE,
      '#rows' => 4,
      '#maxlength' => 2000,
      '#attributes' => [
        'placeholder' => $this->t('e.g., What are the main policy priorities for representatives from Texas?'),
        'aria-describedby' => 'question-help-text question-char-counter',
        'maxlength' => 2000,
      ],
    ];

    $form['options'] = [
      '#type' => 'details',
      '#title' => $this->t('Query Options'),
      '#open' => FALSE,
    ];

    $form['options']['member_filter'] = [
      '#type' => 'textfield',
      '#title' => $this->t('Filter by Member'),
      '#description' => $this->t('Optionally filter results to a specific congressional member (leave blank for all).'),
      '#maxlength' => 255,
      '#attributes' => [
        'placeholder' => $this->t('e.g., Greene, Omar, Pelosi'),
      ],
    ];

    $form['options']['party_filter'] = [
      '#type' => 'select',
      '#title' => $this->t('Filter by Party'),
      '#description' => $this->t('Optionally filter results to a specific political party.'),
      '#options' => [
        '' => $this->t('- All Parties -'),
        'Republican' => $this->t('Republican'),
        'Democrat' => $this->t('Democrat'),
      ],
      '#default_value' => '',
    ];

    $form['options']['state_filter'] = [
      '#type' => 'select',
      '#title' => $this->t('Filter by State'),
      '#description' => $this->t('Optionally filter results to a specific state.'),
      '#options' => $this->getStateOptions(),
      '#default_value' => '',
    ];

    $form['options']['num_sources'] = [
      '#type' => 'number',
      '#title' => $this->t('Number of Sources'),
      '#description' => $this->t('Number of source documents to retrieve (1-20).'),
      '#min' => 1,
      '#max' => 20,
      '#default_value' => 8,
    ];

    $form['actions'] = [
      '#type' => 'actions',
    ];

    $form['actions']['submit'] = [
      '#type' => 'submit',
      '#value' => $this->t('Ask Question'),
      '#button_type' => 'primary',
      '#ajax' => [
        'callback' => '::ajaxSubmitCallback',
        'wrapper' => 'congressional-query-form-wrapper',
        'progress' => [
          'type' => 'throbber',
          'message' => $this->t('Processing your question...'),
        ],
      ],
      '#attributes' => [
        'class' => ['ajax-submit-btn'],
      ],
    ];

    $form['actions']['chat'] = [
      '#type' => 'link',
      '#title' => $this->t('Use Chat Interface'),
      '#url' => Url::fromRoute('congressional_query.chat'),
      '#attributes' => [
        'class' => ['button'],
      ],
    ];

    // Add a wrapper ID for AJAX replacement.
    $form['#prefix'] = '<div id="congressional-query-form-wrapper">';
    $form['#suffix'] = '</div>';

    // Add example questions.
    $form['examples'] = [
      '#type' => 'container',
      '#attributes' => [
        'class' => ['example-questions'],
      ],
    ];

    $form['examples']['title'] = [
      '#markup' => '<h4>' . $this->t('Example Questions') . '</h4>',
    ];

    $examples = congressional_query_get_example_questions();
    foreach ($examples as $i => $example) {
      $form['examples']['example_' . $i] = [
        '#type' => 'html_tag',
        '#tag' => 'button',
        '#value' => $example,
        '#attributes' => [
          'type' => 'button',
          'class' => ['example-question-chip'],
          'data-question' => $example,
        ],
      ];
    }

    return $form;
  }

  /**
   * Get state options for the filter dropdown.
   *
   * @return array
   *   Array of state options keyed by state code.
   */
  protected function getStateOptions(): array {
    return [
      '' => $this->t('- All States -'),
      'AL' => 'Alabama',
      'AK' => 'Alaska',
      'AZ' => 'Arizona',
      'AR' => 'Arkansas',
      'CA' => 'California',
      'CO' => 'Colorado',
      'CT' => 'Connecticut',
      'DE' => 'Delaware',
      'FL' => 'Florida',
      'GA' => 'Georgia',
      'HI' => 'Hawaii',
      'ID' => 'Idaho',
      'IL' => 'Illinois',
      'IN' => 'Indiana',
      'IA' => 'Iowa',
      'KS' => 'Kansas',
      'KY' => 'Kentucky',
      'LA' => 'Louisiana',
      'ME' => 'Maine',
      'MD' => 'Maryland',
      'MA' => 'Massachusetts',
      'MI' => 'Michigan',
      'MN' => 'Minnesota',
      'MS' => 'Mississippi',
      'MO' => 'Missouri',
      'MT' => 'Montana',
      'NE' => 'Nebraska',
      'NV' => 'Nevada',
      'NH' => 'New Hampshire',
      'NJ' => 'New Jersey',
      'NM' => 'New Mexico',
      'NY' => 'New York',
      'NC' => 'North Carolina',
      'ND' => 'North Dakota',
      'OH' => 'Ohio',
      'OK' => 'Oklahoma',
      'OR' => 'Oregon',
      'PA' => 'Pennsylvania',
      'RI' => 'Rhode Island',
      'SC' => 'South Carolina',
      'SD' => 'South Dakota',
      'TN' => 'Tennessee',
      'TX' => 'Texas',
      'UT' => 'Utah',
      'VT' => 'Vermont',
      'VA' => 'Virginia',
      'WA' => 'Washington',
      'WV' => 'West Virginia',
      'WI' => 'Wisconsin',
      'WY' => 'Wyoming',
      'DC' => 'District of Columbia',
      'AS' => 'American Samoa',
      'GU' => 'Guam',
      'MP' => 'Northern Mariana Islands',
      'PR' => 'Puerto Rico',
      'VI' => 'U.S. Virgin Islands',
    ];
  }

  /**
   * {@inheritdoc}
   */
  public function validateForm(array &$form, FormStateInterface $form_state) {
    $question = trim($form_state->getValue('question'));
    $memberFilter = trim($form_state->getValue('member_filter'));
    $partyFilter = $form_state->getValue('party_filter');
    $stateFilter = $form_state->getValue('state_filter');
    $numSources = (int) $form_state->getValue('num_sources');

    // Validate question length.
    if (strlen($question) < 10) {
      $form_state->setErrorByName('question', $this->t('Please enter a more detailed question (at least 10 characters).'));
    }

    if (strlen($question) > 2000) {
      $form_state->setErrorByName('question', $this->t('Question is too long. Please limit to 2000 characters.'));
    }

    // Check for potentially harmful patterns (basic XSS/injection prevention).
    $dangerousPatterns = [
      '/<script\b[^>]*>/i',
      '/javascript:/i',
      '/on\w+\s*=/i',
      '/SELECT\s+.*\s+FROM/i',
      '/UNION\s+SELECT/i',
      '/INSERT\s+INTO/i',
      '/DELETE\s+FROM/i',
      '/DROP\s+TABLE/i',
    ];

    foreach ($dangerousPatterns as $pattern) {
      if (preg_match($pattern, $question)) {
        $form_state->setErrorByName('question', $this->t('Your question contains invalid characters or patterns. Please rephrase your question.'));
        $this->logger('congressional_query')->warning('Potentially malicious input detected: @input', [
          '@input' => substr($question, 0, 100),
        ]);
        break;
      }
    }

    // Validate num_sources bounds.
    if ($numSources < 1 || $numSources > 20) {
      $form_state->setErrorByName('num_sources', $this->t('Number of sources must be between 1 and 20.'));
    }

    // Sanitize member filter (allow only alphanumeric, spaces, hyphens, apostrophes).
    if (!empty($memberFilter)) {
      $sanitizedFilter = preg_replace('/[^a-zA-Z0-9\s\-\'\.]/', '', $memberFilter);
      if ($sanitizedFilter !== $memberFilter) {
        $form_state->setValue('member_filter', $sanitizedFilter);
        $this->messenger()->addWarning($this->t('Special characters were removed from the member filter.'));
      }

      // Check if filter is too short to be meaningful.
      if (strlen($sanitizedFilter) < 2) {
        $form_state->setErrorByName('member_filter', $this->t('Member filter must be at least 2 characters long.'));
      }
    }

    // Validate party filter (must be empty or a valid party).
    if (!empty($partyFilter)) {
      $validParties = ['Republican', 'Democrat'];
      if (!in_array($partyFilter, $validParties, TRUE)) {
        $form_state->setErrorByName('party_filter', $this->t('Invalid party selection.'));
      }
    }

    // Validate state filter (must be empty or a valid state code).
    if (!empty($stateFilter)) {
      $validStates = array_keys($this->getStateOptions());
      if (!in_array($stateFilter, $validStates, TRUE)) {
        $form_state->setErrorByName('state_filter', $this->t('Invalid state selection.'));
      }
    }

    // Rate limiting check (basic implementation using session).
    $session = $this->getRequest()->getSession();
    $queryTimestamps = $session->get('congressional_query_timestamps', []);
    $currentTime = time();

    // Remove timestamps older than 1 minute.
    $queryTimestamps = array_filter($queryTimestamps, function ($timestamp) use ($currentTime) {
      return ($currentTime - $timestamp) < 60;
    });

    if (count($queryTimestamps) >= 10) {
      $form_state->setErrorByName('question', $this->t('You have made too many queries. Please wait a moment before trying again.'));
      $this->logger('congressional_query')->warning('Rate limit exceeded for session.');
    }
    else {
      // Add current timestamp.
      $queryTimestamps[] = $currentTime;
      $session->set('congressional_query_timestamps', $queryTimestamps);
    }
  }

  /**
   * {@inheritdoc}
   */
  public function submitForm(array &$form, FormStateInterface $form_state) {
    $question = trim($form_state->getValue('question'));
    $memberFilter = trim($form_state->getValue('member_filter')) ?: NULL;
    $partyFilter = $form_state->getValue('party_filter') ?: NULL;
    $stateFilter = $form_state->getValue('state_filter') ?: NULL;
    $numSources = (int) $form_state->getValue('num_sources') ?: 8;

    try {
      // Generate answer with all filters.
      $result = $this->ollamaService->answerQuestion(
        $question,
        $memberFilter,
        $numSources,
        $partyFilter,
        $stateFilter
      );

      // Log the query with all filter metadata.
      $queryId = $this->conversationManager->logQuery(
        $question,
        $result['answer'],
        [
          'model' => $result['model'],
          'member_filter' => $memberFilter,
          'party_filter' => $partyFilter,
          'state_filter' => $stateFilter,
          'num_sources' => $result['num_sources'],
          'sources' => $result['sources'],
          'response_time_ms' => $result['response_time_ms'],
          'conversation_id' => $result['conversation_id'],
        ]
      );

      // Redirect to results page.
      $form_state->setRedirect('congressional_query.results', ['query_id' => $queryId]);

      $this->messenger()->addStatus($this->t('Query processed successfully in @time ms.', [
        '@time' => $result['response_time_ms'],
      ]));
    }
    catch (\Exception $e) {
      $this->logger('congressional_query')->error('Query failed: @message', [
        '@message' => $e->getMessage(),
      ]);

      $this->messenger()->addError($this->t('Failed to process query: @error', [
        '@error' => $e->getMessage(),
      ]));
    }
  }

  /**
   * AJAX callback for form submission.
   *
   * @param array $form
   *   The form array.
   * @param \Drupal\Core\Form\FormStateInterface $form_state
   *   The form state.
   *
   * @return \Drupal\Core\Ajax\AjaxResponse
   *   AJAX response with redirect or error messages.
   */
  public function ajaxSubmitCallback(array &$form, FormStateInterface $form_state): AjaxResponse {
    $response = new AjaxResponse();

    // Check for validation errors.
    if ($form_state->hasAnyErrors()) {
      // Re-render the form with error messages.
      $response->addCommand(new HtmlCommand('#congressional-query-form-wrapper', $form));
      $response->addCommand(new InvokeCommand(NULL, 'congressionalQueryFormError', []));
      return $response;
    }

    // Check if we have a redirect set (indicates successful submission).
    $redirect = $form_state->getRedirect();
    if ($redirect instanceof Url) {
      $url = $redirect->toString();
      $response->addCommand(new RedirectCommand($url));

      // Also update browser history.
      $response->addCommand(new InvokeCommand(NULL, 'congressionalQuerySuccess', [$url]));
    }
    else {
      // Fallback: re-render the form.
      $response->addCommand(new HtmlCommand('#congressional-query-form-wrapper', $form));
    }

    return $response;
  }

}
