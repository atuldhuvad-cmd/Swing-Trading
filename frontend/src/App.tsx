import { BrowserRouter as Router, Routes, Route, Link } from 'react-router-dom';
import { useState } from 'react';
import './index.css';

const Dashboard = () => <div className="p-4"><h2>Dashboard</h2><p>Dashboard placeholder</p></div>;
const Recommendations = () => <div className="p-4"><h2>Recommendations</h2><p>Recommendations placeholder</p></div>;
const Stocks = () => <div className="p-4"><h2>Stocks</h2><p>Stocks placeholder</p></div>;
const ImportPage = () => <div className="p-4"><h2>Import</h2><p>Import placeholder</p></div>;
const Settings = () => <div className="p-4"><h2>Settings</h2><p>Settings placeholder</p></div>;

function App() {
  const [isMenuOpen, setIsMenuOpen] = useState(false);

  return (
    <Router>
      <div className="min-h-screen bg-gray-50 flex flex-col md:flex-row">
        {/* Mobile Nav */}
        <div className="md:hidden bg-indigo-600 text-white p-4 flex justify-between items-center">
          <h1 className="text-xl font-bold">Swing Trading</h1>
          <button onClick={() => setIsMenuOpen(!isMenuOpen)} className="focus:outline-none p-2 border rounded">
            Menu
          </button>
        </div>
        
        {/* Sidebar */}
        <nav className={`${isMenuOpen ? 'block' : 'hidden'} md:block w-full md:w-64 bg-indigo-800 text-white flex-shrink-0 md:min-h-screen`}>
          <div className="hidden md:block p-4 border-b border-indigo-700">
            <h1 className="text-2xl font-bold">Swing Trading</h1>
          </div>
          <ul className="flex flex-col py-4">
            <li><Link to="/" className="block px-4 py-2 hover:bg-indigo-700" onClick={() => setIsMenuOpen(false)}>Dashboard</Link></li>
            <li><Link to="/recommendations" className="block px-4 py-2 hover:bg-indigo-700" onClick={() => setIsMenuOpen(false)}>Recommendations</Link></li>
            <li><Link to="/stocks" className="block px-4 py-2 hover:bg-indigo-700" onClick={() => setIsMenuOpen(false)}>Stocks</Link></li>
            <li><Link to="/import" className="block px-4 py-2 hover:bg-indigo-700" onClick={() => setIsMenuOpen(false)}>Import</Link></li>
            <li><Link to="/settings" className="block px-4 py-2 hover:bg-indigo-700" onClick={() => setIsMenuOpen(false)}>Settings</Link></li>
          </ul>
        </nav>

        {/* Main Content */}
        <main className="flex-1 overflow-auto w-full max-w-full">
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/recommendations" element={<Recommendations />} />
            <Route path="/stocks" element={<Stocks />} />
            <Route path="/import" element={<ImportPage />} />
            <Route path="/settings" element={<Settings />} />
          </Routes>
        </main>
      </div>
    </Router>
  );
}

export default App;
