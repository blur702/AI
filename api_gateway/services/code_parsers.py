"""
Multi-language code parser system for Weaviate code entity ingestion.

Provides parsers for Python, TypeScript/JavaScript, and CSS files that extract
comprehensive metadata about code entities (functions, classes, variables,
interfaces, types, styles) and return CodeEntity objects suitable for
Weaviate indexing.

This module mirrors the pattern established in doc_ingestion.py.

Usage:
    from api_gateway.services.code_parsers import CodeParser
    from pathlib import Path

    parser = CodeParser()
    entities = parser.parse_file(Path("example.py"))
    for entity in entities:
        print(f"{entity.entity_type}: {entity.full_name}")

Supported file types:
    - Python (.py)
    - TypeScript (.ts, .tsx)
    - JavaScript (.js, .jsx)
    - CSS (.css)
    - Rust (.rs)

Python Parser Notes:
    - Extracts all parameter types: positional, *args, keyword-only, **kwargs
    - Each parameter includes a 'kind' field: 'positional', 'vararg', 'kwonly', 'kwarg'
    - Nested functions are extracted with parent_entity set to the outer function name
"""

from __future__ import annotations

import ast
import json
import re
import shutil
import subprocess
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ..utils.logger import get_logger
from .code_entity_schema import CodeEntity

logger = get_logger("api_gateway.code_parsers")


# =============================================================================
# Helper Functions
# =============================================================================


def _relative_to_workspace(path: Path) -> str:
    """
    Convert absolute path to workspace-relative path.

    Args:
        path: Absolute file path

    Returns:
        Workspace-relative path string, or absolute path if not within workspace
    """
    workspace_root = Path(__file__).resolve().parents[2]
    try:
        return str(path.resolve().relative_to(workspace_root))
    except ValueError:
        return str(path.resolve())


def _build_full_name(
    file_path: Path, entity_name: str, parent: Optional[str] = None
) -> str:
    """
    Build fully qualified name for an entity.

    Args:
        file_path: Path to source file containing entity
        entity_name: Name of the entity (function, class, etc.)
        parent: Optional parent entity name (for nested entities)

    Returns:
        Fully qualified dotted name (e.g., module.path.ClassName.method_name)

    Format: module.path.ClassName.method_name or module.path.function_name
    """
    # Convert file path to module-like dotted path
    relative_path = _relative_to_workspace(file_path)
    # Remove extension and convert separators to dots
    module_path = relative_path.replace("\\", "/")
    if module_path.endswith(".py"):
        module_path = module_path[:-3]
    elif module_path.endswith((".ts", ".js")):
        module_path = module_path[:-3]
    elif module_path.endswith((".tsx", ".jsx", ".css")):
        module_path = module_path[:-4]
    elif module_path.endswith(".rs"):
        module_path = module_path[:-3]
    module_path = module_path.replace("/", ".")

    if parent:
        return f"{module_path}.{parent}.{entity_name}"
    return f"{module_path}.{entity_name}"


def _serialize_parameters(params: List[Dict[str, Any]]) -> str:
    """
    Convert parameter list to JSON string.

    Args:
        params: List of parameter dictionaries with name, type, default, kind keys

    Returns:
        JSON string representation of parameter list
    """
    return json.dumps(params)


def _serialize_decorators(decorators: List[str]) -> str:
    """
    Convert decorator list to JSON array string.

    Args:
        decorators: List of decorator strings (e.g., ["@property", "@staticmethod"])

    Returns:
        JSON array string
    """
    return json.dumps(decorators)


def _count_line_number(text: str, position: int) -> int:
    """
    Count line number (1-indexed) for a character position in text.

    Args:
        text: Source text
        position: Character position (0-indexed)

    Returns:
        Line number (1-indexed)
    """
    return text[:position].count("\n") + 1


# =============================================================================
# Base Parser Class
# =============================================================================


class BaseParser(ABC):
    """
    Abstract base class for language-specific parsers.

    Subclasses must implement parse_file() and language property to handle
    specific programming languages.
    """

    @abstractmethod
    def parse_file(self, file_path: Path) -> List[CodeEntity]:
        """
        Parse a file and extract code entities.

        Args:
            file_path: Path to the source file

        Returns:
            List of CodeEntity objects extracted from the file
        """
        pass

    @property
    @abstractmethod
    def language(self) -> str:
        """
        Return the language identifier for entities from this parser.

        Returns:
            Language identifier string (e.g., "python", "typescript", "javascript", "css")
        """
        pass


# =============================================================================
# Python Parser
# =============================================================================


