'use client';

import React from 'react';
import { Search, Filter, RotateCcw } from 'lucide-react';

interface OrderFiltersProps {
  search: string;
  onSearchChange: (val: string) => void;
  status: string;
  onStatusChange: (val: string) => void;
  paymentMethod: string;
  onPaymentMethodChange: (val: string) => void;
  onReset: () => void;
}

export const OrderFilters: React.FC<OrderFiltersProps> = ({
  search,
  onSearchChange,
  status,
  onStatusChange,
  paymentMethod,
  onPaymentMethodChange,
  onReset,
}) => {
  return (
    <div className="flex flex-wrap items-center justify-between gap-4 rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      {/* Search Input */}
      <div className="relative min-w-[280px] flex-1">
        <Search className="absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
        <input
          type="text"
          value={search}
          onChange={(e) => onSearchChange(e.target.value)}
          placeholder="Search by Order ID, customer name, phone, or email..."
          className="w-full rounded-lg border border-slate-300 py-2 pl-10 pr-4 text-sm text-slate-800 placeholder-slate-400 focus:border-emerald-500 focus:outline-none focus:ring-1 focus:ring-emerald-500"
        />
      </div>

      {/* Dropdown Filters */}
      <div className="flex flex-wrap items-center gap-3">
        {/* Status Filter */}
        <div className="flex items-center space-x-2">
          <label className="text-xs font-semibold text-slate-500">Status:</label>
          <select
            value={status}
            onChange={(e) => onStatusChange(e.target.value)}
            className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-xs font-medium text-slate-700 focus:border-emerald-500 focus:outline-none focus:ring-1 focus:ring-emerald-500"
          >
            <option value="">All Statuses</option>
            <option value="PENDING">PENDING</option>
            <option value="CONFIRMED">CONFIRMED</option>
            <option value="HOLD">HOLD</option>
            <option value="DELIVERED">DELIVERED</option>
            <option value="RTO">RTO</option>
            <option value="CANCELLED">CANCELLED</option>
          </select>
        </div>

        {/* Payment Method Filter */}
        <div className="flex items-center space-x-2">
          <label className="text-xs font-semibold text-slate-500">Payment:</label>
          <select
            value={paymentMethod}
            onChange={(e) => onPaymentMethodChange(e.target.value)}
            className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-xs font-medium text-slate-700 focus:border-emerald-500 focus:outline-none focus:ring-1 focus:ring-emerald-500"
          >
            <option value="">All Methods</option>
            <option value="COD">Cash on Delivery (COD)</option>
            <option value="PREPAID">Prepaid</option>
          </select>
        </div>

        {/* Reset Button */}
        {(search || status || paymentMethod) && (
          <button
            type="button"
            onClick={onReset}
            className="flex items-center space-x-1 rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-xs font-semibold text-slate-600 hover:bg-slate-100"
          >
            <RotateCcw className="h-3.5 w-3.5" />
            <span>Reset</span>
          </button>
        )}
      </div>
    </div>
  );
};
