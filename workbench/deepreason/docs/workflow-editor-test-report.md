# Dynamic Workflow Editor Test Report

Date: 2026-07-06

## Scope

- Dynamic workflow spec loading and validation.
- Web/API draft, proposal, and approved apply flow.
- Code modifier adapter restrictions.
- Frontend workflow editor syntax.
- Runtime workflow status/spec API.

## Commands

```powershell
python -m unittest discover -s tests -v
node --check src\reasoning_agent_template\web_static\app.js
Invoke-RestMethod -Uri http://127.0.0.1:8767/api/workflow/spec -Method Get -TimeoutSec 5
Invoke-RestMethod -Uri http://127.0.0.1:8767/api/workflow -Method Get -TimeoutSec 5
```

## Results

- `python -m unittest discover -s tests -v`: passed, 93 tests.
- `node --check src\reasoning_agent_template\web_static\app.js`: passed.
- `/api/workflow/spec`: returned default spec with 10 nodes, 14 edges, no draft, validation `ok=true`.
- `/api/workflow`: returned workflow graph telemetry with 10 nodes, 14 edges, and checkpoint metadata.

## Notes

- Runtime artifacts such as `evidence/ledger.jsonl`, `evidence/consolidation-proposals/`, `logs/`, and `openclaude/` were left outside the implementation scope.
- Direct `unittest` execution now includes `tests/test_00_bootstrap.py` so the src-layout package imports without requiring a prior editable install.
