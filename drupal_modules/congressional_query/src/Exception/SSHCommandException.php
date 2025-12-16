<?php

namespace Drupal\congressional_query\Exception;

/**
 * Exception for SSH command execution failures.
 */
class SSHCommandException extends \Exception {

  /**
   * The command that failed.
   *
   * @var string
   */
  protected $command;

  /**
   * The exit code from the command.
   *
   * @var int|null
   */
  protected $exitCode;

  /**
   * Standard error output.
   *
   * @var string
   */
  protected $stderr;

  /**
   * Constructs an SSHCommandException.
   *
   * @param string $message
   *   The exception message.
   * @param string $command
   *   The command that failed (may be sanitized).
   * @param int|null $exit_code
   *   The exit code.
   * @param string $stderr
   *   Standard error output.
   * @param \Throwable|null $previous
   *   The previous exception.
   */
  public function __construct(
    string $message,
    string $command = '',
    ?int $exit_code = NULL,
    string $stderr = '',
    ?\Throwable $previous = NULL
  ) {
    parent::__construct($message, 0, $previous);
    $this->command = $command;
    $this->exitCode = $exit_code;
    $this->stderr = $stderr;
  }

  /**
   * Get the command that failed.
   *
   * @return string
   *   The command.
   */
  public function getCommand(): string {
    return $this->command;
  }

  /**
   * Get the exit code.
   *
   * @return int|null
   *   The exit code.
   */
  public function getExitCode(): ?int {
    return $this->exitCode;
  }

  /**
   * Get standard error output.
   *
   * @return string
   *   The stderr.
   */
  public function getStderr(): string {
    return $this->stderr;
  }

}