class PythonParser(BaseParser):
    """
    Parser for Python source files using the built-in ast module.

    Extracts functions, methods, classes, and module-level variables with
    comprehensive metadata including parameters (positional, *args, kwonly, **kwargs),
    return types, decorators, and docstrings.
    """

    @property
    def language(self) -> str:
        """Return language identifier."""
        return "python"

    def parse_file(self, file_path: Path) -> List[CodeEntity]:
        """
        Parse a Python file and extract code entities.

        Args:
            file_path: Path to Python source file

        Returns:
            List of CodeEntity objects (functions, methods, classes, variables)
        """
        logger.info("Parsing Python file: %s", _relative_to_workspace(file_path))

        try:
            source_code = file_path.read_text(encoding="utf-8")
        except (FileNotFoundError, PermissionError) as exc:
            logger.exception("Failed to read file %s: %s", file_path, exc)
            return []

        try:
            tree = ast.parse(source_code, filename=str(file_path))
        except SyntaxError as exc:
            logger.exception("Syntax error in %s: %s", file_path, exc)
            return []

        entities: List[CodeEntity] = []
        imports = self._extract_imports(tree)
        source_lines = source_code.splitlines()

        class EntityVisitor(ast.NodeVisitor):
            def __init__(
                visitor_self,
                parent: Optional[str] = None,
                parent_is_class: bool = False,
            ):
                visitor_self.parent = parent
                visitor_self.parent_is_class = parent_is_class

            def visit_FunctionDef(visitor_self, node: ast.FunctionDef) -> None:
                entity = self._extract_function(
                    node,
                    file_path,
                    source_lines,
                    imports,
                    visitor_self.parent,
                    is_method=visitor_self.parent_is_class,
                )
                entities.append(entity)

                # Handle nested functions: traverse the body for nested function definitions
                # Nested functions are NOT methods (parent_is_class=False)
                nested_visitor = EntityVisitor(parent=node.name, parent_is_class=False)
                for child in node.body:
                    if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        nested_visitor.visit(child)

            def visit_AsyncFunctionDef(
                visitor_self, node: ast.AsyncFunctionDef
            ) -> None:
                entity = self._extract_function(
                    node,
                    file_path,
                    source_lines,
                    imports,
                    visitor_self.parent,
                    is_async=True,
                    is_method=visitor_self.parent_is_class,
                )
                entities.append(entity)

                # Handle nested functions: traverse the body for nested function definitions
                # Nested functions are NOT methods (parent_is_class=False)
                nested_visitor = EntityVisitor(parent=node.name, parent_is_class=False)
                for child in node.body:
                    if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        nested_visitor.visit(child)

            def visit_ClassDef(visitor_self, node: ast.ClassDef) -> None:
                # Extract class itself
                class_entity = self._extract_class(
                    node, file_path, source_lines, imports, visitor_self.parent
                )
                entities.append(class_entity)

                # Extract methods with class as parent (parent_is_class=True)
                method_visitor = EntityVisitor(parent=node.name, parent_is_class=True)
                for child in node.body:
                    if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        method_visitor.visit(child)
                    elif isinstance(child, ast.ClassDef):
                        # Nested class
                        method_visitor.visit(child)

            def visit_Assign(visitor_self, node: ast.Assign) -> None:
                # Only module-level variables
                if visitor_self.parent is None:
                    for target in node.targets:
                        if isinstance(target, ast.Name):
                            entity = self._extract_variable(
                                target.id, node, file_path, source_lines, imports
                            )
                            entities.append(entity)

            def visit_AnnAssign(visitor_self, node: ast.AnnAssign) -> None:
                # Only module-level annotated assignments
                if visitor_self.parent is None and isinstance(node.target, ast.Name):
                    entity = self._extract_annotated_variable(
                        node, file_path, source_lines, imports
                    )
                    entities.append(entity)

        visitor = EntityVisitor()
        visitor.visit(tree)

        logger.info(
            "Extracted %d entities from %s",
            len(entities),
            _relative_to_workspace(file_path),
        )
        return entities

    def _extract_imports(self, tree: ast.Module) -> List[str]:
        """
        Extract all import statements from a Python AST.

        Args:
            tree: Parsed Python AST module

        Returns:
            List of imported module/package names
        """
        imports: List[str] = []

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append(alias.name)
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                imports.append(module)
                for alias in node.names:
                    imports.append(f"{module}.{alias.name}" if module else alias.name)

        return list(set(imports))

    def _extract_function(
        self,
        node: ast.FunctionDef | ast.AsyncFunctionDef,
        file_path: Path,
        source_lines: List[str],
        imports: List[str],
        parent: Optional[str] = None,
        is_async: bool = False,
        is_method: bool = False,
    ) -> CodeEntity:
        """
        Extract a function or method entity from AST node.

        Args:
            node: AST FunctionDef or AsyncFunctionDef node
            file_path: Source file path
            source_lines: Lines of source code for extracting text
            imports: List of imported modules
            parent: Parent entity name (for nested functions/methods)
            is_async: Whether function is async
            is_method: Whether function is a class method

        Returns:
            CodeEntity object with complete function/method metadata
        """
        name = node.name

        # Parameters - extract all categories
        params: List[Dict[str, Any]] = []

        # 1. Standard positional args (node.args.args)
        for arg in node.args.args:
            param_info: Dict[str, Any] = {
                "name": arg.arg,
                "type": None,
                "default": None,
                "kind": "positional",
            }
            if arg.annotation:
                param_info["type"] = ast.unparse(arg.annotation)
            params.append(param_info)

        # Handle positional defaults (they align to the end of args)
        defaults = node.args.defaults
        if defaults:
            offset = len(node.args.args) - len(defaults)
            for i, default in enumerate(defaults):
                params[offset + i]["default"] = ast.unparse(default)

        # 2. Varargs (*args)
        if node.args.vararg:
            vararg = node.args.vararg
            param_info = {
                "name": f"*{vararg.arg}",
                "type": ast.unparse(vararg.annotation) if vararg.annotation else None,
                "default": None,
                "kind": "vararg",
            }
            params.append(param_info)

        # 3. Keyword-only args (node.args.kwonlyargs)
        for i, arg in enumerate(node.args.kwonlyargs):
            param_info = {
                "name": arg.arg,
                "type": ast.unparse(arg.annotation) if arg.annotation else None,
                "default": None,
                "kind": "kwonly",
            }
            # kw_defaults aligns with kwonlyargs (can have None for no default)
            if i < len(node.args.kw_defaults) and node.args.kw_defaults[i] is not None:
                param_info["default"] = ast.unparse(node.args.kw_defaults[i])
            params.append(param_info)

        # 4. Kwargs (**kwargs)
        if node.args.kwarg:
            kwarg = node.args.kwarg
            param_info = {
                "name": f"**{kwarg.arg}",
                "type": ast.unparse(kwarg.annotation) if kwarg.annotation else None,
                "default": None,
                "kind": "kwarg",
            }
            params.append(param_info)

        # Return type
        return_type = ""
        if node.returns:
            return_type = ast.unparse(node.returns)

        # Decorators
        decorators = []
        for decorator in node.decorator_list:
            decorators.append("@" + ast.unparse(decorator))

        # Modifiers
        modifiers = []
        if is_async or isinstance(node, ast.AsyncFunctionDef):
            modifiers.append("async")
        for dec in decorators:
            if "@staticmethod" in dec:
                modifiers.append("staticmethod")
            elif "@classmethod" in dec:
                modifiers.append("classmethod")
            elif "@property" in dec:
                modifiers.append("property")

        # Docstring
        docstring = ast.get_docstring(node) or ""

        # Source code
        start_line = node.lineno
        end_line = node.end_lineno or node.lineno
        source = "\n".join(source_lines[start_line - 1 : end_line])

        # Signature
        param_str = ", ".join(
            f"{p['name']}: {p['type']}" if p["type"] else p["name"] for p in params
        )
        async_prefix = "async " if "async" in modifiers else ""
        return_suffix = f" -> {return_type}" if return_type else ""
        signature = f"{async_prefix}def {name}({param_str}){return_suffix}"

        entity_type = "method" if is_method else "function"

        return CodeEntity(
            entity_type=entity_type,
            name=name,
            full_name=_build_full_name(file_path, name, parent),
            file_path=_relative_to_workspace(file_path),
            line_start=start_line,
            line_end=end_line,
            signature=signature,
            parameters=_serialize_parameters(params),
            return_type=return_type,
            docstring=docstring,
            decorators=_serialize_decorators(decorators),
            modifiers=", ".join(modifiers),
            parent_entity=parent or "",
            language=self.language,
            source_code=source,
            dependencies=json.dumps(imports),
            relationships=json.dumps({"imports": imports}),
        )

    def _extract_class(
        self,
        node: ast.ClassDef,
        file_path: Path,
        source_lines: List[str],
        imports: List[str],
        parent: Optional[str] = None,
    ) -> CodeEntity:
        """
        Extract a class entity from AST node.

        Args:
            node: AST ClassDef node
            file_path: Source file path
            source_lines: Lines of source code for extracting text
            imports: List of imported modules
            parent: Parent entity name (for nested classes)

        Returns:
            CodeEntity object with class metadata including base classes
        """
        name = node.name

        # Base classes
        bases = []
        for base in node.bases:
            bases.append(ast.unparse(base))

        # Decorators
        decorators = []
        for decorator in node.decorator_list:
            decorators.append("@" + ast.unparse(decorator))

        # Docstring
        docstring = ast.get_docstring(node) or ""

        # Source code
        start_line = node.lineno
        end_line = node.end_lineno or node.lineno
        source = "\n".join(source_lines[start_line - 1 : end_line])

        # Signature
        bases_str = ", ".join(bases)
        signature = f"class {name}({bases_str})" if bases else f"class {name}"

        relationships = {"inherits": bases, "imports": imports}

        return CodeEntity(
            entity_type="class",
            name=name,
            full_name=_build_full_name(file_path, name, parent),
            file_path=_relative_to_workspace(file_path),
            line_start=start_line,
            line_end=end_line,
            signature=signature,
            parameters="[]",
            return_type="",
            docstring=docstring,
            decorators=_serialize_decorators(decorators),
            modifiers="",
            parent_entity=parent or "",
            language=self.language,
            source_code=source,
            dependencies=json.dumps(imports),
            relationships=json.dumps(relationships),
        )

    def _extract_variable(
        self,
        name: str,
        node: ast.Assign,
        file_path: Path,
        source_lines: List[str],
        imports: List[str],
    ) -> CodeEntity:
        """
        Extract a module-level variable assignment.

        Args:
            name: Variable name
            node: AST Assign node
            file_path: Source file path
            source_lines: Lines of source code for extracting text
            imports: List of imported modules

        Returns:
            CodeEntity object for the variable
        """
        start_line = node.lineno
        end_line = node.end_lineno or node.lineno
        source = "\n".join(source_lines[start_line - 1 : end_line])

        # Try to get the value as string
        value_str = ""
        try:
            value_str = ast.unparse(node.value)
        except Exception:
            pass

        signature = f"{name} = {value_str}" if value_str else name

        return CodeEntity(
            entity_type="variable",
            name=name,
            full_name=_build_full_name(file_path, name),
            file_path=_relative_to_workspace(file_path),
            line_start=start_line,
            line_end=end_line,
            signature=signature,
            parameters="[]",
            return_type="",
            docstring="",
            decorators="[]",
            modifiers="",
            parent_entity="",
            language=self.language,
            source_code=source,
            dependencies=json.dumps(imports),
            relationships=json.dumps({"imports": imports}),
        )

    def _extract_annotated_variable(
        self,
        node: ast.AnnAssign,
        file_path: Path,
        source_lines: List[str],
        imports: List[str],
    ) -> CodeEntity:
        """
        Extract an annotated module-level variable.

        Args:
            node: AST AnnAssign node (annotated assignment)
            file_path: Source file path
            source_lines: Lines of source code for extracting text
            imports: List of imported modules

        Returns:
            CodeEntity object for the typed variable
        """
        name = node.target.id  # type: ignore
        start_line = node.lineno
        end_line = node.end_lineno or node.lineno
        source = "\n".join(source_lines[start_line - 1 : end_line])

        type_annotation = ast.unparse(node.annotation)
        value_str = ""
        if node.value:
            try:
                value_str = ast.unparse(node.value)
            except Exception:
                pass

        if value_str:
            signature = f"{name}: {type_annotation} = {value_str}"
        else:
            signature = f"{name}: {type_annotation}"

        return CodeEntity(
            entity_type="variable",
            name=name,
            full_name=_build_full_name(file_path, name),
            file_path=_relative_to_workspace(file_path),
            line_start=start_line,
            line_end=end_line,
            signature=signature,
            parameters="[]",
            return_type=type_annotation,
            docstring="",
            decorators="[]",
            modifiers="",
            parent_entity="",
            language=self.language,
            source_code=source,
            dependencies=json.dumps(imports),
            relationships=json.dumps({"imports": imports}),
        )


