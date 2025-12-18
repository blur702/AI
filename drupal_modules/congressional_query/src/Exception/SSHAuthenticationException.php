<?php

namespace Drupal\congressional_query\Exception;

/**
 * Exception for SSH authentication failures.
 */
class SSHAuthenticationException extends \Exception {

  /**
   * The authentication method that was attempted.
   *
   * @var string
   */
  protected $authMethod;

  /**
   * The username that failed authentication.
   *
   * @var string
   */
  protected $username;

  /**
   * Constructs an SSHAuthenticationException.
   *
   * @param string $message
   *   The exception message.
   * @param string $username
   *   The username that failed.
   * @param string $auth_method
   *   The auth method attempted (password, key).
   * @param \Throwable|null $previous
   *   The previous exception.
   */
  public function __construct(
    string $message,
    string $username = '',
    string $auth_method = 'password',
    ?\Throwable $previous = NULL
  ) {
    parent::__construct($message, 0, $previous);
    $this->username = $username;
    $this->authMethod = $auth_method;
  }

  /**
   * Get the authentication method.
   *
   * @return string
   *   The auth method.
   */
  public function getAuthMethod(): string {
    return $this->authMethod;
  }

  /**
   * Get the username.
   *
   * @return string
   *   The username.
   */
  public function getUsername(): string {
    return $this->username;
  }

}
