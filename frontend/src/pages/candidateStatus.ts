export const CLASSIFICATION_MEANING: Record<string, string> = {
  FINAL_CANDIDATE: 'Passes current Phase 5 trend screen. It is not a BUY instruction.',
  WATCH: 'Primary trend criterion passes, trend confirmation fails.',
  REJECTED: 'Primary mandatory trend criterion fails.',
  INSUFFICIENT_DATA: 'Mandatory evidence unavailable.',
};

export function asOfDate(value: string | null | undefined): string | null {
  if (!value) return null;
  const day = String(value).slice(0, 10);
  return day || null;
}

export function statusBadgeClass(status: string): string {
  switch (status) {
    case 'FINAL_CANDIDATE':
      return 'bg-green-50 text-green-800';
    case 'WATCH':
      return 'bg-amber-50 text-amber-800';
    case 'REJECTED':
      return 'bg-red-50 text-red-800';
    case 'INSUFFICIENT_DATA':
      return 'bg-gray-100 text-gray-700';
    default:
      return 'bg-blue-50 text-blue-800';
  }
}

export function displayValue(value: string | number | null | undefined): string {
  if (value === null || value === undefined || value === '') return 'N/A';
  return String(value);
}

export function criterionResult(row: { result?: string | null } | null | undefined): string {
  return row?.result || 'N/A';
}
