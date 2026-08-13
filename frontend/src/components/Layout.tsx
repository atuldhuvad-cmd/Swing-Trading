import { Outlet, Link, useLocation } from 'react-router-dom';
import { Home, Database, ListPlus } from 'lucide-react';

export default function Layout() {
  const location = useLocation();

  const isActive = (path: string) => {
    return location.pathname === path ? 'text-blue-600 font-bold' : 'text-gray-500';
  };

  return (
    <div className="flex flex-col min-h-screen bg-gray-50">
      <header className="bg-white shadow-sm sticky top-0 z-10">
        <div className="max-w-md mx-auto px-4 py-3 flex justify-between items-center">
          <h1 className="text-xl font-bold text-gray-800">Swing Trading</h1>
        </div>
      </header>

      <main className="flex-1 max-w-md mx-auto w-full px-4 py-4 pb-20">
        <Outlet />
      </main>

      <nav className="fixed bottom-0 w-full bg-white border-t border-gray-200">
        <div className="max-w-md mx-auto flex justify-around p-3">
          <Link to="/" className={`flex flex-col items-center ${isActive('/')}`}>
            <Home size={24} />
            <span className="text-xs mt-1">Home</span>
          </Link>
          <Link to="/recommendations/new" className={`flex flex-col items-center ${isActive('/recommendations/new')}`}>
            <ListPlus size={24} />
            <span className="text-xs mt-1">Recommend</span>
          </Link>
          <Link to="/master" className={`flex flex-col items-center ${isActive('/master')}`}>
            <Database size={24} />
            <span className="text-xs mt-1">Master</span>
          </Link>
        </div>
      </nav>
    </div>
  );
}
