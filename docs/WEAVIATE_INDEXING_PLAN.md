# Comprehensive Codebase Index Plan

## Goal
Transform the Weaviate vector database into a comprehensive semantic mapping of the entire project that LLMs query BEFORE searching the codebase directly. Auto-update on every git commit.

## Current State
- **Documentation**: 142 chunks (only `docs/` + root `.md` files)
- **CodeEntity**: 21,514 entities (core project only)
- **MCP Server**: Only exposes `search_documentation` (no code search)
- **Git hooks**: None configured
- **CLAUDE.md**: No reference to vector DB

---

## Implementation Plan

### Phase 1: Add Code Search MCP Tool (Immediate Value)

**1.1 Add `search_code` tool to MCP server**
- File: `mcp_servers/documentation/main.py`
- Search CodeEntity collection with semantic similarity
- Support filtering by: entity_type, service_name, language
- Return: name, signature, file_path:line_start, docstring, source_code snippet

**1.2 Add `search_codebase` unified tool**
- Searches both Documentation AND CodeEntity collections
- Returns combined, ranked results
- Best for "how does X work?" queries needing both docs and code

### Phase 2: Update CLAUDE.md for Vector DB Usage

**2.1 Add Weaviate section instructing LLMs to:**
- Query vector DB BEFORE using Glob/Grep
- Use `search_code` for finding definitions
- Use `search_documentation` for understanding concepts
- Use `search_codebase` for comprehensive understanding

### Phase 3: Expand Code Indexing to All Services

**3.1 Full reindex with all services**
```bash
python -m api_gateway.services.code_ingestion reindex --service all
python -m api_gateway.services.code_ingestion ingest --service core
```

**3.2 Update dashboard SettingsPanel to support "all" option**
- Add option to index all services at once

### Phase 4: Expand Documentation Coverage

**4.1 Include service READMEs**
- Modify `doc_ingestion.py` to scan AI service directories for README.md
- Add service attribution to doc chunks

### Phase 5: Git Hook for Auto-Update

**5.1 Create post-commit hook**
- File: `.git/hooks/post-commit`
- Detect changed files from commit
- Trigger incremental ingestion for affected files only

**5.2 Incremental ingestion support**
- Add `ingest_files(file_paths: List[Path])` to code_ingestion.py
- Delete old entities for changed files before re-indexing
- File: `api_gateway/services/ingestion_trigger.py`

**5.3 Hook script**
```bash
#!/bin/bash
# .git/hooks/post-commit
changed_files=$(git diff-tree --no-commit-id --name-only -r HEAD)
python -m api_gateway.services.ingestion_trigger --files "$changed_files"
```

### Phase 6: Enhanced Schema (Future)

**6.1 Test linkage**
- Add `has_tests`, `test_file_path` fields
- Link source entities to test files

**6.2 Cross-references**
- Populate `relationships` field with actual entity references

---

## Files to Create/Modify

| File | Action | Description |
|------|--------|-------------|
| `mcp_servers/documentation/main.py` | Modify | Add `search_code`, `search_codebase` tools |
| `CLAUDE.md` | Modify | Add Weaviate usage instructions |
| `api_gateway/services/doc_ingestion.py` | Modify | Scan service READMEs |
| `api_gateway/services/ingestion_trigger.py` | Create | Handle incremental updates from git hooks |
| `.git/hooks/post-commit` | Create | Trigger ingestion on commit |

---

## Execution Order

1. **Phase 1** - Add MCP tools (search_code, search_codebase)
2. **Phase 2** - Update CLAUDE.md with usage instructions
3. **Phase 3** - Full reindex with all services
4. **Phase 4** - Include service READMEs in documentation
5. **Phase 5** - Git hooks for auto-update

---

## Success Criteria

- [ ] `search_code` MCP tool returns relevant code entities
- [ ] `search_codebase` returns combined doc + code results
- [ ] CLAUDE.md instructs LLMs to query DB before file search
- [ ] All 8 AI services indexed in CodeEntity collection
- [ ] Service READMEs included in Documentation collection
- [ ] Git commits trigger automatic incremental reindex
