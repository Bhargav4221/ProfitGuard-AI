'use client';

import React, { useState, useEffect } from 'react';
import {
  Settings,
  ShieldCheck,
  Building,
  User,
  IndianRupee,
  Save,
  CheckCircle2,
  AlertCircle,
  RefreshCw,
  Sparkles,
  Lock,
  Layers,
  HelpCircle,
} from 'lucide-react';
import { fetchEconomics, updateEconomics } from '@/services/api';
import { MerchantEconomics } from '@/types';

interface SettingsTabProps {
  orgName: string;
  orgId: string;
  userEmail: string;
  onRerunOnboarding: () => void;
}

export const SettingsTab: React.FC<SettingsTabProps> = ({
  orgName,
  orgId,
  userEmail,
  onRerunOnboarding,
}) => {
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  // Form fields
  const [cogsPercent, setCogsPercent] = useState('30.00');
  const [forwardShipping, setForwardShipping] = useState('70.00');
  const [reverseShipping, setReverseShipping] = useState('65.00');
  const [packagingCost, setPackagingCost] = useState('20.00');
  const [codCarrierFee, setCodCarrierFee] = useState('35.00');
  const [codFeeIncurredOn, setCodFeeIncurredOn] = useState('UPON_DELIVERY_ONLY');
  const [pgPercent, setPgPercent] = useState('2.00');
  const [pgFlat, setPgFlat] = useState('3.00');
  const [inventoryDamageRate, setInventoryDamageRate] = useState('0.05');
  const [otpCost, setOtpCost] = useState('0.50');
  const [manualReviewCost, setManualReviewCost] = useState('18.00');
  const [prepaidIncentiveDiscount, setPrepaidIncentiveDiscount] = useState('50.00');
  const [prepaidCommsCost, setPrepaidCommsCost] = useState('0.50');
  const [safetyValueCap, setSafetyValueCap] = useState('3500.00');
  const [allowAutoCancel, setAllowAutoCancel] = useState(false);

  useEffect(() => {
    loadEconomics();
  }, []);

  const loadEconomics = async () => {
    setLoading(true);
    setErrorMessage(null);
    try {
      const data: MerchantEconomics = await fetchEconomics();
      if (data) {
        setCogsPercent(data.default_cogs_percent || '30.00');
        setForwardShipping(data.forward_shipping_cost || '70.00');
        setReverseShipping(data.reverse_shipping_cost || '65.00');
        setPackagingCost(data.packaging_cost || '20.00');
        setCodCarrierFee(data.cod_carrier_fee || '35.00');
        const rawPolicy = data.cod_fee_incurred_on || 'UPON_DELIVERY_ONLY';
        const normalizedPolicy =
          rawPolicy === 'DELIVERY_ATTEMPT_1' || rawPolicy === 'UPON_DISPATCH'
            ? 'UPON_MANIFEST'
            : rawPolicy === 'DELIVERED_ONLY'
            ? 'UPON_DELIVERY_ONLY'
            : rawPolicy;
        setCodFeeIncurredOn(normalizedPolicy);
        setPgPercent(data.payment_gateway_percent || '2.00');
        setPgFlat(data.payment_gateway_flat || '3.00');
        setInventoryDamageRate(data.inventory_damage_rate || '0.05');
        setOtpCost(data.otp_verification_cost || '0.50');
        setManualReviewCost(data.manual_review_cost || '18.00');
        setPrepaidIncentiveDiscount(data.prepaid_incentive_discount || '50.00');
        setPrepaidCommsCost(data.prepaid_comms_cost || '0.50');
        setSafetyValueCap(data.safety_value_cap || '3500.00');
        setAllowAutoCancel(!!data.allow_auto_cancel);
      }
    } catch (err: any) {
      setErrorMessage(err.message || 'Failed to load merchant economics.');
    } finally {
      setLoading(false);
    }
  };

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setSuccessMessage(null);
    setErrorMessage(null);
    try {
      await updateEconomics({
        default_cogs_percent: cogsPercent,
        forward_shipping_cost: forwardShipping,
        reverse_shipping_cost: reverseShipping,
        packaging_cost: packagingCost,
        cod_carrier_fee: codCarrierFee,
        cod_fee_incurred_on: codFeeIncurredOn,
        payment_gateway_percent: pgPercent,
        payment_gateway_flat: pgFlat,
        inventory_damage_rate: inventoryDamageRate,
        otp_verification_cost: otpCost,
        manual_review_cost: manualReviewCost,
        prepaid_incentive_discount: prepaidIncentiveDiscount,
        prepaid_comms_cost: prepaidCommsCost,
        safety_value_cap: safetyValueCap,
        allow_auto_cancel: allowAutoCancel,
      });
      setSuccessMessage('Merchant unit economics saved successfully. Realized contribution calculations updated.');
      setTimeout(() => setSuccessMessage(null), 5000);
    } catch (err: any) {
      setErrorMessage(err.message || 'Failed to update economics configuration.');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
          <div>
            <div className="flex items-center space-x-2">
              <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-emerald-100 text-emerald-800">
                <Settings className="h-4 w-4" />
              </span>
              <h2 className="text-lg font-bold text-slate-900">Workspace & Economics Settings</h2>
            </div>
            <p className="mt-1 text-xs text-slate-500 max-w-2xl">
              Calibrate your brand&apos;s unit economics, 3PL logistics charges, and policy guardrails to ensure mathematical fidelity across the decision engine and financial ledger.
            </p>
          </div>
          <button
            type="button"
            onClick={onRerunOnboarding}
            className="inline-flex items-center space-x-1.5 rounded-xl border border-slate-200 bg-slate-50 px-3.5 py-2 text-xs font-semibold text-slate-700 hover:bg-slate-100 transition shrink-0"
          >
            <Sparkles className="h-4 w-4 text-emerald-600" />
            <span>Launch Setup Wizard</span>
          </button>
        </div>
      </div>

      {/* Notifications */}
      {successMessage && (
        <div className="flex items-center space-x-2.5 rounded-xl border border-emerald-200 bg-emerald-50 p-4 text-xs text-emerald-800 shadow-sm">
          <CheckCircle2 className="h-4 w-4 shrink-0 text-emerald-600" />
          <span>{successMessage}</span>
        </div>
      )}

      {errorMessage && (
        <div className="flex items-center space-x-2.5 rounded-xl border border-rose-200 bg-rose-50 p-4 text-xs text-rose-800 shadow-sm">
          <AlertCircle className="h-4 w-4 shrink-0 text-rose-600" />
          <span>{errorMessage}</span>
        </div>
      )}

      {/* Organization Context Card */}
      <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
        <h3 className="text-sm font-bold text-slate-900 mb-4 flex items-center gap-2">
          <Building className="h-4 w-4 text-slate-500" />
          Organization & Tenant Context
        </h3>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 text-xs">
          <div className="p-3.5 rounded-xl bg-slate-50 border border-slate-100">
            <span className="text-[11px] text-slate-500 block mb-1">Store / Workspace Name</span>
            <span className="font-bold text-slate-900">{orgName || 'Acme D2C Store'}</span>
          </div>
          <div className="p-3.5 rounded-xl bg-slate-50 border border-slate-100">
            <span className="text-[11px] text-slate-500 block mb-1">Active User</span>
            <span className="font-bold text-slate-900 truncate block">{userEmail || 'merchant@store.com'}</span>
          </div>
          <div className="p-3.5 rounded-xl bg-slate-50 border border-slate-100">
            <span className="text-[11px] text-slate-500 block mb-1">Tenant ID</span>
            <span className="font-mono text-[10px] text-slate-700 truncate block">{orgId || 'Active Tenant'}</span>
          </div>
          <div className="p-3.5 rounded-xl bg-slate-50 border border-slate-100">
            <span className="text-[11px] text-slate-500 block mb-1">Role & Permissions</span>
            <span className="inline-flex items-center gap-1 font-bold text-emerald-700">
              <ShieldCheck className="h-3.5 w-3.5" /> Owner / Administrator
            </span>
          </div>
        </div>
      </div>

      {/* Economics Form */}
      <form onSubmit={handleSave} className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm space-y-6">
        <div className="flex items-center justify-between pb-4 border-b border-slate-200">
          <div>
            <h3 className="text-sm font-bold text-slate-900 flex items-center gap-2">
              <IndianRupee className="h-4 w-4 text-emerald-600" />
              Merchant Unit Economics Calibration
            </h3>
            <p className="text-xs text-slate-500 mt-0.5">
              Parameters utilized in Expected Contribution scoring, risk heuristics, and settled ledger reconciliation
            </p>
          </div>
          {loading && (
            <span className="flex items-center space-x-1.5 text-xs text-slate-400">
              <RefreshCw className="h-3.5 w-3.5 animate-spin" />
              <span>Loading parameters...</span>
            </span>
          )}
        </div>

        {/* Section 1: Fulfillment & Logistics */}
        <div>
          <h4 className="text-xs font-bold uppercase tracking-wider text-slate-500 mb-3">
            Fulfillment & 3PL Logistics Rates
          </h4>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">Default COGS (%)</label>
              <div className="relative">
                <input
                  type="number"
                  step="0.1"
                  required
                  value={cogsPercent}
                  onChange={(e) => setCogsPercent(e.target.value)}
                  className="w-full rounded-xl border border-slate-300 py-2 px-3 text-xs text-slate-800 focus:border-emerald-500 focus:outline-none"
                />
                <span className="absolute right-3 top-2 text-xs text-slate-400">%</span>
              </div>
              <span className="text-[10px] text-slate-400 mt-1 block">Catalog baseline product cost</span>
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">Forward Shipping Cost (₹)</label>
              <div className="relative">
                <input
                  type="number"
                  step="0.5"
                  required
                  value={forwardShipping}
                  onChange={(e) => setForwardShipping(e.target.value)}
                  className="w-full rounded-xl border border-slate-300 py-2 px-3 text-xs text-slate-800 focus:border-emerald-500 focus:outline-none"
                />
                <span className="absolute right-3 top-2 text-xs text-slate-400">₹</span>
              </div>
              <span className="text-[10px] text-slate-400 mt-1 block">Carrier freight outward charge</span>
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">Reverse Shipping / RTO Cost (₹)</label>
              <div className="relative">
                <input
                  type="number"
                  step="0.5"
                  required
                  value={reverseShipping}
                  onChange={(e) => setReverseShipping(e.target.value)}
                  className="w-full rounded-xl border border-slate-300 py-2 px-3 text-xs text-slate-800 focus:border-emerald-500 focus:outline-none"
                />
                <span className="absolute right-3 top-2 text-xs text-slate-400">₹</span>
              </div>
              <span className="text-[10px] text-slate-400 mt-1 block">Carrier return penalty on failed delivery</span>
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">Packaging Cost (₹)</label>
              <div className="relative">
                <input
                  type="number"
                  step="0.5"
                  required
                  value={packagingCost}
                  onChange={(e) => setPackagingCost(e.target.value)}
                  className="w-full rounded-xl border border-slate-300 py-2 px-3 text-xs text-slate-800 focus:border-emerald-500 focus:outline-none"
                />
                <span className="absolute right-3 top-2 text-xs text-slate-400">₹</span>
              </div>
              <span className="text-[10px] text-slate-400 mt-1 block">Boxes, flyers, labels, inserts</span>
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">COD Carrier Surcharge (₹)</label>
              <div className="relative">
                <input
                  type="number"
                  step="0.5"
                  required
                  value={codCarrierFee}
                  onChange={(e) => setCodCarrierFee(e.target.value)}
                  className="w-full rounded-xl border border-slate-300 py-2 px-3 text-xs text-slate-800 focus:border-emerald-500 focus:outline-none"
                />
                <span className="absolute right-3 top-2 text-xs text-slate-400">₹</span>
              </div>
              <span className="text-[10px] text-slate-400 mt-1 block">3PL cash collection fee</span>
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">COD Fee Incurred Trigger</label>
              <select
                value={codFeeIncurredOn}
                onChange={(e) => setCodFeeIncurredOn(e.target.value)}
                className="w-full rounded-xl border border-slate-300 py-2 px-3 text-xs text-slate-800 focus:border-emerald-500 focus:outline-none"
              >
                <option value="UPON_DELIVERY_ONLY">Upon Delivery Only (Refunded or waived if shipment RTOs)</option>
                <option value="UPON_MANIFEST">Upon Manifest (Incurred upon initial dispatch/attempt 1)</option>
              </select>
              <span className="text-[10px] text-slate-400 mt-1 block">Matches your 3PL carrier agreement</span>
            </div>
          </div>
        </div>

        {/* Section 2: Payment Gateway & Intervention Costs */}
        <div className="pt-4 border-t border-slate-200">
          <h4 className="text-xs font-bold uppercase tracking-wider text-slate-500 mb-3">
            Payment Processing & Operational Interventions
          </h4>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">Payment Gateway (%)</label>
              <div className="relative">
                <input
                  type="number"
                  step="0.05"
                  value={pgPercent}
                  onChange={(e) => setPgPercent(e.target.value)}
                  className="w-full rounded-xl border border-slate-300 py-2 px-3 text-xs text-slate-800 focus:border-emerald-500 focus:outline-none"
                />
                <span className="absolute right-3 top-2 text-xs text-slate-400">%</span>
              </div>
              <span className="text-[10px] text-slate-400 mt-1 block">e.g. Razorpay / Cashfree</span>
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">PG Flat Fee (₹)</label>
              <div className="relative">
                <input
                  type="number"
                  step="0.5"
                  value={pgFlat}
                  onChange={(e) => setPgFlat(e.target.value)}
                  className="w-full rounded-xl border border-slate-300 py-2 px-3 text-xs text-slate-800 focus:border-emerald-500 focus:outline-none"
                />
                <span className="absolute right-3 top-2 text-xs text-slate-400">₹</span>
              </div>
              <span className="text-[10px] text-slate-400 mt-1 block">Fixed fee per transaction</span>
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">OTP Verification Cost (₹)</label>
              <div className="relative">
                <input
                  type="number"
                  step="0.05"
                  value={otpCost}
                  onChange={(e) => setOtpCost(e.target.value)}
                  className="w-full rounded-xl border border-slate-300 py-2 px-3 text-xs text-slate-800 focus:border-emerald-500 focus:outline-none"
                />
                <span className="absolute right-3 top-2 text-xs text-slate-400">₹</span>
              </div>
              <span className="text-[10px] text-slate-400 mt-1 block">SMS / WhatsApp OTP cost</span>
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">Manual Review Cost (₹)</label>
              <div className="relative">
                <input
                  type="number"
                  step="0.5"
                  value={manualReviewCost}
                  onChange={(e) => setManualReviewCost(e.target.value)}
                  className="w-full rounded-xl border border-slate-300 py-2 px-3 text-xs text-slate-800 focus:border-emerald-500 focus:outline-none"
                />
                <span className="absolute right-3 top-2 text-xs text-slate-400">₹</span>
              </div>
              <span className="text-[10px] text-slate-400 mt-1 block">Operator calling overhead</span>
            </div>
          </div>
        </div>

        {/* Section 3: Policy Guardrails */}
        <div className="pt-4 border-t border-slate-200">
          <h4 className="text-xs font-bold uppercase tracking-wider text-slate-500 mb-3">
            Policy Guardrails & Auto-Action Limits
          </h4>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">Safety Value Cap (₹)</label>
              <div className="relative">
                <input
                  type="number"
                  step="100"
                  value={safetyValueCap}
                  onChange={(e) => setSafetyValueCap(e.target.value)}
                  className="w-full rounded-xl border border-slate-300 py-2 px-3 text-xs text-slate-800 focus:border-emerald-500 focus:outline-none"
                />
                <span className="absolute right-3 top-2 text-xs text-slate-400">₹</span>
              </div>
              <span className="text-[10px] text-slate-400 mt-1 block">
                Orders above this amount require manual operator sign-off before cancellation
              </span>
            </div>

            <div className="flex items-center space-x-3 pt-4">
              <input
                type="checkbox"
                id="allowAutoCancel"
                checked={allowAutoCancel}
                onChange={(e) => setAllowAutoCancel(e.target.checked)}
                className="h-4 w-4 rounded border-slate-300 text-emerald-600 focus:ring-emerald-500"
              />
              <label htmlFor="allowAutoCancel" className="text-xs font-semibold text-slate-700 cursor-pointer">
                Allow Automatic Cancellation for Proven Unrecoverable Orders
                <span className="block text-[10px] text-slate-400 font-normal mt-0.5">
                  When enabled, high-risk orders with negative EC below the safety cap can transition directly to CANCELLED.
                </span>
              </label>
            </div>
          </div>
        </div>

        {/* Save Bar */}
        <div className="pt-4 border-t border-slate-200 flex items-center justify-end">
          <button
            type="submit"
            disabled={saving}
            className="flex items-center space-x-2 rounded-xl bg-emerald-600 px-5 py-2.5 text-xs font-bold text-white shadow-sm hover:bg-emerald-700 transition disabled:opacity-50"
          >
            {saving ? (
              <>
                <RefreshCw className="h-4 w-4 animate-spin" />
                <span>Updating Economics...</span>
              </>
            ) : (
              <>
                <Save className="h-4 w-4" />
                <span>Save Unit Economics</span>
              </>
            )}
          </button>
        </div>
      </form>
    </div>
  );
};
