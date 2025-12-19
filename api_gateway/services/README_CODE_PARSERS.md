# Code Parser System

Multi-language code parser system for extracting code entities and ingesting them into Weaviate for semantic code search.

## Overview

The code parser system provides parsers for Python, TypeScript/JavaScript, and CSS files that extract comprehensive metadata about code entities (functions, classes, variables, interfaces, types, styles) and return `CodeEntity` objects suitable for Weaviate indexing.

This module mirrors the pattern established in `doc_ingestion.py`.

## Architecture

```text
CodeParser (Unified Interface)
    │
    ├── PythonParser
    │   └── Uses Python's built-in `ast` module
    │
    ├── TypeScriptParser
    │   └── Uses Node.js subprocess with ts_parser.js
    │
    └── CSSParser
        └── Uses regex patterns
```

## Supported Languages

| Language   | Extensions    | Parser           | Entity Types                                                                    |
| ---------- | ------------- | ---------------- | ------------------------------------------------------------------------------- |
| Python     | `.py`         | PythonParser     | function, method, class, variable                                               |
| TypeScript | `.ts`, `.tsx` | TypeScriptParser | function, method, class, interface, type, enum, variable, property, constructor |
| JavaScript | `.js`, `.jsx` | TypeScriptParser | function, method, class, variable, property, constructor                        |
| CSS        | `.css`        | CSSParser        | style, animation                                                                |

## Entity Metadata

Each `CodeEntity` contains:

| Field           | Description                                            |
| --------------- | ------------------------------------------------------ |
| `entity_type`   | Type of code entity (function, class, interface, etc.) |
| `name`          | Simple name of the entity                              |
| `full_name`     | Fully qualified name with module path                  |
| `file_path`     | Relative path from workspace root                      |
| `line_start`    | Starting line number (1-indexed)                       |
| `line_end`      | Ending line number (1-indexed)                         |
| `signature`     | Function/method signature or declaration               |
| `parameters`    | Parameter list (JSON string)                           |
| `return_type`   | Return type annotation                                 |
| `docstring`     | Documentation string/JSDoc                             |
| `decorators`    | Decorator/annotation list (JSON array)                 |
| `modifiers`     | Access modifiers, async, static, export, etc.          |
| `parent_entity` | Parent class/module name                               |
| `language`      | Source language identifier                             |
| `source_code`   | Full source code of the entity                         |
| `dependencies`  | Import dependencies (JSON array)                       |
| `relationships` | Cross-references (JSON object)                         |

## Usage

### Basic Usage

```python
from pathlib import Path
from api_gateway.services.code_parsers import CodeParser

parser = CodeParser()
entities = parser.parse_file(Path("example.py"))

for entity in entities:
    print(f"{entity.entity_type}: {entity.full_name}")
    print(f"  Lines: {entity.line_start}-{entity.line_end}")
    print(f"  Signature: {entity.signature}")
```

### Using Specific Parsers

```python
from pathlib import Path
from api_gateway.services.code_parsers import PythonParser, TypeScriptParser, CSSParser

# Python
python_parser = PythonParser()
py_entities = python_parser.parse_file(Path("module.py"))

# TypeScript
ts_parser = TypeScriptParser(file_extension=".ts")
ts_entities = ts_parser.parse_file(Path("component.ts"))

# JavaScript
js_parser = TypeScriptParser(file_extension=".js")
js_entities = js_parser.parse_file(Path("utils.js"))

# CSS
css_parser = CSSParser()
css_entities = css_parser.parse_file(Path("styles.css"))
```

### Convenience Functions

```python
from pathlib import Path
from api_gateway.services.code_parsers import (
    parse_file,
    is_supported,
    get_supported_extensions,
)

# Parse any supported file
entities = parse_file(Path("example.ts"))

# Check if file type is supported
if is_supported(Path("example.py")):
    print("Python is supported!")

# Get all supported extensions
extensions = get_supported_extensions()
# ['.py', '.ts', '.tsx', '.js', '.jsx', '.css']
```

### Weaviate Integration

```python
from api_gateway.services.code_parsers import CodeParser
from api_gateway.services.weaviate_connection import WeaviateConnection

parser = CodeParser()
entities = parser.parse_file(Path("example.py"))

with WeaviateConnection() as client:
    collection = client.collections.get("CodeEntity")
    for entity in entities:
        collection.data.insert(entity.to_properties())
```

## Testing

Run the test suite:

```bash
# Run all tests
python -m unittest api_gateway.services.tests.test_code_parsers

# Run with verbose output
python -m unittest api_gateway.services.tests.test_code_parsers -v

# Run specific test class
python -m unittest api_gateway.services.tests.test_code_parsers.TestPythonParser

# Run specific test
python -m unittest api_gateway.services.tests.test_code_parsers.TestPythonParser.test_extracts_simple_function
```

## Requirements

### Python Parser

- Python 3.8+ (uses built-in `ast` module)

### TypeScript/JavaScript Parser

- Node.js installed and available in PATH
- TypeScript package (already in project's `package.json`)

### CSS Parser

- No additional dependencies (uses built-in `re` module)

## Troubleshooting

### Node.js Not Found

If TypeScript/JavaScript parsing returns empty results:

1. Verify Node.js is installed: `node --version`
2. Ensure `node` is in your PATH
3. Check the log output for warnings about Node.js availability

### Syntax Errors in Source Files

The parsers handle syntax errors gracefully:

- Python: Returns empty list and logs the syntax error
- TypeScript/JavaScript: Returns empty list and logs stderr from Node.js
- CSS: May return partial results for malformed CSS

### Performance Considerations

For large codebases:

- Python parsing is fast (in-process)
- TypeScript/JavaScript parsing has subprocess overhead (30s timeout)
- CSS parsing is fast (regex-based)

Consider batching file parsing and using parallel processing for large-scale ingestion.

## Extending for New Languages

To add support for a new language:

1. Create a new parser class extending `BaseParser`:

```python
class NewLanguageParser(BaseParser):
    @property
    def language(self) -> str:
        return "newlang"

    def parse_file(self, file_path: Path) -> List[CodeEntity]:
        # Implementation here
        pass
```

2. Register the extension in `CodeParser`:

```python
class CodeParser:
    SUPPORTED_EXTENSIONS = {".py", ".ts", ".tsx", ".js", ".jsx", ".css", ".newlang"}

    def parse_file(self, file_path: Path) -> List[CodeEntity]:
        suffix = file_path.suffix.lower()
        # ... existing code ...
        elif suffix == ".newlang":
            parser = NewLanguageParser()
            return parser.parse_file(file_path)
```

3. Add tests in `test_code_parsers.py`

## Files

```
api_gateway/services/
├── code_parsers.py          # Main parser module
├── code_entity_schema.py    # CodeEntity dataclass and Weaviate schema
├── ts_parser.js             # Node.js TypeScript parser helper
├── README_CODE_PARSERS.md   # This file
└── tests/
    ├── __init__.py
    ├── test_code_parsers.py # Unit tests
    └── fixtures/
        ├── __init__.py
        ├── sample.py        # Python test fixture
        ├── sample.ts        # TypeScript test fixture
        ├── sample.js        # JavaScript test fixture
        └── sample.css       # CSS test fixture
```