# =============================================================================
# TypeScript/JavaScript Parser
# =============================================================================


class TypeScriptParser(BaseParser):
    """
    Parser for TypeScript/JavaScript files using Node.js subprocess.

    Uses ts_parser.js Node.js script to parse TypeScript/JavaScript files via
    the TypeScript compiler API. Extracts functions, classes, interfaces, types,
    and variables.
    """

    def __init__(self, file_extension: str = ".ts"):
        """
        Initialize the TypeScript parser.

        Args:
            file_extension: File extension to determine language (.ts, .tsx, .js, .jsx)
        """
        self._file_extension = file_extension
        self._node_path: Optional[str] = None
        self._ts_parser_path = Path(__file__).parent / "ts_parser.cjs"

    @property
    def language(self) -> str:
        """
        Return language identifier based on file extension.

        Returns:
            "typescript" for .ts/.tsx files, "javascript" for .js/.jsx files
        """
        if self._file_extension in (".ts", ".tsx"):
            return "typescript"
        return "javascript"

    def _get_node_path(self) -> Optional[str]:
        """
        Get path to Node.js executable.

        Returns:
            Path to node executable, or None if not found
        """
        if self._node_path is None:
            self._node_path = shutil.which("node")
        return self._node_path

    def parse_file(self, file_path: Path) -> List[CodeEntity]:
        """
        Parse a TypeScript/JavaScript file and extract code entities.

        Args:
            file_path: Path to TypeScript/JavaScript source file

        Returns:
            List of CodeEntity objects extracted via ts_parser.js subprocess
        """
        logger.info("Parsing %s file: %s", self.language, _relative_to_workspace(file_path))

        node_path = self._get_node_path()
        if not node_path:
            logger.warning("Node.js not found, cannot parse TypeScript/JavaScript files")
            return []

        if not self._ts_parser_path.exists():
            logger.error("TypeScript parser script not found at %s", self._ts_parser_path)
            return []

        try:
            result = subprocess.run(
                [node_path, str(self._ts_parser_path), str(file_path)],
                capture_output=True,
                text=True,
                timeout=30,
                cwd=str(Path(__file__).parent),
            )
        except subprocess.TimeoutExpired:
            logger.warning("TypeScript parser timed out for %s", file_path)
            return []
        except Exception as exc:
            logger.exception("Failed to run TypeScript parser for %s: %s", file_path, exc)
            return []

        if result.returncode != 0:
            logger.error(
                "TypeScript parser failed for %s: %s",
                file_path,
                result.stderr,
            )
            return []

        # Handle empty or None output
        if not result.stdout or not result.stdout.strip():
            logger.warning("TypeScript parser returned empty output for %s", file_path)
            return []

        try:
            raw_entities = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            logger.exception("Failed to parse TypeScript parser output for %s: %s", file_path, exc)
            return []

        entities: List[CodeEntity] = []
        relative_path = _relative_to_workspace(file_path)

        for raw in raw_entities:
            # Prefer full_name from ts_parser.js if present and non-empty,
            # otherwise fall back to building it ourselves
            raw_full_name = raw.get("full_name", "")
            if raw_full_name and isinstance(raw_full_name, str) and raw_full_name.strip():
                full_name = raw_full_name
            else:
                full_name = _build_full_name(
                    file_path,
                    raw.get("name", ""),
                    raw.get("parent_entity") or None,
                )

            entity = CodeEntity(
                entity_type=raw.get("entity_type", "unknown"),
                name=raw.get("name", ""),
                full_name=full_name,
                file_path=relative_path,
                line_start=raw.get("line_start", 0),
                line_end=raw.get("line_end", 0),
                signature=raw.get("signature", ""),
                parameters=raw.get("parameters", "[]"),
                return_type=raw.get("return_type", ""),
                docstring=raw.get("docstring", ""),
                decorators=raw.get("decorators", "[]"),
                modifiers=raw.get("modifiers", ""),
                parent_entity=raw.get("parent_entity", ""),
                language=self.language,
                source_code=raw.get("source_code", ""),
                dependencies=raw.get("dependencies", "[]"),
                relationships=raw.get("relationships", "{}"),
            )
            entities.append(entity)

        logger.info(
            "Extracted %d entities from %s",
            len(entities),
            relative_path,
        )
        return entities


