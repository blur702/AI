/**
 * TypeScript/JavaScript parser helper script.
 *
 * Uses the TypeScript compiler API to parse source files and extract
 * comprehensive metadata about code entities (functions, classes, interfaces,
 * types, variables).
 *
 * Usage:
 *   node ts_parser.js <file_path>
 *
 * Output:
 *   JSON array of code entities to stdout
 *   Errors to stderr
 */

const ts = require("typescript");
const fs = require("fs");
const path = require("path");

/**
 * Get JSDoc comment text for a node.
 * @param {ts.Node} node
 * @param {ts.SourceFile} sourceFile
 * @returns {string}
 */
function getJSDocComment(node, sourceFile) {
  const jsDocs = ts.getJSDocCommentsAndTags(node);
  if (!jsDocs || jsDocs.length === 0) {
    return "";
  }

  const comments = [];
  for (const jsDoc of jsDocs) {
    if (ts.isJSDoc(jsDoc) && jsDoc.comment) {
      if (typeof jsDoc.comment === "string") {
        comments.push(jsDoc.comment);
      } else if (Array.isArray(jsDoc.comment)) {
        comments.push(jsDoc.comment.map((c) => c.text || "").join(""));
      }
    }
  }
  return comments.join("\n").trim();
}

/**
 * Get modifiers for a node (export, async, static, etc.).
 * @param {ts.Node} node
 * @returns {string[]}
 */
function getModifiers(node) {
  const modifiers = [];

  if (node.modifiers) {
    for (const mod of node.modifiers) {
      switch (mod.kind) {
        case ts.SyntaxKind.ExportKeyword:
          modifiers.push("export");
          break;
        case ts.SyntaxKind.DefaultKeyword:
          modifiers.push("default");
          break;
        case ts.SyntaxKind.AsyncKeyword:
          modifiers.push("async");
          break;
        case ts.SyntaxKind.StaticKeyword:
          modifiers.push("static");
          break;
        case ts.SyntaxKind.ReadonlyKeyword:
          modifiers.push("readonly");
          break;
        case ts.SyntaxKind.PublicKeyword:
          modifiers.push("public");
          break;
        case ts.SyntaxKind.PrivateKeyword:
          modifiers.push("private");
          break;
        case ts.SyntaxKind.ProtectedKeyword:
          modifiers.push("protected");
          break;
        case ts.SyntaxKind.AbstractKeyword:
          modifiers.push("abstract");
          break;
        case ts.SyntaxKind.ConstKeyword:
          modifiers.push("const");
          break;
        case ts.SyntaxKind.DeclareKeyword:
          modifiers.push("declare");
          break;
      }
    }
  }

  return modifiers;
}

/**
 * Get decorators for a node.
 * @param {ts.Node} node
 * @param {ts.SourceFile} sourceFile
 * @returns {string[]}
 */
function getDecorators(node, sourceFile) {
  const decorators = [];

  // TypeScript 5.0+ uses canHaveDecorators/getDecorators
  if (ts.canHaveDecorators && ts.canHaveDecorators(node)) {
    const nodeDecorators = ts.getDecorators(node);
    if (nodeDecorators) {
      for (const decorator of nodeDecorators) {
        decorators.push("@" + decorator.expression.getText(sourceFile));
      }
    }
  }
  // Fallback for older TypeScript versions
  else if (node.decorators) {
    for (const decorator of node.decorators) {
      decorators.push("@" + decorator.expression.getText(sourceFile));
    }
  }

  return decorators;
}

/**
 * Get line and column information for a position.
 * @param {ts.SourceFile} sourceFile
 * @param {number} pos
 * @returns {{line: number, character: number}}
 */
function getLineInfo(sourceFile, pos) {
  const { line, character } = sourceFile.getLineAndCharacterOfPosition(pos);
  return { line: line + 1, character }; // Convert to 1-indexed
}

/**
 * Extract parameter information from a function-like declaration.
 * @param {ts.FunctionLikeDeclaration} node
 * @param {ts.SourceFile} sourceFile
 * @returns {Array<{name: string, type: string, optional: boolean, default: string|null}>}
 */
