<?php

namespace Drupal\congressional_query\Exception;

/**
 * Exception for validation errors.
 */
class ValidationException extends ApiException {

  /**
   * Field-level validation errors.
   *
   * @var array
   */
  protected $fieldErrors;

  /**
   * Constructs a ValidationException.
   *
   * @param array $field_errors
   *   Array of field => error message.
   * @param string $message
   *   The error message.
   * @param \Throwable|null $previous
   *   Previous exception.
   */
  public function __construct(
    array $field_errors = [],
    string $message = 'Validation failed',
    ?\Throwable $previous = NULL
  ) {
    $this->fieldErrors = $field_errors;

    parent::__construct(
      $message,
      'VALIDATION_ERROR',
      400,
      ['fields' => $field_errors],
      $previous
    );
  }

  /**
   * Gets the field errors.
   *
   * @return array
   *   Field errors array.
   */
  public function getFieldErrors(): array {
    return $this->fieldErrors;
  }

}
