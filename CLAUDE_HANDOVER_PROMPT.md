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
- Broker PDF upload/storage UI/API with a read-only intake preview (SHA-256 duplicates, extracted fields, match/conflict against stored recommendations). Neither uploading nor previewing creates a recommendation.
- Windows wrapper scripts and optional Task Scheduler registration scripts.
- Start/stop batch files for local use.

Read this validation record before changing automation:

`D:\Swing Trading\docs\post-phase5-data-tools-validation.md`

## Production database — protect this baseline

Production database:

`D:\Swing Trading\data\swing_trading.db`

Verified on 2026-09-24, after the controlled production OHLCV catch-up, the post-catch-up candidate refresh, the first ICICI recommendation import and the first scheduled OHLCV run (2026-09-23 19:00):

- SHA-256: `5de2603571b7587851ad1cb14426eec9a387878d05b7f80124f44068a579d54d`
- `daily_ohlcv`: 5446
- `fundamental_snapshot`: 20
- `candidate_evaluation_run`: 70
- `candidate_criterion_result`: 630
- `risk_reward_result`: 53
- `broker_recommendation`: 9
- `data_import_batch`: 109
- `trade_journal`: 0
- Latest OHLCV date: 2026-09-23
- Synthetic/test OHLCV: 0
- Duplicate canonical keys, invalid OHLC, negative volume: 0
- `PRAGMA integrity_check`: `ok`
- `PRAGMA foreign_key_check`: 0 violations

### Completed production OHLCV catch-up (2026-09-22)

NSE Bhavcopy sessions 2026-09-04 to 2026-09-22 (12 sessions, 27 tracked rows each, 324 rows, import batches 92-103) were imported into production through `scratch/auto_download_ohlcv.py --confirm-production` after disposable acceptance, exact-file revalidation and a verified backup. Details: `docs/automated-refresh-acceptance-validation.md`.

Pre-import backups (SQLite backup API, 5095 rows, latest 2026-09-03, integrity `ok`, 0 FK violations, SHA-256 `269328ce902872d704324f6af5b3664b9f60fed8d1fa8187502595eaaf6650c0`):

- `data\backups\swing_trading_pre_ohlcv_catchup_20260922_150209.db`
- `data\swing_trading_backup_20260922_150250_207469.db` (automation backup)

Candidate evaluations were not rerun during the catch-up itself; they were refreshed afterwards (below).

### Completed post-catch-up candidate refresh (2026-09-22)

Every tracked stock was re-evaluated once with the active `phase5_trend_screen_v1` configuration (fingerprint `146408d7d5de3ce55acd5465d2c788acca9d8e1875c21e1af470151a3f0f97fe`) through the application services (`CorporateActionService`, `TechnicalService`, `FundamentalService`, `CandidateService.evaluate_candidate`, `RiskRewardService`). No evaluation was written by SQL. Rules, thresholds, formulas, OHLCV, fundamentals and broker data were not changed. Run folder (git-ignored): `manual_inputs/candidate_refresh/run_20260922_155830`.

- Pre-refresh backup (SQLite backup API, runs 43, criteria 387, risk/reward 36, every table identical to production, integrity `ok`, 0 FK violations): `data\backups\swing_trading_pre_candidate_refresh_20260922_155830.db`, SHA-256 `d2f5a660f95488f5d75c640cfa6cba04b28ac96dc2b2768f21c333cf8c5fec9d`.
- Rehearsed on two independent disposable copies; both passed and produced identical results, and production then matched them exactly.
- Production: 27 new runs (ids 44-70, one per tracked stock), 243 new criterion rows (27 x 9 criteria), 17 new risk/reward rows (only where ATR14, Support20 and Resistance20 exist and 0 < stop < entry < target).
- Latest classifications: FINAL_CANDIDATE 3, WATCH 4, REJECTED 13, INSUFFICIENT_DATA 7. The 7 INSUFFICIENT_DATA stocks are the six 18-session stocks and INDIGO (12 sessions), none of which has imported fundamentals.
- Historical runs 1-43, their 387 criteria and risk/reward rows 1-36 are unchanged; every non-candidate table is unchanged.

### ICICI import and scheduler (2026-09-23)

First controlled ICICI Direct import, through `scratch/auto_download_broker_recs_icici.py --import --confirm-production` (committed application workflow, no direct SQL):