function extractParameters(node, sourceFile) {
  const params = [];

  if (node.parameters) {
    for (const param of node.parameters) {
      const paramInfo = {
        name: param.name.getText(sourceFile),
        type: param.type ? param.type.getText(sourceFile) : "any",
        optional: !!param.questionToken,
        default: param.initializer
          ? param.initializer.getText(sourceFile)
          : null,
      };
      params.push(paramInfo);
    }
  }

  return params;
}

/**
 * Get the return type of a function-like declaration.
 * @param {ts.FunctionLikeDeclaration} node
 * @param {ts.SourceFile} sourceFile
 * @returns {string}
 */
function getReturnType(node, sourceFile) {
  if (node.type) {
    return node.type.getText(sourceFile);
  }
  return "";
}

/**
 * Build a signature string for a function.
 * @param {string} name
 * @param {Array} params
 * @param {string} returnType
 * @param {boolean} isAsync
 * @returns {string}
 */
function buildFunctionSignature(name, params, returnType, isAsync) {
  const asyncPrefix = isAsync ? "async " : "";
  const paramStr = params
    .map((p) => {
      let s = p.name;
      if (p.optional) s += "?";
      if (p.type && p.type !== "any") s += ": " + p.type;
      if (p.default) s += " = " + p.default;
      return s;
    })
    .join(", ");
  const retStr = returnType ? `: ${returnType}` : "";
  return `${asyncPrefix}function ${name}(${paramStr})${retStr}`;
}

/**
 * Extract interface properties.
 * @param {ts.InterfaceDeclaration} node
 * @param {ts.SourceFile} sourceFile
 * @returns {Array<{name: string, type: string, optional: boolean}>}
 */
function extractInterfaceProperties(node, sourceFile) {
  const props = [];

  for (const member of node.members) {
    if (ts.isPropertySignature(member)) {
      props.push({
        name: member.name.getText(sourceFile),
        type: member.type ? member.type.getText(sourceFile) : "any",
        optional: !!member.questionToken,
      });
    } else if (ts.isMethodSignature(member)) {
      const params = extractParameters(member, sourceFile);
      const returnType = getReturnType(member, sourceFile);
      props.push({
        name: member.name.getText(sourceFile),
        type: `(${params.map((p) => `${p.name}: ${p.type}`).join(", ")}) => ${returnType || "void"}`,
        optional: !!member.questionToken,
        isMethod: true,
      });
    }
  }

  return props;
}

/**
 * Extract heritage clauses (extends, implements).
 * @param {ts.Node} node
 * @param {ts.SourceFile} sourceFile
 * @returns {{extends: string[], implements: string[]}}
 */
function extractHeritage(node, sourceFile) {
  const result = { extends: [], implements: [] };

  if (node.heritageClauses) {
    for (const clause of node.heritageClauses) {
      const types = clause.types.map((t) => t.expression.getText(sourceFile));
      if (clause.token === ts.SyntaxKind.ExtendsKeyword) {
        result.extends.push(...types);
      } else if (clause.token === ts.SyntaxKind.ImplementsKeyword) {
        result.implements.push(...types);
      }
    }
  }

  return result;
}

/**
 * Parse a TypeScript/JavaScript file and extract code entities.
 * @param {string} filePath
 * @returns {Array}
 */
