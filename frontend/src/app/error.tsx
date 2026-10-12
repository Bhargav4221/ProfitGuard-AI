'use client';

import React, { useEffect } from 'react';
import { AlertTriangle, RefreshCw } from 'lucide-react';

export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error('ProfitGuard UI caught runtime error:', error);
  }, [error]);

  const handleResetSession = () => {
    if (typeof window !== 'undefined') {
      localStorage.removeItem('profitguard_token');
      localStorage.removeItem('profitguard_org_id');
    }
    reset();
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-slate-50 p-6">
      <div className="max-w-md w-full rounded-2xl border border-rose-200 bg-white p-6 shadow-xl text-center">
        <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-2xl bg-rose-100 text-rose-600 mb-4">
          <AlertTriangle className="h-7 w-7" />
        </div>
        <h2 className="text-xl font-bold text-slate-900 mb-2">Application Error</h2>
        <p className="text-xs text-slate-600 mb-4">
          {error?.message || 'An unexpected error occurred while rendering the dashboard.'}
        </p>
        {error?.digest && (
          <p className="text-[10px] font-mono text-slate-400 mb-4">Digest: {error.digest}</p>
        )}
        <div className="flex justify-center space-x-3">
          <button
            onClick={handleResetSession}
            className="flex items-center space-x-2 rounded-xl bg-emerald-600 px-4 py-2.5 text-xs font-semibold text-white shadow-md hover:bg-emerald-700 transition"
          >
            <RefreshCw className="h-3.5 w-3.5" />
            <span>Reset & Retry</span>
          </button>
          <button
            onClick={() => window.location.reload()}
            className="rounded-xl border border-slate-300 bg-white px-4 py-2.5 text-xs font-semibold text-slate-700 hover:bg-slate-50 transition"
          >
            Reload Page
          </button>
        </div>
      </div>
    </div>
  );
}
