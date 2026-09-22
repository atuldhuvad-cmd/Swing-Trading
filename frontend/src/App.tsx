import { Routes, Route } from 'react-router-dom';
import Layout from './components/Layout';
import Home from './pages/Home';
import DataHub from './pages/DataHub';
import CandidateDashboard from './pages/CandidateDashboard';
import StockDetailConsensus from './pages/StockDetailConsensus';
import RecommendationEntry from './pages/RecommendationEntry';
import MasterData from './pages/MasterData';
import ImportWizard from './pages/ImportWizard';
import ImportHistory from './pages/ImportHistory';
import ReviewQueue from './pages/ReviewQueue';
import SourceReadiness from './pages/SourceReadiness';
import Settings from './pages/Settings';
import BrokerRecommendations from './pages/BrokerRecommendations';
import FinalCandidates from './pages/FinalCandidates';
import CandidateEvidence from './pages/CandidateEvidence';
import MarketDataStatus from './pages/MarketDataStatus';
import DataSync from './pages/DataSync';
import BrokerUploads from './pages/BrokerUploads';
import FundamentalImport from './pages/FundamentalImport';
import TradeJournal from './pages/TradeJournal';
import TradePlanForm from './pages/TradePlanForm';

function App() {
  return (
    <Routes>
      <Route path="/" element={<Layout />}>
        <Route index element={<Home />} />
        <Route path="data" element={<DataHub />} />
        <Route path="final-candidates" element={<FinalCandidates />} />
        <Route path="evidence/:stockId" element={<CandidateEvidence />} />
        <Route path="market-data" element={<MarketDataStatus />} />
        <Route path="data-sync" element={<DataSync />} />
        <Route path="fundamentals/import" element={<FundamentalImport />} />
        <Route path="broker-opinion" element={<CandidateDashboard />} />
        <Route path="consensus/:stockId" element={<StockDetailConsensus />} />
        <Route path="recommendations/new" element={<RecommendationEntry />} />
        <Route path="recommendations" element={<BrokerRecommendations />} />
        <Route path="broker-uploads" element={<BrokerUploads />} />
        <Route path="master" element={<MasterData />} />
        <Route path="imports/new" element={<ImportWizard />} />
        <Route path="imports/history" element={<ImportHistory />} />
        <Route path="review" element={<ReviewQueue />} />
        <Route path="source-readiness" element={<SourceReadiness />} />
        <Route path="settings" element={<Settings />} />
        <Route path="trades" element={<TradeJournal />} />
        <Route path="trades/plan/:stockId" element={<TradePlanForm />} />
      </Route>
    </Routes>
  );
}

export default App;
