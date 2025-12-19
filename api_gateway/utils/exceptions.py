"""
Custom exceptions for API Gateway.

Defines domain-specific exceptions with error codes for consistent
error handling across the application.
"""


class ServiceUnavailableError(Exception):
    """Raised when a requested AI service is not available."""

    code = "SERVICE_UNAVAILABLE"

    def __init__(self, message: str):
        """Initialize with error message."""
        self.message = message
        super().__init__(message)


class VRAMConflictError(Exception):
    """Raised when VRAM is insufficient or in conflict with other processes."""

    code = "VRAM_CONFLICT"

    def __init__(self, message: str):
        """Initialize with error message."""
        self.message = message
        super().__init__(message)


class JobNotFoundError(Exception):
    """Raised when a requested job ID does not exist."""

    code = "JOB_NOT_FOUND"

    def __init__(self, message: str):
        """Initialize with error message."""
        self.message = message
        super().__init__(message)


class InvalidAPIKeyError(Exception):
    """Raised when API key is missing, invalid, or inactive."""

    code = "INVALID_API_KEY"

    def __init__(self, message: str):
        """Initialize with error message."""
        self.message = message
        super().__init__(message)


class JobTimeoutError(Exception):
    """Raised when a job exceeds its configured timeout."""

    code = "JOB_TIMEOUT"

    def __init__(self, message: str):
        """Initialize with error message."""
        self.message = message
        super().__init__(message)
