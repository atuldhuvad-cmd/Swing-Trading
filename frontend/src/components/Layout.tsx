import { Outlet, Link, useLocation } from 'react-router-dom';
import { Home, Database, ListPlus, Upload, CheckSquare, Settings } from 'lucide-react';

export default function Layout() {
  const location = useLocation();

  const isActive = (path: string) => {
    return location.pathname.startsWith(path) ? 'text-blue-600 font-bold' : 'text-gray-500';
  };

  return (
    <div className="flex flex-col min-h-screen bg-gray-50">
      <header className="bg-white shadow-sm sticky top-0 z-10">
        <div className="max-w-4xl mx-auto px-4 py-3 flex justify-between items-center">
          <h1 className="text-xl font-bold text-gray-800">Swing Trading</h1>
        </div>
      </header>

      <main className="flex-1 max-w-4xl mx-auto w-full px-4 py-4 pb-20">
        <Outlet />
      </main>

      <nav className="fixed bottom-0 w-full bg-white border-t border-gray-200">
        <div className="max-w-4xl mx-auto flex justify-around px-2 py-2">
          <Link to="/" className={`flex flex-col items-center ${location.pathname === '/' ? 'text-blue-600 font-bold' : 'text-gray-500'}`}>
            <Home size={22} />
            <span className="text-xs mt-1">Home</span>
          </Link>
          <Link to="/recommendations/new" className={`flex flex-col items-center ${isActive('/recommendations/new')}`}>
            <ListPlus size={22} />
            <span className="text-xs mt-1">Rec</span>
          </Link>
          <Link to="/imports/new" className={`flex flex-col items-center ${isActive('/imports')}`}>
            <Upload size={22} />
            <span className="text-xs mt-1">Import</span>
          </Link>
          <Link to="/review" className={`flex flex-col items-center ${isActive('/review')}`}>
            <CheckSquare size={22} />
            <span className="text-xs mt-1">Review</span>
          </Link>
          <Link to="/recommendations" className={`flex flex-col items-center ${location.pathname === '/recommendations' ? 'text-blue-600 font-bold' : 'text-gray-500'}`}>
            <ListPlus size={22} />
            <span className="text-xs mt-1">List</span>
          </Link>
          <Link to="/settings" className={`flex flex-col items-center ${isActive('/settings')}`}><Settings size={22}/><span className="text-xs mt-1">Settings</span></Link>
          <Link to="/master" className={`flex flex-col items-center ${isActive('/master')}`}>
            <Database size={22} />
            <span className="text-xs mt-1">Master</span>
          </Link>
        </div>
      </nav>
    </div>
  );
}
