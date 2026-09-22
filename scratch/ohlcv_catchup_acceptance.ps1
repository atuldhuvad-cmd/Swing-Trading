<#
.SYNOPSIS
  Non-persistent OHLCV catch-up acceptance test against a disposable copy of production.

.DESCRIPTION
  Unit 1  Verify repository commit (local and remote) and the production baseline.
  Unit 2  Live NSE Bhavcopy download in --dry-run mode and archive validation.
  Unit 3  Disposable database copy under $env:TEMP via SQLite's backup API.
  Unit 4  Import through scratch\auto_download_ohlcv.py (OhlcvService.confirm_import)
          against the disposable copy only.
  Unit 5  Exact-file idempotency replay through the same workflow.
  Unit 6  Technical-indicator readiness on the disposable copy (read-only).

  Production is only opened read-only and its SHA-256 is checked before and after.
  DATABASE_URL is set only inside this PowerShell process and removed afterwards.
  Evidence (JSON + run.log) is written to manual_inputs\nse\auto\acceptance\<stamp>,
  which is git-ignored.

.EXAMPLE
  powershell -NoProfile -ExecutionPolicy Bypass -File 'D:\Swing Trading\scratch\ohlcv_catchup_acceptance.ps1'
#>
param(
    [string]$From = '04-09-2026',
    [string]$To = (Get-Date -Format 'dd-MM-yyyy'),
    # When set, local HEAD and the remote branch must both equal this commit.
    # When empty, local HEAD must equal the remote branch head.
    [string]$ExpectedCommit = '',
    [string]$Branch = 'release/final-phase5-batch-b-20260820'
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'

$Root       = 'D:\Swing Trading'
$ProdDb     = Join-Path $Root 'data\swing_trading.db'
$ProdSha    = 'fd78dda7e8d4f8a27fafdbd878e3a1dc329de44860659104ffad0e321522f5b5'
$Py         = Join-Path $Root 'backend\venv\Scripts\python.exe'
$AutoScript = Join-Path $Root 'scratch\auto_download_ohlcv.py'
$Helper     = Join-Path $Root 'scratch\ohlcv_catchup_acceptance.py'
$AutoDir    = Join-Path $Root 'manual_inputs\nse\auto'
$Stamp      = Get-Date -Format 'yyyyMMdd_HHmmss'
$Evidence   = Join-Path $AutoDir "acceptance\$Stamp"
$TempRoot   = [System.IO.Path]::GetFullPath($env:TEMP)
$TestDb     = Join-Path $TempRoot "swing_trading_ohlcv_catchup_$Stamp.db"
$AllowedUntracked = @(
    'scratch/ohlcv_catchup_acceptance.py',
    'scratch/ohlcv_catchup_acceptance.ps1',
    'scratch/release_gate.ps1'
)

New-Item -ItemType Directory -Force -Path $Evidence | Out-Null
$Log = Join-Path $Evidence 'run.log'
$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'
$env:PYTHONWARNINGS = 'ignore'
$Results = [ordered]@{}

function Write-Log([string]$Message) {
    $line = '[{0}] {1}' -f (Get-Date -Format 'HH:mm:ss'), $Message
    Write-Host $line
    Add-Content -Path $Log -Value $line -Encoding UTF8
}

function Invoke-Logged([string]$Label, [string]$Exe, [string[]]$Arguments) {
    Write-Log "RUN  $Label"
    $prev = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        & $Exe @Arguments 2>&1 | ForEach-Object {
            $s = "$_"
            Write-Host $s
            Add-Content -Path $Log -Value $s -Encoding UTF8
        }
        $code = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $prev
    }
    Write-Log "EXIT $Label = $code"
    return $code
}

