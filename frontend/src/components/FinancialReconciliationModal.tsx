'use client';

import React, { useState, useEffect } from 'react';
import {
  X,
  Receipt,
  CheckCircle2,
  AlertCircle,
  HelpCircle,
  ShieldCheck,
  TrendingUp,
  RefreshCw,
  Clock,
  ArrowRight,
} from 'lucide-react';
import { Order, FinancialReconciliation } from '@/types';
import { fetchOrderReconciliation, reconcileOrder } from '@/services/api';

interface FinancialReconciliationModalProps {
  order: Order | null;
  isOpen: boolean;
  onClose: () => void;
}

export const FinancialReconciliationModal: React.FC<FinancialReconciliationModalProps> = ({
  order,
  isOpen,
  onClose,
}) => {
  const [reconciliation, setReconciliation] = useState<FinancialReconciliation | null>(null);
  const [loading, setLoading] = useState<boolean>(false);
  const [actionLoading, setActionLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (isOpen && order) {
      loadReconciliation();
    } else {
      setReconciliation(null);
      setError(null);
    }
  }, [isOpen, order]);

  const loadReconciliation = async () => {
    if (!order) return;
    setLoading(true);
    setError(null);
    try {
      const data = await fetchOrderReconciliation(order.id);
      setReconciliation(data);
    } catch (err: any) {
      // If 404, we can auto-trigger initial reconciliation
      handleReconcileNow();
    } finally {
      setLoading(false);
    }
  };

  const handleReconcileNow = async () => {
    if (!order) return;
    setActionLoading(true);
    setError(null);
    try {
      const settled = await reconcileOrder(order.id, 'User initiated reconciliation in dashboard');
      setReconciliation(settled);
    } catch (err: any) {
      setError(err.message || 'Failed to settle financial reconciliation');
    } finally {
      setActionLoading(false);
    }
  };

  if (!isOpen || !order) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/60 p-4 backdrop-blur-sm">
      <div className="relative w-full max-w-3xl max-h-[90vh] flex flex-col rounded-2xl bg-white shadow-2xl border border-slate-200 overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-slate-100 bg-slate-50/80 px-6 py-4">
          <div className="flex items-center space-x-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-purple-100 text-purple-700">
              <Receipt className="h-5 w-5" />
            </div>
            <div>
              <div className="flex items-center space-x-2">
                <h2 className="text-lg font-bold text-slate-900">Financial Reconciliation Ledger</h2>
                <span className="rounded-full bg-slate-200/70 px-2.5 py-0.5 text-xs font-semibold text-slate-800">
                  {order.external_order_id}
                </span>
                {reconciliation?.is_simulated && (
                  <span className="rounded-full bg-amber-100 border border-amber-300 px-2 py-0.5 text-[10px] font-bold text-amber-800 uppercase tracking-wider">
                    [SIMULATED]
                  </span>
                )}
              </div>
              <p className="text-xs text-slate-500">
                Authoritative unit economics, zero double-counting accounting ledger
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="rounded-lg p-2 text-slate-400 hover:bg-slate-200/60 hover:text-slate-600 transition"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Content Body */}
        <div className="overflow-y-auto p-6 space-y-6">
          {error && (
            <div className="flex items-center space-x-2 rounded-xl bg-rose-50 border border-rose-200 p-3.5 text-xs text-rose-700">
              <AlertCircle className="h-4 w-4 shrink-0 text-rose-500" />
              <span>{error}</span>
            </div>
          )}

          {loading ? (
            <div className="flex flex-col items-center justify-center py-16 space-y-3">
              <RefreshCw className="h-8 w-8 animate-spin text-purple-600" />
              <p className="text-sm font-medium text-slate-600">Calculating realized contribution ledger...</p>
            </div>
          ) : reconciliation ? (
            <>
              {/* Summary Metrics Cards */}
              <div className="grid grid-cols-4 gap-3">
                <div className="rounded-xl border border-slate-200 bg-slate-50 p-3.5">
                  <p className="text-[11px] font-medium text-slate-500 uppercase tracking-wider">Order Value (GMV)</p>
                  <p className="text-lg font-bold text-slate-900 mt-1">₹{reconciliation.order_value}</p>
                  <p className="text-[10px] text-slate-500 mt-0.5">Immutable checkout value</p>
                </div>
                <div className="rounded-xl border border-slate-200 bg-slate-50 p-3.5">
                  <p className="text-[11px] font-medium text-slate-500 uppercase tracking-wider">Collected Revenue</p>
                  <p className="text-lg font-bold text-slate-900 mt-1">₹{reconciliation.collected_revenue}</p>
                  <p className="text-[10px] text-slate-500 mt-0.5">Actual cash collected</p>
                </div>
                <div className="rounded-xl border border-slate-200 bg-slate-50 p-3.5">
                  <p className="text-[11px] font-medium text-slate-500 uppercase tracking-wider">Total Expenses</p>
                  <p className="text-lg font-bold text-rose-700 mt-1">-₹{reconciliation.total_expenses}</p>
                  <p className="text-[10px] text-slate-500 mt-0.5">Direct + intervention costs</p>
                </div>
                <div className="rounded-xl border border-emerald-200 bg-emerald-50/80 p-3.5">
                  <p className="text-[11px] font-medium text-emerald-800 uppercase tracking-wider">Realized Contribution (RC)</p>
                  <p className="text-lg font-bold text-emerald-700 mt-1">₹{reconciliation.realized_contribution}</p>
                  <p className="text-[10px] text-emerald-600 mt-0.5 font-medium">Authoritative net margin</p>
                </div>
              </div>

              {/* Status and Timestamp Banner */}
              <div className="flex items-center justify-between rounded-xl bg-purple-50/70 border border-purple-200 px-4 py-2.5 text-xs text-purple-900">
                <div className="flex items-center space-x-2">
                  <ShieldCheck className="h-4 w-4 text-purple-700" />
                  <span>
                    Status: <strong className="font-semibold uppercase">{reconciliation.reconciliation_status}</strong>
                  </span>
                  <span className="text-purple-400">•</span>
                  <span>
                    Reconciled At: <strong className="font-semibold">{new Date(reconciliation.reconciled_at).toLocaleString('en-IN')}</strong>
                  </span>
                </div>
                {reconciliation.contribution_variance && (
                  <div className="flex items-center space-x-1 font-semibold text-purple-800">
                    <span>Variance vs EC:</span>
                    <span className={Number(reconciliation.contribution_variance) >= 0 ? 'text-emerald-700' : 'text-rose-700'}>
                      {Number(reconciliation.contribution_variance) >= 0 ? '+' : ''}₹{reconciliation.contribution_variance}
                    </span>
                  </div>
                )}
              </div>

              {/* Detailed Itemized Ledger Table */}
              <div className="rounded-xl border border-slate-200 overflow-hidden">
                <div className="bg-slate-100/80 px-4 py-2 border-b border-slate-200 font-semibold text-xs text-slate-700 uppercase tracking-wider">
                  Itemized Financial Accounting Ledger
                </div>
                <table className="w-full text-xs text-left">
                  <thead className="bg-slate-50 text-slate-500 border-b border-slate-200">
                    <tr>
                      <th className="py-2.5 px-4 font-semibold">Ledger Component</th>
                      <th className="py-2.5 px-4 font-semibold">Cost Policy & Rule</th>
                      <th className="py-2.5 px-4 text-right font-semibold">Amount</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100 text-slate-700">
                    <tr className="hover:bg-slate-50/50">
                      <td className="py-2.5 px-4 font-medium text-slate-900">Collected Revenue</td>
                      <td className="py-2.5 px-4 text-slate-500">Delivered COD/Prepaid cash collection (₹0 if RTO/Cancelled)</td>
                      <td className="py-2.5 px-4 text-right font-bold text-emerald-600">₹{reconciliation.collected_revenue}</td>
                    </tr>
                    <tr className="hover:bg-slate-50/50">
                      <td className="py-2.5 px-4 font-medium text-slate-900">Cost of Goods Sold (COGS)</td>
                      <td className="py-2.5 px-4 text-slate-500">Unit manufacturing/procurement cost of delivered items</td>
                      <td className="py-2.5 px-4 text-right font-semibold text-rose-600">-₹{reconciliation.cogs}</td>
                    </tr>
                    <tr className="hover:bg-slate-50/50">
                      <td className="py-2.5 px-4 font-medium text-slate-900">Forward Shipping Cost (S_f)</td>
                      <td className="py-2.5 px-4 text-slate-500">Sunk immediately upon courier manifest/dispatch</td>
                      <td className="py-2.5 px-4 text-right font-semibold text-rose-600">-₹{reconciliation.forward_shipping_cost}</td>
                    </tr>
                    <tr className="hover:bg-slate-50/50">
                      <td className="py-2.5 px-4 font-medium text-slate-900">Reverse Shipping Cost (S_r)</td>
                      <td className="py-2.5 px-4 text-slate-500">
                        {Number(reconciliation.reverse_shipping_cost) === 0
                          ? 'Avoided on successful delivery (₹0.00)'
                          : 'Incurred return transit fee upon physical carrier receipt'}
                      </td>
                      <td className="py-2.5 px-4 text-right font-semibold text-rose-600">
                        -₹{reconciliation.reverse_shipping_cost}
                      </td>
                    </tr>
                    <tr className="hover:bg-slate-50/50">
                      <td className="py-2.5 px-4 font-medium text-slate-900">Payment & Gateway Fees</td>
                      <td className="py-2.5 px-4 text-slate-500">COD collection fee or Prepaid gateway MDR</td>
                      <td className="py-2.5 px-4 text-right font-semibold text-rose-600">-₹{reconciliation.payment_fee}</td>
                    </tr>
                    <tr className="hover:bg-slate-50/50">
                      <td className="py-2.5 px-4 font-medium text-slate-900">Packaging & Pick/Pack</td>
                      <td className="py-2.5 px-4 text-slate-500">Materials and warehouse fulfillment per order</td>
                      <td className="py-2.5 px-4 text-right font-semibold text-rose-600">-₹{reconciliation.packaging_cost}</td>
                    </tr>
                    <tr className="hover:bg-slate-50/50">
                      <td className="py-2.5 px-4 font-medium text-slate-900">Inventory Impairment / Damage</td>
                      <td className="py-2.5 px-4 text-slate-500">Confirmed damage loss during return transit (₹0 if delivered)</td>
                      <td className="py-2.5 px-4 text-right font-semibold text-rose-600">-₹{reconciliation.inventory_damage_cost}</td>
                    </tr>
                    <tr className="hover:bg-slate-50/50">
                      <td className="py-2.5 px-4 font-medium text-slate-900">Pre-Dispatch Intervention Cost</td>
                      <td className="py-2.5 px-4 text-slate-500">Automated OTP SMS/WhatsApp/Call verification fee</td>
                      <td className="py-2.5 px-4 text-right font-semibold text-rose-600">-₹{reconciliation.pre_dispatch_intervention_cost}</td>
                    </tr>
                    <tr className="hover:bg-slate-50/50">
                      <td className="py-2.5 px-4 font-medium text-slate-900">NDR Delivery Recovery Cost</td>
                      <td className="py-2.5 px-4 text-slate-500">Failed delivery customer outreach and reattempt booking</td>
                      <td className="py-2.5 px-4 text-right font-semibold text-rose-600">-₹{reconciliation.ndr_recovery_intervention_cost}</td>
                    </tr>
                    <tr className="bg-slate-100/90 font-bold text-slate-900 border-t-2 border-slate-300">
                      <td className="py-3 px-4 text-sm" colSpan={2}>
                        Authoritative Realized Contribution (RC)
                      </td>
                      <td className="py-3 px-4 text-right text-sm text-emerald-700">
                        ₹{reconciliation.realized_contribution}
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>

              {/* Zero Double-Counting Guarantee Callout */}
              <div className="rounded-xl border border-blue-200 bg-blue-50/70 p-4 text-xs text-blue-900 space-y-1.5">
                <div className="flex items-center space-x-2 font-bold text-blue-950">
                  <ShieldCheck className="h-4 w-4 text-blue-700" />
                  <span>Zero Double-Counting Guarantee</span>
                </div>
                <p className="text-blue-800 leading-relaxed font-mono text-[11px]">
                  RC = Collected Revenue − COGS − S_f − S_r − Payment_Fee − Packaging − Damage − PreDispatch_Cost − NDR_Cost
                </p>
                <p className="text-slate-600 leading-relaxed">
                  {reconciliation.accounting_convention}
                </p>
              </div>
            </>
          ) : (
            <div className="text-center py-12">
              <p className="text-sm text-slate-600">No reconciliation record found.</p>
              <button
                onClick={handleReconcileNow}
                disabled={actionLoading}
                className="mt-3 inline-flex items-center space-x-1.5 rounded-lg bg-purple-600 px-4 py-2 text-xs font-semibold text-white hover:bg-purple-700 transition"
              >
                {actionLoading && <RefreshCw className="h-3.5 w-3.5 animate-spin" />}
                <span>Settle Ledger Now</span>
              </button>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between border-t border-slate-100 bg-slate-50/80 px-6 py-3.5">
          <button
            onClick={handleReconcileNow}
            disabled={actionLoading || loading}
            className="inline-flex items-center space-x-1.5 rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-xs font-semibold text-slate-700 shadow-sm hover:bg-slate-50 transition disabled:opacity-50"
          >
            <RefreshCw className={`h-3.5 w-3.5 ${actionLoading ? 'animate-spin' : ''}`} />
            <span>Re-settle & Recalculate</span>
          </button>
          <button
            onClick={onClose}
            className="rounded-lg bg-slate-900 px-4 py-1.5 text-xs font-semibold text-white shadow-sm hover:bg-slate-800 transition"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
};
