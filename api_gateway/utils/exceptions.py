class ServiceUnavailableError(Exception):
    code = "SERVICE_UNAVAILABLE"

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


class VRAMConflictError(Exception):
    code = "VRAM_CONFLICT"

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


class JobNotFoundError(Exception):
    code = "JOB_NOT_FOUND"

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


class InvalidAPIKeyError(Exception):
    code = "INVALID_API_KEY"

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


class JobTimeoutError(Exception):
    code = "JOB_TIMEOUT"

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)

