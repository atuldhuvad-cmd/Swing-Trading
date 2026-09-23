"""Deterministic tests for scratch/register_scheduled_tasks.ps1.

Nothing here registers, replaces, disables or deletes a scheduled task. Definitions are
built in memory through scheduled_task_definitions.ps1, and the registration script is only
run in modes that cannot mutate Task Scheduler (missing/invalid task, missing confirmation,
-WhatIf, -ValidateOnly, and a confirmed request for the one task the script refuses).
"""

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRATCH = ROOT / "scratch"
REGISTER = SCRATCH / "register_scheduled_tasks.ps1"
DEFS = SCRATCH / "scheduled_task_definitions.ps1"
POWERSHELL = shutil.which("powershell.exe")

pytestmark = pytest.mark.skipif(
    sys.platform != "win32" or POWERSHELL is None, reason="Task Scheduler definitions need Windows PowerShell"
)

FAKE_ROOT = r"C:\Fake Root\Swing Trading"


def ps(command: str, timeout: int = 120) -> subprocess.CompletedProcess:
    return subprocess.run(
        [POWERSHELL, "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command],
        capture_output=True, text=True, timeout=timeout,
    )


def run_register(*args: str, timeout: int = 120) -> subprocess.CompletedProcess:
    if ROOT.name != "Swing Trading":
        pytest.skip("registration script only runs from the authoritative checkout")
    return subprocess.run(
        [POWERSHELL, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(REGISTER), *args],
        capture_output=True, text=True, timeout=timeout,
    )


def summaries(task: str, root: str = FAKE_ROOT) -> list[dict]:
    result = ps(
        f". '{DEFS}'; "
        f"$s = @(Select-SwingTasks -RepoRoot '{root}' -Task '{task}' | ForEach-Object {{ Get-SwingTaskSummary -Definition $_ }}); "
        "ConvertTo-Json -InputObject $s -Depth 4"
    )
    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    return data if isinstance(data, list) else [data]


def live_task_fingerprints() -> dict[str, str]:
    """Read-only snapshot of every SwingTrading-* task definition currently registered."""
    result = ps(
        "Get-ScheduledTask | Where-Object TaskName -like 'SwingTrading*' | "
        "ForEach-Object { $x = Export-ScheduledTask -TaskName $_.TaskName; $h = [Security.Cryptography.SHA256]::Create(); "
        "$_.TaskName + '|' + [BitConverter]::ToString($h.ComputeHash([Text.Encoding]::UTF8.GetBytes($x))) }"
    )
    assert result.returncode == 0, result.stderr
    return {line.split("|")[0]: line for line in result.stdout.splitlines() if line.strip()}


# ---------------------------------------------------------------- selection

def test_icici_selection_returns_only_the_icici_task():
    (task,) = summaries("ICICI")
    assert task["TaskName"] == "SwingTrading-ICICI-Recs"


def test_each_selection_is_isolated_and_stable():
    ohlcv = summaries("OHLCV")
    assert [t["TaskName"] for t in ohlcv] == ["SwingTrading-OHLCV-Bhavcopy"]
    fundamentals = summaries("Fundamentals")
    assert [t["TaskName"] for t in fundamentals] == ["SwingTrading-Fundamentals"]
    # Selecting other tasks never changes how ICICI is defined.
    assert summaries("ICICI") == [t for t in summaries("All") if t["Key"] == "ICICI"]


def test_all_selection_has_three_distinct_tasks():
    names = [t["TaskName"] for t in summaries("All")]
    assert names == ["SwingTrading-ICICI-Recs", "SwingTrading-OHLCV-Bhavcopy", "SwingTrading-Fundamentals"]


def test_invalid_selection_is_rejected():
    result = ps(f". '{DEFS}'; Select-SwingTasks -RepoRoot '{FAKE_ROOT}' -Task 'Bogus'")
    assert result.returncode != 0 and "Unknown task selection" in result.stderr
    assert run_register("-Task", "Bogus").returncode != 0


# ---------------------------------------------------------------- definition contents

def test_icici_action_path_and_working_directory_are_exact_and_quoted():
    (task,) = summaries("ICICI")
    assert task["Execute"].lower().endswith(r"system32\cmd.exe")
    assert task["Arguments"] == '/d /c "' + FAKE_ROOT + r'\scratch\run_broker_recs_icici.bat"'
    assert task["WorkingDirectory"] == FAKE_ROOT
    assert task["Wrapper"] == FAKE_ROOT + r"\scratch\run_broker_recs_icici.bat"


def test_triggers_run_weekdays_and_icici_follows_ohlcv():
    icici, ohlcv = summaries("ICICI")[0], summaries("OHLCV")[0]
    assert icici["StartTime"] == "20:00" and ohlcv["StartTime"] == "19:00"
    assert icici["DaysOfWeek"] == ohlcv["DaysOfWeek"] == 62  # Monday..Friday bitmask
    assert icici["StartTime"] > ohlcv["StartTime"]


def test_every_task_has_a_bounded_limit_and_icici_is_thirty_minutes():
    tasks = {t["Key"]: t for t in summaries("All")}
    assert tasks["ICICI"]["LimitMinutes"] == 30
    assert all(0 < t["LimitMinutes"] <= 240 for t in tasks.values())


def test_every_task_prevents_overlapping_runs():
    assert all(t["MultipleInstances"] == "IgnoreNew" for t in summaries("All"))


def test_no_credentials_or_principal_in_definitions_or_script():
    assert all(t["HasPrincipal"] is False for t in summaries("All"))
    for path in (REGISTER, DEFS, SCRATCH / "run_broker_recs_icici.bat"):
        text = path.read_text(encoding="utf-8").lower()
        for forbidden in ("-password", "-credential", "-runlevel highest", "-logontype password", "-user ", "secret", "apikey", "cookie"):
            assert forbidden not in text, (path.name, forbidden)


def test_fundamentals_is_flagged_as_not_registerable():
    (task,) = summaries("Fundamentals")
    assert task["Unsupported"] and "Monthly" in task["Unsupported"]
    assert all(t["Unsupported"] is None for t in summaries("ICICI") + summaries("OHLCV"))


# ---------------------------------------------------------------- mutation gates

def test_registration_requires_an_explicit_task():
    result = run_register()
    assert result.returncode == 2 and "Nothing is registered implicitly" in result.stderr


def test_registration_requires_confirmation_and_changes_nothing():
    before = live_task_fingerprints()
    result = run_register("-Task", "ICICI")
    assert result.returncode == 2 and "-ConfirmRegistration" in result.stderr
    assert live_task_fingerprints() == before


def test_preview_modes_are_non_mutating_and_show_the_plan():
    before = live_task_fingerprints()
    whatif = run_register("-Task", "ICICI", "-WhatIf")
    assert whatif.returncode == 0
    assert "No scheduled tasks were created or changed" in whatif.stdout
    assert "Limit:      30 minutes" in whatif.stdout and "SwingTrading-ICICI-Recs" in whatif.stdout
    assert "OHLCV" not in whatif.stdout  # unrelated tasks are not part of the plan
    validate = run_register("-ValidateOnly")
    assert validate.returncode == 0 and "No scheduled tasks were created or changed" in validate.stdout
    assert live_task_fingerprints() == before  # unrelated and ICICI tasks untouched


def test_confirmed_request_for_an_unregisterable_task_is_refused_before_any_change():
    before = live_task_fingerprints()
    result = run_register("-Task", "Fundamentals", "-ConfirmRegistration")
    assert result.returncode == 2 and "cannot be registered by this script" in result.stderr
    assert live_task_fingerprints() == before


def test_only_one_guarded_register_call_and_no_delete_or_disable_paths():
    text = REGISTER.read_text(encoding="utf-8")
    assert text.count("Register-ScheduledTask ") == 1
    for forbidden in ("Unregister-ScheduledTask", "Disable-ScheduledTask", "Set-ScheduledTask", "schtasks"):
        assert forbidden not in text
    register_at = text.index("Register-ScheduledTask @params")
    assert text.index("-not $ConfirmRegistration") < register_at
    assert text.index("$blocked.Count -gt 0") < register_at
    assert text.index("$ValidateOnly -or $previewOnly") < register_at


# ---------------------------------------------------------------- wrappers

@pytest.mark.parametrize("name,log", [
    ("run_broker_recs_icici.bat", "broker_recs_icici.log"),
    ("run_ohlcv.bat", "ohlcv.log"),
    ("run_fundamentals.bat", "fundamentals.log"),
])
def test_wrappers_log_and_return_the_script_exit_code(name, log):
    text = (SCRATCH / name).read_text(encoding="utf-8")
    assert "set ROOT=%~dp0.." in text  # resolves relative to its own location
    assert log in text
    assert "set RUN_EXIT=%ERRORLEVEL%" in text
    assert "exit /b %RUN_EXIT%" in text


def test_icici_wrapper_passes_the_production_confirmation_flag():
    text = (SCRATCH / "run_broker_recs_icici.bat").read_text(encoding="utf-8")
    assert "--import --confirm-production" in text


# ---------------------------------------------------------------- regression: post-registration message

def test_registered_message_and_limit_helper_handle_the_stored_limit_format():
    """Regression: the line printed after Register-ScheduledTask read .TotalMinutes off the
    ISO-8601 string ExecutionTimeLimit and aborted the script with exit 1 after registering."""
    result = ps(
        f". '{DEFS}'; "
        f"$m = @(Select-SwingTasks -RepoRoot '{FAKE_ROOT}' -Task 'All' | ForEach-Object {{ Get-SwingRegisteredMessage -Definition $_ }}); "
        "ConvertTo-Json -InputObject $m"
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == [
        "Registered: SwingTrading-ICICI-Recs (Mon-Fri 20:00, limit 30 min)",
        "Registered: SwingTrading-OHLCV-Bhavcopy (Mon-Fri 19:00, limit 120 min)",
        "Registered: SwingTrading-Fundamentals (15th of Feb/May/Aug/Nov 09:00, limit 60 min)",
    ]


def test_registration_script_never_reads_total_minutes_from_the_raw_limit():
    for path in (REGISTER, DEFS):
        text = path.read_text(encoding="utf-8")
        assert "ExecutionTimeLimit.TotalMinutes" not in text, path.name
    assert "Get-SwingRegisteredMessage" in REGISTER.read_text(encoding="utf-8")