# =============================================================================
# CSS Parser
# =============================================================================


class CSSParser(BaseParser):
    """
    Parser for CSS files using regex patterns.

    Extracts CSS style rules (selectors with properties) and @keyframes animations.
    Handles comments and nested structures correctly.
    """

    # Pattern for CSS rules: selector { properties }
    RULE_PATTERN = re.compile(
        r"([^{}@]+?)\s*\{([^{}]*)\}",
        re.MULTILINE | re.DOTALL,
    )

    # Pattern for @keyframes animations
    KEYFRAMES_PATTERN = re.compile(
        r"@keyframes\s+([a-zA-Z_][a-zA-Z0-9_-]*)\s*\{((?:[^{}]|\{[^{}]*\})*)\}",
        re.MULTILINE | re.DOTALL,
    )

    # Pattern for CSS properties
    PROPERTY_PATTERN = re.compile(
        r"([a-zA-Z-]+)\s*:\s*([^;]+);?",
        re.MULTILINE,
    )

    @property
    def language(self) -> str:
        """Return language identifier."""
        return "css"

    def parse_file(self, file_path: Path) -> List[CodeEntity]:
        """
        Parse a CSS file and extract style rules and animations.

        Args:
            file_path: Path to CSS file

        Returns:
            List of CodeEntity objects (styles and animations)
        """
        logger.info("Parsing CSS file: %s", _relative_to_workspace(file_path))

        try:
            content = file_path.read_text(encoding="utf-8")
        except (FileNotFoundError, PermissionError) as exc:
            logger.exception("Failed to read file %s: %s", file_path, exc)
            return []

        entities: List[CodeEntity] = []
        relative_path = _relative_to_workspace(file_path)

        # Track keyframe positions to avoid double-matching their internal rules
        keyframe_spans: List[Tuple[int, int]] = []

        # Extract keyframe animations directly from original content
        for match in self.KEYFRAMES_PATTERN.finditer(content):
            matched_text = match.group(0)

            # Skip if match contains a comment (malformed or edge case)
            if re.search(r"/\*", matched_text):
                continue

            animation_name = match.group(1).strip()
            animation_body = match.group(2).strip()

            # Use positions from original content for accurate line numbers
            line_start = _count_line_number(content, match.start())
            line_end = _count_line_number(content, match.end())

            # Track this span to exclude from rule parsing
            keyframe_spans.append((match.start(), match.end()))

            # Parse keyframe steps
            steps = []
            for step_match in re.finditer(
                r"([\d%]+|from|to)\s*\{([^}]*)\}", animation_body
            ):
                step_name = step_match.group(1).strip()
                step_props = self._parse_properties(step_match.group(2))
                steps.append({"step": step_name, "properties": step_props})

            entity = CodeEntity(
                entity_type="animation",
                name=animation_name,
                full_name=f"{relative_path}::@keyframes {animation_name}",
                file_path=relative_path,
                line_start=line_start,
                line_end=line_end,
                signature=f"@keyframes {animation_name}",
                parameters=json.dumps(steps),
                return_type="",
                docstring="",
                decorators="[]",
                modifiers="",
                parent_entity="",
                language=self.language,
                source_code=content[match.start():match.end()].strip(),
                dependencies="[]",
                relationships="{}",
            )
            entities.append(entity)

        # Extract CSS rules directly from original content
        for match in self.RULE_PATTERN.finditer(content):
            # Skip if this match is inside a keyframe block
            match_start = match.start()
            match_end = match.end()
            inside_keyframe = any(
                kf_start <= match_start and match_end <= kf_end
                for kf_start, kf_end in keyframe_spans
            )
            if inside_keyframe:
                continue

            raw_selector = match.group(1)
            properties_block = match.group(2).strip()

            # Handle comments in the selector portion:
            # If the selector contains a comment, extract only the part after the last comment
            # and adjust the effective start position for line number calculation
            selector_offset = 0
            if "/*" in raw_selector:
                # Find the position after the last comment end (*/)
                last_comment_end = raw_selector.rfind("*/")
                if last_comment_end != -1:
                    selector_offset = last_comment_end + 2
                    raw_selector = raw_selector[selector_offset:]

            selector = raw_selector.strip()

            # Skip empty or at-rule selectors
            if not selector or selector.startswith("@"):
                continue

            # Clean up selector (remove extra whitespace) for name/full_name fields
            selector = " ".join(selector.split())

            # Calculate line numbers - adjust start if we skipped comments
            # The actual rule starts after any preceding comments
            actual_start = match.start() + selector_offset
            # Find where the selector actually begins (skip leading whitespace)
            while actual_start < match_end and content[actual_start] in " \t\n\r":
                actual_start += 1

            line_start = _count_line_number(content, actual_start)
            line_end = _count_line_number(content, match.end())

            properties = self._parse_properties(properties_block)

            entity = CodeEntity(
                entity_type="style",
                name=selector,
                full_name=f"{relative_path}::{selector}",
                file_path=relative_path,
                line_start=line_start,
                line_end=line_end,
                signature=selector,
                parameters=json.dumps(properties),
                return_type="",
                docstring="",
                decorators="[]",
                modifiers="",
                parent_entity="",
                language=self.language,
                source_code=content[actual_start:match.end()].strip(),
                dependencies="[]",
                relationships="{}",
            )
            entities.append(entity)

        logger.info(
            "Extracted %d entities from %s",
            len(entities),
            relative_path,
        )
        return entities

    def _parse_properties(self, block: str) -> List[Dict[str, str]]:
        """
        Parse CSS properties from a block of text.

        Args:
            block: CSS properties block text

        Returns:
            List of dicts with "property" and "value" keys
        """
        properties = []
        for match in self.PROPERTY_PATTERN.finditer(block):
            properties.append({
                "property": match.group(1).strip(),
                "value": match.group(2).strip(),
            })
        return properties




