<?php

namespace Drupal\congressional_query\Service;

use Drupal\Core\Datetime\DateFormatterInterface;

/**
 * Service for formatting unified API responses.
 */
class ApiResponseFormatter {

  /**
   * The date formatter.
   *
   * @var \Drupal\Core\Datetime\DateFormatterInterface
   */
  protected $dateFormatter;

  /**
   * Constructs an ApiResponseFormatter.
   *
   * @param \Drupal\Core\Datetime\DateFormatterInterface $date_formatter
   *   The date formatter.
   */
  public function __construct(DateFormatterInterface $date_formatter) {
    $this->dateFormatter = $date_formatter;
  }

  /**
   * Formats a successful response.
   *
   * @param mixed $data
   *   The response data.
   * @param array $meta
   *   Optional metadata.
   *
   * @return array
   *   Formatted response array.
   */
  public function success($data, array $meta = []): array {
    $response = [
      'success' => TRUE,
      'data' => $data,
      'timestamp' => $this->getTimestamp(),
    ];

    if (!empty($meta)) {
      $response['meta'] = $meta;
    }

    return $response;
  }

  /**
   * Formats an error response.
   *
   * @param string $code
   *   Error code.
   * @param string $message
   *   Error message.
   * @param array $details
   *   Optional error details.
   *
   * @return array
   *   Formatted error response.
   */
  public function error(string $code, string $message, array $details = []): array {
    $error = [
      'code' => $code,
      'message' => $message,
    ];

    if (!empty($details)) {
      $error['details'] = $details;
    }

    return [
      'success' => FALSE,
      'error' => $error,
      'timestamp' => $this->getTimestamp(),
    ];
  }

  /**
   * Formats a validation error response.
   *
   * @param array $errors
   *   Array of field => error message.
   *
   * @return array
   *   Formatted validation error response.
   */
  public function validationError(array $errors): array {
    return $this->error(
      'VALIDATION_ERROR',
      'One or more fields failed validation',
      ['fields' => $errors]
    );
  }

  /**
   * Formats an authentication error response.
   *
   * @param string $message
   *   Optional custom message.
   *
   * @return array
   *   Formatted auth error response.
   */
  public function authError(string $message = 'Invalid or missing API key'): array {
    return $this->error('AUTH_ERROR', $message);
  }

  /**
   * Formats a rate limit error response.
   *
   * @param int $retry_after
   *   Seconds until rate limit resets.
   *
   * @return array
   *   Formatted rate limit error response.
   */
  public function rateLimitError(int $retry_after): array {
    return $this->error(
      'RATE_LIMIT_EXCEEDED',
      'Too many requests. Please retry later.',
      ['retry_after' => $retry_after]
    );
  }

  /**
   * Formats a not found error response.
   *
   * @param string $resource
   *   The resource type.
   * @param string|null $id
   *   Optional resource ID.
   *
   * @return array
   *   Formatted not found error response.
   */
  public function notFoundError(string $resource, ?string $id = NULL): array {
    $message = $id
      ? sprintf('%s with ID %s not found', ucfirst($resource), $id)
      : sprintf('%s not found', ucfirst($resource));

    return $this->error('NOT_FOUND', $message);
  }

  /**
   * Formats a server error response.
   *
   * @param string $message
   *   Error message.
   * @param string|null $trace_id
   *   Optional trace ID for debugging.
   *
   * @return array
   *   Formatted server error response.
   */
  public function serverError(string $message = 'An internal error occurred', ?string $trace_id = NULL): array {
    $details = [];
    if ($trace_id) {
      $details['trace_id'] = $trace_id;
    }

    return $this->error('SERVER_ERROR', $message, $details);
  }

  /**
   * Formats a paginated response.
   *
   * @param array $items
   *   The items.
   * @param int $total
   *   Total item count.
   * @param int $page
   *   Current page (1-based).
   * @param int $per_page
   *   Items per page.
   *
   * @return array
   *   Formatted paginated response.
   */
  public function paginated(array $items, int $total, int $page, int $per_page): array {
    $total_pages = (int) ceil($total / $per_page);

    return $this->success($items, [
      'pagination' => [
        'total' => $total,
        'per_page' => $per_page,
        'current_page' => $page,
        'total_pages' => $total_pages,
        'has_next' => $page < $total_pages,
        'has_prev' => $page > 1,
      ],
    ]);
  }

  /**
   * Gets the current ISO 8601 timestamp.
   *
   * @return string
   *   ISO 8601 timestamp.
   */
  protected function getTimestamp(): string {
    return gmdate('Y-m-d\TH:i:s\Z');
  }

}