- Imported four calls, all `BUY`, `CURRENT`, 12-18 month horizon: CARYSIL (call 2026-08-12, entry 1195, target 1410), ASTRAMICRO (2026-08-11, 1711, 1980), HINDALCO (2026-08-11, 1060, 1240), GLAND (2026-08-11, 2664, 3150). Broker recommendations 5 -> 9; the original five stay `CURRENT`.
- Provenance: ICICI Direct's own website (`BROKER_WEBSITE`), `VERIFIED_PRIMARY`, each with its official `mailcontent.icicidirect.com` report PDF link. Stop loss and price-at-recommendation are NULL (the page gives no stop and its CMP is a live price, kept only in the evidence text).
- Pre-import backup (SQLite backup API, all 27 tables identical to production, integrity `ok`, 0 FK violations): `data\backups\swing_trading_pre_icici_import_20260923_141343.db`, SHA-256 `61802c766ea69dc4b3b0f67fdd718747117560b8cd9b6a0be26ff57e1dd4b1cb`. The import also wrote its own automation backup.
- No OHLCV, fundamentals, candidate evaluation, risk/reward, trade journal or classification row changed: exactly four rows were added to each of `broker_recommendation`, `source_reference`, `recommendation_source` and `recommendation_status_history`, and no existing row changed.
- Production SHA-256 after the import: `bffa9e78df236d9cf47bdd9e08026cd6ea8769bd5d8d3da04e1660fe590f9049`.
- Scheduler: `SwingTrading-ICICI-Recs`, Monday to Friday at 20:00, runs `scratch\run_broker_recs_icici.bat` (`--import --confirm-production`) as the interactive user with no stored password, never overlaps itself, and has a 30-minute execution limit. A manual run of the registered task exited 0 and imported nothing (all seven tracked calls already recorded).
- OHLCV scheduler: `SwingTrading-OHLCV-Bhavcopy`, Monday to Friday at 19:00, 120-minute limit, same user/overlap settings. Its first scheduled run (2026-09-23 19:00) exited 0 and imported the 2026-09-23 session: 27 EQ `NSE_BHAVCOPY` rows (one per tracked stock), import batches 104-109, 0 duplicates or invalid rows, integrity `ok`, 0 FK violations. Because it runs every weekday, the pinned production SHA in the guards goes stale after each run and must be re-verified before a release gate.
- Import safeguards: name match of at least 0.9 and unambiguous, mapped rating, valid non-future call date within 400 days, at least 20 page rows, at most 25 writes per run, verified backup first.

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
- `scratch\scheduled_task_definitions.ps1`

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
- ICICI discovery is report-only by default; only `--import` (with `--confirm-production` on production) inserts recommendations, under the guards listed in the ICICI section.
- Scheduled wrappers preserve real exit codes.
- Task Scheduler uses `IgnoreNew` to prevent overlapping task instances.

Live disposable proof already completed:

- NSE Bhavcopy for 2026-09-16 downloaded successfully.
- Import through `OhlcvService.confirm_import` on a disposable production copy inserted 27 tracked rows.
- Invalid: 0; conflicts: 0.
- Exact replay inserted 0 and skipped 27 duplicates.
- Disposable copy had 0 duplicate keys, 0 invalid OHLC, 0 negative volume, integrity `ok`, and 0 FK violations.
- Production was not imported.

