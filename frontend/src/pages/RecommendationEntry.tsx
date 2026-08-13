import { useState, useEffect } from 'react';
import { Save, AlertCircle } from 'lucide-react';
import api from '../api';
import { useNavigate } from 'react-router-dom';

export default function RecommendationEntry() {
  const navigate = useNavigate();
  const [stocks, setStocks] = useState<any[]>([]);
  const [brokers, setBrokers] = useState<any[]>([]);
  
  const [selectedStock, setSelectedStock] = useState<number | null>(null);
  const [selectedBroker, setSelectedBroker] = useState<number | null>(null);
  const [rating, setRating] = useState('');
  const [targetPrice, setTargetPrice] = useState('');
  const [sourceUrl, setSourceUrl] = useState('');
  
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    api.get('/stocks').then(res => setStocks(res.data)).catch(console.error);
    api.get('/brokers').then(res => setBrokers(res.data)).catch(console.error);
  }, []);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedStock || !selectedBroker || !rating) {
      setError('Please fill all required fields');
      return;
    }
    
    setError('');
    setLoading(true);

    try {
      // 1 is ID for direct entry source type as per Stage 2
      const payload = {
        stock_id: selectedStock,
        broker_id: selectedBroker,
        recommendation_date: new Date().toISOString(),
        original_rating: rating,
        normalized_rating: rating.toUpperCase().replace(/\s+/g, '_'),
        target_price: targetPrice ? parseFloat(targetPrice) : null,
        evidence: [
          {
            source_type_id: 1, // PRIMARY_DIRECT
            verification_status: "VERIFIED_PRIMARY",
            url: sourceUrl || null
          }
        ]
      };

      await api.post('/recommendations', payload);
      alert('Recommendation saved successfully!');
      navigate('/');
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to save recommendation');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-6 max-w-md mx-auto">
      <h2 className="text-2xl font-bold text-gray-800">New Recommendation</h2>
      
      {error && (
        <div className="bg-red-50 text-red-700 p-3 rounded-md flex items-start gap-2">
          <AlertCircle className="shrink-0 mt-0.5" size={18} />
          <span className="text-sm">{error}</span>
        </div>
      )}

      <form onSubmit={handleSubmit} className="space-y-4 bg-white p-4 rounded-xl shadow-sm border border-gray-100">
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Stock</label>
          <select 
            className="w-full p-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500"
            value={selectedStock || ''}
            onChange={e => setSelectedStock(Number(e.target.value))}
          >
            <option value="">Select Stock...</option>
            {stocks.map(s => <option key={s.stock_id} value={s.stock_id}>{s.nse_symbol}</option>)}
          </select>
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Broker</label>
          <select 
            className="w-full p-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500"
            value={selectedBroker || ''}
            onChange={e => setSelectedBroker(Number(e.target.value))}
          >
            <option value="">Select Broker...</option>
            {brokers.map(b => <option key={b.broker_id} value={b.broker_id}>{b.display_name}</option>)}
          </select>
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Rating</label>
          <select 
            className="w-full p-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500"
            value={rating}
            onChange={e => setRating(e.target.value)}
          >
            <option value="">Select Rating...</option>
            <option value="Strong Buy">Strong Buy</option>
            <option value="Buy">Buy</option>
            <option value="Accumulate">Accumulate</option>
            <option value="Hold">Hold</option>
            <option value="Reduce">Reduce</option>
            <option value="Sell">Sell</option>
            <option value="Strong Sell">Strong Sell</option>
          </select>
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Target Price (Optional)</label>
          <input 
            type="number"
            step="0.05"
            className="w-full p-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500"
            value={targetPrice}
            onChange={e => setTargetPrice(e.target.value)}
            placeholder="e.g. 1500.50"
          />
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1">Source URL (Optional)</label>
          <input 
            type="url"
            className="w-full p-2 border border-gray-300 rounded-md focus:ring-2 focus:ring-blue-500"
            value={sourceUrl}
            onChange={e => setSourceUrl(e.target.value)}
            placeholder="https://..."
          />
        </div>

        <button 
          type="submit"
          disabled={loading}
          className="w-full py-3 bg-blue-600 text-white font-semibold rounded-lg shadow-sm hover:bg-blue-700 disabled:opacity-50 flex items-center justify-center gap-2"
        >
          <Save size={20} />
          {loading ? 'Saving...' : 'Save Recommendation'}
        </button>
      </form>
    </div>
  );
}
