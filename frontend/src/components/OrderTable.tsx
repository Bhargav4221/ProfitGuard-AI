'use client';

import React from 'react';
import {
  ChevronLeft,
  ChevronRight,
  Package,
  Clock,
  CheckCircle2,
  AlertCircle,
  Truck,
  RotateCcw,
  Ban,
  Sparkles,
  Receipt,
  Check,
  RotateCw,
} from 'lucide-react';
import { Order } from '@/types';

interface OrderTableProps {
  orders: Order[];
  total: number;
  limit: number;
  offset: number;
  onPageChange: (newOffset: number) => void;
  isLoading: boolean;
  onSelectOrder: (order: Order) => void;
  onSimulateOrder?: (order: Order) => void;
  onConfirmOrder?: (order: Order) => void;
  onResumeOrder?: (order: Order) => void;
  onReconcileOrder?: (order: Order) => void;
  onCreateOrder?: () => void;
}

export const OrderTable: React.FC<OrderTableProps> = ({
  orders,
  total,
  limit,
  offset,
  onPageChange,
  isLoading,
  onSelectOrder,
  onSimulateOrder,
  onConfirmOrder,
  onResumeOrder,
  onReconcileOrder,
  onCreateOrder,
}) => {
  const currentPage = Math.floor(offset / limit) + 1;
  const totalPages = Math.max(1, Math.ceil(total / limit));

  const getStatusBadge = (status: Order['status']) => {
    switch (status) {
      case 'DELIVERED':
        return (
          <span className="inline-flex items-center gap-1 rounded-full bg-emerald-50 px-2.5 py-0.5 text-xs font-semibold text-emerald-700">
            <CheckCircle2 className="h-3 w-3" />
            DELIVERED
          </span>
        );
      case 'NDR':
        return (
          <span className="inline-flex items-center gap-1 rounded-full bg-rose-50 px-2.5 py-0.5 text-xs font-semibold text-rose-700">
            <AlertCircle className="h-3 w-3" />
            NDR
          </span>
        );
      case 'OUT_FOR_DELIVERY':
        return (
          <span className="inline-flex items-center gap-1 rounded-full bg-amber-50 px-2.5 py-0.5 text-xs font-semibold text-amber-700">
            <Truck className="h-3 w-3" />
            OUT FOR DELIVERY
          </span>
        );
      case 'SHIPPED':
        return (
          <span className="inline-flex items-center gap-1 rounded-full bg-purple-50 px-2.5 py-0.5 text-xs font-semibold text-purple-700">
            <Truck className="h-3 w-3" />
            SHIPPED
          </span>
        );
      case 'READY_TO_SHIP':
        return (
          <span className="inline-flex items-center gap-1 rounded-full bg-indigo-50 px-2.5 py-0.5 text-xs font-semibold text-indigo-700">
            <Package className="h-3 w-3" />
            READY TO SHIP
          </span>
        );
      case 'CONFIRMED':
        return (
          <span className="inline-flex items-center gap-1 rounded-full bg-blue-50 px-2.5 py-0.5 text-xs font-semibold text-blue-700">
            <CheckCircle2 className="h-3 w-3" />
            CONFIRMED
          </span>
        );
      case 'RTO':
        return (
          <span className="inline-flex items-center gap-1 rounded-full bg-rose-100 px-2.5 py-0.5 text-xs font-semibold text-rose-800">
            <RotateCcw className="h-3 w-3" />
            RTO
          </span>
        );
      case 'HOLD':
        return (
          <span className="inline-flex items-center gap-1 rounded-full bg-amber-50 px-2.5 py-0.5 text-xs font-semibold text-amber-700">
            <AlertCircle className="h-3 w-3" />
            HOLD
          </span>
        );
      case 'CANCELLED':
        return (
          <span className="inline-flex items-center gap-1 rounded-full bg-slate-100 px-2.5 py-0.5 text-xs font-semibold text-slate-600">
            <Ban className="h-3 w-3" />
            CANCELLED
          </span>
        );
      default:
        return (
          <span className="inline-flex items-center gap-1 rounded-full bg-blue-50 px-2.5 py-0.5 text-xs font-semibold text-blue-700">
            <Clock className="h-3 w-3" />
            {status}
          </span>
        );
    }
  };

  return (
    <div className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
      <div className="overflow-x-auto">
        <table className="w-full text-left text-sm text-slate-600">
          <thead className="border-b border-slate-200 bg-slate-50/80 text-xs font-semibold uppercase tracking-wider text-slate-500">
            <tr>
              <th className="px-5 py-3.5">Order ID</th>
              <th className="px-5 py-3.5">Customer & Phone</th>
              <th className="px-5 py-3.5">Location</th>
              <th className="px-5 py-3.5">Payment</th>
              <th className="px-5 py-3.5">Original Value</th>
              <th className="px-5 py-3.5">Status</th>
              <th className="px-5 py-3.5">Channel</th>
              <th className="px-5 py-3.5">Date</th>
              <th className="px-5 py-3.5 text-right">AI Engine</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {isLoading ? (
              <tr>
                <td colSpan={9} className="py-12 text-center text-slate-400">
                  Loading orders...
                </td>
              </tr>
            ) : orders.length === 0 ? (
              <tr>
                <td colSpan={9} className="py-14 text-center">
                  <div className="flex flex-col items-center justify-center space-y-3 text-slate-500 max-w-sm mx-auto">
                    <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-slate-100 text-slate-400">
                      <Package className="h-6 w-6" />
                    </div>
                    <div>
                      <p className="text-sm font-bold text-slate-800">No orders found</p>
                      <p className="text-xs text-slate-500 mt-0.5">
                        Create an order manually, sync from Shopify, or import a CSV to evaluate pre-dispatch risk.
                      </p>
                    </div>
                    <div className="flex items-center space-x-2.5 pt-1">
                      {onCreateOrder && (
                        <button
                          type="button"
                          onClick={onCreateOrder}
                          className="rounded-lg bg-emerald-600 px-3.5 py-1.5 text-xs font-bold text-white shadow-sm hover:bg-emerald-700 transition"
                        >
                          + Create Order
                        </button>
                      )}
                    </div>
                  </div>
                </td>
              </tr>
            ) : (
              orders.map((order) => (
                <tr key={order.id} className="transition hover:bg-slate-50/80">
                  <td className="px-5 py-3.5">
                    <div className="font-mono text-sm font-bold text-slate-900">
                      {order.external_order_id}
                    </div>
                  </td>
                  <td className="px-5 py-3.5">
                    <div className="font-medium text-slate-900">{order.customer_name || '—'}</div>
                    <div className="font-mono text-xs text-slate-500">{order.customer_phone || '—'}</div>
                  </td>
                  <td className="px-5 py-3.5">
                    <div className="text-slate-800">{order.shipping_city || '—'}</div>
                    <div className="font-mono text-xs text-slate-500">
                      {order.shipping_pincode ? `PIN: ${order.shipping_pincode}` : ''}
                    </div>
                  </td>
                  <td className="px-5 py-3.5">
                    <span
                      className={`inline-block rounded px-2 py-0.5 text-xs font-bold ${
                        order.payment_method === 'COD'
                          ? 'bg-amber-100 text-amber-800'
                          : 'bg-emerald-100 text-emerald-800'
                      }`}
                    >
                      {order.payment_method}
                    </span>
                  </td>
                  <td className="px-5 py-3.5">
                    <div className="font-semibold text-slate-900">
                      ₹{parseFloat(order.order_value).toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                    </div>
                    <div className="text-[10px] text-slate-400">Immutable GMV</div>
                  </td>
                  <td className="px-5 py-3.5">
                    <div className="flex flex-col gap-1 items-start">
                      {getStatusBadge(order.status)}
                      <span className="inline-block text-[10px] font-mono px-1.5 py-0.5 rounded bg-slate-100 text-slate-600 border border-slate-200">
                        {order.fulfillment_status}
                      </span>
                    </div>
                  </td>
                  <td className="px-5 py-3.5">
                    <span className="rounded bg-slate-100 px-2 py-0.5 text-xs font-medium text-slate-700">
                      {order.source_channel}
                    </span>
                  </td>
                  <td className="px-5 py-3.5 text-xs text-slate-500">
                    {new Date(order.order_date).toLocaleDateString('en-IN', {
                      day: 'numeric',
                      month: 'short',
                      year: 'numeric',
                    })}
                  </td>
                  <td className="px-5 py-3.5 text-right">
                    <div className="inline-flex items-center space-x-1.5">
                      {order.status === 'PENDING' && onConfirmOrder && (
                        <button
                          type="button"
                          onClick={() => onConfirmOrder(order)}
                          className="inline-flex items-center space-x-1 rounded-lg border border-emerald-300 bg-emerald-50 px-2 py-1 text-xs font-bold text-emerald-800 shadow-sm transition hover:bg-emerald-100"
                          title="Confirm order to advance into delivery lifecycle"
                        >
                          <Check className="h-3 w-3 text-emerald-700" />
                          <span>Confirm</span>
                        </button>
                      )}
                      {order.status === 'HOLD' && onResumeOrder && (
                        <button
                          type="button"
                          onClick={() => onResumeOrder(order)}
                          className="inline-flex items-center space-x-1 rounded-lg border border-amber-300 bg-amber-50 px-2 py-1 text-xs font-bold text-amber-800 shadow-sm transition hover:bg-amber-100"
                          title="Release HOLD and resume order to CONFIRMED"
                        >
                          <RotateCw className="h-3 w-3 text-amber-700" />
                          <span>Resume</span>
                        </button>
                      )}
                      {onSimulateOrder && (
                        <button
                          type="button"
                          onClick={() => onSimulateOrder(order)}
                          className="inline-flex items-center space-x-1 rounded-lg border border-blue-200 bg-blue-50 px-2 py-1 text-xs font-semibold text-blue-700 shadow-sm transition hover:bg-blue-100 hover:border-blue-300"
                          title="Simulate courier delivery events"
                        >
                          <Truck className="h-3 w-3 text-blue-600" />
                          <span>Simulate</span>
                        </button>
                      )}
                      <button
                        type="button"
                        onClick={() => onSelectOrder(order)}
                        className="inline-flex items-center space-x-1 rounded-lg border border-emerald-200 bg-emerald-50 px-2 py-1 text-xs font-semibold text-emerald-700 shadow-sm transition hover:bg-emerald-100 hover:border-emerald-300"
                        title="Evaluate risk and pre-dispatch actions"
                      >
                        <Sparkles className="h-3 w-3 text-emerald-600" />
                        <span>Decide</span>
                      </button>
                      {onReconcileOrder && (
                        <button
                          type="button"
                          onClick={() => onReconcileOrder(order)}
                          className="inline-flex items-center space-x-1 rounded-lg border border-purple-200 bg-purple-50 px-2 py-1 text-xs font-semibold text-purple-700 shadow-sm transition hover:bg-purple-100 hover:border-purple-300"
                          title="View authoritative realized contribution ledger"
                        >
                          <Receipt className="h-3 w-3 text-purple-600" />
                          <span>Ledger</span>
                        </button>
                      )}
                    </div>
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
          Showing{' '}
          <span className="font-semibold text-slate-800">
            {total === 0 ? 0 : offset + 1}
          </span>{' '}
          to{' '}
          <span className="font-semibold text-slate-800">
            {Math.min(offset + limit, total)}
          </span>{' '}
          of <span className="font-semibold text-slate-800">{total}</span> orders
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
