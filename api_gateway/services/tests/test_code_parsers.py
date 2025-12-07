"""
Unit tests for the code parser system.

Tests all language-specific parsers (Python, TypeScript/JavaScript, CSS)
and the unified CodeParser interface.

Usage:
    python -m unittest api_gateway.services.tests.test_code_parsers
    python -m unittest api_gateway.services.tests.test_code_parsers -v
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from api_gateway.services.code_entity_schema import CodeEntity
from api_gateway.services.code_parsers import (
    CodeParser,
    CSSParser,
    PythonParser,
    TypeScriptParser,
    _build_full_name,
    _relative_to_workspace,
    _serialize_decorators,
    _serialize_parameters,
    get_supported_extensions,
    is_supported,
    parse_file,
)

# Path to test fixtures
FIXTURES_DIR = Path(__file__).parent / "fixtures"


# =============================================================================
# Helper Function Tests
# =============================================================================


class TestHelperFunctions(unittest.TestCase):
    """Tests for module-level helper functions."""

    def test_serialize_parameters(self) -> None:
        """Test parameter list serialization to JSON."""
        params = [
            {"name": "x", "type": "int", "default": None},
            {"name": "y", "type": "str", "default": "hello"},
        ]
        result = _serialize_parameters(params)
        self.assertEqual(json.loads(result), params)

    def test_serialize_decorators(self) -> None:
        """Test decorator list serialization to JSON."""
        decorators = ["@staticmethod", "@property"]
        result = _serialize_decorators(decorators)
        self.assertEqual(json.loads(result), decorators)

    def test_build_full_name_without_parent(self) -> None:
        """Test full name generation without parent entity."""
        path = FIXTURES_DIR / "sample.py"
        result = _build_full_name(path, "my_function")
        self.assertIn("sample.my_function", result)

    def test_build_full_name_with_parent(self) -> None:
        """Test full name generation with parent entity."""
        path = FIXTURES_DIR / "sample.py"
        result = _build_full_name(path, "method_name", parent="MyClass")
        self.assertIn("MyClass.method_name", result)


# =============================================================================
# Python Parser Tests
# =============================================================================


class TestPythonParser(unittest.TestCase):
    """Tests for the Python AST parser."""

    @classmethod
    def setUpClass(cls) -> None:
        """Set up test fixtures."""
        cls.parser = PythonParser()
        cls.sample_file = FIXTURES_DIR / "sample.py"
        if cls.sample_file.exists():
            cls.entities = cls.parser.parse_file(cls.sample_file)
        else:
            cls.entities = []

    def test_parser_language(self) -> None:
        """Test that parser identifies as Python."""
        self.assertEqual(self.parser.language, "python")

    def test_parses_sample_file(self) -> None:
        """Test that sample file parses successfully."""
        if not self.sample_file.exists():
            self.skipTest("Sample file not found")
        self.assertGreater(len(self.entities), 0)

    def test_extracts_simple_function(self) -> None:
        """Test extraction of a simple function."""
        if not self.sample_file.exists():
            self.skipTest("Sample file not found")

        func = next(
            (e for e in self.entities if e.name == "simple_function"),
            None,
        )
        self.assertIsNotNone(func)
        self.assertEqual(func.entity_type, "function")
        self.assertEqual(func.return_type, "int")
        self.assertIn("x", func.parameters)
        self.assertIn("y", func.parameters)
        self.assertIn("Add two numbers", func.docstring)

    def test_extracts_async_function(self) -> None:
        """Test extraction of an async function."""
        if not self.sample_file.exists():
            self.skipTest("Sample file not found")

        func = next(
            (e for e in self.entities if e.name == "async_function"),
            None,
        )
        self.assertIsNotNone(func)
        self.assertEqual(func.entity_type, "function")
        self.assertIn("async", func.modifiers)

    def test_extracts_function_with_defaults(self) -> None:
        """Test extraction of function with default parameters."""
        if not self.sample_file.exists():
            self.skipTest("Sample file not found")

        func = next(
            (e for e in self.entities if e.name == "function_with_defaults"),
            None,
        )
        self.assertIsNotNone(func)
        params = json.loads(func.parameters)
        # Find the 'count' parameter
        count_param = next((p for p in params if p["name"] == "count"), None)
        self.assertIsNotNone(count_param)
        self.assertEqual(count_param["default"], "10")

    def test_extracts_class(self) -> None:
        """Test extraction of a class."""
        if not self.sample_file.exists():
            self.skipTest("Sample file not found")

        cls = next(
            (e for e in self.entities if e.name == "BaseService"),
            None,
        )
        self.assertIsNotNone(cls)
        self.assertEqual(cls.entity_type, "class")
        self.assertIn("Base class for services", cls.docstring)

    def test_extracts_class_with_inheritance(self) -> None:
        """Test extraction of class with base classes."""
        if not self.sample_file.exists():
            self.skipTest("Sample file not found")

        cls = next(
            (e for e in self.entities if e.name == "AdvancedService"),
            None,
        )
        self.assertIsNotNone(cls)
        self.assertIn("BaseService", cls.signature)
        relationships = json.loads(cls.relationships)
        self.assertIn("BaseService", relationships.get("inherits", []))

    def test_extracts_methods_with_parent(self) -> None:
        """Test that methods have correct parent_entity."""
        if not self.sample_file.exists():
            self.skipTest("Sample file not found")

        method = next(
            (e for e in self.entities if e.name == "get_name" and e.parent_entity == "BaseService"),
            None,
        )
        self.assertIsNotNone(method)
        self.assertEqual(method.entity_type, "method")
        self.assertEqual(method.parent_entity, "BaseService")

    def test_extracts_staticmethod(self) -> None:
        """Test extraction of static method with decorator."""
        if not self.sample_file.exists():
            self.skipTest("Sample file not found")

        method = next(
            (e for e in self.entities if e.name == "validate_config"),
            None,
        )
        self.assertIsNotNone(method)
        self.assertIn("staticmethod", method.modifiers)
        decorators = json.loads(method.decorators)
        self.assertIn("@staticmethod", decorators)

    def test_extracts_classmethod(self) -> None:
        """Test extraction of class method with decorator."""
        if not self.sample_file.exists():
            self.skipTest("Sample file not found")

        method = next(
            (e for e in self.entities if e.name == "from_dict"),
            None,
        )
        self.assertIsNotNone(method)
        self.assertIn("classmethod", method.modifiers)

    def test_extracts_property(self) -> None:
        """Test extraction of property decorator."""
        if not self.sample_file.exists():
            self.skipTest("Sample file not found")

        prop = next(
            (e for e in self.entities if e.name == "is_configured"),
            None,
        )
        self.assertIsNotNone(prop)
        self.assertIn("property", prop.modifiers)

    def test_extracts_dataclass(self) -> None:
        """Test extraction of dataclass."""
        if not self.sample_file.exists():
            self.skipTest("Sample file not found")

        cls = next(
            (e for e in self.entities if e.name == "SimpleDataclass"),
            None,
        )
        self.assertIsNotNone(cls)
        decorators = json.loads(cls.decorators)
        self.assertTrue(any("dataclass" in d for d in decorators))

    def test_extracts_module_variable(self) -> None:
        """Test extraction of module-level variables."""
        if not self.sample_file.exists():
            self.skipTest("Sample file not found")

        var = next(
            (e for e in self.entities if e.name == "DEFAULT_TIMEOUT"),
            None,
        )
        self.assertIsNotNone(var)
        self.assertEqual(var.entity_type, "variable")
        self.assertEqual(var.return_type, "int")

    def test_line_numbers_accurate(self) -> None:
        """Test that line numbers are accurate."""
        if not self.sample_file.exists():
            self.skipTest("Sample file not found")

        func = next(
            (e for e in self.entities if e.name == "simple_function"),
            None,
        )
        self.assertIsNotNone(func)
        self.assertGreater(func.line_start, 0)
        self.assertGreaterEqual(func.line_end, func.line_start)

    def test_source_code_extracted(self) -> None:
        """Test that source code is extracted."""
        if not self.sample_file.exists():
            self.skipTest("Sample file not found")

        func = next(
            (e for e in self.entities if e.name == "simple_function"),
            None,
        )
        self.assertIsNotNone(func)
        self.assertIn("def simple_function", func.source_code)
        self.assertIn("return x + y", func.source_code)

    def test_imports_extracted(self) -> None:
        """Test that import dependencies are extracted."""
        if not self.sample_file.exists():
            self.skipTest("Sample file not found")

        func = next(
            (e for e in self.entities if e.name == "simple_function"),
            None,
        )
        self.assertIsNotNone(func)
        dependencies = json.loads(func.dependencies)
        self.assertIn("json", dependencies)

    def test_handles_syntax_error(self) -> None:
        """Test that syntax errors are handled gracefully."""
        with patch.object(Path, "read_text", return_value="def broken("):
            result = self.parser.parse_file(Path("fake.py"))
        self.assertEqual(result, [])

    def test_handles_missing_file(self) -> None:
        """Test handling of missing files."""
        result = self.parser.parse_file(Path("nonexistent.py"))
        self.assertEqual(result, [])

    def test_to_properties_works(self) -> None:
        """Test that CodeEntity.to_properties() works for Weaviate."""
        if not self.sample_file.exists():
            self.skipTest("Sample file not found")

        if self.entities:
            entity = self.entities[0]
            props = entity.to_properties()
            self.assertIn("entity_type", props)
            self.assertIn("name", props)
            self.assertIn("source_code", props)

    def test_extracts_varargs_and_kwargs(self) -> None:
        """Test extraction of *args, keyword-only args, and **kwargs."""
        if not self.sample_file.exists():
            self.skipTest("Sample file not found")

        func = next(
            (e for e in self.entities if e.name == "function_with_varargs"),
            None,
        )
        self.assertIsNotNone(func)
        params = json.loads(func.parameters)

        # Check for *args with kind="vararg"
        vararg = next((p for p in params if p.get("kind") == "vararg"), None)
        self.assertIsNotNone(vararg)
        self.assertEqual(vararg["name"], "*args")
        self.assertEqual(vararg["type"], "int")

        # Check for keyword-only arg with kind="kwonly"
        kwonly = next((p for p in params if p.get("kind") == "kwonly"), None)
        self.assertIsNotNone(kwonly)
        self.assertEqual(kwonly["name"], "multiplier")
        self.assertEqual(kwonly["default"], "1")

        # Check for **kwargs with kind="kwarg"
        kwarg = next((p for p in params if p.get("kind") == "kwarg"), None)
        self.assertIsNotNone(kwarg)
        self.assertEqual(kwarg["name"], "**kwargs")
        self.assertEqual(kwarg["type"], "str")

    def test_extracts_nested_function(self) -> None:
        """Test extraction of nested functions with correct parent_entity."""
        if not self.sample_file.exists():
            self.skipTest("Sample file not found")

        # Check outer function
        outer = next(
            (e for e in self.entities if e.name == "outer_function"),
            None,
        )
        self.assertIsNotNone(outer)
        self.assertEqual(outer.entity_type, "function")
        self.assertEqual(outer.parent_entity, "")

        # Check nested inner function
        inner = next(
            (e for e in self.entities if e.name == "inner_function"),
            None,
        )
        self.assertIsNotNone(inner)
        self.assertEqual(inner.entity_type, "function")
        self.assertEqual(inner.parent_entity, "outer_function")
        self.assertIn("outer_function.inner_function", inner.full_name)

    def test_parameter_kind_field_exists(self) -> None:
        """Test that all parameters have a 'kind' field."""
        if not self.sample_file.exists():
            self.skipTest("Sample file not found")

        func = next(
            (e for e in self.entities if e.name == "simple_function"),
            None,
        )
        self.assertIsNotNone(func)
        params = json.loads(func.parameters)
        for param in params:
            self.assertIn("kind", param)
            self.assertEqual(param["kind"], "positional")


# =============================================================================
# TypeScript Parser Tests
# =============================================================================


class TestTypeScriptParser(unittest.TestCase):
    """Tests for the TypeScript/JavaScript parser."""

    @classmethod
    def setUpClass(cls) -> None:
        """Set up test fixtures."""
        cls.ts_parser = TypeScriptParser(file_extension=".ts")
        cls.js_parser = TypeScriptParser(file_extension=".js")
        cls.ts_file = FIXTURES_DIR / "sample.ts"
        cls.js_file = FIXTURES_DIR / "sample.js"

    def test_ts_parser_language(self) -> None:
        """Test that TypeScript parser identifies correctly."""
        self.assertEqual(self.ts_parser.language, "typescript")

    def test_js_parser_language(self) -> None:
        """Test that JavaScript parser identifies correctly."""
        self.assertEqual(self.js_parser.language, "javascript")

    @unittest.skipUnless(
        FIXTURES_DIR.joinpath("sample.ts").exists(),
        "TypeScript fixture not found",
    )
    def test_parses_typescript_file(self) -> None:
        """Test parsing of TypeScript file."""
        # Skip if Node.js not available
        import shutil
        if not shutil.which("node"):
            self.skipTest("Node.js not found")

        entities = self.ts_parser.parse_file(self.ts_file)
        self.assertGreater(len(entities), 0)

    @unittest.skipUnless(
        FIXTURES_DIR.joinpath("sample.ts").exists(),
        "TypeScript fixture not found",
    )
    def test_extracts_interface(self) -> None:
        """Test extraction of TypeScript interface."""
        import shutil
        if not shutil.which("node"):
            self.skipTest("Node.js not found")

        entities = self.ts_parser.parse_file(self.ts_file)
        interface = next(
            (e for e in entities if e.name == "ServiceConfig"),
            None,
        )
        self.assertIsNotNone(interface)
        self.assertEqual(interface.entity_type, "interface")
        self.assertIn("interface ServiceConfig", interface.signature)

    @unittest.skipUnless(
        FIXTURES_DIR.joinpath("sample.ts").exists(),
        "TypeScript fixture not found",
    )
    def test_extracts_type_alias(self) -> None:
        """Test extraction of TypeScript type alias."""
        import shutil
        if not shutil.which("node"):
            self.skipTest("Node.js not found")

        entities = self.ts_parser.parse_file(self.ts_file)
        type_alias = next(
            (e for e in entities if e.name == "ServiceStatus"),
            None,
        )
        self.assertIsNotNone(type_alias)
        self.assertEqual(type_alias.entity_type, "type")

    @unittest.skipUnless(
        FIXTURES_DIR.joinpath("sample.ts").exists(),
        "TypeScript fixture not found",
    )
    def test_extracts_class_with_extends(self) -> None:
        """Test extraction of class with inheritance."""
        import shutil
        if not shutil.which("node"):
            self.skipTest("Node.js not found")

        entities = self.ts_parser.parse_file(self.ts_file)
        cls = next(
            (e for e in entities if e.name == "ConfiguredService"),
            None,
        )
        self.assertIsNotNone(cls)
        self.assertEqual(cls.entity_type, "class")
        self.assertIn("extends BaseService", cls.signature)

    @unittest.skipUnless(
        FIXTURES_DIR.joinpath("sample.ts").exists(),
        "TypeScript fixture not found",
    )
    def test_extracts_async_function(self) -> None:
        """Test extraction of async function."""
        import shutil
        if not shutil.which("node"):
            self.skipTest("Node.js not found")

        entities = self.ts_parser.parse_file(self.ts_file)
        func = next(
            (e for e in entities if e.name == "fetchData"),
            None,
        )
        self.assertIsNotNone(func)
        self.assertIn("async", func.modifiers)

    @unittest.skipUnless(
        FIXTURES_DIR.joinpath("sample.ts").exists(),
        "TypeScript fixture not found",
    )
    def test_extracts_arrow_function(self) -> None:
        """Test extraction of arrow function assigned to variable."""
        import shutil
        if not shutil.which("node"):
            self.skipTest("Node.js not found")

        entities = self.ts_parser.parse_file(self.ts_file)
        func = next(
            (e for e in entities if e.name == "multiply"),
            None,
        )
        self.assertIsNotNone(func)
        self.assertEqual(func.entity_type, "function")

    @unittest.skipUnless(
        FIXTURES_DIR.joinpath("sample.ts").exists(),
        "TypeScript fixture not found",
    )
    def test_extracts_enum(self) -> None:
        """Test extraction of TypeScript enum."""
        import shutil
        if not shutil.which("node"):
            self.skipTest("Node.js not found")

        entities = self.ts_parser.parse_file(self.ts_file)
        enum = next(
            (e for e in entities if e.name == "LogLevel"),
            None,
        )
        self.assertIsNotNone(enum)
        self.assertEqual(enum.entity_type, "enum")

    @unittest.skipUnless(
        FIXTURES_DIR.joinpath("sample.ts").exists(),
        "TypeScript fixture not found",
    )
    def test_extracts_jsdoc_as_docstring(self) -> None:
        """Test that JSDoc comments are extracted as docstrings."""
        import shutil
        if not shutil.which("node"):
            self.skipTest("Node.js not found")

        entities = self.ts_parser.parse_file(self.ts_file)
        func = next(
            (e for e in entities if e.name == "add"),
            None,
        )
        self.assertIsNotNone(func)
        self.assertIn("Simple utility function", func.docstring)

    @unittest.skipUnless(
        FIXTURES_DIR.joinpath("sample.ts").exists(),
        "TypeScript fixture not found",
    )
    def test_extracts_method_modifiers(self) -> None:
        """Test extraction of method modifiers (static, async, public/private)."""
        import shutil
        if not shutil.which("node"):
            self.skipTest("Node.js not found")

        entities = self.ts_parser.parse_file(self.ts_file)
        method = next(
            (e for e in entities if e.name == "fromConfig" and e.parent_entity == "ConfiguredService"),
            None,
        )
        self.assertIsNotNone(method)
        self.assertIn("static", method.modifiers)

    @unittest.skipUnless(
        FIXTURES_DIR.joinpath("sample.js").exists(),
        "JavaScript fixture not found",
    )
    def test_parses_javascript_file(self) -> None:
        """Test parsing of JavaScript file."""
        import shutil
        if not shutil.which("node"):
            self.skipTest("Node.js not found")

        entities = self.js_parser.parse_file(self.js_file)
        self.assertGreater(len(entities), 0)
        # Verify language is set to javascript
        for entity in entities:
            self.assertEqual(entity.language, "javascript")

    def test_handles_node_not_found(self) -> None:
        """Test handling when Node.js is not available."""
        with patch("shutil.which", return_value=None):
            parser = TypeScriptParser(file_extension=".ts")
            result = parser.parse_file(Path("fake.ts"))
        self.assertEqual(result, [])

    def test_handles_subprocess_timeout(self) -> None:
        """Test handling of subprocess timeout."""
        import subprocess
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("node", 30)):
            with patch("shutil.which", return_value="/usr/bin/node"):
                parser = TypeScriptParser(file_extension=".ts")
                parser._ts_parser_path = Path(__file__).parent.parent / "ts_parser.js"
                result = parser.parse_file(Path("fake.ts"))
        self.assertEqual(result, [])

    def test_handles_invalid_json_output(self) -> None:
        """Test handling of invalid JSON from subprocess."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "not valid json"
        mock_result.stderr = ""

        with patch("subprocess.run", return_value=mock_result):
            with patch("shutil.which", return_value="/usr/bin/node"):
                parser = TypeScriptParser(file_extension=".ts")
                parser._ts_parser_path = Path(__file__).parent.parent / "ts_parser.js"
                result = parser.parse_file(Path("fake.ts"))
        self.assertEqual(result, [])