Task definitions are validated without registering them:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File 'D:\Swing Trading\scratch\register_scheduled_tasks.ps1' -Task ICICI -WhatIf
```

`register_scheduled_tasks.ps1` never registers implicitly. `-Task ICICI|OHLCV|Fundamentals|All` is required, and Task Scheduler is changed only with `-ConfirmRegistration`; `-WhatIf` and `-ValidateOnly` preview without changing anything. Selecting one task changes only that task. Every task has a bounded execution limit (ICICI 30 minutes, OHLCV 120, Fundamentals 60) and `MultipleInstances = IgnoreNew`. `Fundamentals` is previewable but cannot be registered by the script: no installed PowerShell here has a working `New-ScheduledTaskTrigger -Monthly`, and a monthly trigger cannot be verified without registering one, so register it by hand if wanted.

Registered tasks: `SwingTrading-ICICI-Recs` (2026-09-23) and `SwingTrading-OHLCV-Bhavcopy` (2026-09-23). `SwingTrading-Fundamentals` is not registered. Registering tasks changes OS state and requires an explicit user request.

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

Current production contains nine genuine ICICI Securities recommendations: five entered by hand (HDFCBANK, APOLLOHOSP, NRBBEARING, BHARTIARTL, INDIGO) and four imported by the automation on 2026-09-23 (CARYSIL, ASTRAMICRO, HINDALCO, GLAND). Do not alter them without explicit authorization.

### ICICI Direct

Automated discovery is implemented against ICICI Direct's official public page. The live acceptance run parsed 100 rows. Four false stock-name matches were discovered and fixed; tests now reject those identities. Matched records preserve official ICICI PDF links. A default run is report-only; `--import` (added in commit `1255a22`) records new and changed calls for tracked stocks, and a production write also needs `--confirm-production`. See "ICICI import and scheduler (2026-09-23)" above for the first import and the scheduled task.

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
- Every stored PDF records its SHA-256; a byte-identical file is refused with HTTP 409 (`DUPLICATE_FILE`). Entries stored before SHA-256 existed stay valid: their hash is computed from the stored file when needed and the manifest is not rewritten. Optional `discovery_source` / `discovery_url` (for example Trendlyne) are kept separate from the broker, which is the author.

### Broker PDF intake preview

- `backend\app\services\broker_pdf_extraction.py` reads report text with `pypdf` (pinned in `requirements.txt`) and proposes fields for Motilal Oswal, ICICI Securities and Axis Securities layouts. Every field has a status (`KNOWN`, `UNKNOWN`, `AMBIGUOUS`, `NOT_STATED`); nothing is guessed. Entry range, stop loss and horizon are read only when the report states them for the call; a horizon that appears only in the broker's rating legend stays empty with a warning. The report CMP is proposed as `recommended_price`, never as an entry price.
- `backend\app\services\broker_pdf_intake_service.py` and `POST /api/broker-uploads/preview` are strictly read-only (no file, manifest or database write). Actions: `NEW`, `NEW_REVISION`, `ATTACH_SOURCE`, `EXACT_DUPLICATE`, `CONFLICT_REVIEW_REQUIRED`, `UNKNOWN_STOCK`, `UNKNOWN_BROKER`, `REVIEW_REQUIRED`; `duplicate_file` is reported separately. The canonical source is `BROKER_RESEARCH` with the broker as publication; `VERIFIED_PRIMARY` is only proposed until the visible PDF is checked.
- There is no confirm/import step for PDFs yet. A later import must be separately authorised.

### Broker PDF hardening (cloud commit, not yet Windows-validated)

- `ATTACH_SOURCE`/`EXACT_DUPLICATE` require a complete match: report CMP and target `KNOWN` and equal; optional entry/stop/horizon equal when both sides state them. Ambiguous optional fields, `MISSING_MANDATORY_FIELD` and `UNSTATED_STORED_FIELD` give `REVIEW_REQUIRED`.
- `source_reference` gains nullable `document_sha256` and `local_upload_id` (migration `f2a7c9d41b3e`, plain `ADD COLUMN` + index; existing rows stay NULL, no hashes inferred). `EXACT_DUPLICATE` needs a source linked to that recommendation with the exact SHA; a PDF already linked to another recommendation gives `REVIEW_REQUIRED` (`DOCUMENT_ALREADY_LINKED`).
- **The new code queries these columns, so production must be migrated before the new backend starts**: back up (SQLite backup API), `alembic upgrade head`, then verify counts, integrity and FK checks. Not yet done on Windows.
- Manifest writes are locked (in-process + `msvcrt`/`fcntl` file lock `.manifest.lock`) and atomically replaced; a failed index write removes the new PDF.
- Previews parse the PDF in a killable subprocess (`pdf_text_worker.py`; 30 s timeout, 60 pages, 1,000,000 text characters, 2 concurrent parses) off the event loop.
- CORS allows only `http://127.0.0.1:5173` and `http://localhost:5173`, without credentials; write requests (POST/PUT/PATCH) carrying any other `Origin` get 403. If Vite runs on another port (for example for Playwright), set `CORS_ALLOWED_ORIGINS` (JSON list) for the backend.

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
