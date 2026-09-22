# Claude Handover Prompt — Swing Trading

Continue the actual local Swing Trading application.

## Authoritative workspace

Working path:

`D:\Swing Trading`

The local filesystem, executable application, and production SQLite database are authoritative. GitHub is not required for this work. Do not infer completeness from a remote repository.

Local Git identity is informational only:

- Branch: `release/final-phase5-batch-b-20260820`
- HEAD: `8a1d7db0fb25ef03e5bd96c6f311a91287fe7e70`
- The worktree contains substantial valid, uncommitted post-Phase-5 work.

Do not reset, clean, checkout over, discard, stage, commit, push, pull, merge, or synchronize anything unless I explicitly request it. Preserve every existing local modification and untracked project file.

## Current development stage

The application is post-Phase-5 with local data-automation and broker-document integration implemented and release-validated. The published Phase-5 commit does not contain all active local work.

Implemented locally:

- Responsive FastAPI + React Swing Trading application.
- Genuine OHLCV import, provenance, conflict detection, idempotency, corporate actions, technical indicators, fundamentals, candidate evaluation, risk/reward, evidence API, broker consensus, and trade journal.
- Data Sync UI/API for NSE OHLCV/Bhavcopy, NSE fundamental-filing discovery, and ICICI Direct recommendation discovery.
- Broker PDF upload/storage UI/API. Uploading a PDF preserves evidence only; it does not create a recommendation.
- Windows wrapper scripts and optional Task Scheduler registration scripts.
- Start/stop batch files for local use.

Read this validation record before changing automation:

`D:\Swing Trading\docs\post-phase5-data-tools-validation.md`

## Production database — protect this baseline

Production database:

`D:\Swing Trading\data\swing_trading.db`

Verified on 2026-09-22:

- `daily_ohlcv`: 5095
- `fundamental_snapshot`: 20
- `candidate_evaluation_run`: 43
- `candidate_criterion_result`: 387
- `risk_reward_result`: 36
- `broker_recommendation`: 5
- `data_import_batch`: 91
- `trade_journal`: 0
- Latest OHLCV date: 2026-09-03
- Synthetic/test OHLCV: 0
- `PRAGMA integrity_check`: `ok`
- `PRAGMA foreign_key_check`: 0 violations

Do not modify production merely to make a test pass. Before any authorized production correction or import:

1. Reconfirm the baseline.
2. Create a timestamped SQLite backup using SQLite's backup API.
3. Record before counts.
4. Use the application's actual preview/confirm workflow, never ad-hoc SQL inserts.
5. Make only the approved change.
6. Verify counts, integrity, foreign keys, provenance, duplicates, and conflicts afterward.

Do not run production candidate evaluations, fundamental confirms, OHLCV imports, recommendation imports, or trade-journal writes without an explicit task authorizing that specific production operation.

## Python and frontend environments

Python executable:

`D:\Swing Trading\backend\venv\Scripts\python.exe`

Do not install packages unless a verified missing dependency genuinely requires it.

Backend commands:

```powershell
cd 'D:\Swing Trading\backend'
.\venv\Scripts\python.exe -m pytest
.\venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Frontend commands:

```powershell
cd 'D:\Swing Trading\frontend'
npm test -- --run
npm run lint
npm run build
npm run dev -- --host 127.0.0.1
```

Browser regression:

```powershell
cd 'D:\Swing Trading\frontend'
$env:STAGE8_BASE_URL='http://127.0.0.1:5173'
npm run test:e2e
```

The Playwright trade-lifecycle write tests intentionally skip against production unless a disposable backend is configured.

## Last executed release gate

Verified on 2026-09-17 after automation hardening:

- Backend: 196 passed.
- Frontend unit tests: 51 passed.
- Frontend build: PASS.
- Frontend lint: PASS with five pre-existing warnings.
- Full Playwright suite: 195 passed, 7 intentionally skipped.
- Responsive checks: 320, 375, 390, 768, and 1024 pixels.
- Dedicated browser console/network checks: PASS.
- `GET /health`: PASS.
- Production database SHA/counts remained unchanged during validation.

Do not repeat these as current PASS results unless you execute them again after further code changes.

## Automated refresh safety model

Relevant files:

- `scratch\auto_download_ohlcv.py`
- `scratch\auto_download_fundamentals.py`
- `scratch\auto_download_broker_recs_icici.py`
- `backend\app\services\data_sync_service.py`
- `backend\app\routers\data_sync.py`
- `frontend\src\pages\DataSync.tsx`
- `scratch\register_scheduled_tasks.ps1`

Required behavior:

- Production OHLCV writes require explicit UI/API confirmation.
- The OHLCV script independently requires `--confirm-production` when the configured DB is production.
- Production imports cannot use `--no-backup`.
- Backups use SQLite's backup API and validate integrity.
- The script follows `DATABASE_URL`, allowing safe disposable-copy validation.
- Only one in-app instance of each refresh job may run at once.
- Full-market Bhavcopy filters to mapped EQ stocks; unmapped market rows are reported separately from invalid rows.
- Exact replay must insert zero duplicate OHLCV rows.
- Fundamentals discovery downloads/reports filings only; it never fabricates or imports metrics.
- ICICI discovery downloads/reports candidates only; it never inserts recommendations.
- Scheduled wrappers preserve real exit codes.
- Task Scheduler uses `IgnoreNew` to prevent overlapping task instances.

Live disposable proof already completed:

- NSE Bhavcopy for 2026-09-16 downloaded successfully.
- Import through `OhlcvService.confirm_import` on a disposable production copy inserted 27 tracked rows.
- Invalid: 0; conflicts: 0.
- Exact replay inserted 0 and skipped 27 duplicates.
- Disposable copy had 0 duplicate keys, 0 invalid OHLC, 0 negative volume, integrity `ok`, and 0 FK violations.
- Production was not imported.

Task definitions were validated without registering them:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File 'D:\Swing Trading\scratch\register_scheduled_tasks.ps1' -ValidateOnly
```

