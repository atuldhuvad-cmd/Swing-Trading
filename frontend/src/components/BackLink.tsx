import { ArrowLeft } from 'lucide-react';
import { useNavigate } from 'react-router-dom';

/** React Router stores a session index on history.state.idx. */
export function hasInAppHistory(): boolean {
  const idx = (window.history.state as { idx?: number } | null)?.idx;
  return typeof idx === 'number' && idx > 0;
}

export function useBack(fallback: string) {
  const navigate = useNavigate();
  return () => {
    if (hasInAppHistory()) {
      navigate(-1);
      return;
    }
    navigate(fallback);
  };
}

interface BackLinkProps {
  fallback: string;
  label?: string;
}

export default function BackLink({ fallback, label = 'Back' }: BackLinkProps) {
  const goBack = useBack(fallback);

  return (
    <button
      type="button"
      onClick={goBack}
      data-testid="back-link"
      className="inline-flex items-center gap-1 min-h-[44px] min-w-[44px] px-2 -ml-2 text-sm font-medium text-blue-600 hover:underline"
    >
      <ArrowLeft size={18} className="shrink-0" aria-hidden />
      <span className="break-words">← {label}</span>
    </button>
  );
}
