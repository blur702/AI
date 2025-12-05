# Playwright Test Suite

This directory contains a TypeScript-based Playwright test suite for the dashboard UI, dashboard backend, API gateway, and AI services.

## Prerequisites

- Node.js 18+ recommended
- `npm install` executed in the project root
- All core services running (dashboard backend, API gateway, Open WebUI, ComfyUI, Ollama, Wan2GP, YuE, DiffRhythm, MusicGen, Stable Audio, AllTalk, N8N)

## Installation

From the project root:

- Install dependencies: `npm install`
- Configure environment: copy `.env.example` to `.env` and adjust URLs as needed

## Running Tests

- All tests (headless): `npm test`
- All tests (headed): `npm run test:headed`
- API tests only: `npm run test:api`
- UI tests only: `npm run test:ui`
- Smoke tests: `npm run test:smoke`
- Debug with inspector: `npm run test:debug`
- Playwright UI mode: `npm run test:ui-mode`
- Open HTML report: `npm run test:report`
- Code generator: `npm run test:codegen`
- Service-specific tests (via `SERVICE` env): `npm run test:services`
- Run in parallel (default workers): `npm run test:parallel`
- Run serially: `npm run test:serial`
- Chromium only: `npm run test:chrome`
- Firefox only: `npm run test:firefox`
- WebKit only: `npm run test:webkit`

## Structure

- `config/` – Playwright config
- `fixtures/` – shared Playwright fixtures
- `page-objects/` – Page Object Model classes
- `api-clients/` – HTTP and WebSocket clients
- `utils/` – helpers for waiting, assertions, screenshots, WebSockets
- `tests/` – API, UI, integration, and smoke specs
- `test-data/` – prompts, models, and assets
- `reports/` – test reports and artifacts

## Adding New Tests

- Create or extend page objects under `page-objects/`
- Use fixtures from `fixtures/base.fixture.ts` or `fixtures/services.fixture.ts`
- Place API specs under `tests/api/` and UI specs under `tests/ui/`

## Debugging

- Use `npm run test:debug` for inspector mode
- Use `npm run test:ui-mode` for interactive UI mode
- Traces, screenshots, and videos are captured on failures and retries