function Get-Native([string]$Exe, [string[]]$Arguments) {
    $prev = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        $out = & $Exe @Arguments 2>&1 | ForEach-Object { "$_" }
        $code = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $prev
    }
    Add-Content -Path $Log -Value ("$Exe $($Arguments -join ' ') -> exit $code") -Encoding UTF8
    foreach ($l in @($out)) { if ($null -ne $l) { Add-Content -Path $Log -Value "  $l" -Encoding UTF8 } }
    return ,@(@($out) + "__EXIT__$code")
}

function Split-Native($Result) {
    $lines = @($Result | Where-Object { $_ -notlike '__EXIT__*' })
    $code = [int](($Result | Where-Object { $_ -like '__EXIT__*' } | Select-Object -Last 1) -replace '__EXIT__', '')
    return @{ Lines = $lines; Code = $code }
}

function Stop-Acceptance([string]$Message) {
    Write-Log "STOP: $Message"
    throw $Message
}

function Invoke-Helper([string]$Label, [string[]]$Arguments) {
    $code = Invoke-Logged $Label $Py (@($Helper) + $Arguments)
    $Results[$Label] = if ($code -eq 0) { 'PASS' } else { 'FAIL' }
    if ($code -ne 0) { Stop-Acceptance "$Label failed (exit $code) - see $Evidence" }
}

function Assert-ProdHash([string]$Label) {
    $h = (Get-FileHash -Algorithm SHA256 -LiteralPath $ProdDb).Hash.ToLowerInvariant()
    Write-Log "Production SHA-256 ($Label): $h"
    if ($h -ne $ProdSha) {
        $Results["prod-sha-$Label"] = 'FAIL'
        Stop-Acceptance "Production SHA-256 changed ($Label): $h"
    }
    $Results["prod-sha-$Label"] = 'PASS'
}

function Get-NewReport([string[]]$Before) {
    $new = Get-ChildItem -LiteralPath $AutoDir -Filter 'auto_download_report_*.json' |
        Where-Object { $Before -notcontains $_.Name } |
        Sort-Object LastWriteTime | Select-Object -Last 1
    if ($null -eq $new) { Stop-Acceptance 'No new automation report was written' }
    return $new.FullName
}

function Get-ReportNames {
    if (-not (Test-Path -LiteralPath $AutoDir)) { return @() }
    return @(Get-ChildItem -LiteralPath $AutoDir -Filter 'auto_download_report_*.json' | ForEach-Object { $_.Name })
}

