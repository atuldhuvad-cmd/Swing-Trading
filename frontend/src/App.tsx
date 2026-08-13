import { Routes, Route } from 'react-router-dom';
import Layout from './components/Layout';
import CandidateDashboard from './pages/CandidateDashboard';
import StockDetailConsensus from './pages/StockDetailConsensus';
import RecommendationEntry from './pages/RecommendationEntry';
import MasterData from './pages/MasterData';
import ImportWizard from './pages/ImportWizard';
import ImportHistory from './pages/ImportHistory';
import ReviewQueue from './pages/ReviewQueue';

function App() {
  return (
    <Routes>
      <Route path="/" element={<Layout />}>
        <Route index element={<CandidateDashboard />} />
        <Route path="consensus/:stockId" element={<StockDetailConsensus />} />
        <Route path="recommendations/new" element={<RecommendationEntry />} />
        <Route path="master" element={<MasterData />} />
        <Route path="imports/new" element={<ImportWizard />} />
        <Route path="imports/history" element={<ImportHistory />} />
        <Route path="review" element={<ReviewQueue />} />
      </Route>
    </Routes>
  );
}

export default App;
