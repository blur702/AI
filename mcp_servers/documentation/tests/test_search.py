"""
Unit tests for MCP Documentation Search server.

Uses mocking to avoid requiring a running Weaviate instance.
"""

from __future__ import annotations

import logging
import sys
import unittest
from unittest.mock import MagicMock, patch


class TestSearchDocumentation(unittest.TestCase):
    """Tests for the search_documentation function."""

    def setUp(self) -> None:
        """Set up test fixtures."""
        # Mock objects for Weaviate responses
        self.mock_obj1 = MagicMock()
        self.mock_obj1.properties = {
            "title": "Getting Started",
            "content": "This is the getting started guide.",
            "file_path": "docs/getting-started.md",
            "section": "h1",
        }

        self.mock_obj2 = MagicMock()
        self.mock_obj2.properties = {
            "title": "Installation",
            "content": "Installation instructions here.",
            "file_path": "docs/getting-started.md",
            "section": "h2",
        }

    @patch("mcp_servers.documentation.main.WeaviateConnection")
    def test_search_documentation_success(self, mock_conn_class: MagicMock) -> None:
        """Test successful documentation search."""
        from mcp_servers.documentation.main import search_documentation

        # Set up mock client
        mock_client = MagicMock()
        mock_conn_class.return_value.__enter__.return_value = mock_client
        mock_conn_class.return_value.__exit__.return_value = None

        # Mock collection exists
        mock_client.collections.exists.return_value = True

        # Mock collection query
        mock_collection = MagicMock()
        mock_client.collections.get.return_value = mock_collection

        mock_response = MagicMock()
        mock_response.objects = [self.mock_obj1, self.mock_obj2]
        mock_collection.query.near_text.return_value = mock_response

        # Execute search
        results = search_documentation("getting started", limit=5)

        # Verify results - should be a list on success
        self.assertIsInstance(results, list)
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0]["title"], "Getting Started")
        self.assertEqual(results[0]["file_path"], "docs/getting-started.md")
        self.assertEqual(results[1]["title"], "Installation")

        # Verify query was called correctly
        mock_collection.query.near_text.assert_called_once_with(
            query="getting started",
            limit=5,
        )

    @patch("mcp_servers.documentation.main.WeaviateConnection")
    def test_search_documentation_empty(self, mock_conn_class: MagicMock) -> None:
        """Test search with no results."""
        from mcp_servers.documentation.main import search_documentation

        mock_client = MagicMock()
        mock_conn_class.return_value.__enter__.return_value = mock_client
        mock_conn_class.return_value.__exit__.return_value = None

        mock_client.collections.exists.return_value = True

        mock_collection = MagicMock()
        mock_client.collections.get.return_value = mock_collection

        mock_response = MagicMock()
        mock_response.objects = []
        mock_collection.query.near_text.return_value = mock_response

        results = search_documentation("nonexistent topic")

        self.assertIsInstance(results, list)
        self.assertEqual(len(results), 0)

    @patch("mcp_servers.documentation.main.WeaviateConnection")
    def test_search_documentation_collection_not_exists(self, mock_conn_class: MagicMock) -> None:
        """Test search when collection doesn't exist returns error dict."""
        from mcp_servers.documentation.main import search_documentation

        mock_client = MagicMock()
        mock_conn_class.return_value.__enter__.return_value = mock_client
        mock_conn_class.return_value.__exit__.return_value = None

        mock_client.collections.exists.return_value = False

        results = search_documentation("test query")

        # Should return error dict, not empty list
        self.assertIsInstance(results, dict)
        self.assertEqual(results["error"], "collection_not_found")
        mock_client.collections.get.assert_not_called()

    @patch("mcp_servers.documentation.main.WeaviateConnection")
    def test_search_documentation_connection_error(self, mock_conn_class: MagicMock) -> None:
        """Test search with connection error returns error dict."""
        from mcp_servers.documentation.main import search_documentation

        mock_conn_class.return_value.__enter__.side_effect = ConnectionError("Failed to connect")

        results = search_documentation("test query")

        # Should return error dict with connection_failed
        self.assertIsInstance(results, dict)
        self.assertEqual(results["error"], "connection_failed")
        self.assertIn("message", results)

    @patch("mcp_servers.documentation.main.WeaviateConnection")
    def test_search_documentation_query_error(self, mock_conn_class: MagicMock) -> None:
        """Test search with query execution error returns error dict."""
        from mcp_servers.documentation.main import search_documentation

        mock_client = MagicMock()
        mock_conn_class.return_value.__enter__.return_value = mock_client
        mock_conn_class.return_value.__exit__.return_value = None

        mock_client.collections.exists.return_value = True

        mock_collection = MagicMock()
        mock_client.collections.get.return_value = mock_collection
        mock_collection.query.near_text.side_effect = Exception("Query failed")

        results = search_documentation("test query")

        # Should return error dict with query_failed
        self.assertIsInstance(results, dict)
        self.assertEqual(results["error"], "query_failed")
        self.assertIn("message", results)

    @patch("mcp_servers.documentation.main.WeaviateConnection")
    def test_search_documentation_limit_parameter(self, mock_conn_class: MagicMock) -> None:
        """Test that limit parameter is correctly passed."""
        from mcp_servers.documentation.main import search_documentation

        mock_client = MagicMock()
        mock_conn_class.return_value.__enter__.return_value = mock_client
        mock_conn_class.return_value.__exit__.return_value = None

        mock_client.collections.exists.return_value = True

        mock_collection = MagicMock()
        mock_client.collections.get.return_value = mock_collection

        mock_response = MagicMock()
        mock_response.objects = []
        mock_collection.query.near_text.return_value = mock_response

        # Test with default limit
        search_documentation("test")
        mock_collection.query.near_text.assert_called_with(query="test", limit=10)

        # Test with custom limit
        search_documentation("test", limit=25)
        mock_collection.query.near_text.assert_called_with(query="test", limit=25)

    def test_search_documentation_invalid_limit_negative(self) -> None:
        """Test that negative limit returns error dict."""
        from mcp_servers.documentation.main import search_documentation

        results = search_documentation("test", limit=-5)

        self.assertIsInstance(results, dict)
        self.assertEqual(results["error"], "invalid_limit")
        self.assertIn("message", results)
        self.assertIn("-5", results["message"])

    def test_search_documentation_invalid_limit_zero(self) -> None:
        """Test that zero limit returns error dict."""
        from mcp_servers.documentation.main import search_documentation

        results = search_documentation("test", limit=0)

        self.assertIsInstance(results, dict)
        self.assertEqual(results["error"], "invalid_limit")
        self.assertIn("message", results)

    def test_search_documentation_invalid_limit_too_large(self) -> None:
        """Test that limit > 100 returns error dict."""
        from mcp_servers.documentation.main import search_documentation

        results = search_documentation("test", limit=150)

        self.assertIsInstance(results, dict)
        self.assertEqual(results["error"], "invalid_limit")
        self.assertIn("message", results)
        self.assertIn("150", results["message"])

    @patch("mcp_servers.documentation.main.WeaviateConnection")
    def test_search_documentation_limit_boundary_min(self, mock_conn_class: MagicMock) -> None:
        """Test that limit=1 (minimum) is accepted."""
        from mcp_servers.documentation.main import search_documentation

        mock_client = MagicMock()
        mock_conn_class.return_value.__enter__.return_value = mock_client
        mock_conn_class.return_value.__exit__.return_value = None

        mock_client.collections.exists.return_value = True

        mock_collection = MagicMock()
        mock_client.collections.get.return_value = mock_collection

        mock_response = MagicMock()
        mock_response.objects = []
        mock_collection.query.near_text.return_value = mock_response

        results = search_documentation("test", limit=1)

        # Should succeed, not return error
        self.assertIsInstance(results, list)
        mock_collection.query.near_text.assert_called_with(query="test", limit=1)

    @patch("mcp_servers.documentation.main.WeaviateConnection")
    def test_search_documentation_limit_boundary_max(self, mock_conn_class: MagicMock) -> None:
        """Test that limit=100 (maximum) is accepted."""
        from mcp_servers.documentation.main import search_documentation

        mock_client = MagicMock()
        mock_conn_class.return_value.__enter__.return_value = mock_client
        mock_conn_class.return_value.__exit__.return_value = None

        mock_client.collections.exists.return_value = True

        mock_collection = MagicMock()
        mock_client.collections.get.return_value = mock_collection

        mock_response = MagicMock()
        mock_response.objects = []
        mock_collection.query.near_text.return_value = mock_response

        results = search_documentation("test", limit=100)

        # Should succeed, not return error
        self.assertIsInstance(results, list)
        mock_collection.query.near_text.assert_called_with(query="test", limit=100)

    @patch("mcp_servers.documentation.main.WeaviateConnection")
    def test_search_documentation_missing_properties(self, mock_conn_class: MagicMock) -> None:
        """Test handling of results with missing properties."""
        from mcp_servers.documentation.main import search_documentation

        mock_client = MagicMock()
        mock_conn_class.return_value.__enter__.return_value = mock_client
        mock_conn_class.return_value.__exit__.return_value = None

        mock_client.collections.exists.return_value = True

        mock_collection = MagicMock()
        mock_client.collections.get.return_value = mock_collection

        # Object with missing properties
        mock_obj = MagicMock()
        mock_obj.properties = {"title": "Only Title"}

        mock_response = MagicMock()
        mock_response.objects = [mock_obj]
        mock_collection.query.near_text.return_value = mock_response

        results = search_documentation("test")

        self.assertIsInstance(results, list)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["title"], "Only Title")
        self.assertEqual(results[0]["content"], "")
        self.assertEqual(results[0]["file_path"], "")
        self.assertEqual(results[0]["section"], "")


