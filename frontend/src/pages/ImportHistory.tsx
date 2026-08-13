import { useEffect, useState } from 'react';
import { importsApi } from '../api';

export default function ImportHistory() {
  const [batches, setBatches] = useState<any[]>([]);

  useEffect(() => {
    loadBatches();
  }, []);

  const loadBatches = async () => {
    const data = await importsApi.getBatches();
    setBatches(data);
  };

  const handleRollback = async (batchId: number) => {
    if (confirm('Are you sure you want to rollback this batch?')) {
      await importsApi.rollbackBatch(batchId);
      loadBatches();
    }
  };

  return (
    <div className="max-w-4xl mx-auto p-4 space-y-4">
      <h1 className="text-2xl font-bold">Import History</h1>
      <div className="overflow-x-auto">
        <table className="w-full text-left text-sm whitespace-nowrap bg-white shadow-sm border rounded">
          <thead>
            <tr className="bg-gray-100 border-b">
              <th className="p-2">Batch ID</th>
              <th className="p-2">Filename</th>
              <th className="p-2">Date</th>
              <th className="p-2">Status</th>
              <th className="p-2">Rows</th>
              <th className="p-2">Accepted</th>
              <th className="p-2">Rejected</th>
              <th className="p-2">Duplicates</th>
              <th className="p-2">Review</th>
              <th className="p-2">Action</th>
            </tr>
          </thead>
          <tbody>
            {batches.map((b: any) => (
              <tr key={b.batch_id} className="border-t">
                <td className="p-2">{b.batch_id}</td>
                <td className="p-2">{b.filename}</td>
                <td className="p-2">{new Date(b.import_date).toLocaleString()}</td>
                <td className="p-2 font-semibold">{b.status}</td>
                <td className="p-2">{b.total_rows}</td>
                <td className="p-2 text-green-600">{b.accepted_rows}</td>
                <td className="p-2 text-red-600">{b.rejected_rows}</td>
                <td className="p-2 text-yellow-600">{b.duplicate_rows}</td>
                <td className="p-2 text-blue-600">{b.review_rows}</td>
                <td className="p-2">
                  {b.status === 'COMPLETED' && (
                    <button 
                      onClick={() => handleRollback(b.batch_id)}
                      className="text-red-600 underline text-xs"
                    >
                      Rollback
                    </button>
                  )}
                </td>
              </tr>
            ))}
            {batches.length === 0 && (
              <tr><td colSpan={10} className="p-4 text-center">No imports found</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