# =============================================================================
# CSS Parser Tests
# =============================================================================


class TestCSSParser(unittest.TestCase):
    """Tests for the CSS parser."""

    @classmethod
    def setUpClass(cls) -> None:
        """Set up test fixtures."""
        cls.parser = CSSParser()
        cls.sample_file = FIXTURES_DIR / "sample.css"
        if cls.sample_file.exists():
            cls.entities = cls.parser.parse_file(cls.sample_file)
        else:
            cls.entities = []

    def test_parser_language(self) -> None:
        """Test that parser identifies as CSS."""
        self.assertEqual(self.parser.language, "css")

    def test_parses_sample_file(self) -> None:
        """Test that sample file parses successfully."""
        if not self.sample_file.exists():
            self.skipTest("Sample CSS file not found")
        self.assertGreater(len(self.entities), 0)

    def test_extracts_class_selector(self) -> None:
        """Test extraction of class selector rule."""
        if not self.sample_file.exists():
            self.skipTest("Sample CSS file not found")

        rule = next(
            (e for e in self.entities if e.name == ".card" and e.entity_type == "style"),
            None,
        )
        self.assertIsNotNone(rule)
        self.assertEqual(rule.entity_type, "style")
        params = json.loads(rule.parameters)
        # Check that properties were extracted
        prop_names = [p["property"] for p in params]
        self.assertIn("display", prop_names)
        self.assertIn("background", prop_names)

    def test_extracts_hover_selector(self) -> None:
        """Test extraction of hover pseudo-class selector."""
        if not self.sample_file.exists():
            self.skipTest("Sample CSS file not found")

        rule = next(
            (e for e in self.entities if ".card:hover" in e.name and e.entity_type == "style"),
            None,
        )
        self.assertIsNotNone(rule)

    def test_extracts_keyframe_animation(self) -> None:
        """Test extraction of @keyframes animation."""
        if not self.sample_file.exists():
            self.skipTest("Sample CSS file not found")

        anim = next(
            (e for e in self.entities if e.name == "spin" and e.entity_type == "animation"),
            None,
        )
        self.assertIsNotNone(anim)
        self.assertEqual(anim.entity_type, "animation")
        self.assertIn("@keyframes spin", anim.signature)

    def test_extracts_multiple_animations(self) -> None:
        """Test extraction of multiple keyframe animations."""
        if not self.sample_file.exists():
            self.skipTest("Sample CSS file not found")

        animations = [e for e in self.entities if e.entity_type == "animation"]
        animation_names = [a.name for a in animations]
        self.assertIn("spin", animation_names)
        self.assertIn("fadeIn", animation_names)
        self.assertIn("pulse", animation_names)

    def test_extracts_button_variants(self) -> None:
        """Test extraction of button variant classes."""
        if not self.sample_file.exists():
            self.skipTest("Sample CSS file not found")

        btn_primary = next(
            (e for e in self.entities if e.name == ".btn-primary" and e.entity_type == "style"),
            None,
        )
        self.assertIsNotNone(btn_primary)

    def test_extracts_disabled_state(self) -> None:
        """Test extraction of :disabled pseudo-class."""
        if not self.sample_file.exists():
            self.skipTest("Sample CSS file not found")

        rule = next(
            (e for e in self.entities if ":disabled" in e.name and e.entity_type == "style"),
            None,
        )
        self.assertIsNotNone(rule)

    def test_source_code_contains_full_rule(self) -> None:
        """Test that source code contains the full CSS rule."""
        if not self.sample_file.exists():
            self.skipTest("Sample CSS file not found")

        rule = next(
            (e for e in self.entities if e.name == ".btn" and e.entity_type == "style"),
            None,
        )
        self.assertIsNotNone(rule)
        self.assertIn("{", rule.source_code)
        self.assertIn("}", rule.source_code)

    def test_handles_empty_file(self) -> None:
        """Test handling of empty CSS file."""
        with patch.object(Path, "read_text", return_value=""):
            result = self.parser.parse_file(Path("empty.css"))
        self.assertEqual(result, [])

    def test_handles_missing_file(self) -> None:
        """Test handling of missing CSS file."""
        result = self.parser.parse_file(Path("nonexistent.css"))
        self.assertEqual(result, [])

    def test_properties_parsed_correctly(self) -> None:
        """Test that CSS properties are parsed into correct JSON structure."""
        if not self.sample_file.exists():
            self.skipTest("Sample CSS file not found")

        rule = next(
            (e for e in self.entities if e.name == ".card" and e.entity_type == "style"),
            None,
        )
        self.assertIsNotNone(rule)
        params = json.loads(rule.parameters)
        # Check structure of properties
        self.assertTrue(all("property" in p and "value" in p for p in params))

    def test_line_numbers_accurate_with_comments(self) -> None:
        """Test that line numbers are accurate when file has comments."""
        if not self.sample_file.exists():
            self.skipTest("Sample CSS file not found")

        # The .card rule starts at line 9 in sample.css (after the multi-line header comment)
        rule = next(
            (e for e in self.entities if e.name == ".card" and e.entity_type == "style"),
            None,
        )
        self.assertIsNotNone(rule)
        # .card starts at line 9 and ends at line 17 in the original file
        self.assertEqual(rule.line_start, 9)
        self.assertEqual(rule.line_end, 17)

    def test_keyframe_line_numbers_accurate(self) -> None:
        """Test that keyframe animation line numbers are accurate."""
        if not self.sample_file.exists():
            self.skipTest("Sample CSS file not found")

        # @keyframes spin starts at line 166 in sample.css
        anim = next(
            (e for e in self.entities if e.name == "spin" and e.entity_type == "animation"),
            None,
        )
        self.assertIsNotNone(anim)
        # @keyframes spin is at lines 166-173
        self.assertEqual(anim.line_start, 166)
        self.assertEqual(anim.line_end, 173)

    def test_line_numbers_with_inline_css(self) -> None:
        """Test line numbers are accurate using direct content parsing."""
        # Create a temporary CSS file with known content
        import tempfile
        import os

        css_content = """/* Header comment */
/* Another comment */
@keyframes test {
  0% { opacity: 0; }
  100% { opacity: 1; }
}
/* Comment before rule */
.rule-after-keyframe {
  color: red;
}
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.css', delete=False) as f:
            f.write(css_content)
            temp_path = f.name

        try:
            entities = self.parser.parse_file(Path(temp_path))

            # @keyframes test starts at line 3
            anim = next((e for e in entities if e.entity_type == "animation"), None)
            self.assertIsNotNone(anim)
            self.assertEqual(anim.line_start, 3)
            self.assertEqual(anim.line_end, 6)

            # .rule-after-keyframe starts at line 8 (after comment is stripped)
            rule = next((e for e in entities if e.entity_type == "style"), None)
            self.assertIsNotNone(rule)
            self.assertEqual(rule.line_start, 8)
            self.assertEqual(rule.line_end, 10)
        finally:
            os.unlink(temp_path)


# =============================================================================
# Unified CodeParser Tests
# =============================================================================


class TestCodeParser(unittest.TestCase):
    """Tests for the unified CodeParser interface."""

    def setUp(self) -> None:
        """Set up test parser instance."""
        self.parser = CodeParser()

    def test_supported_extensions(self) -> None:
        """Test get_supported_extensions returns correct list."""
        extensions = get_supported_extensions()
        self.assertIn(".py", extensions)
        self.assertIn(".ts", extensions)
        self.assertIn(".tsx", extensions)
        self.assertIn(".js", extensions)
        self.assertIn(".jsx", extensions)
        self.assertIn(".css", extensions)

    def test_is_supported_python(self) -> None:
        """Test is_supported for Python files."""
        self.assertTrue(is_supported(Path("test.py")))

    def test_is_supported_typescript(self) -> None:
        """Test is_supported for TypeScript files."""
        self.assertTrue(is_supported(Path("test.ts")))
        self.assertTrue(is_supported(Path("test.tsx")))

    def test_is_supported_javascript(self) -> None:
        """Test is_supported for JavaScript files."""
        self.assertTrue(is_supported(Path("test.js")))
        self.assertTrue(is_supported(Path("test.jsx")))

    def test_is_supported_css(self) -> None:
        """Test is_supported for CSS files."""
        self.assertTrue(is_supported(Path("test.css")))

    def test_not_supported_txt(self) -> None:
        """Test is_supported returns False for unsupported types."""
        self.assertFalse(is_supported(Path("test.txt")))
        self.assertFalse(is_supported(Path("test.json")))
        self.assertFalse(is_supported(Path("test.md")))

    def test_routes_to_python_parser(self) -> None:
        """Test that .py files are routed to Python parser."""
        sample_py = FIXTURES_DIR / "sample.py"
        if not sample_py.exists():
            self.skipTest("Sample Python file not found")

        entities = self.parser.parse_file(sample_py)
        self.assertGreater(len(entities), 0)
        for entity in entities:
            self.assertEqual(entity.language, "python")

    def test_routes_to_typescript_parser(self) -> None:
        """Test that .ts files are routed to TypeScript parser."""
        import shutil
        if not shutil.which("node"):
            self.skipTest("Node.js not found")

        sample_ts = FIXTURES_DIR / "sample.ts"
        if not sample_ts.exists():
            self.skipTest("Sample TypeScript file not found")

        entities = self.parser.parse_file(sample_ts)
        self.assertGreater(len(entities), 0)
        for entity in entities:
            self.assertEqual(entity.language, "typescript")

    def test_routes_to_javascript_parser(self) -> None:
        """Test that .js files are routed to JavaScript parser."""
        import shutil
        if not shutil.which("node"):
            self.skipTest("Node.js not found")

        sample_js = FIXTURES_DIR / "sample.js"
        if not sample_js.exists():
            self.skipTest("Sample JavaScript file not found")

        entities = self.parser.parse_file(sample_js)
        self.assertGreater(len(entities), 0)
        for entity in entities:
            self.assertEqual(entity.language, "javascript")

    def test_routes_to_css_parser(self) -> None:
        """Test that .css files are routed to CSS parser."""
        sample_css = FIXTURES_DIR / "sample.css"
        if not sample_css.exists():
            self.skipTest("Sample CSS file not found")

        entities = self.parser.parse_file(sample_css)
        self.assertGreater(len(entities), 0)
        for entity in entities:
            self.assertEqual(entity.language, "css")

    def test_unsupported_returns_empty(self) -> None:
        """Test that unsupported file types return empty list."""
        result = self.parser.parse_file(Path("test.txt"))
        self.assertEqual(result, [])

    def test_handles_parsing_errors(self) -> None:
        """Test that parsing errors don't crash the parser."""
        # Create a mock that raises an exception
        with patch.object(
            PythonParser,
            "parse_file",
            side_effect=Exception("Test error"),
        ):
            result = self.parser.parse_file(Path("test.py"))
        self.assertEqual(result, [])