# =============================================================================
# Rust Parser
# =============================================================================


class RustParser(BaseParser):
    """
    Parser for Rust files using regex patterns.

    Extracts functions, structs, traits, enums, impls, and constants from Rust source files.
    Handles async functions, generics, and visibility modifiers.
    """

    # Pattern for function definitions (pub async fn, fn, etc.)
    FN_PATTERN = re.compile(
        r"(?:///[^\n]*\n)*"  # Optional doc comments
        r"((?:pub(?:\([^)]+\))?\s+)?(?:async\s+)?(?:unsafe\s+)?(?:const\s+)?)"  # modifiers
        r"fn\s+([a-zA-Z_][a-zA-Z0-9_]*)"  # fn name
        r"(<[^>]+>)?"  # optional generics
        r"\s*\(([^)]*)\)"  # parameters
        r"(?:\s*->\s*([^\n{]+))?"  # optional return type
        r"\s*(?:where[^{]+)?"  # optional where clause
        r"\s*\{",  # opening brace
        re.MULTILINE | re.DOTALL,
    )

    # Pattern for struct definitions
    STRUCT_PATTERN = re.compile(
        r"(?:///[^\n]*\n)*"  # Optional doc comments
        r"((?:pub(?:\([^)]+\))?\s+)?)"  # visibility
        r"struct\s+([a-zA-Z_][a-zA-Z0-9_]*)"  # struct name
        r"(<[^>]+>)?"  # optional generics
        r"(?:\s*\([^)]*\))?"  # tuple struct
        r"(?:\s*where[^{;]+)?"  # optional where clause
        r"\s*[{;]",  # opening brace or semicolon
        re.MULTILINE | re.DOTALL,
    )

    # Pattern for trait definitions
    TRAIT_PATTERN = re.compile(
        r"(?:///[^\n]*\n)*"  # Optional doc comments
        r"((?:pub(?:\([^)]+\))?\s+)?(?:unsafe\s+)?)"  # visibility and unsafe
        r"trait\s+([a-zA-Z_][a-zA-Z0-9_]*)"  # trait name
        r"(<[^>]+>)?"  # optional generics
        r"(?:\s*:\s*[^{]+)?"  # optional supertraits
        r"(?:\s*where[^{]+)?"  # optional where clause
        r"\s*\{",
        re.MULTILINE | re.DOTALL,
    )

    # Pattern for enum definitions
    ENUM_PATTERN = re.compile(
        r"(?:///[^\n]*\n)*"  # Optional doc comments
        r"((?:pub(?:\([^)]+\))?\s+)?)"  # visibility
        r"enum\s+([a-zA-Z_][a-zA-Z0-9_]*)"  # enum name
        r"(<[^>]+>)?"  # optional generics
        r"(?:\s*where[^{]+)?"  # optional where clause
        r"\s*\{",
        re.MULTILINE | re.DOTALL,
    )

    # Pattern for impl blocks
    IMPL_PATTERN = re.compile(
        r"((?:unsafe\s+)?)"  # unsafe modifier
        r"impl\s*"
        r"(<[^>]+>)?"  # optional generics
        r"\s*(?:([a-zA-Z_][a-zA-Z0-9_:<>]*)\s+for\s+)?"  # optional trait for
        r"([a-zA-Z_][a-zA-Z0-9_:<>]+)"  # type name
        r"(?:\s*where[^{]+)?"  # optional where clause
        r"\s*\{",
        re.MULTILINE | re.DOTALL,
    )

    # Pattern for const/static
    CONST_PATTERN = re.compile(
        r"(?:///[^\n]*\n)*"  # Optional doc comments
        r"((?:pub(?:\([^)]+\))?\s+)?)"  # visibility
        r"(const|static(?:\s+mut)?)\s+"
        r"([a-zA-Z_][a-zA-Z0-9_]*)"  # name
        r"\s*:\s*([^=]+)"  # type
        r"\s*=",
        re.MULTILINE,
    )

    # Pattern for type aliases
    TYPE_ALIAS_PATTERN = re.compile(
        r"(?:///[^\n]*\n)*"  # Optional doc comments
        r"((?:pub(?:\([^)]+\))?\s+)?)"  # visibility
        r"type\s+([a-zA-Z_][a-zA-Z0-9_]*)"  # name
        r"(<[^>]+>)?"  # optional generics
        r"\s*=\s*([^;]+);",
        re.MULTILINE,
    )

    @property
    def language(self) -> str:
        """Return language identifier."""
        return "rust"

    def parse_file(self, file_path: Path) -> List[CodeEntity]:
        """
        Parse a Rust file and extract code entities.

        Args:
            file_path: Path to Rust file

        Returns:
            List of CodeEntity objects (functions, structs, traits, enums, etc.)
        """
        logger.info("Parsing Rust file: %s", _relative_to_workspace(file_path))

        try:
            content = file_path.read_text(encoding="utf-8")
        except (FileNotFoundError, PermissionError) as exc:
            logger.exception("Failed to read file %s: %s", file_path, exc)
            return []

        entities: List[CodeEntity] = []
        relative_path = _relative_to_workspace(file_path)

        # Extract functions
        entities.extend(self._extract_functions(content, relative_path))

        # Extract structs
        entities.extend(self._extract_structs(content, relative_path))

        # Extract traits
        entities.extend(self._extract_traits(content, relative_path))

        # Extract enums
        entities.extend(self._extract_enums(content, relative_path))

        # Extract impl blocks
        entities.extend(self._extract_impls(content, relative_path))

        # Extract constants and statics
        entities.extend(self._extract_constants(content, relative_path))

        # Extract type aliases
        entities.extend(self._extract_type_aliases(content, relative_path))

        logger.info(
            "Extracted %d entities from %s",
            len(entities),
            relative_path,
        )
        return entities

    def _extract_doc_comment(self, content: str, pos: int) -> str:
        """Extract doc comments preceding a position."""
        lines = content[:pos].split("\n")
        doc_lines = []
        for line in reversed(lines):
            stripped = line.strip()
            if stripped.startswith("///"):
                doc_lines.insert(0, stripped[3:].strip())
            elif stripped.startswith("//!"):
                doc_lines.insert(0, stripped[3:].strip())
            elif stripped == "" or stripped.startswith("//"):
                continue
            else:
                break
        return "\n".join(doc_lines)

    def _extract_modifiers(self, mod_str: str) -> str:
        """Extract modifiers from a modifier string."""
        mods = []
        if "pub" in mod_str:
            mods.append("pub")
        if "async" in mod_str:
            mods.append("async")
        if "unsafe" in mod_str:
            mods.append("unsafe")
        if "const" in mod_str:
            mods.append("const")
        return ", ".join(mods)

    def _find_block_end(self, content: str, start: int) -> int:
        """Find the end of a brace-delimited block.

        Handles:
        - String literals ("..." and '...')
        - Raw strings (r"..." and r#"..."#)
        - Line comments (//)
        - Block comments (/* */)
        """
        depth = 1
        i = start
        length = len(content)

        while i < length and depth > 0:
            ch = content[i]

            # Skip string literals
            if ch == '"':
                # Check for raw string r"..." or r#"..."#
                if i > 0 and content[i - 1] == "r":
                    # Count # symbols after r
                    hash_count = 0
                    j = i - 1
                    while j > 0 and content[j - 1] == "#":
                        hash_count += 1
                        j -= 1
                    # Find matching closing: "# * hash_count
                    i += 1
                    while i < length:
                        if content[i] == '"':
                            # Check for closing #s
                            end_hashes = 0
                            k = i + 1
                            while k < length and content[k] == "#" and end_hashes < hash_count:
                                end_hashes += 1
                                k += 1
                            if end_hashes == hash_count:
                                i = k
                                break
                        i += 1
                else:
                    # Regular string literal
                    i += 1
                    while i < length:
                        if content[i] == "\\" and i + 1 < length:
                            i += 2  # Skip escaped character
                        elif content[i] == '"':
                            i += 1
                            break
                        else:
                            i += 1
                continue

            # Skip character literals
            if ch == "'":
                i += 1
                if i < length and content[i] == "\\":
                    i += 2  # Skip escaped char in char literal
                elif i < length:
                    i += 1  # Skip the character
                if i < length and content[i] == "'":
                    i += 1  # Skip closing quote
                continue

            # Skip line comments
            if ch == "/" and i + 1 < length and content[i + 1] == "/":
                while i < length and content[i] != "\n":
                    i += 1
                continue

            # Skip block comments
            if ch == "/" and i + 1 < length and content[i + 1] == "*":
                i += 2
                while i + 1 < length:
                    if content[i] == "*" and content[i + 1] == "/":
                        i += 2
                        break
                    i += 1
                continue

            # Count braces
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
            i += 1

        return i

    def _extract_functions(self, content: str, file_path: str) -> List[CodeEntity]:
        """Extract function definitions."""
        entities = []
        for match in self.FN_PATTERN.finditer(content):
            modifiers = self._extract_modifiers(match.group(1) or "")
            name = match.group(2)
            generics = (match.group(3) or "").strip()
            params = match.group(4).strip()
            return_type = (match.group(5) or "").strip()

            line_start = _count_line_number(content, match.start())
            block_end = self._find_block_end(content, match.end())
            line_end = _count_line_number(content, block_end)
            source = content[match.start():block_end].strip()

            # Parse parameters
            param_list = self._parse_rust_params(params)

            signature = f"fn {name}{generics}({params})"
            if return_type:
                signature += f" -> {return_type}"

            docstring = self._extract_doc_comment(content, match.start())

            entities.append(CodeEntity(
                entity_type="function",
                name=name,
                full_name=_build_full_name(Path(file_path), name),
                file_path=file_path,
                line_start=line_start,
                line_end=line_end,
                signature=signature,
                parameters=json.dumps(param_list),
                return_type=return_type,
                docstring=docstring,
                decorators="[]",
                modifiers=modifiers,
                parent_entity="",
                language=self.language,
                source_code=source[:2000],  # Truncate long sources
                dependencies="[]",
                relationships="{}",
            ))
        return entities

    def _parse_rust_params(self, params: str) -> List[Dict[str, Any]]:
        """Parse Rust function parameters.

        Handles nested brackets for:
        - Generics: <T, U>
        - Parentheses: (for tuples and function pointers)
        - Square brackets: [u8; 32] (arrays), &[T] (slices)
        - Curly braces: impl Fn() -> {} (closures)
        """
        if not params.strip():
            return []
        param_list = []
        # Split by comma, handling all nested bracket types
        depth = 0
        current = ""
        for char in params:
            if char in "<([{":
                depth += 1
            elif char in ">)]}":
                depth -= 1
            if char == "," and depth == 0:
                if current.strip():
                    param_list.append(self._parse_single_param(current.strip()))
                current = ""
            else:
                current += char
        if current.strip():
            param_list.append(self._parse_single_param(current.strip()))
        return param_list

    def _parse_single_param(self, param: str) -> Dict[str, Any]:
        """Parse a single Rust parameter."""
        # Handle self, &self, &mut self
        if param in ("self", "&self", "&mut self"):
            return {"name": "self", "type": param, "kind": "self"}
        # Handle name: Type patterns
        if ":" in param:
            parts = param.split(":", 1)
            return {"name": parts[0].strip(), "type": parts[1].strip(), "kind": "positional"}
        return {"name": param, "type": "", "kind": "positional"}

    def _extract_structs(self, content: str, file_path: str) -> List[CodeEntity]:
        """Extract struct definitions."""
        entities = []
        for match in self.STRUCT_PATTERN.finditer(content):
            modifiers = self._extract_modifiers(match.group(1) or "")
            name = match.group(2)
            generics = (match.group(3) or "").strip()

            line_start = _count_line_number(content, match.start())
            # Find end of struct
            if content[match.end() - 1] == ";":
                line_end = line_start
                source = content[match.start():match.end()].strip()
            else:
                block_end = self._find_block_end(content, match.end())
                line_end = _count_line_number(content, block_end)
                source = content[match.start():block_end].strip()

            docstring = self._extract_doc_comment(content, match.start())

            entities.append(CodeEntity(
                entity_type="struct",
                name=name,
                full_name=_build_full_name(Path(file_path), name),
                file_path=file_path,
                line_start=line_start,
                line_end=line_end,
                signature=f"struct {name}{generics}",
                parameters="[]",
                return_type="",
                docstring=docstring,
                decorators="[]",
                modifiers=modifiers,
                parent_entity="",
                language=self.language,
                source_code=source[:2000],
                dependencies="[]",
                relationships="{}",
            ))
        return entities

    def _extract_traits(self, content: str, file_path: str) -> List[CodeEntity]:
        """Extract trait definitions."""
        entities = []
        for match in self.TRAIT_PATTERN.finditer(content):
            modifiers = self._extract_modifiers(match.group(1) or "")
            name = match.group(2)
            generics = (match.group(3) or "").strip()

            line_start = _count_line_number(content, match.start())
            block_end = self._find_block_end(content, match.end())
            line_end = _count_line_number(content, block_end)
            source = content[match.start():block_end].strip()
            docstring = self._extract_doc_comment(content, match.start())

            entities.append(CodeEntity(
                entity_type="trait",
                name=name,
                full_name=_build_full_name(Path(file_path), name),
                file_path=file_path,
                line_start=line_start,
                line_end=line_end,
                signature=f"trait {name}{generics}",
                parameters="[]",
                return_type="",
                docstring=docstring,
                decorators="[]",
                modifiers=modifiers,
                parent_entity="",
                language=self.language,
                source_code=source[:2000],
                dependencies="[]",
                relationships="{}",
            ))
        return entities

    def _extract_enums(self, content: str, file_path: str) -> List[CodeEntity]:
        """Extract enum definitions."""
        entities = []
        for match in self.ENUM_PATTERN.finditer(content):
            modifiers = self._extract_modifiers(match.group(1) or "")
            name = match.group(2)
            generics = (match.group(3) or "").strip()

            line_start = _count_line_number(content, match.start())
            block_end = self._find_block_end(content, match.end())
            line_end = _count_line_number(content, block_end)
            source = content[match.start():block_end].strip()
            docstring = self._extract_doc_comment(content, match.start())

            entities.append(CodeEntity(
                entity_type="enum",
                name=name,
                full_name=_build_full_name(Path(file_path), name),
                file_path=file_path,
                line_start=line_start,
                line_end=line_end,
                signature=f"enum {name}{generics}",
                parameters="[]",
                return_type="",
                docstring=docstring,
                decorators="[]",
                modifiers=modifiers,
                parent_entity="",
                language=self.language,
                source_code=source[:2000],
                dependencies="[]",
                relationships="{}",
            ))
        return entities

    def _extract_impls(self, content: str, file_path: str) -> List[CodeEntity]:
        """Extract impl blocks."""
        entities = []
        for match in self.IMPL_PATTERN.finditer(content):
            modifiers = self._extract_modifiers(match.group(1) or "")
            generics = (match.group(2) or "").strip()
            trait_name = match.group(3)
            type_name = match.group(4)

            line_start = _count_line_number(content, match.start())
            block_end = self._find_block_end(content, match.end())
            line_end = _count_line_number(content, block_end)
            source = content[match.start():block_end].strip()

            if trait_name:
                # Use underscores for consistent naming across name and full_name
                name = f"{trait_name}_for_{type_name}"
                signature = f"impl{generics} {trait_name} for {type_name}"
            else:
                name = type_name
                signature = f"impl{generics} {type_name}"

            entities.append(CodeEntity(
                entity_type="impl",
                name=name,
                full_name=_build_full_name(Path(file_path), name),
                file_path=file_path,
                line_start=line_start,
                line_end=line_end,
                signature=signature,
                parameters="[]",
                return_type="",
                docstring="",
                decorators="[]",
                modifiers=modifiers,
                parent_entity="",
                language=self.language,
                source_code=source[:2000],
                dependencies="[]",
                relationships="{}",
            ))
        return entities

    def _extract_constants(self, content: str, file_path: str) -> List[CodeEntity]:
        """Extract const and static declarations."""
        entities = []
        for match in self.CONST_PATTERN.finditer(content):
            modifiers = self._extract_modifiers(match.group(1) or "")
            kind = match.group(2)  # const or static
            name = match.group(3)
            type_annotation = match.group(4).strip()

            line_start = _count_line_number(content, match.start())
            line_end = line_start
            docstring = self._extract_doc_comment(content, match.start())

            entities.append(CodeEntity(
                entity_type="constant" if "const" in kind else "static",
                name=name,
                full_name=_build_full_name(Path(file_path), name),
                file_path=file_path,
                line_start=line_start,
                line_end=line_end,
                signature=f"{kind} {name}: {type_annotation}",
                parameters="[]",
                return_type=type_annotation,
                docstring=docstring,
                decorators="[]",
                modifiers=modifiers,
                parent_entity="",
                language=self.language,
                source_code="",
                dependencies="[]",
                relationships="{}",
            ))
        return entities

    def _extract_type_aliases(self, content: str, file_path: str) -> List[CodeEntity]:
        """Extract type alias declarations."""
        entities = []
        for match in self.TYPE_ALIAS_PATTERN.finditer(content):
            modifiers = self._extract_modifiers(match.group(1) or "")
            name = match.group(2)
            generics = (match.group(3) or "").strip()
            aliased_type = match.group(4).strip()

            line_start = _count_line_number(content, match.start())
            line_end = line_start
            docstring = self._extract_doc_comment(content, match.start())

            entities.append(CodeEntity(
                entity_type="type",
                name=name,
                full_name=_build_full_name(Path(file_path), name),
                file_path=file_path,
                line_start=line_start,
                line_end=line_end,
                signature=f"type {name}{generics} = {aliased_type}",
                parameters="[]",
                return_type=aliased_type,
                docstring=docstring,
                decorators="[]",
                modifiers=modifiers,
                parent_entity="",
                language=self.language,
                source_code="",
                dependencies="[]",
                relationships="{}",
            ))
        return entities


