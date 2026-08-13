import { useEffect, useState } from 'react';
import { reviewApi } from '../api';

export default function ReviewQueue() {
  const [items, setItems] = useState<any[]>([]);

  useEffect(() => {
    loadItems();
  }, []);

  const loadItems = async () => {
    const data = await reviewApi.getItems();
    setItems(data);
  };

  const handleResolve = async (reviewId: number, action: string, brokerId?: number) => {
    await reviewApi.resolveItem(reviewId, { action, resolved_broker_id: brokerId });
    loadItems();
  };

  return (
    <div className="max-w-4xl mx-auto p-4 space-y-4">
      <h1 className="text-2xl font-bold">Review Queue</h1>
      <div className="grid grid-cols-1 gap-4">
        {items.map((item: any) => (
          <div key={item.review_id} className="border p-4 rounded bg-white shadow-sm space-y-2">
            <div className="flex justify-between">
              <h2 className="font-semibold text-lg">{item.reason}</h2>
              <span className="text-sm text-gray-500">{new Date(item.created_at).toLocaleString()}</span>
            </div>
            {item.mapped_data && (
              <div className="bg-gray-50 p-2 text-sm rounded">
                <p><strong>Stock:</strong> {item.mapped_data.nse_symbol}</p>
                <p><strong>Broker:</strong> {item.mapped_data.broker_name}</p>
                <p><strong>Date:</strong> {item.mapped_data.recommendation_date}</p>
                <p><strong>Raw Data:</strong> {JSON.stringify(item.raw_data)}</p>
              </div>
            )}
            <div className="flex gap-2 mt-2">
              <button onClick={() => handleResolve(item.review_id, 'ACCEPT_AS_NEW')} className="bg-green-600 text-white px-3 py-1 rounded text-sm">
                Accept As New
              </button>
              <button onClick={() => handleResolve(item.review_id, 'REJECT')} className="bg-red-600 text-white px-3 py-1 rounded text-sm">
                Reject
              </button>
            </div>
          </div>
        ))}
        {items.length === 0 && (
          <div className="text-center p-4 text-gray-500 border rounded bg-white">No items in review queue</div>
        )}
      </div>
    </div>
  );
}