No Windows scheduled tasks were created. Registering tasks changes OS state and requires an explicit user request.

## Broker recommendation evidence policy

Broker recommendations are evidence, not guaranteed BUY/SELL instructions.

Rules:

- Preserve stock identity, broker identity, recommendation date, original rating, target, stop, entry information, horizon, analyst/publication details, source reference, original extract, verification status, and provenance where explicitly available.
- Never infer absent values.
- Missing values remain `NULL`/N/A.
- `VERIFIED_PRIMARY` requires an official broker publication or authenticated official broker page.
- Reputable attributed media may be `VERIFIED_SECONDARY`; it must not masquerade as the original brokerage source.
- `PROVISIONAL` or rejected evidence must not contribute to candidate consensus.
- Multiple sources for one recommendation must not inflate unique broker count.
- Preserve revisions/supersession rather than overwriting history.

Current production contains five genuine ICICI Securities recommendations. Do not alter them without explicit authorization.

### ICICI Direct

Automated discovery is implemented against ICICI Direct's official public page. The live acceptance run parsed 100 rows. Four false stock-name matches were discovered and fixed; tests now reject those identities. Matched records preserve official ICICI PDF links. Discovery remains non-persistent.

### Angel One

The user has an Angel One account and can access authenticated Trading Ideas. Do not request, store, print, or automate collection of their PIN, password, OTP, TOTP, cookies, JWT, refresh token, or session credentials.

The user supplied authenticated page text proving this example:

- Symbol: CDSL
- Company: Central Depository Services (India) Ltd
- Call: `MTF BUY`
- Horizon: `SHORT TERM`
- Recommended range: INR 1,412.50–1,413.00
- Target: INR 1,759.00
- Stop loss: INR 1,240.00
- Updated: 28 Aug 2026, 02:22 AM
- Source: authenticated Angel One Trading Ideas page

This record has NOT been imported. The application currently stores one recommended price, while Angel One supplies an entry range. Do not silently choose the lower bound, upper bound, midpoint, or any other value. Preserve the complete range in source evidence and obtain an explicit mapping decision before import or extend the schema/workflow safely if requested.

Angel One's “Know Your Stock” analytics and screeners are not broker recommendations. For example, the supplied “Promoter & FII Buying” screener contains dynamic prices, volume, and 52-week ranges but no explicit analyst call, recommendation date, target, or stop. Do not insert screener output into `broker_recommendation` or count it toward broker consensus. A separate timestamped screener-evidence model would require explicit design approval.

### Other sources

- Motilal Oswal: public but structurally unstable; download/report-only plus manual verification is the safe option.
- Mirae Asset Sharekhan: official public research pages exist, but page families vary; download/report-only plus manual verification.
- HDFC Securities: login-required; manual official document intake only unless a compliant supported interface is confirmed.
- Angel One: login-required for authenticated ideas; manual evidence intake only under the current design.
- TOI or other media: secondary attribution only, not brokerage-primary evidence when the original report is available.

## Broker PDF upload

Relevant files:

- `backend\app\services\broker_upload_service.py`
- `backend\app\routers\broker_uploads.py`
- `frontend\src\pages\BrokerUploads.tsx`

Security behavior already implemented:

- Maximum upload size is bounded.
- File content must have a PDF signature, not merely a `.pdf` name.
- Stored paths must remain inside the upload directory.
- A corrupt manifest is preserved and treated as an error, not overwritten as an empty manifest.
- Uploading does not create or change a recommendation.

## Core application invariants

Do not change these merely to produce more candidates:

- Candidate rules or thresholds.
- Technical formulas.
- Fundamental values or their source mappings.
- Raw OHLCV.
- Historical candidate runs, criteria, risk/reward results, or evidence.
- Consensus unique-broker counting.
- Missing/UNKNOWN evidence behavior.

UNKNOWN must never become PASS. Do not fabricate support, resistance, entry, target, stop, financial metrics, prices, recommendations, or classifications.

No live trading, broker order execution, paper trading, cloud sync, or credential storage should be added unless explicitly requested as a separate approved feature.

## Responsive and browser requirements

Maintain usable layouts at:

- 320px
- 375px
- 390px
- 768px
- 1024px

Require no page-level horizontal overflow, usable navigation and controls, readable evidence, touch-friendly actions, explicit empty/error states, no essential hover-only information, and no unexpected console errors or failed network calls.

## First actions in the new Claude session

1. Confirm the working path is exactly `D:\Swing Trading`.
2. Read this handover and `docs\post-phase5-data-tools-validation.md`.
3. Inspect `git status --short` only to understand local changes; do not mutate Git state.
4. Verify the project Python executable exists.
5. Recheck production counts, `PRAGMA integrity_check`, and `PRAGMA foreign_key_check` read-only.
6. Inspect the specific files relevant to the next requested feature.
7. State the verified current stage and identify any difference from this handover.
8. Continue in small units: inspect, verify, implement, test, and report.

Do not begin a production import, register scheduled tasks, integrate Angel One login, or alter recommendation evidence until I explicitly request that operation.

## Reporting standard

Every PASS must come from an actual executed check. Every database count must come from SQLite. Every source claim must come from local code/data or an authoritative primary source. If something was not executed or cannot be verified, report `NOT VERIFIED`.

Keep responses concise and factual. Distinguish clearly between:

- implemented,
- tested,
- production-enabled,
- available but not activated,
- and proposed future work.