$exitCode = 1
try {
    Write-Log "Evidence folder: $Evidence"
    Write-Log "Date range: $From to $To"
    Remove-Item Env:DATABASE_URL -ErrorAction SilentlyContinue

    # ------------------------------------------------------------------ UNIT 1
    Write-Log '=== UNIT 1: repository and production baseline ==='
    Set-Location -LiteralPath $Root
    $cwd = (Get-Location).Path
    Write-Log "Working directory: $cwd"
    if ($cwd -ne $Root) { Stop-Acceptance "Unexpected working directory $cwd" }

    $st = Split-Native (Get-Native 'git' @('status', '--short'))
    $st.Lines | Set-Content -Path (Join-Path $Evidence 'git_status_before.txt') -Encoding UTF8
    $unexpected = @($st.Lines | Where-Object {
        $_ -and -not $_.StartsWith('warning:') -and
        -not ($_.StartsWith('?? ') -and ($AllowedUntracked -contains $_.Substring(3).Trim().Trim('"')))
    })
    Write-Log ("git status --short: {0} line(s), unexpected: {1}" -f @($st.Lines).Count, $unexpected.Count)
    if ($st.Code -ne 0 -or $unexpected.Count -gt 0) {
        $unexpected | ForEach-Object { Write-Log "  unexpected: $_" }
        Stop-Acceptance 'Worktree has unexpected changes; inspect before proceeding'
    }

    $branchNow = (Split-Native (Get-Native 'git' @('branch', '--show-current'))).Lines[0].Trim()
    $headNow   = (Split-Native (Get-Native 'git' @('rev-parse', 'HEAD'))).Lines[0].Trim()
    $remote    = Split-Native (Get-Native 'git' @('ls-remote', '--heads', 'origin', $Branch))
    $remoteSha = (@($remote.Lines | Where-Object { $_ -match "refs/heads/$([regex]::Escape($Branch))$" }) | Select-Object -First 1)
    if ($remoteSha) { $remoteSha = ($remoteSha -split '\s+')[0] }
    Write-Log "Branch: $branchNow | HEAD: $headNow | origin: $remoteSha"
    if ($branchNow -ne $Branch) { Stop-Acceptance "Branch is $branchNow" }
    if ($remoteSha -ne $headNow) { Stop-Acceptance "Local HEAD $headNow != origin/$Branch $remoteSha" }
    if ($ExpectedCommit -and $headNow -ne $ExpectedCommit) { Stop-Acceptance "Local HEAD is $headNow, expected $ExpectedCommit" }
    $Results['git-commit-local-and-remote'] = 'PASS'

    if (-not (Test-Path -LiteralPath $Py)) { Stop-Acceptance "Python not found: $Py" }
    if (-not (Test-Path -LiteralPath $ProdDb)) { Stop-Acceptance "Production DB not found: $ProdDb" }
    Write-Log "Python: $Py"
    Assert-ProdHash 'start'
    Invoke-Helper 'unit1-verify-production' @('verify-prod', '--out', (Join-Path $Evidence '01_production_before.json'))

    # ------------------------------------------------------------------ UNIT 2
    Write-Log '=== UNIT 2: live NSE Bhavcopy download (dry run) ==='
    $before = Get-ReportNames
    $code = Invoke-Logged 'unit2-dry-run-download' $Py @($AutoScript, '--dry-run', '--skip-symbols', '--bhavcopy-from', $From, '--bhavcopy-to', $To)
    $dryReport = Get-NewReport $before
    Copy-Item -LiteralPath $dryReport -Destination (Join-Path $Evidence 'automation_report_dry_run.json')
    Write-Log "Dry-run report: $dryReport (script exit $code)"
    Invoke-Helper 'unit2-validate-downloads' @('validate-downloads', '--report', $dryReport, '--evidence', $Evidence,
        '--out', (Join-Path $Evidence '02_downloads.json'))
    if ($code -ne 0) { Stop-Acceptance "Dry-run script exit code $code" }
    Assert-ProdHash 'after-dry-run'

    # ------------------------------------------------------------------ UNIT 3
    Write-Log '=== UNIT 3: disposable database copy ==='
    if ([string]::Equals($TestDb, $ProdDb, [StringComparison]::OrdinalIgnoreCase)) { Stop-Acceptance 'Disposable path equals production' }
    Write-Log "Disposable database: $TestDb"
    Invoke-Helper 'unit3-backup-api-copy' @('backup', '--dest', $TestDb, '--out', (Join-Path $Evidence '03_disposable_copy.json'))
    Assert-ProdHash 'after-copy'

    # -------------------------------------------------------------- UNITS 4-6
    try {
        $env:DATABASE_URL = 'sqlite:///' + $TestDb.Replace('\', '/')
        Write-Log "DATABASE_URL (process only): $env:DATABASE_URL"
        Invoke-Helper 'unit4-resolve-database' @('resolve-db', '--expect', $TestDb, '--out', (Join-Path $Evidence '04_resolved_database.json'))

        Write-Log '=== UNIT 4: import into the disposable copy ==='
        Invoke-Helper 'unit4-snapshot-before' @('snapshot', '--db', $TestDb, '--out', (Join-Path $Evidence '05_copy_before_import.json'))
        $before = Get-ReportNames
        $code = Invoke-Logged 'unit4-import-disposable' $Py @($AutoScript, '--skip-symbols', '--bhavcopy-from', $From, '--bhavcopy-to', $To)
        $importReport = Get-NewReport $before
        Copy-Item -LiteralPath $importReport -Destination (Join-Path $Evidence 'automation_report_import.json')
        Write-Log "Import report: $importReport (script exit $code)"
        Invoke-Helper 'unit4-check-import-report' @('check-import', '--report', $importReport,
            '--dryrun', (Join-Path $Evidence '02_downloads.json'), '--expect', $TestDb, '--evidence', $Evidence,
            '--out', (Join-Path $Evidence '06_import_report_check.json'))
        if ($code -ne 0) { Stop-Acceptance "Import script exit code $code" }
        Invoke-Helper 'unit4-snapshot-after' @('snapshot', '--db', $TestDb, '--out', (Join-Path $Evidence '07_copy_after_import.json'))
        Invoke-Helper 'unit4-compare-import' @('compare', '--mode', 'import',
            '--before', (Join-Path $Evidence '05_copy_before_import.json'),
            '--after', (Join-Path $Evidence '07_copy_after_import.json'),
            '--import-check', (Join-Path $Evidence '06_import_report_check.json'),
            '--dryrun', (Join-Path $Evidence '02_downloads.json'),
            '--out', (Join-Path $Evidence '08_import_comparison.json'))
        Assert-ProdHash 'after-import'

        Write-Log '=== UNIT 5: idempotency replay ==='
        Invoke-Helper 'unit5-replay' @('replay', '--expect', $TestDb,
            '--import-check', (Join-Path $Evidence '06_import_report_check.json'),
            '--files', (Join-Path $Evidence 'import_files'),
            '--out', (Join-Path $Evidence '09_replay.json'))
        Invoke-Helper 'unit5-snapshot-after-replay' @('snapshot', '--db', $TestDb, '--out', (Join-Path $Evidence '10_copy_after_replay.json'))
        Invoke-Helper 'unit5-compare-replay' @('compare', '--mode', 'replay',
            '--before', (Join-Path $Evidence '07_copy_after_import.json'),
            '--after', (Join-Path $Evidence '10_copy_after_replay.json'),
            '--out', (Join-Path $Evidence '11_replay_comparison.json'))
        Assert-ProdHash 'after-replay'

        Write-Log '=== UNIT 6: technical readiness (read-only on the copy) ==='
        Invoke-Helper 'unit6-technical-readiness' @('technical', '--expect', $TestDb,
            '--dryrun', (Join-Path $Evidence '02_downloads.json'),
            '--out', (Join-Path $Evidence '12_technical_readiness.json'))
    } finally {
        Remove-Item Env:DATABASE_URL -ErrorAction SilentlyContinue
        Write-Log 'DATABASE_URL removed from this process'
    }

    Write-Log '=== FINAL: production unchanged ==='
    Assert-ProdHash 'end'
    Invoke-Helper 'final-verify-production' @('verify-prod', '--out', (Join-Path $Evidence '13_production_after.json'))
    $exitCode = 0
} catch {
    Write-Log "ERROR: $($_.Exception.Message)"
    $exitCode = 1
} finally {
    Remove-Item Env:DATABASE_URL -ErrorAction SilentlyContinue
    try {
        $st = Split-Native (Get-Native 'git' @('-C', $Root, 'status', '--short'))
        $st.Lines | Set-Content -Path (Join-Path $Evidence 'git_status_after.txt') -Encoding UTF8
    } catch { Write-Log "git status after run failed: $($_.Exception.Message)" }
    $summary = [ordered]@{
        stamp = $Stamp
        from = $From
        to = $To
        disposable_db = $TestDb
        evidence = $Evidence
        overall = $(if ($exitCode -eq 0) { 'PASS' } else { 'FAIL' })
        steps = $Results
    }
    $summary | ConvertTo-Json -Depth 5 | Set-Content -Path (Join-Path $Evidence 'summary.json') -Encoding UTF8
    Write-Log "OVERALL: $($summary.overall)  (evidence: $Evidence)"
}
exit $exitCode
