# Automated refresh acceptance and release gate: 2026-09-22

Commit tested: `c8c8da3927ed76d08398b3b4e786ee61ec101cf9` on `release/final-phase5-batch-b-20260820`. Local HEAD and the remote branch matched. The only untracked files were the three runners added here.

All checks ran on Windows through PowerShell. Production was opened read-only. Every import ran against a disposable SQLite copy under `%TEMP%`, made with SQLite's backup API.

## NSE catch-up acceptance (`scratch/ohlcv_catchup_acceptance.ps1`)

Evidence: `manual_inputs/nse/auto/acceptance/20260922_135949` (git-ignored). All 13 checks passed.

- **Range and sessions:** 2026-09-04 to 2026-09-22. Twelve NSE Bhavcopy sessions were available: 09-04, 09-07 to 09-11, 09-15 to 09-18, 09-21 and 09-22.
- **Dates with no NSE file:** seven. Six were weekend days, plus Monday 2026-09-14. That date is reported as NO_FILE, not as a failure.
- **Archive checks (every file):** ZIP signature present, exactly one `BhavCopy_NSE_CM` CSV, and the full UDiFF column set. `TradDt` matches the file date. The saved CSV equals the archive member. There was no Quote-SLB content and no HTML, JSON or CAPTCHA. The dry-run and import SHA-256 values match.
- **Disposable import:** ran through `auto_download_ohlcv.py` and `OhlcvService.confirm_import`. The run report shows `production_database: false`, and the backup went to the temporary directory.
  - 324 rows inserted: 27 tracked stocks on each of the 12 sessions.
  - 0 invalid tracked rows and 0 conflicts. Unmapped market rows (2,606 to 2,638 per session) are reported separately from invalid rows.
  - After import: 0 duplicate keys, 0 invalid OHLC, 0 negative volumes and 0 synthetic rows. Integrity was `ok` with 0 foreign-key violations, and no existing row changed.
  - Every tracked stock now ends on 2026-09-22 with 12 more sessions. INDIGO went from 0 to 12.
- **Replay of the exact imported files:** 0 inserted and 324 duplicates skipped, with 0 conflicts. The `daily_ohlcv` count and values were unchanged. The replay added 12 audit batches, one per file, which is the application's existing design.
- **Technical readiness (read-only on the copy):** PASS.
  - The 20 stocks with 264–265 sessions have all indicators.
  - The six stocks with 18 sessions have RSI14 and ATR14/ATR % only. Every other indicator correctly stays null until the stock has enough history.
  - INDIGO has 12 sessions, so all its indicators are correctly null.

## Release gate (`scratch/release_gate.ps1`)

- **Backend:** 196 passed.
- **Frontend unit tests:** 51 passed.
- **Lint:** PASS, with the five existing warnings.
- **Production build:** PASS.
- **Live checks:** `GET /health` returned `{"status":"ok","foreign_keys":1}`. The Data Sync and Broker Uploads API routes and pages returned PASS.
- **Dedicated Data Sync/Broker Uploads suite:** 7 passed, covering 320, 375, 390, 768 and 1024px plus console/network checks.
- **Full Playwright suite:** 195 passed and 7 skipped, out of 202.
  - The skips are the `trade-lifecycle.spec.ts` write flows, which run only with `TRADE_LIFECYCLE_E2E=1`.
  - The backend ran against a disposable production copy.
  - Backend access log: 581 × 200 and 13 × 404. All 404s are the suite's intentional `/api/evidence/stocks/999999` invalid-stock checks. There were no 5xx responses and nothing in the frontend error log.
- **Run details:** An earlier full-suite run was interrupted at 147/202 and is not counted. The full suite then completed with `-PlaywrightOnly` (log `scratch/logs/release_gate_20260922_141604.log`). That option skips only steps already passed in `release_gate_20260922_140202.log`.

## Production protection

- **SHA-256 before and after every unit and gate run:** `eb0e2eaf4fe40db4e3dd2c43f90fb7ec43a0370fcaa6645f923b5bf1322de49e`.
- **Counts unchanged:**

  | Table | Rows |
  |---|---|
  | `daily_ohlcv` | 5095 |
  | `fundamental_snapshot` | 20 |
  | `candidate_evaluation_run` | 43 |
  | `candidate_criterion_result` | 387 |
  | `risk_reward_result` | 36 |
  | `broker_recommendation` | 5 |
  | `data_import_batch` | 91 |
  | `trade_journal` | 0 |

- **Latest OHLCV date:** still 2026-09-03.
- **SQLite:** `PRAGMA integrity_check` returns `ok`, and `PRAGMA foreign_key_check` returns 0 rows.
- **Production not changed:** the catch-up was not imported into production, and no candidate evaluation, recommendation or fundamental was changed. No scheduled task was registered.

A production catch-up import needs a separate explicit authorization, using `--confirm-production`.

## Stricter release gate rerun (commit after 2d5e466)

`scratch/release_gate.ps1` now checks the Playwright summary lines, not just the exit code. A Playwright step passes only if:

- the exit code is 0;
- every declared test either passed or was skipped;
- no test failed, was flaky, was interrupted or did not run;
- the number of skips matches the expected count: 7 for the full suite (0 when `TRADE_LIFECYCLE_E2E` is set), 0 for the data-tools spec.

A step that never finishes stays `NOT COMPLETED`, which fails the gate. Before the backend starts, the gate also checks that the application database resolves to the disposable copy.

Full Windows run, 2026-09-22 (`scratch/logs/release_gate_20260922_142812.log`, OVERALL: PASS):

- **Backend:** 196 passed.
- **Frontend unit tests:** 51 passed. The jsdom `AxiosError: Network Error` stderr lines come from page tests that have no backend; none of those tests failed.
- **Lint:** PASS, with the five existing warnings.
- **Build:** PASS.
- **Disposable database:** copy created, and the application resolves to it.
- **Live checks:** `/health`, Data Sync and Broker Uploads APIs and pages all PASS.
- **Data-tools spec:** 7 passed, 0 skipped of 7.
- **Full Playwright suite:** 195 passed, 7 skipped of 202. It ran to completion, with no failed, flaky, interrupted or did-not-run tests.
- **Backend responses:** only 200s, plus the suite's intentional `/api/evidence/stocks/999999` 404 checks. There were no 5xx responses.
- **Production:** SHA-256 was `eb0e2eaf4fe40db4e3dd2c43f90fb7ec43a0370fcaa6645f923b5bf1322de49e` at start and end. Integrity is `ok` with 0 foreign-key violations, and the data was not imported or modified.
