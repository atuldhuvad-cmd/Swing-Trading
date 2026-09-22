import { Link } from 'react-router-dom';
import type { ReactNode } from 'react';

function Group({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="bg-white p-4 rounded-lg border border-gray-200 min-w-0">
      <h2 className="font-semibold text-gray-900">{title}</h2>
      <div className="mt-2 flex flex-col gap-1">{children}</div>
    </section>
  );
}

function Item({ to, label, hint }: { to: string; label: string; hint: string }) {
  return (
    <Link to={to} className="min-h-[44px] py-2 text-sm text-blue-700 hover:underline break-words">
      {label}
      <span className="block text-[11px] text-gray-500 font-normal">{hint}</span>
    </Link>
  );
}

export default function DataHub() {
  return (
    <div className="space-y-4 min-w-0">
      <div className="bg-white p-4 rounded-lg border border-gray-200">
        <h1 className="text-xl font-bold text-gray-900">Data</h1>
        <p className="text-xs text-gray-600 mt-1 break-words">
          Maintenance screens for stored market data, fundamentals, broker reports, and health checks.
        </p>
      </div>

      <Group title="Market Data">
        <Item to="/market-data" label="Market data status" hint="Stored OHLCV coverage and SMA200 readiness. No live-price upload in this screen." />
        <Item to="/data-sync" label="Data sync" hint="Run the auto-download scripts (OHLCV/Bhavcopy, fundamentals, ICICI recs) and see their reports." />
      </Group>

      <Group title="Fundamentals">
        <Item to="/fundamentals/import" label="Manual fundamental import" hint="Enter published line items. Missing values stay unknown." />
      </Group>

      <Group title="Broker Reports">
        <Item to="/recommendations/new" label="Enter a recommendation" hint="Type facts from a report you already have." />
        <Item to="/broker-uploads" label="Upload broker PDF" hint="Save a PDF report from Motilal Oswal, HDFC Securities, 5paisa, or any other brokerage here." />
        <Item to="/imports/new" label="CSV / XLSX import" hint="Upload a structured file, map columns, preview, then confirm." />
        <Item to="/review" label="Review queue" hint="Resolve import rows that need a human check." />
        <Item to="/imports/history" label="Import history" hint="Past recommendation batches." />
        <Item to="/recommendations" label="Recommendation list" hint="Saved broker recommendations." />
        <Item to="/broker-opinion" label="Broker opinion universe" hint="Display-only consensus. Not a buy list." />
      </Group>

      <Group title="Data Health">
        <Item to="/source-readiness" label="Source readiness" hint="Which broker sources are configured." />
        <Item to="/settings" label="Settings" hint="Freshness windows for consensus display." />
        <Item to="/master" label="Master data" hint="Stocks and brokers." />
      </Group>
    </div>
  );
}
