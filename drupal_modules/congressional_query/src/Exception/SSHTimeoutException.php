<?php

namespace Drupal\congressional_query\Exception;

/**
 * Exception for SSH timeout errors.
 */
class SSHTimeoutException extends \Exception {

  /**
   * The operation that timed out.
   *
   * @var string
   */
  protected $operation;

  /**
   * The timeout value in seconds.
   *
   * @var int
   */
  protected $timeoutSeconds;

  /**
   * Constructs an SSHTimeoutException.
   *
   * @param string $message
   *   The exception message.
   * @param string $operation
   *   The operation that timed out.
   * @param int $timeout_seconds
   *   The timeout value.
   * @param \Throwable|null $previous
   *   The previous exception.
   */
  public function __construct(
    string $message,
    string $operation = 'connection',
    int $timeout_seconds = 30,
    ?\Throwable $previous = NULL
  ) {
    parent::__construct($message, 0, $previous);
    $this->operation = $operation;
    $this->timeoutSeconds = $timeout_seconds;
  }

  /**
   * Get the operation that timed out.
   *
   * @return string
   *   The operation.
   */
  public function getOperation(): string {
    return $this->operation;
  }

  /**
   * Get the timeout value.
   *
   * @return int
   *   Timeout in seconds.
   */
  public function getTimeoutSeconds(): int {
    return $this->timeoutSeconds;
  }

}
