import { useState, useEffect } from 'react';
import api from '../api';

export default function MasterData() {
  const [stocks, setStocks] = useState<any[]>([]);
  const [brokers, setBrokers] = useState<any[]>([]);

  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    try {
      const [stockRes, brokerRes] = await Promise.all([
        api.get('/stocks'),
        api.get('/brokers')
      ]);
      setStocks(stockRes.data);
      setBrokers(brokerRes.data);
    } catch (e) {
      console.error(e);
    }
  };

  return (
    <div className="space-y-6">
      <h2 className="text-2xl font-bold">Master Data</h2>
      
      <div>
        <h3 className="text-xl font-semibold mb-2">Brokers ({brokers.length})</h3>
        <div className="bg-white rounded-lg shadow overflow-hidden border border-gray-200">
          <ul className="divide-y divide-gray-200 max-h-60 overflow-y-auto">
            {brokers.map(b => (
              <li key={b.broker_id} className="p-3 hover:bg-gray-50 flex justify-between">
                <span className="font-medium text-gray-800">{b.display_name}</span>
                <span className="text-sm text-gray-500">{b.canonical_name}</span>
              </li>
            ))}
            {brokers.length === 0 && <li className="p-3 text-gray-500 text-center">No brokers found</li>}
          </ul>
        </div>
      </div>

      <div>
        <h3 className="text-xl font-semibold mb-2">Stocks ({stocks.length})</h3>
        <div className="bg-white rounded-lg shadow overflow-hidden border border-gray-200">
          <ul className="divide-y divide-gray-200 max-h-60 overflow-y-auto">
            {stocks.map(s => (
              <li key={s.stock_id} className="p-3 hover:bg-gray-50 flex justify-between">
                <span className="font-bold text-blue-600">{s.nse_symbol}</span>
                <span className="text-sm text-gray-700">{s.company_name}</span>
              </li>
            ))}
            {stocks.length === 0 && <li className="p-3 text-gray-500 text-center">No stocks found</li>}
          </ul>
        </div>
      </div>
    </div>
  );
}
