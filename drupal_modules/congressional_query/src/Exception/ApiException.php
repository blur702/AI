<?php

namespace Drupal\congressional_query\Exception;

/**
 * Base exception class for API errors.
 */
class ApiException extends \Exception {

  /**
   * The error code.
   *
   * @var string
   */
  protected $errorCode;

  /**
   * The HTTP status code.
   *
   * @var int
   */
  protected $statusCode;

  /**
   * Additional error details.
   *
   * @var array
   */
  protected $details;

  /**
   * Constructs an ApiException.
   *
   * @param string $message
   *   The error message.
   * @param string $error_code
   *   The error code.
   * @param int $status_code
   *   The HTTP status code.
   * @param array $details
   *   Additional details.
   * @param \Throwable|null $previous
   *   Previous exception.
   */
  public function __construct(
    string $message,
    string $error_code = 'API_ERROR',
    int $status_code = 500,
    array $details = [],
    ?\Throwable $previous = NULL
  ) {
    parent::__construct($message, 0, $previous);
    $this->errorCode = $error_code;
    $this->statusCode = $status_code;
    $this->details = $details;
  }

  /**
   * Gets the error code.
   *
   * @return string
   *   The error code.
   */
  public function getErrorCode(): string {
    return $this->errorCode;
  }

  /**
   * Gets the HTTP status code.
   *
   * @return int
   *   The status code.
   */
  public function getStatusCode(): int {
    return $this->statusCode;
  }

  /**
   * Gets additional details.
   *
   * @return array
   *   The details array.
   */
  public function getDetails(): array {
    return $this->details;
  }

  /**
   * Converts the exception to an API response array.
   *
   * @return array
   *   The response array.
   */
  public function toResponse(): array {
    $error = [
      'code' => $this->errorCode,
      'message' => $this->getMessage(),
    ];

    if (!empty($this->details)) {
      $error['details'] = $this->details;
    }

    return [
      'success' => FALSE,
      'error' => $error,
      'timestamp' => gmdate('Y-m-d\TH:i:s\Z'),
    ];
  }

}
