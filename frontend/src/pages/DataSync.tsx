import { useEffect, useState } from 'react';
import BackLink from '../components/BackLink';
import { dataSyncApi } from '../api';

interface JobStatus {
  job_id: string;
  label: string;
  writes_db: boolean;
  script_exists: boolean;
  last_report: {
    report_path: string;
    mtime: number;
    summary: Record<string, unknown>;
  } | null;
}

interface RunResult {
  job_id: string;
  label: string;
  writes_db: boolean;
  timed_out: boolean;
  returncode: number | null;
  duration_seconds: number;
  stdout_tail: string;
  stderr_tail: string;
  report: { report_path: string; mtime: number; summary: Record<string, unknown> } | null;
}

function formatTime(mtime?: number): string {
  if (!mtime) return 'Never run';
  return new Date(mtime * 1000).toLocaleString();
}

function SummaryLine({ summary }: { summary: Record<string, unknown> }) {
  const entries = Object.entries(summary).filter(([, v]) => v !== null && v !== undefined);
  if (entries.length === 0) return null;
  return (
    <div className="mt-1 flex flex-wrap gap-x-3 gap-y-0.5 text-[11px] text-gray-600">
      {entries.map(([k, v]) => (
        <span key={k}>
          <span className="text-gray-400">{k}:</span> {typeof v === 'object' ? JSON.stringify(v) : String(v)}
        </span>
      ))}
    </div>
  );
}

function JobCard({ job, onRun }: { job: JobStatus; onRun: (jobId: string) => Promise<void> }) {
  const [running, setRunning] = useState(false);
  const [confirmed, setConfirmed] = useState(!job.writes_db);
  const [result, setResult] = useState<RunResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleRun = async () => {
    setRunning(true);
    setError(null);
    setResult(null);
    try {
      const res = await dataSyncApi.runJob(job.job_id, job.writes_db && confirmed);
      setResult(res);
      await onRun(job.job_id);
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'Run failed');
    } finally {
      setRunning(false);
      if (job.writes_db) setConfirmed(false);
    }
  };

  return (
    <div className="bg-white p-4 rounded-lg border border-gray-200 min-w-0">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="font-semibold text-gray-900">{job.label}</div>
          <div className="text-[11px] text-gray-500 mt-0.5">
            {job.writes_db ? 'Writes to the production database' : 'Download only — nothing is imported'}
          </div>
        </div>
      </div>

      <div className="mt-2 text-xs text-gray-600">
        Last run: {formatTime(job.last_report?.mtime)}
      </div>
      {job.last_report && <SummaryLine summary={job.last_report.summary} />}

      {!job.script_exists && (
        <div className="mt-2 text-xs text-red-600">Script not found on disk — cannot run.</div>
      )}

      {job.writes_db && !confirmed && (
        <label className="mt-3 flex items-start gap-2 text-xs text-gray-700">
          <input
            type="checkbox"
            className="mt-0.5"
            checked={confirmed}
            onChange={(e) => setConfirmed(e.target.checked)}
          />
          I understand this will back up, then import into, the production database.
        </label>
      )}

      <button
        type="button"
        disabled={running || !job.script_exists || (job.writes_db && !confirmed)}
        onClick={handleRun}
        className="mt-3 min-h-[44px] w-full rounded-md bg-blue-600 text-white text-sm font-medium disabled:opacity-50 disabled:cursor-not-allowed"
      >
        {running ? 'Running…' : 'Run now'}
      </button>

      {error && (
        <div className="mt-3 bg-red-50 p-3 rounded-md text-red-600 text-xs border border-red-200 break-words">
          {error}
        </div>
      )}

      {result && (
        <div className="mt-3 border-t border-gray-100 pt-3 text-xs">
          <div className={result.timed_out || (result.returncode ?? 0) !== 0 ? 'text-amber-700' : 'text-green-700'}>
            {result.timed_out
              ? `Timed out after ${result.duration_seconds}s`
              : `Finished in ${result.duration_seconds}s (exit code ${result.returncode})`}
          </div>
          {result.report && <SummaryLine summary={result.report.summary} />}
          {!result.report && !result.timed_out && (
            <div className="mt-1 text-gray-500">No new report file was written — see output below.</div>
          )}
          <details className="mt-2">
            <summary className="cursor-pointer text-gray-500">Output</summary>
            <pre className="mt-1 whitespace-pre-wrap break-words bg-gray-50 p-2 rounded text-[10px] text-gray-700 max-h-64 overflow-y-auto">
              {result.stdout_tail}
              {result.stderr_tail && `\n--- stderr ---\n${result.stderr_tail}`}
            </pre>
          </details>
        </div>
      )}
    </div>
  );
}

export default function DataSync() {
  const [jobs, setJobs] = useState<JobStatus[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = async () => {
    try {
      const res = await dataSyncApi.getJobs();
      setJobs(res.jobs || []);
      setError(null);
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'Failed to load data sync status');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  return (
    <div className="space-y-4 min-w-0">
      <div className="bg-white p-4 rounded-lg border border-gray-200">
        <BackLink fallback="/data" />
        <h1 className="text-xl font-bold text-gray-900">Data Sync</h1>
        <p className="text-xs text-gray-500 mt-1">
          Run the on-demand download scripts from here instead of a terminal. Each script is unchanged —
          this just triggers the same file and shows you its report. Nothing runs automatically from this
          screen; for a schedule, see scratch/register_scheduled_tasks.ps1.
        </p>
      </div>

      {loading && <div className="text-sm text-gray-500">Loading…</div>}
      {error && <div className="bg-red-50 p-4 rounded-md text-red-600 text-sm border border-red-200">{error}</div>}

      <div className="grid grid-cols-1 gap-3">
        {jobs.map((job) => (
          <JobCard key={job.job_id} job={job} onRun={load} />
        ))}
      </div>
    </div>
  );
}
