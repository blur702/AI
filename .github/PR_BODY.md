## Summary
- Add pause/resume functionality for AI services using OS-level process suspension (psutil)
- Add pause/resume functionality for all ingestion operations (doc, code, scrapers)
- Implement cooperative pause checking via `check_paused` callback pattern
- Add paused state visual indicators throughout the dashboard UI
- Extend status chips to show Completed/Failed states in Settings panel

## Changes
- **Backend**: Added pause/resume to `service_manager.py`, `ingestion_manager.py`, `app.py`
- **Scrapers**: Added `check_paused` callback to `doc_ingestion.py`, `code_ingestion.py`, `drupal_scraper.py`, `mdn_javascript_scraper.py`, `mdn_webapis_scraper.py`
- **Frontend**: Updated types, hooks, SettingsPanel, ServiceCard, App.tsx for pause state handling
- **Docs**: Added CodeRabbit integration documentation to CLAUDE.md

## Test plan
- [ ] Verify service pause/resume buttons work correctly
- [ ] Verify ingestion pause/resume in Settings panel works
- [ ] Verify status chips show correct states (Running, Paused, Completed, Failed)
- [ ] Verify dark mode styling for pause button is correct

🤖 Generated with [Claude Code](https://claude.com/claude-code)
