<#
.SYNOPSIS
  Fresh release gate: backend pytest, frontend unit tests, lint, build, live
  backend/frontend smoke checks and the full Playwright suite.

.DESCRIPTION
  The backend and frontend are started with the same commands as
  Start-SwingTrading.bat (uvicorn app.main:app / npm run dev --strictPort) on
  127.0.0.1:8000 and 127.0.0.1:5173. The only difference: the backend's
  DATABASE_URL points at a disposable SQLite backup of production under
  $env:TEMP, so the browser suite can never write to production. Production
  SHA-256 is verified before and after. Nothing is committed.

  If port 8000 or 5173 is already in use (for example the app is running),
  the live checks are skipped rather than stopping your processes.

  -PlaywrightOnly skips pytest, frontend unit tests, lint, build and the
  dedicated data-tools spec, and reruns only the live checks plus the full
  Playwright suite against a fresh disposable database copy.

.EXAMPLE
  powershell -NoProfile -ExecutionPolicy Bypass -File 'D:\Swing Trading\scratch\release_gate.ps1'
  powershell -NoProfile -ExecutionPolicy Bypass -File 'D:\Swing Trading\scratch\release_gate.ps1' -PlaywrightOnly
#>
param(
    [int]$BackendPort = 8000,
    [int]$FrontendPort = 5173,
    [switch]$PlaywrightOnly,
    # Tests intentionally skipped by the full suite: the 7 trade-lifecycle
    # write flows, which only run when TRADE_LIFECYCLE_E2E=1.
    [int]$ExpectedFullSuiteSkips = 7
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'

$Root     = 'D:\Swing Trading'
$Backend  = Join-Path $Root 'backend'
$Frontend = Join-Path $Root 'frontend'
$ProdDb   = Join-Path $Root 'data\swing_trading.db'
$ProdSha  = 'bffa9e78df236d9cf47bdd9e08026cd6ea8769bd5d8d3da04e1660fe590f9049'
$Py       = Join-Path $Backend 'venv\Scripts\python.exe'
$Helper   = Join-Path $Root 'scratch\ohlcv_catchup_acceptance.py'
$Stamp    = Get-Date -Format 'yyyyMMdd_HHmmss'
$LogDir   = Join-Path $Root 'scratch\logs'
$Log      = Join-Path $LogDir "release_gate_$Stamp.log"
$GateDb   = Join-Path ([System.IO.Path]::GetFullPath($env:TEMP)) "swing_trading_release_gate_$Stamp.db"
$Results  = [ordered]@{}
$script:LastOutput = New-Object System.Collections.Generic.List[string]
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'

function Write-Log([string]$Message) {
    $line = '[{0}] {1}' -f (Get-Date -Format 'HH:mm:ss'), $Message
    Write-Host $line
    Add-Content -Path $Log -Value $line -Encoding UTF8
}

function Invoke-Logged([string]$Label, [string]$Exe, [string[]]$Arguments, [string]$Dir) {
    Write-Log "RUN  $Label  ($Exe $($Arguments -join ' '))"
    $prev = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    Push-Location -LiteralPath $Dir
    $script:LastOutput = New-Object System.Collections.Generic.List[string]
    try {
        & $Exe @Arguments 2>&1 | ForEach-Object {
            $s = "$_"
            $script:LastOutput.Add($s)
            Write-Host $s
            Add-Content -Path $Log -Value $s -Encoding UTF8
        }
        $code = $LASTEXITCODE
    } finally {
        Pop-Location
        $ErrorActionPreference = $prev
    }
    $Results[$Label] = if ($code -eq 0) { 'PASS' } else { "FAIL (exit $code)" }
    Write-Log "EXIT $Label = $code"
    return $code
}

function Get-PlaywrightCount([string[]]$Lines, [string]$Pattern) {
    $m = @($Lines | ForEach-Object { [regex]::Match($_, $Pattern) } | Where-Object { $_.Success } | Select-Object -Last 1)
    if ($m.Count -eq 0) { return 0 }
    return [int]$m[0].Groups[1].Value
}

# Playwright exits 0 even when tests are skipped, so the exit code alone cannot
# prove a complete run. Require: a declared total, every test accounted for as
# passed or skipped, no failed/flaky/interrupted/did-not-run tests, and exactly
# the expected number of intentional skips.
function Invoke-Playwright([string]$Label, [string[]]$Arguments, [int]$ExpectedSkipped) {
    $Results[$Label] = 'NOT COMPLETED'
    $code = Invoke-Logged $Label 'npx.cmd' $Arguments $Frontend
    $lines = @($script:LastOutput)
    $total       = Get-PlaywrightCount $lines '^\s*Running (\d+) tests?\b'
    $passed      = Get-PlaywrightCount $lines '^\s*(\d+) passed\b'
    $skipped     = Get-PlaywrightCount $lines '^\s*(\d+) skipped\b'
    $failed      = Get-PlaywrightCount $lines '^\s*(\d+) failed\b'
    $flaky       = Get-PlaywrightCount $lines '^\s*(\d+) flaky\b'
    $interrupted = Get-PlaywrightCount $lines '^\s*(\d+) interrupted\b'
    $didNotRun   = Get-PlaywrightCount $lines '^\s*(\d+) did not run\b'
    $summary = "total=$total passed=$passed skipped=$skipped (expected $ExpectedSkipped) failed=$failed flaky=$flaky interrupted=$interrupted didNotRun=$didNotRun exit=$code"
    $ok = ($code -eq 0) -and ($total -gt 0) -and ($passed + $skipped -eq $total) -and
          ($skipped -eq $ExpectedSkipped) -and ($failed + $flaky + $interrupted + $didNotRun -eq 0)
    $Results[$Label] = if ($ok) { "PASS ($passed passed, $skipped skipped of $total)" } else { "FAIL ($summary)" }
    Write-Log "$Label result: $summary"
}

function Test-PortBusy([int]$Port) {
    $c = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    return ($null -ne $c)
}

function Get-ProdHash {
    return (Get-FileHash -Algorithm SHA256 -LiteralPath $ProdDb).Hash.ToLowerInvariant()
}

function Wait-Http([string]$Url, [int]$Seconds) {
    $deadline = (Get-Date).AddSeconds($Seconds)
    while ((Get-Date) -lt $deadline) {
        try {
            $r = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 5
            if ($r.StatusCode -eq 200) { return $r }
        } catch { Start-Sleep -Seconds 1 }
    }
    return $null
}

function Test-Http([string]$Label, [string]$Url, [scriptblock]$Check) {
    try {
        $r = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 15
        $ok = ($r.StatusCode -eq 200) -and (& $Check $r)
        $body = $r.Content
        if ($body.Length -gt 300) { $body = $body.Substring(0, 300) + '...' }
        Write-Log "$Label -> HTTP $($r.StatusCode): $body"
    } catch {
        $ok = $false
        Write-Log "$Label -> ERROR $($_.Exception.Message)"
    }
    $Results[$Label] = if ($ok) { 'PASS' } else { 'FAIL' }
}

$procs = @()
$exitCode = 1
try {
    Remove-Item Env:DATABASE_URL -ErrorAction SilentlyContinue
    Set-Location -LiteralPath $Root
    Write-Log "Log: $Log"
    $h = Get-ProdHash
    Write-Log "Production SHA-256 (start): $h"
    if ($h -ne $ProdSha) { throw "Production SHA-256 differs from baseline at start: $h" }
    $Results['prod-sha-start'] = 'PASS'

    if ($PlaywrightOnly) {
        Write-Log 'PlaywrightOnly: pytest, unit tests, lint, build and the dedicated data-tools spec are not rerun.'
    } else {
        [void](Invoke-Logged 'backend-pytest' $Py @('-m', 'pytest') $Backend)
        [void](Invoke-Logged 'frontend-unit' 'npm.cmd' @('test', '--', '--run') $Frontend)
        [void](Invoke-Logged 'frontend-lint' 'npm.cmd' @('run', 'lint') $Frontend)
        [void](Invoke-Logged 'frontend-build' 'npm.cmd' @('run', 'build') $Frontend)
    }

    if ((Test-PortBusy $BackendPort) -or (Test-PortBusy $FrontendPort)) {
        Write-Log "Port $BackendPort or $FrontendPort is already in use; live checks and Playwright NOT RUN."
        $Results['live-checks'] = 'NOT RUN (port in use)'
    } else {
        if ((Invoke-Logged 'gate-db-backup' $Py @($Helper, 'backup', '--dest', $GateDb, '--out', ($GateDb + '.check.json')) $Root) -ne 0) { throw 'Disposable gate database copy failed' }
        $env:DATABASE_URL = 'sqlite:///' + $GateDb.Replace('\', '/')
        Write-Log "Backend DATABASE_URL (process only): $env:DATABASE_URL"
        if ((Invoke-Logged 'gate-db-resolves-to-disposable-copy' $Py @($Helper, 'resolve-db', '--expect', $GateDb, '--out', ($GateDb + '.resolve.json')) $Backend) -ne 0) {
            throw 'Backend database does not resolve to the disposable copy'
        }
        $be = Start-Process -FilePath $Py -WorkingDirectory $Backend -PassThru -NoNewWindow `
            -ArgumentList @('-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', "$BackendPort") `
            -RedirectStandardOutput (Join-Path $LogDir "release_gate_$Stamp`_backend.out.log") `
            -RedirectStandardError (Join-Path $LogDir "release_gate_$Stamp`_backend.err.log")
        $procs += $be
        $fe = Start-Process -FilePath 'npm.cmd' -WorkingDirectory $Frontend -PassThru -NoNewWindow `
            -ArgumentList @('run', 'dev', '--', '--host', '127.0.0.1', '--port', "$FrontendPort", '--strictPort') `
            -RedirectStandardOutput (Join-Path $LogDir "release_gate_$Stamp`_frontend.out.log") `
            -RedirectStandardError (Join-Path $LogDir "release_gate_$Stamp`_frontend.err.log")
        $procs += $fe

        if ($null -eq (Wait-Http "http://127.0.0.1:$BackendPort/health" 60)) { throw 'Backend did not become healthy' }
        if ($null -eq (Wait-Http "http://127.0.0.1:$FrontendPort/" 90)) { throw 'Frontend did not start' }

        Test-Http 'GET /health' "http://127.0.0.1:$BackendPort/health" {
            param($r) $j = $r.Content | ConvertFrom-Json; ($j.status -eq 'ok') -and ($j.foreign_keys -eq 1)
        }
        Test-Http 'GET /api/data-sync/jobs (via frontend proxy)' "http://127.0.0.1:$FrontendPort/api/data-sync/jobs" { param($r) $true }
        Test-Http 'GET /api/broker-uploads (via frontend proxy)' "http://127.0.0.1:$FrontendPort/api/broker-uploads" { param($r) $true }
        Test-Http 'GET /data-sync page' "http://127.0.0.1:$FrontendPort/data-sync" { param($r) $r.Content -match 'id="root"' }
        Test-Http 'GET /broker-uploads page' "http://127.0.0.1:$FrontendPort/broker-uploads" { param($r) $r.Content -match 'id="root"' }

        $env:STAGE8_BASE_URL = "http://127.0.0.1:$FrontendPort"
        if (-not $PlaywrightOnly) {
            Invoke-Playwright 'playwright-data-tools (Data Sync, Broker Uploads, 320-1024px, console/network)' @('playwright', 'test', 'e2e/post-phase5-data-tools.spec.ts') 0
        }
        # Same command as `npm run test:e2e` (playwright test), invoked directly so
        # its summary lines can be verified.
        $fullSkips = if ($env:TRADE_LIFECYCLE_E2E) { 0 } else { $ExpectedFullSuiteSkips }
        Invoke-Playwright 'playwright-full-suite' @('playwright', 'test') $fullSkips
    }
    $exitCode = 0
} catch {
    Write-Log "ERROR: $($_.Exception.Message)"
    $Results['gate-error'] = $_.Exception.Message
} finally {
    foreach ($p in $procs) {
        if ($p -and -not $p.HasExited) {
            $ErrorActionPreference = 'Continue'
            & taskkill.exe /PID $p.Id /T /F 2>&1 | Out-Null
            Write-Log "Stopped process tree $($p.Id)"
        }
    }
    Remove-Item Env:DATABASE_URL -ErrorAction SilentlyContinue
    Remove-Item Env:STAGE8_BASE_URL -ErrorAction SilentlyContinue
    $h = Get-ProdHash
    Write-Log "Production SHA-256 (end): $h"
    $Results['prod-sha-end'] = if ($h -eq $ProdSha) { 'PASS' } else { "FAIL ($h)" }
    Write-Log '=== SUMMARY ==='
    foreach ($k in $Results.Keys) { Write-Log ("{0,-80} {1}" -f $k, $Results[$k]) }
    $failed = @($Results.Values | Where-Object { "$_" -notlike 'PASS*' })
    if ($failed.Count -gt 0) { $exitCode = 1 }
    Write-Log "OVERALL: $(if ($exitCode -eq 0) { 'PASS' } else { 'FAIL / INCOMPLETE' })"
}
exit $exitCode
