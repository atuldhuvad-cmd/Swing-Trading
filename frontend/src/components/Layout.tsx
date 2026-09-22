import { Outlet, Link, useLocation } from 'react-router-dom';
import { Home, BarChart3, ShieldCheck, BookOpen } from 'lucide-react';
import type { ReactNode } from 'react';

const DATA_PATHS = [
  '/data',
  '/market-data',
  '/data-sync',
  '/fundamentals',
  '/recommendations',
  '/imports',
  '/review',
  '/master',
  '/settings',
  '/source-readiness',
  '/broker-opinion',
  '/broker-uploads',
  '/consensus',
];

function isActive(pathname: string, to: string) {
  if (to === '/') return pathname === '/';
  if (to === '/final-candidates') {
    return pathname.startsWith('/final-candidates') || pathname.startsWith('/evidence');
  }
  if (to === '/trades') return pathname.startsWith('/trades');
  if (to === '/data') return DATA_PATHS.some((p) => pathname === p || pathname.startsWith(`${p}/`));
  return pathname.startsWith(to);
}

export default function Layout() {
  const location = useLocation();

  const item = (to: string, label: string, icon: ReactNode) => {
    const active = isActive(location.pathname, to);
    return (
      <Link
        to={to}
        className={`flex flex-col items-center justify-center min-w-[52px] min-h-[48px] px-3 py-1 rounded-xl transition-colors ${active ? 'text-blue-600 dark:text-blue-400 font-bold bg-blue-50' : 'text-gray-600 hover:bg-gray-100'}`}
      >
        {icon}
        <span className="text-[10px] sm:text-xs mt-0.5 text-center">{label}</span>
      </Link>
    );
  };

  return (
    <div className="flex flex-col min-h-screen bg-gray-50 overflow-x-clip">
      <header className="bg-white shadow-sm sticky top-0 z-10">
        <div className="max-w-4xl mx-auto px-4 py-3 flex justify-between items-center min-w-0">
          <h1 className="text-lg sm:text-xl font-bold text-gray-800 truncate">Swing Trading</h1>
        </div>
      </header>

      <main className="flex-1 max-w-4xl mx-auto w-full min-w-0 px-4 py-4 pb-24">
        <Outlet />
      </main>

      <nav className="fixed bottom-0 w-full bg-white border-t-2 border-gray-300 shadow-[0_-4px_14px_rgba(0,0,0,0.12)] z-20">
        <div className="max-w-4xl mx-auto flex justify-around px-1 py-1.5">
          {item('/', 'Home', <Home size={22} />)}
          {item('/final-candidates', 'Candidates', <ShieldCheck size={22} />)}
          {item('/trades', 'Journal', <BookOpen size={22} />)}
          {item('/data', 'Data', <BarChart3 size={22} />)}
        </div>
      </nav>
    </div>
  );
}