# =============================================================================
# Integration Tests
# =============================================================================


class TestCodeParserIntegration(unittest.TestCase):
    """Integration tests parsing real codebase files."""

    def setUp(self) -> None:
        """Set up parser instance."""
        self.parser = CodeParser()
        # Get workspace root (3 levels up from this file)
        self.workspace_root = Path(__file__).resolve().parents[3]

    def test_parse_doc_ingestion(self) -> None:
        """Test parsing the doc_ingestion.py file."""
        doc_ingestion = self.workspace_root / "api_gateway" / "services" / "doc_ingestion.py"
        if not doc_ingestion.exists():
            self.skipTest("doc_ingestion.py not found")

        entities = self.parser.parse_file(doc_ingestion)
        self.assertGreater(len(entities), 0)

        # Check for known entities
        entity_names = [e.name for e in entities]
        self.assertIn("DocChunk", entity_names)
        self.assertIn("scan_markdown_files", entity_names)
        self.assertIn("chunk_by_headers", entity_names)
        self.assertIn("ingest_documentation", entity_names)

    def test_parse_code_entity_schema(self) -> None:
        """Test parsing the code_entity_schema.py file."""
        schema_file = self.workspace_root / "api_gateway" / "services" / "code_entity_schema.py"
        if not schema_file.exists():
            self.skipTest("code_entity_schema.py not found")

        entities = self.parser.parse_file(schema_file)
        self.assertGreater(len(entities), 0)

        # Check for the CodeEntity class
        code_entity = next(
            (e for e in entities if e.name == "CodeEntity"),
            None,
        )
        self.assertIsNotNone(code_entity)
        self.assertEqual(code_entity.entity_type, "class")

    def test_entity_to_properties_for_weaviate(self) -> None:
        """Test that all entities can be converted to Weaviate properties."""
        sample_py = FIXTURES_DIR / "sample.py"
        if not sample_py.exists():
            self.skipTest("Sample Python file not found")

        entities = self.parser.parse_file(sample_py)
        for entity in entities:
            props = entity.to_properties()
            # All required fields should be present
            self.assertIn("entity_type", props)
            self.assertIn("name", props)
            self.assertIn("full_name", props)
            self.assertIn("file_path", props)
            self.assertIn("line_start", props)
            self.assertIn("line_end", props)
            self.assertIn("language", props)
            # Values should be the correct types
            self.assertIsInstance(props["line_start"], int)
            self.assertIsInstance(props["line_end"], int)
            self.assertIsInstance(props["name"], str)


# =============================================================================
# Convenience Function Tests
# =============================================================================


class TestConvenienceFunctions(unittest.TestCase):
    """Tests for module-level convenience functions."""

    def test_parse_file_function(self) -> None:
        """Test the parse_file convenience function."""
        sample_py = FIXTURES_DIR / "sample.py"
        if not sample_py.exists():
            self.skipTest("Sample Python file not found")

        entities = parse_file(sample_py)
        self.assertGreater(len(entities), 0)

    def test_get_supported_extensions_function(self) -> None:
        """Test the get_supported_extensions convenience function."""
        extensions = get_supported_extensions()
        self.assertIsInstance(extensions, list)
        self.assertGreater(len(extensions), 0)

    def test_is_supported_function(self) -> None:
        """Test the is_supported convenience function."""
        self.assertTrue(is_supported(Path("test.py")))
        self.assertFalse(is_supported(Path("test.txt")))


if __name__ == "__main__":
    unittest.main()
