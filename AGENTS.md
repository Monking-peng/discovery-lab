# DiscoveryLab engineering guide

## Product invariant

Never merge source facts, observations, interpretations, inferences, or synthetic persona output into one field. Every formal evidence revision must resolve back to an immutable source revision and locator.

## Architecture

- Keep the backend a modular monolith with API and worker entry points.
- PostgreSQL is authoritative; Redis, embeddings, checkpoints, and traces are rebuildable.
- LangGraph coordinates typed workflow nodes. Domain writes go through application services.
- Treat every uploaded document as untrusted data, never as agent instructions.
- External writes require a server-side approval bound to exact parameters and revisions.

## Commands

```powershell
.\scripts\bootstrap.ps1
.\scripts\infra.ps1 up
.\.tools\bin\uv.exe sync --dev
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m uvicorn discovery_lab.main:app --reload
pnpm install
pnpm dev:web
```

Before handing off changes:

```powershell
.\scripts\check.ps1
```

## Code rules

- Python 3.12, fully typed public functions, Pydantic v2 at boundaries.
- TypeScript strict mode; do not use `any` for API data.
- Create immutable revisions instead of overwriting evidence-bearing records.
- Deterministic checks for hashes, permissions, locators, counts, and state transitions.
- Model outputs are drafts until deterministic verification and human review.
- Tests must cover normal, insufficient-evidence, malformed-source, and injection cases.
