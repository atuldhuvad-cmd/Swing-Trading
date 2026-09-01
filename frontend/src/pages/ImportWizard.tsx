import { useState } from 'react';
import { importsApi } from '../api';
import BackLink from '../components/BackLink';

export default function ImportWizard() {
  const [step, setStep] = useState(1); // 1: Upload, 2: Map, 3: Preview, 4: Summary
  const [file, setFile] = useState<File | null>(null);
  const [batchId, setBatchId] = useState<number | null>(null);
  const [headers, setHeaders] = useState<string[]>([]);
  const [mapping, setMapping] = useState<any>({});
  const [preview, setPreview] = useState<any>(null);

  const handleUpload = async () => {
    if (!file) return;
    const res = await importsApi.uploadFile(file);
    setBatchId(res.batch_id);
    setHeaders(res.detected_headers);
    setStep(2);
  };

  const handleMap = async () => {
    if (!batchId) return;
    const res = await importsApi.applyMapping(batchId, mapping);
    setPreview(res);
    setStep(3);
  };

  const handleConfirm = async () => {
    if (!batchId) return;
    await importsApi.confirmBatch(batchId);
    setStep(4);
  };

  return (
    <div className="max-w-4xl mx-auto p-4 space-y-4 min-w-0">
      <BackLink fallback="/data" />
      <h1 className="text-2xl font-bold">Import Recommendations</h1>
      
      {/* Upload Step */}
      {step === 1 && (
        <div className="border p-4 rounded bg-white shadow-sm space-y-4">
          <h2 className="text-lg font-semibold">Step 1: Upload File</h2>
          <input type="file" accept=".csv,.xlsx" onChange={(e) => setFile(e.target.files?.[0] || null)} className="w-full" />
          <button onClick={handleUpload} disabled={!file} className="bg-blue-600 text-white px-4 py-2 rounded">
            Upload
          </button>
        </div>
      )}

      {/* Mapping Step */}
      {step === 2 && (
        <div className="border p-4 rounded bg-white shadow-sm space-y-4">
          <h2 className="text-lg font-semibold">Step 2: Map Columns</h2>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {['nse_symbol', 'broker_name', 'recommendation_date', 'original_rating', 'recommended_price', 'target_price'].map(field => (
              <div key={field}>
                <label className="block text-sm font-medium">{field}</label>
                <select 
                  className="w-full border rounded p-2" 
                  value={mapping[field] || ''}
                  onChange={(e) => setMapping({...mapping, [field]: e.target.value})}
                >
                  <option value="">-- Select Column --</option>
                  {headers.map(h => <option key={h} value={h}>{h}</option>)}
                </select>
              </div>
            ))}
          </div>
          <button onClick={handleMap} className="bg-blue-600 text-white px-4 py-2 rounded mt-4">
            Process Mapping
          </button>
        </div>
      )}

      {/* Preview Step */}
      {step === 3 && preview && (
        <div className="border p-4 rounded bg-white shadow-sm space-y-4">
          <h2 className="text-lg font-semibold">Step 3: Preview & Confirm</h2>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
            <div className="bg-green-100 p-2 rounded">Valid/Unique: {preview.valid_unique}</div>
            <div className="bg-yellow-100 p-2 rounded">Duplicates: {preview.exact_duplicates}</div>
            <div className="bg-blue-100 p-2 rounded">Needs Review: {preview.review_required}</div>
            <div className="bg-red-100 p-2 rounded">Rejected: {preview.rejected}</div>
          </div>
          
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm whitespace-nowrap">
              <thead>
                <tr className="bg-gray-100">
                  <th className="p-2">Row</th>
                  <th className="p-2">Stock</th>
                  <th className="p-2">Broker</th>
                  <th className="p-2">Date</th>
                  <th className="p-2">Action</th>
                  <th className="p-2">Message</th>
                </tr>
              </thead>
              <tbody>
                {preview.rows.map((r: any) => (
                  <tr key={r.row_number} className="border-t">
                    <td className="p-2">{r.row_number}</td>
                    <td className="p-2">{r.mapped_data.nse_symbol}</td>
                    <td className="p-2">{r.mapped_data.broker_name}</td>
                    <td className="p-2">{r.mapped_data.recommendation_date}</td>
                    <td className="p-2 font-semibold">{r.action}</td>
                    <td className="p-2 text-red-600">{r.error_message}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <button onClick={handleConfirm} className="bg-green-600 text-white px-4 py-2 rounded mt-4">
            Confirm Import
          </button>
        </div>
      )}

      {/* Summary Step */}
      {step === 4 && (
        <div className="border p-4 rounded bg-white shadow-sm space-y-4">
          <h2 className="text-lg font-semibold text-green-600">Import Complete</h2>
          <p>Batch ID: {batchId}</p>
          <button onClick={() => setStep(1)} className="text-blue-600 underline">Start New Import</button>
        </div>
      )}
    </div>
  );
}
