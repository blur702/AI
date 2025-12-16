<?php

namespace Drupal\congressional_query\Exception;

/**
 * Exception for SSH connection establishment failures.
 */
class SSHConnectionException extends \Exception {

  /**
   * The host that failed to connect.
   *
   * @var string
   */
  protected $host;

  /**
   * The port that was attempted.
   *
   * @var int
   */
  protected $port;

  /**
   * Number of connection attempts made.
   *
   * @var int
   */
  protected $attempts;

  /**
   * Constructs an SSHConnectionException.
   *
   * @param string $message
   *   The exception message.
   * @param string $host
   *   The host that failed.
   * @param int $port
   *   The port attempted.
   * @param int $attempts
   *   Number of attempts made.
   * @param \Throwable|null $previous
   *   The previous exception.
   */
  public function __construct(
    string $message,
    string $host = '',
    int $port = 22,
    int $attempts = 1,
    ?\Throwable $previous = NULL
  ) {
    parent::__construct($message, 0, $previous);
    $this->host = $host;
    $this->port = $port;
    $this->attempts = $attempts;
  }

  /**
   * Get the host that failed to connect.
   *
   * @return string
   *   The host.
   */
  public function getHost(): string {
    return $this->host;
  }

  /**
   * Get the port that was attempted.
   *
   * @return int
   *   The port.
   */
  public function getPort(): int {
    return $this->port;
  }

  /**
   * Get the number of connection attempts.
   *
   * @return int
   *   The attempts count.
   */
  public function getAttempts(): int {
    return $this->attempts;
  }

}
