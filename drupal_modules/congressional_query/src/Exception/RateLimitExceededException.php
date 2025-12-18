<?php

namespace Drupal\congressional_query\Exception;

/**
 * Exception for rate limit exceeded errors.
 */
class RateLimitExceededException extends ApiException {

  /**
   * The retry-after value in seconds.
   *
   * @var int
   */
  protected $retryAfter;

  /**
   * Constructs a RateLimitExceededException.
   *
   * @param int $retry_after
   *   Seconds until rate limit resets.
   * @param string $message
   *   The error message.
   * @param array $details
   *   Additional details.
   * @param \Throwable|null $previous
   *   Previous exception.
   */
  public function __construct(
    int $retry_after = 3600,
    string $message = 'Rate limit exceeded. Please try again later.',
    array $details = [],
    ?\Throwable $previous = NULL
  ) {
    $this->retryAfter = $retry_after;
    $details['retry_after'] = $retry_after;

    parent::__construct($message, 'RATE_LIMIT_EXCEEDED', 429, $details, $previous);
  }

  /**
   * Gets the retry-after value.
   *
   * @return int
   *   Seconds until rate limit resets.
   */
  public function getRetryAfter(): int {
    return $this->retryAfter;
  }

}
