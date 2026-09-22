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