class TestLoggingConfiguration(unittest.TestCase):
    """Tests for logging configuration."""

    def test_logging_to_stderr(self) -> None:
        """Verify logging goes to stderr, not stdout."""
        # Import the actual logger from the module
        from mcp_servers.documentation.main import logger

        # Verify logger has at least one handler
        self.assertGreater(len(logger.handlers), 0, "Logger should have at least one handler")

        # Find StreamHandler that writes to stderr
        stderr_handler = None
        for (
            handler
        ) in logging.getLogger().handlers:  # Check root logger handlers set by basicConfig
            if isinstance(handler, logging.StreamHandler) and handler.stream == sys.stderr:
                stderr_handler = handler
                break

        self.assertIsNotNone(
            stderr_handler, "Logger should have a StreamHandler writing to sys.stderr"
        )

        # Verify handler level is INFO or lower (allows INFO messages)
        self.assertLessEqual(
            stderr_handler.level, logging.INFO, "Handler level should be INFO or lower"
        )

        # Verify formatter exists and has expected pattern
        self.assertIsNotNone(stderr_handler.formatter, "Handler should have a formatter")
        format_string = stderr_handler.formatter._fmt
        self.assertIn("%(levelname)s", format_string, "Formatter should include log level")
        self.assertIn("%(name)s", format_string, "Formatter should include logger name")
        self.assertIn("%(message)s", format_string, "Formatter should include message")


