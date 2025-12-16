<?php

namespace Drupal\congressional_query\Exception;

/**
 * Exception for invalid API key errors.
 */
class InvalidApiKeyException extends ApiException {

  /**
   * Constructs an InvalidApiKeyException.
   *
   * @param string $message
   *   The error message.
   * @param array $details
   *   Additional details.
   * @param \Throwable|null $previous
   *   Previous exception.
   */
  public function __construct(
    string $message = 'Invalid or missing API key',
    array $details = [],
    ?\Throwable $previous = NULL
  ) {
    parent::__construct($message, 'INVALID_API_KEY', 401, $details, $previous);
  }

}
