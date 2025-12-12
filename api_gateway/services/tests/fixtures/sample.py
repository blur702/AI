"""
Sample Python module for testing the code parser.

This module contains various Python constructs to test the parser's
ability to extract functions, classes, variables, and other entities.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional, TypeVar

# Module-level constant
DEFAULT_TIMEOUT: int = 30

# Module-level variable without annotation
MAX_RETRIES = 3

# Type variable for generics
T = TypeVar("T")


def simple_function(x: int, y: int) -> int:
    """
    Add two numbers together.

    Args:
        x: First number
        y: Second number

    Returns:
        Sum of x and y
    """
    return x + y


def function_with_defaults(
    name: str,
    count: int = 10,
    enabled: bool = True,
    options: Optional[Dict[str, Any]] = None,
) -> str:
    """Function with default parameter values."""
    return f"{name}: {count}, enabled={enabled}"


async def async_function(url: str) -> Dict[str, Any]:
    """
    Asynchronous function that fetches data.

    Args:
        url: The URL to fetch

    Returns:
        Response data as dictionary
    """
    return {"url": url, "status": "ok"}


@dataclass
class SimpleDataclass:
    """A simple dataclass with typed fields."""

    name: str
    value: int
    enabled: bool = True


class BaseService:
    """Base class for services."""

    def __init__(self, name: str) -> None:
        """Initialize the service with a name."""
        self.name = name

    def get_name(self) -> str:
        """Return the service name."""
        return self.name


class AdvancedService(BaseService):
    """
    Advanced service with more features.

    This class extends BaseService with additional functionality
    including configuration management and async operations.
    """

    def __init__(
        self,
        name: str,
        config: Optional[Dict[str, Any]] = None,
        timeout: int = DEFAULT_TIMEOUT,
    ) -> None:
        """
        Initialize the advanced service.

        Args:
            name: Service name
            config: Optional configuration dictionary
            timeout: Request timeout in seconds
        """
        super().__init__(name)
        self.config = config or {}
        self.timeout = timeout

    @property
    def is_configured(self) -> bool:
        """Check if the service has configuration."""
        return bool(self.config)

    @staticmethod
    def validate_config(config: Dict[str, Any]) -> bool:
        """
        Validate a configuration dictionary.

        Args:
            config: Configuration to validate

        Returns:
            True if valid, False otherwise
        """
        return "name" in config

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AdvancedService":
        """
        Create an instance from a dictionary.

        Args:
            data: Dictionary with service data

        Returns:
            New AdvancedService instance
        """
        return cls(
            name=data.get("name", "default"),
            config=data.get("config"),
            timeout=data.get("timeout", DEFAULT_TIMEOUT),
        )

    async def fetch_data(self, endpoint: str) -> Dict[str, Any]:
        """
        Fetch data from an endpoint asynchronously.

        Args:
            endpoint: API endpoint path

        Returns:
            Response data
        """
        return {"endpoint": endpoint, "service": self.name}

    class NestedHelper:
        """A nested helper class."""

        def __init__(self, parent: "AdvancedService") -> None:
            self.parent = parent

        def get_parent_name(self) -> str:
            """Get the parent service name."""
            return self.parent.name


# Annotated variable with complex type
service_registry: Dict[str, BaseService] = {}


def _private_helper(data: Any) -> str:
    """Private helper function."""
    return str(data)


def function_with_varargs(
    *args: int,
    multiplier: int = 1,
    **kwargs: str,
) -> Dict[str, Any]:
    """
    Function with *args, keyword-only args, and **kwargs.

    Args:
        *args: Variable positional arguments
        multiplier: Keyword-only argument with default
        **kwargs: Variable keyword arguments

    Returns:
        Dictionary with processed arguments
    """
    return {
        "sum": sum(args) * multiplier,
        "kwargs": kwargs,
    }


def outer_function(x: int) -> int:
    """
    Outer function that contains a nested function.

    Args:
        x: Input value

    Returns:
        Processed value from nested function
    """
    def inner_function(y: int) -> int:
        """Nested inner function that doubles the value."""
        return y * 2

    return inner_function(x) + x
