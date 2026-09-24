# Automated refresh and broker uploads: release validation 2026-09-17

Local changes remain uncommitted. The published Phase 5 commit is unchanged.

## Implemented and checked

- Data Sync lists the three refresh jobs and their reports. Production-writing OHLCV runs require explicit UI/API confirmation, and the script independently refuses unconfirmed production writes or production imports without a backup.
- Only one instance of each in-app job can run at a time. Scheduled wrappers return the real script exit code; Task Scheduler registration uses `IgnoreNew` and supports `-ValidateOnly` without changing Windows tasks.
- Broker PDF storage has a bounded upload read, PDF signature check, upload-directory containment, and refuses to overwrite an unreadable manifest. PDF storage does not create recommendations.
- OHLCV pre-import backups use SQLite's backup API, follow the configured application database instead of a hard-coded path, validate integrity, and close connections.
- Live NSE Bhavcopy for 2026-09-16 was downloaded and imported through `OhlcvService.confirm_import` on a disposable production copy: 27 tracked rows inserted, 0 invalid, 0 conflicts. Exact replay inserted 0 and skipped 27 duplicates. The copy retained 0 duplicate keys, 0 invalid OHLC, 0 negative volume, integrity `ok`, and 0 FK violations.
- Live ICICI discovery parsed 100 rows. Four known false company matches were found and fixed; regression tests now reject those identities. Matched records preserve the official ICICI PDF reference. Discovery remains non-persistent.
- Data navigation stays active on the broker-upload page.
- Browser checks use current API coverage instead of frozen August session counts and indicator values. Broker consensus checks cover the empty state when recommendations have aged out.

## Executed validation

- Automated-refresh targeted backend: 11 passed.
- Backend: 196 passed.
- Frontend: 51 passed; production build succeeded; lint succeeded with five existing warnings.
- Final browser suite: 195 passed, 7 skipped. The skipped cases are trade-write flows that require a disposable backend.
- New data tools: seven browser cases passed, including 320, 375, 390, 768, 1024 pixel layouts and console/network checks. No job was launched by the browser tests.
- Trade lifecycle browser writes were skipped because they require a disposable backend.
- Live BEL NSE historical download: nine rows accepted by a read-only application preview, no invalid/unmapped/duplicate/conflicting rows. No production import performed.
- Live BEL fundamentals discovery: completed with zero new filings; this does not prove PDF extraction or a populated discovery result.
- Task definitions were validated without registration. No Windows scheduled task was created or changed.

## Production protection

After validation: 5095 OHLCV rows, 20 fundamental snapshots, 43 evaluations, 387 criteria, 36 risk/reward records, 5 broker recommendations, 0 journal rows. These counts match the inspected starting state. SQLite integrity is ok; foreign-key violations are zero. Candidate rules and financial evidence were not edited.

## Remaining acceptance

Release gate complete. Scheduled-task activation remains a separate user action; none was registered in this validation. Use `powershell -File scratch/register_scheduled_tasks.ps1 -ValidateOnly` to recheck installation prerequisites without creating tasks, then run it explicitly when you want Windows scheduling enabled.

## Broker PDF intake preview: validation 2026-09-24

The sections above describe the 2026-09-17 release. Since then both the ICICI and OHLCV tasks have been registered (see `CLAUDE_HANDOVER_PROMPT.md`).

- Added a read-only `POST /api/broker-uploads/preview` and a Preview step on the Broker Uploads screen. Text extraction uses `pypdf==6.19.0` (declared in `backend/requirements.txt`). Stored uploads now record SHA-256 and optional discovery provenance; byte-identical files are refused (409). The one pre-existing manifest entry stays valid and unchanged.
- Real preview of seven Trendlyne-discovered broker PDFs (six unique), run through the application service on a disposable production copy:
  - `NEW` 1: ADANIENT (Motilal Oswal, 2026-09-09, Buy, report CMP 3105, target 3880).
  - `EXACT_DUPLICATE` 1: INDIGO (ICICI Securities, 2026-08-31). The PDF is byte-identical to the upload stored on 2026-09-03, and recommendation #5 already has `BROKER_RESEARCH` / `VERIFIED_PRIMARY` evidence for it, so no new source is proposed.
  - `CONFLICT_REVIEW_REQUIRED` 1: HDFCBANK (ICICI Securities, 2026-08-31). The PDF states CMP 720 and target 920 (previous target 1,020); stored recommendation #1, from ICICI Direct's Investing Ideas web page, has 709.6 and 925 plus entry 725. Nothing is attached or overwritten.
  - `UNKNOWN_STOCK` 3: MAXHEALTH, TATASTEEL (Motilal Oswal) and COFORGE (Axis Securities, CMP as of 2026-09-11 against a report dated 2026-09-15). Archive only; nothing is added to `stock_master`.
  - `DUPLICATE_FILE` 1: the second MAXHEALTH copy (SHA-256 `A87F6D965703FFEC3C7242028BCF34098CBB8725680CDF30DDF13ABB1E5D4424`, same as the first).
  - `ATTACH_SOURCE` 0, `REJECTED` 0.
- No report states an entry range, stop loss or call-specific horizon, so all of those stay empty. Broker PDFs are proposed as `BROKER_RESEARCH` / `VERIFIED_PRIMARY`, pending visual confirmation; Trendlyne is recorded only as `discovery_source`, with the URL marked unavailable.
- The disposable database, production, the upload manifest and the upload folder were byte-identical before and after the preview.
- Release gate `scratch/logs/release_gate_20260924_145301.log`: OVERALL PASS. Backend 247 passed, frontend unit 57, lint with the five known warnings, build PASS, data-tools Playwright 13 of 13 (including the PDF preview at 320, 375, 390, 768 and 1024 px), full Playwright 202 passed and 7 skipped of 209, no 5xx. Production SHA-256 `5de2603571b7587851ad1cb14426eec9a387878d05b7f80124f44068a579d54d` at start and end. After the gate, test fixtures were changed to use clearly synthetic analyst names; the affected backend (31), frontend unit (57) and data-tools Playwright (13) suites were rerun and passed.
- No recommendation was imported. A PDF import (only ADANIENT `NEW` is eligible) needs a separately authorised task.