class TestSettings(unittest.TestCase):
    """Tests for settings configuration."""

    def test_settings_defaults(self) -> None:
        """Test that settings have expected defaults."""
        from mcp_servers.documentation import settings

        self.assertEqual(settings.WEAVIATE_URL, "http://localhost:8080")
        self.assertEqual(settings.WEAVIATE_GRPC_HOST, "localhost")
        self.assertIsInstance(settings.WEAVIATE_GRPC_PORT, int)
        self.assertEqual(settings.WEAVIATE_GRPC_PORT, 50051)

    def test_documentation_collection_name(self) -> None:
        """Test that collection name matches doc_ingestion."""
        from api_gateway.services.weaviate_connection import DOCUMENTATION_COLLECTION_NAME

        self.assertEqual(DOCUMENTATION_COLLECTION_NAME, "Documentation")


class TestLimitConstants(unittest.TestCase):
    """Tests for limit validation constants."""

    def test_limit_constants_defined(self) -> None:
        """Test that MIN_LIMIT and MAX_LIMIT are defined."""
        from mcp_servers.documentation.main import MAX_LIMIT, MIN_LIMIT

        self.assertEqual(MIN_LIMIT, 1)
        self.assertEqual(MAX_LIMIT, 100)


if __name__ == "__main__":
    unittest.main()
