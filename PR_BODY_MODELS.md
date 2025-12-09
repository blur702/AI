## Summary
- Add React Router for multi-page navigation with `/models` route
- Create comprehensive Models page with model management UI (VRAM display, search, filters, model cards)
- Enhance backend API with detailed model info endpoints and improved parsing

## Backend Changes
- Add `?detailed=true` support to `/api/models/ollama/list` for unified API
- Improve `get_ollama_model_info()` to use structured `--verbose` output (less brittle parsing)
- Fix `/api/models/ollama/<model>/services` to clarify it returns LLM-capable services (potential usage)
- Add MODEL_CAPABILITIES database for 40+ model families with descriptions
- Add VRAM estimation based on quantization type (Q4/Q5/Q6/Q8/FP16/FP32)

## Frontend Changes
- Add react-router-dom@^6.20.0 for routing
- Create `DashboardHome` component (extracted from App.tsx)
- Create `ModelsPage` with VRAM summary, model cards, search/filter, dialogs
- Create `useModels` hook for model state management with 30s polling
- Update `useSocket` to handle `model_download_progress` WebSocket events
- Add model mappings to services config (openwebui, ollama)

## New API Endpoints
- `GET /api/models/ollama/info/<model_name>` - detailed model info
- `GET /api/models/ollama/detailed` - all models with full details
- `POST /api/models/ollama/remove` - delete model with confirmation

## Test plan
- [ ] Verify `/models` route loads and displays model cards
- [ ] Test model load/unload functionality
- [ ] Test model download with progress updates
- [ ] Verify VRAM estimation displays correctly
- [ ] Test search and filter controls
- [ ] Verify navigation between Dashboard and Models pages

🤖 Generated with [Claude Code](https://claude.com/claude-code)
