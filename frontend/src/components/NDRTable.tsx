'use client';

import React from 'react';
import {
  RotateCcw,
  CheckCircle2,
  Clock,
  AlertCircle,
  TrendingUp,
  ChevronLeft,
  ChevronRight,
  Package,
  Sparkles,
} from 'lucide-react';
import { NDRCase } from '@/types';

interface NDRTableProps {
  cases: NDRCase[];
  total: number;
  limit: number;
  offset: number;
  onPageChange: (newOffset: number) => void;
  isLoading: boolean;
  onSelectCase: (ndrCase: NDRCase) => void;
}

export const NDRTable: React.FC<NDRTableProps> = ({
  cases,
  total,
  limit,
  offset,
  onPageChange,
  isLoading,
  onSelectCase,
}) => {
  const currentPage = Math.floor(offset / limit) + 1;
  const totalPages = Math.max(1, Math.ceil(total / limit));

  const getStatusBadge = (status: NDRCase['status']) => {
    switch (status) {
      case 'OPEN':
        return (
          <span className="inline-flex items-center gap-1 rounded-full bg-rose-50 px-2.5 py-0.5 text-xs font-semibold text-rose-700">
            <AlertCircle className="h-3 w-3" />
            OPEN
          </span>
        );
      case 'IN_PROGRESS':
        return (
          <span className="inline-flex items-center gap-1 rounded-full bg-amber-50 px-2.5 py-0.5 text-xs font-semibold text-amber-700">
            <Clock className="h-3 w-3" />
            IN PROGRESS
          </span>
        );
      case 'REATTEMPT_SCHEDULED':
        return (
          <span className="inline-flex items-center gap-1 rounded-full bg-blue-50 px-2.5 py-0.5 text-xs font-semibold text-blue-700">
            <Clock className="h-3 w-3" />
            REATTEMPT
          </span>
        );
      case 'RESOLVED_DELIVERED':
        return (
          <span className="inline-flex items-center gap-1 rounded-full bg-emerald-50 px-2.5 py-0.5 text-xs font-semibold text-emerald-700">
            <CheckCircle2 className="h-3 w-3" />
            RESCUED
          </span>
        );
      case 'RESOLVED_RTO':
        return (
          <span className="inline-flex items-center gap-1 rounded-full bg-slate-100 px-2.5 py-0.5 text-xs font-semibold text-slate-600">
            <RotateCcw className="h-3 w-3" />
            RTO
          </span>
        );
      default:
        return (
          <span className="inline-flex items-center gap-1 rounded-full bg-slate-100 px-2.5 py-0.5 text-xs font-semibold text-slate-700">
            {status}
          </span>
        );
    }
  };

  const getPriorityBadge = (priority: NDRCase['priority']) => {
    switch (priority) {
      case 'HIGH':
        return <span className="rounded bg-rose-100 px-2 py-0.5 text-[10px] font-bold text-rose-800">HIGH</span>;
      case 'MEDIUM':
        return <span className="rounded bg-amber-100 px-2 py-0.5 text-[10px] font-bold text-amber-800">MED</span>;
      default:
        return <span className="rounded bg-blue-100 px-2 py-0.5 text-[10px] font-bold text-blue-800">LOW</span>;
    }
  };

  return (
    <div className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
      <div className="overflow-x-auto">
        <table className="w-full text-left text-sm text-slate-600">
          <thead className="border-b border-slate-200 bg-slate-50/80 text-xs font-semibold uppercase tracking-wider text-slate-500">
            <tr>
              <th className="px-5 py-3.5">Case & Order</th>
              <th className="px-5 py-3.5">Customer & Phone</th>
              <th className="px-5 py-3.5">Failure Reason</th>
              <th className="px-5 py-3.5">Attempts</th>
              <th className="px-5 py-3.5">Priority</th>
              <th className="px-5 py-3.5">AI Recovery Lift</th>
              <th className="px-5 py-3.5">Status</th>
              <th className="px-5 py-3.5 text-right">Action</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {isLoading ? (
              <tr>
                <td colSpan={8} className="py-12 text-center text-slate-400">
                  Loading recovery cases...
                </td>
              </tr>
            ) : cases.length === 0 ? (
              <tr>
                <td colSpan={8} className="py-12 text-center">
                  <div className="flex flex-col items-center justify-center space-y-2 text-slate-400">
                    <Package className="h-10 w-10 text-slate-300" />
                    <p className="text-sm font-medium">No NDR cases currently in queue</p>
                    <p className="text-xs">Failed courier delivery attempts will automatically appear here for rescue</p>
                  </div>
                </td>
              </tr>
            ) : (
              cases.map((c) => (
                <tr key={c.id} className="transition hover:bg-slate-50/80">
                  <td className="px-5 py-3.5">
                    <div className="font-mono text-xs font-bold text-slate-900">{c.case_number}</div>
                    <div className="font-mono text-[11px] text-slate-500">
                      Order: {c.order_external_id || '—'}
                    </div>
                  </td>
                  <td className="px-5 py-3.5">
                    <div className="font-medium text-slate-900">{c.customer_name || '—'}</div>
                    <div className="font-mono text-xs text-slate-500">{c.customer_phone || '—'}</div>
                  </td>
                  <td className="px-5 py-3.5">
                    <span className="font-semibold text-rose-700 text-xs">{c.reason_code}</span>
                    <div className="text-[10px] text-slate-400 truncate max-w-[180px]">
                      {c.carrier_reason_raw || 'Carrier scan reported failure'}
                    </div>
                  </td>
                  <td className="px-5 py-3.5">
                    <span className="font-bold text-slate-800">{c.attempt_count}</span>
                    <span className="text-[10px] text-slate-400"> / 3</span>
                  </td>
                  <td className="px-5 py-3.5">{getPriorityBadge(c.priority)}</td>
                  <td className="px-5 py-3.5">
                    {c.expected_recovery_lift ? (
                      <div>
                        <div className="flex items-center space-x-1 font-bold text-emerald-700">
                          <TrendingUp className="h-3.5 w-3.5" />
                          <span>+₹{parseFloat(c.expected_recovery_lift).toLocaleString('en-IN', { minimumFractionDigits: 2 })}</span>
                        </div>
                        <div className="text-[10px] text-slate-500 font-medium">{c.recommended_recovery_action}</div>
                      </div>
                    ) : (
                      <span className="text-xs text-slate-400">—</span>
                    )}
                  </td>
                  <td className="px-5 py-3.5">{getStatusBadge(c.status)}</td>
                  <td className="px-5 py-3.5 text-right">
                    <button
                      type="button"
                      onClick={() => onSelectCase(c)}
                      className="inline-flex items-center space-x-1.5 rounded-lg border border-rose-200 bg-rose-50 px-2.5 py-1 text-xs font-semibold text-rose-700 shadow-sm transition hover:bg-rose-100 hover:border-rose-300"
                    >
                      <Sparkles className="h-3 w-3 text-rose-600" />
                      <span>Manage Rescue</span>
                    </button>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* Pagination Footer */}
      <div className="flex items-center justify-between border-t border-slate-200 px-5 py-3.5 text-xs text-slate-600">
        <div>
          Showing <span className="font-semibold text-slate-800">{total === 0 ? 0 : offset + 1}</span> to{' '}
          <span className="font-semibold text-slate-800">{Math.min(offset + limit, total)}</span> of{' '}
          <span className="font-semibold text-slate-800">{total}</span> NDR cases
        </div>
        <div className="flex items-center space-x-2">
          <button
            type="button"
            disabled={offset === 0 || isLoading}
            onClick={() => onPageChange(Math.max(0, offset - limit))}
            className="flex items-center space-x-1 rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 font-medium hover:bg-slate-50 disabled:opacity-40"
          >
            <ChevronLeft className="h-4 w-4" />
            <span>Previous</span>
          </button>
          <span className="px-2">
            Page {currentPage} of {totalPages}
          </span>
          <button
            type="button"
            disabled={offset + limit >= total || isLoading}
            onClick={() => onPageChange(offset + limit)}
            className="flex items-center space-x-1 rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 font-medium hover:bg-slate-50 disabled:opacity-40"
          >
            <span>Next</span>
            <ChevronRight className="h-4 w-4" />
          </button>
        </div>
      </div>
    </div>
  );
};