# =============================================================================
# Unified Code Parser
# =============================================================================


class CodeParser:
    """
    Unified code parser that delegates to language-specific parsers.

    Automatically detects the language based on file extension and uses
    the appropriate parser (Python, TypeScript, JavaScript, or CSS).

    Supported file types:
        - Python: .py
        - TypeScript: .ts, .tsx
        - JavaScript: .js, .jsx
        - CSS: .css
        - Rust: .rs
    """

    SUPPORTED_EXTENSIONS = {".py", ".ts", ".tsx", ".js", ".jsx", ".css", ".rs"}

    def __init__(self):
        """
        Initialize the code parser with all language-specific parsers.

        Creates instances of PythonParser and CSSParser. TypeScriptParser
        instances are created per-file based on extension.
        """
        self._python_parser = PythonParser()
        self._css_parser = CSSParser()
        self._rust_parser = RustParser()

    def parse_file(self, file_path: Path) -> List[CodeEntity]:
        """
        Parse a file and extract code entities.

        Automatically selects the appropriate parser based on file extension.

        Args:
            file_path: Path to the source file

        Returns:
            List of CodeEntity objects extracted from the file.
            Returns empty list if file type is not supported or parsing fails.
        """
        suffix = file_path.suffix.lower()

        if not self.is_supported(file_path):
            logger.debug("Unsupported file type: %s", suffix)
            return []

        try:
            if suffix == ".py":
                return self._python_parser.parse_file(file_path)
            elif suffix in (".ts", ".tsx"):
                parser = TypeScriptParser(file_extension=suffix)
                return parser.parse_file(file_path)
            elif suffix in (".js", ".jsx"):
                parser = TypeScriptParser(file_extension=suffix)
                return parser.parse_file(file_path)
            elif suffix == ".css":
                return self._css_parser.parse_file(file_path)
            elif suffix == ".rs":
                return self._rust_parser.parse_file(file_path)
            else:
                return []
        except Exception as exc:
            logger.exception("Failed to parse %s: %s", file_path, exc)
            return []

    @classmethod
    def get_supported_extensions(cls) -> List[str]:
        """
        Return list of supported file extensions.

        Returns:
            List of extension strings (e.g., [".py", ".ts", ".tsx", ...])
        """
        return list(cls.SUPPORTED_EXTENSIONS)

    @classmethod
    def is_supported(cls, file_path: Path) -> bool:
        """
        Check if a file type is supported by the parser.

        Args:
            file_path: Path to file to check

        Returns:
            True if file extension is supported, False otherwise
        """
        return file_path.suffix.lower() in cls.SUPPORTED_EXTENSIONS


# =============================================================================
# Module-level convenience functions
# =============================================================================


def parse_file(file_path: Path) -> List[CodeEntity]:
    """
    Convenience function to parse a file without explicitly creating a parser.

    Args:
        file_path: Path to the source file

    Returns:
        List of CodeEntity objects extracted from the file
    """
    parser = CodeParser()
    return parser.parse_file(file_path)


def get_supported_extensions() -> List[str]:
    """Return list of supported file extensions."""
    return CodeParser.get_supported_extensions()


def is_supported(file_path: Path) -> bool:
    """Check if a file type is supported by the parser."""
    return CodeParser.is_supported(file_path)
