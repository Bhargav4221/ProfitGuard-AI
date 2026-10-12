import React from 'react';
import { ShieldAlert } from 'lucide-react';

export default function Loading() {
  return (
    <div className="min-h-screen flex flex-col items-center justify-center bg-slate-50 p-6">
      <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-emerald-600 text-white shadow-lg shadow-emerald-500/20 animate-pulse mb-4">
        <ShieldAlert className="h-7 w-7" />
      </div>
      <h3 className="text-sm font-semibold text-slate-700">Loading ProfitGuard AI...</h3>
      <p className="text-xs text-slate-400 mt-1">Connecting multi-tenant workspace</p>
    </div>
  );
}
