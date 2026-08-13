import { Routes, Route } from 'react-router-dom';
import Layout from './components/Layout';
// import Home from './pages/Home';
import RecommendationEntry from './pages/RecommendationEntry';
import MasterData from './pages/MasterData';

function App() {
  return (
    <Routes>
      <Route path="/" element={<Layout />}>
        <Route index element={<div className="p-4 text-center">Dashboard (Stage 4)</div>} />
        <Route path="recommendations/new" element={<RecommendationEntry />} />
        <Route path="master" element={<MasterData />} />
      </Route>
    </Routes>
  );
}

export default App;