function parseFile(filePath) {
  const absolutePath = path.resolve(filePath);
  // Read file with fallback encoding to handle non-UTF-8 files
  let fileContent;
  try {
    fileContent = fs.readFileSync(absolutePath, "utf-8");
  } catch (e) {
    // If UTF-8 fails, try reading as latin1 (ISO-8859-1) which accepts any byte sequence
    fileContent = fs.readFileSync(absolutePath, "latin1");
  }
  const isTypeScript =
    filePath.endsWith(".ts") || filePath.endsWith(".tsx");
  const language = isTypeScript ? "typescript" : "javascript";

  const sourceFile = ts.createSourceFile(
    path.basename(filePath),
    fileContent,
    ts.ScriptTarget.Latest,
    true,
    isTypeScript
      ? filePath.endsWith(".tsx")
        ? ts.ScriptKind.TSX
        : ts.ScriptKind.TS
      : filePath.endsWith(".jsx")
        ? ts.ScriptKind.JSX
        : ts.ScriptKind.JS
  );

  const entities = [];
  const imports = [];

  /**
   * Visit a node and extract entity information.
   * @param {ts.Node} node
   * @param {string|null} parentEntity
   */
  function visit(node, parentEntity = null) {
    const startInfo = getLineInfo(sourceFile, node.getStart(sourceFile));
    const endInfo = getLineInfo(sourceFile, node.getEnd());

    // Import declarations - collect for dependencies
    if (ts.isImportDeclaration(node)) {
      const moduleSpecifier = node.moduleSpecifier;
      if (ts.isStringLiteral(moduleSpecifier)) {
        imports.push(moduleSpecifier.text);
      }
      return;
    }

    // Function declarations
    if (ts.isFunctionDeclaration(node) && node.name) {
      const name = node.name.getText(sourceFile);
      const modifiers = getModifiers(node);
      const params = extractParameters(node, sourceFile);
      const returnType = getReturnType(node, sourceFile);
      const isAsync = modifiers.includes("async");
      const decorators = getDecorators(node, sourceFile);

      entities.push({
        entity_type: "function",
        name: name,
        full_name: parentEntity ? `${parentEntity}.${name}` : name,
        line_start: startInfo.line,
        line_end: endInfo.line,
        signature: buildFunctionSignature(name, params, returnType, isAsync),
        parameters: JSON.stringify(params),
        return_type: returnType,
        docstring: getJSDocComment(node, sourceFile),
        decorators: JSON.stringify(decorators),
        modifiers: modifiers.join(", "),
        parent_entity: parentEntity || "",
        language: language,
        source_code: node.getText(sourceFile),
      });
    }

    // Arrow functions assigned to variables
    if (ts.isVariableStatement(node)) {
      const modifiers = getModifiers(node);
      const decorators = getDecorators(node, sourceFile);

      for (const decl of node.declarationList.declarations) {
        if (ts.isIdentifier(decl.name)) {
          const name = decl.name.getText(sourceFile);

          // Check if it's an arrow function or function expression
          if (
            decl.initializer &&
            (ts.isArrowFunction(decl.initializer) ||
              ts.isFunctionExpression(decl.initializer))
          ) {
            const func = decl.initializer;
            const params = extractParameters(func, sourceFile);
            const returnType = getReturnType(func, sourceFile);
            const isAsync =
              func.modifiers?.some(
                (m) => m.kind === ts.SyntaxKind.AsyncKeyword
              ) || false;

            entities.push({
              entity_type: "function",
              name: name,
              full_name: parentEntity ? `${parentEntity}.${name}` : name,
              line_start: startInfo.line,
              line_end: endInfo.line,
              signature: buildFunctionSignature(
                name,
                params,
                returnType,
                isAsync
              ),
              parameters: JSON.stringify(params),
              return_type: returnType,
              docstring: getJSDocComment(node, sourceFile),
              decorators: JSON.stringify(decorators),
              modifiers: modifiers.join(", "),
              parent_entity: parentEntity || "",
              language: language,
              source_code: node.getText(sourceFile),
            });
          } else {
            // Regular variable
            const typeAnnotation = decl.type
              ? decl.type.getText(sourceFile)
              : "";
            const isConst =
              node.declarationList.flags & ts.NodeFlags.Const
                ? "const"
                : node.declarationList.flags & ts.NodeFlags.Let
                  ? "let"
                  : "var";

            entities.push({
              entity_type: "variable",
              name: name,
              full_name: parentEntity ? `${parentEntity}.${name}` : name,
              line_start: startInfo.line,
              line_end: endInfo.line,
              signature: `${isConst} ${name}${typeAnnotation ? `: ${typeAnnotation}` : ""}`,
              parameters: "[]",
              return_type: typeAnnotation,
              docstring: getJSDocComment(node, sourceFile),
              decorators: JSON.stringify(decorators),
              modifiers: [...modifiers, isConst].join(", "),
              parent_entity: parentEntity || "",
              language: language,
              source_code: node.getText(sourceFile),
            });
          }
        }
      }
      return;
    }

    // Class declarations
    if (ts.isClassDeclaration(node)) {
      const name = node.name ? node.name.getText(sourceFile) : "AnonymousClass";
      const modifiers = getModifiers(node);
      const decorators = getDecorators(node, sourceFile);
      const heritage = extractHeritage(node, sourceFile);

      const relationships = {
        extends: heritage.extends,
        implements: heritage.implements,
      };

      entities.push({
        entity_type: "class",
        name: name,
        full_name: parentEntity ? `${parentEntity}.${name}` : name,
        line_start: startInfo.line,
        line_end: endInfo.line,
        signature: `class ${name}${heritage.extends.length ? ` extends ${heritage.extends.join(", ")}` : ""}${heritage.implements.length ? ` implements ${heritage.implements.join(", ")}` : ""}`,
        parameters: "[]",
        return_type: "",
        docstring: getJSDocComment(node, sourceFile),
        decorators: JSON.stringify(decorators),
        modifiers: modifiers.join(", "),
        parent_entity: parentEntity || "",
        language: language,
        source_code: node.getText(sourceFile),
        relationships: JSON.stringify(relationships),
      });

      // Visit class members with class as parent
      for (const member of node.members) {
        if (ts.isMethodDeclaration(member) && member.name) {
          const methodName = member.name.getText(sourceFile);
          const methodModifiers = getModifiers(member);
          const methodParams = extractParameters(member, sourceFile);
          const methodReturnType = getReturnType(member, sourceFile);
          const isAsync = methodModifiers.includes("async");
          const methodDecorators = getDecorators(member, sourceFile);
          const memberStart = getLineInfo(
            sourceFile,
            member.getStart(sourceFile)
          );
          const memberEnd = getLineInfo(sourceFile, member.getEnd());

          entities.push({
            entity_type: "method",
            name: methodName,
            full_name: `${name}.${methodName}`,
            line_start: memberStart.line,
            line_end: memberEnd.line,
            signature: buildFunctionSignature(
              methodName,
              methodParams,
              methodReturnType,
              isAsync
            ).replace("function ", ""),
            parameters: JSON.stringify(methodParams),
            return_type: methodReturnType,
            docstring: getJSDocComment(member, sourceFile),
            decorators: JSON.stringify(methodDecorators),
            modifiers: methodModifiers.join(", "),
            parent_entity: name,
            language: language,
            source_code: member.getText(sourceFile),
          });
        } else if (ts.isPropertyDeclaration(member) && member.name) {
          const propName = member.name.getText(sourceFile);
          const propModifiers = getModifiers(member);
          const propType = member.type ? member.type.getText(sourceFile) : "";
          const propDecorators = getDecorators(member, sourceFile);
          const memberStart = getLineInfo(
            sourceFile,
            member.getStart(sourceFile)
          );
          const memberEnd = getLineInfo(sourceFile, member.getEnd());

          entities.push({
            entity_type: "property",
            name: propName,
            full_name: `${name}.${propName}`,
            line_start: memberStart.line,
            line_end: memberEnd.line,
            signature: `${propName}${member.questionToken ? "?" : ""}${propType ? `: ${propType}` : ""}`,
            parameters: "[]",
            return_type: propType,
            docstring: getJSDocComment(member, sourceFile),
            decorators: JSON.stringify(propDecorators),
            modifiers: propModifiers.join(", "),
            parent_entity: name,
            language: language,
            source_code: member.getText(sourceFile),
          });
        } else if (ts.isConstructorDeclaration(member)) {
          const ctorParams = extractParameters(member, sourceFile);
          const ctorDecorators = getDecorators(member, sourceFile);
          const memberStart = getLineInfo(
            sourceFile,
            member.getStart(sourceFile)
          );
          const memberEnd = getLineInfo(sourceFile, member.getEnd());

          entities.push({
            entity_type: "constructor",
            name: "constructor",
            full_name: `${name}.constructor`,
            line_start: memberStart.line,
            line_end: memberEnd.line,
            signature: `constructor(${ctorParams.map((p) => `${p.name}: ${p.type}`).join(", ")})`,
            parameters: JSON.stringify(ctorParams),
            return_type: name,
            docstring: getJSDocComment(member, sourceFile),
            decorators: JSON.stringify(ctorDecorators),
            modifiers: "",
            parent_entity: name,
            language: language,
            source_code: member.getText(sourceFile),
          });
        }
      }
      return;
    }

    // Interface declarations
    if (ts.isInterfaceDeclaration(node)) {
      const name = node.name.getText(sourceFile);
      const modifiers = getModifiers(node);
      const heritage = extractHeritage(node, sourceFile);
      const props = extractInterfaceProperties(node, sourceFile);

      entities.push({
        entity_type: "interface",
        name: name,
        full_name: parentEntity ? `${parentEntity}.${name}` : name,
        line_start: startInfo.line,
        line_end: endInfo.line,
        signature: `interface ${name}${heritage.extends.length ? ` extends ${heritage.extends.join(", ")}` : ""}`,
        parameters: JSON.stringify(props),
        return_type: "",
        docstring: getJSDocComment(node, sourceFile),
        decorators: "[]",
        modifiers: modifiers.join(", "),
        parent_entity: parentEntity || "",
        language: language,
        source_code: node.getText(sourceFile),
        relationships: JSON.stringify({ extends: heritage.extends }),
      });
      return;
    }

    // Type alias declarations
    if (ts.isTypeAliasDeclaration(node)) {
      const name = node.name.getText(sourceFile);
      const modifiers = getModifiers(node);
      const typeValue = node.type.getText(sourceFile);

      entities.push({
        entity_type: "type",
        name: name,
        full_name: parentEntity ? `${parentEntity}.${name}` : name,
        line_start: startInfo.line,
        line_end: endInfo.line,
        signature: `type ${name} = ${typeValue}`,
        parameters: "[]",
        return_type: typeValue,
        docstring: getJSDocComment(node, sourceFile),
        decorators: "[]",
        modifiers: modifiers.join(", "),
        parent_entity: parentEntity || "",
        language: language,
        source_code: node.getText(sourceFile),
      });
      return;
    }

    // Enum declarations
    if (ts.isEnumDeclaration(node)) {
      const name = node.name.getText(sourceFile);
      const modifiers = getModifiers(node);
      const members = node.members.map((m) => m.name.getText(sourceFile));

      entities.push({
        entity_type: "enum",
        name: name,
        full_name: parentEntity ? `${parentEntity}.${name}` : name,
        line_start: startInfo.line,
        line_end: endInfo.line,
        signature: `enum ${name} { ${members.join(", ")} }`,
        parameters: JSON.stringify(members),
        return_type: "",
        docstring: getJSDocComment(node, sourceFile),
        decorators: "[]",
        modifiers: modifiers.join(", "),
        parent_entity: parentEntity || "",
        language: language,
        source_code: node.getText(sourceFile),
      });
      return;
    }

    // Continue traversing
    ts.forEachChild(node, (child) => visit(child, parentEntity));
  }

  // Start visiting from the source file
  ts.forEachChild(sourceFile, (node) => visit(node, null));

  // Add import dependencies to all entities
  const dependenciesJson = JSON.stringify(imports);
  for (const entity of entities) {
    if (!entity.relationships) {
      entity.relationships = JSON.stringify({ imports: imports });
    } else {
      const rel = JSON.parse(entity.relationships);
      rel.imports = imports;
      entity.relationships = JSON.stringify(rel);
    }
    entity.dependencies = dependenciesJson;
  }

  return entities;
}

// Main execution
if (require.main === module) {
  const args = process.argv.slice(2);

  if (args.length === 0) {
    console.error("Usage: node ts_parser.js <file_path>");
    process.exit(1);
  }

  const filePath = args[0];

  if (!fs.existsSync(filePath)) {
    console.error(`File not found: ${filePath}`);
    process.exit(1);
  }

  try {
    const entities = parseFile(filePath);
    console.log(JSON.stringify(entities, null, 2));
  } catch (error) {
    console.error(`Error parsing file: ${error.message}`);
    process.exit(1);
  }
}

module.exports = { parseFile };
