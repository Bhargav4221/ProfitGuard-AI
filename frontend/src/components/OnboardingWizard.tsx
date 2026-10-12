'use client';

import React, { useState } from 'react';
import {
  ShieldCheck,
  Building,
  TrendingUp,
  Truck,
  FileSpreadsheet,
  Webhook,
  CheckCircle2,
  ArrowRight,
  ArrowLeft,
  Settings,
  HelpCircle,
  IndianRupee,
  Package,
  Layers,
  X,
  AlertCircle,
} from 'lucide-react';
import { updateEconomics } from '@/services/api';

interface OnboardingWizardProps {
  orgName: string;
  orgId: string;
  onComplete: () => void;
  onClose?: () => void;
  onOpenCSVImport?: () => void;
  onOpenCreateOrder?: () => void;
}

export const OnboardingWizard: React.FC<OnboardingWizardProps> = ({
  orgName,
  orgId,
  onComplete,
  onClose,
  onOpenCSVImport,
  onOpenCreateOrder,
}) => {
  const [step, setStep] = useState<1 | 2 | 3 | 4>(1);

  // Step 1: Store & Carriers
  const [storeName, setStoreName] = useState(orgName || 'My D2C Store');
  const [selectedCarriers, setSelectedCarriers] = useState<string[]>(['Delhivery', 'Blue Dart']);

  // Step 2: Unit Economics
  const [cogsPercent, setCogsPercent] = useState('35.00');
  const [forwardShipping, setForwardShipping] = useState('70.00');
  const [reverseShipping, setReverseShipping] = useState('75.00');
  const [packagingCost, setPackagingCost] = useState('20.00');
  const [codCarrierFee, setCodCarrierFee] = useState('40.00');
  const [codFeeIncurredOn, setCodFeeIncurredOn] = useState('UPON_DELIVERY_ONLY');
  const [isSavingEconomics, setIsSavingEconomics] = useState(false);
  const [economicsSaved, setEconomicsSaved] = useState(false);
  const [economicsError, setEconomicsError] = useState<string | null>(null);

  // Step 3: Ingestion Preference
  const [preferredIngestion, setPreferredIngestion] = useState<'CSV' | 'WEBHOOK' | 'MANUAL'>('CSV');

  const toggleCarrier = (carrier: string) => {
    setSelectedCarriers((prev) =>
      prev.includes(carrier) ? prev.filter((c) => c !== carrier) : [...prev, carrier]
    );
  };

  const handleSaveEconomics = async () => {
    setIsSavingEconomics(true);
    setEconomicsError(null);
    try {
      await updateEconomics({
        default_cogs_percent: cogsPercent,
        forward_shipping_cost: forwardShipping,
        reverse_shipping_cost: reverseShipping,
        packaging_cost: packagingCost,
        cod_carrier_fee: codCarrierFee,
        cod_fee_incurred_on: codFeeIncurredOn,
      });
      setEconomicsSaved(true);
      setStep(3);
    } catch (err: any) {
      setEconomicsError(err.message || 'Could not save unit economics. You can configure them later in Settings.');
      // Allow proceeding even if network fails
      setStep(3);
    } finally {
      setIsSavingEconomics(false);
    }
  };

  const handleFinish = () => {
    if (typeof window !== 'undefined' && orgId) {
      localStorage.setItem(`profitguard_onboarding_completed_${orgId}`, 'true');
    }
    onComplete();
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/80 backdrop-blur-sm p-4">
      <div className="relative w-full max-w-2xl rounded-2xl border border-slate-800 bg-slate-900 text-slate-100 shadow-2xl overflow-hidden flex flex-col max-h-[90vh]">
        {/* Header */}
        <div className="px-6 py-5 border-b border-slate-800 flex items-center justify-between bg-slate-900/80">
          <div className="flex items-center space-x-3">
            <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-emerald-500 text-slate-950 font-bold">
              <ShieldCheck className="h-5 w-5" />
            </div>
            <div>
              <h2 className="text-base font-bold text-white leading-tight">Merchant Onboarding Setup</h2>
              <p className="text-xs text-slate-400">Configure your store economics and order protection pipeline</p>
            </div>
          </div>
          {onClose && (
            <button
              onClick={onClose}
              className="text-slate-400 hover:text-white p-1 rounded-lg hover:bg-slate-800 transition"
            >
              <X className="h-5 w-5" />
            </button>
          )}
        </div>

        {/* Step Progress Indicators */}
        <div className="px-6 py-3 border-b border-slate-800 bg-slate-950/40 flex items-center justify-between text-xs">
          {[
            { num: 1, title: 'Store & 3PLs' },
            { num: 2, title: 'Unit Economics' },
            { num: 3, title: 'Order Ingestion' },
            { num: 4, title: 'Command Center' },
          ].map((item) => (
            <div
              key={item.num}
              className={`flex items-center space-x-2 ${
                step === item.num
                  ? 'text-emerald-400 font-bold'
                  : step > item.num
                  ? 'text-slate-300'
                  : 'text-slate-500'
              }`}
            >
              <div
                className={`flex h-5 w-5 items-center justify-center rounded-full text-[11px] font-bold ${
                  step === item.num
                    ? 'bg-emerald-500 text-slate-950'
                    : step > item.num
                    ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/40'
                    : 'bg-slate-800 text-slate-400'
                }`}
              >
                {step > item.num ? '✓' : item.num}
              </div>
              <span className="hidden sm:inline">{item.title}</span>
            </div>
          ))}
        </div>

        {/* Content Body */}
        <div className="p-6 overflow-y-auto flex-1">
          {step === 1 && (
            <div className="space-y-6">
              <div>
                <label className="block text-xs font-semibold text-slate-300 mb-1.5">
                  Store / Brand Name
                </label>
                <div className="relative">
                  <Building className="absolute left-3.5 top-3 h-4 w-4 text-slate-500" />
                  <input
                    type="text"
                    value={storeName}
                    onChange={(e) => setStoreName(e.target.value)}
                    className="w-full rounded-xl border border-slate-700 bg-slate-800/80 py-2.5 pl-10 pr-3.5 text-xs text-white placeholder-slate-500 focus:border-emerald-500 focus:outline-none"
                    placeholder="Acme D2C Lifestyle"
                  />
                </div>
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-300 mb-2">
                  Select Primary Courier & Logistics Partners
                </label>
                <p className="text-[11px] text-slate-400 mb-3">
                  ProfitGuard normalizes tracking states across major Indian 3PLs and warehouse systems.
                </p>
                <div className="grid grid-cols-2 sm:grid-cols-3 gap-2.5">
                  {['Delhivery', 'Blue Dart', 'Xpressbees', 'Shadowfax', 'DTDC', 'Ekart'].map((carrier) => {
                    const isSelected = selectedCarriers.includes(carrier);
                    return (
                      <button
                        type="button"
                        key={carrier}
                        onClick={() => toggleCarrier(carrier)}
                        className={`flex items-center justify-between p-3 rounded-xl border text-xs font-medium transition ${
                          isSelected
                            ? 'border-emerald-500/60 bg-emerald-500/10 text-emerald-300'
                            : 'border-slate-800 bg-slate-800/50 text-slate-400 hover:border-slate-700 hover:text-slate-200'
                        }`}
                      >
                        <span>{carrier}</span>
                        {isSelected && <CheckCircle2 className="h-4 w-4 text-emerald-400" />}
                      </button>
                    );
                  })}
                </div>
              </div>

              <div className="rounded-xl border border-slate-800 bg-slate-950 p-4 text-xs text-slate-400">
                <span className="font-semibold text-slate-300 block mb-1">Currency & Regional Standard</span>
                Defaulting to Indian Rupee (INR ₹), 6-digit postal pincode validation, and standard Indian COD lifecycle states.
              </div>
            </div>
          )}

          {step === 2 && (
            <div className="space-y-5">
              <div className="rounded-xl border border-emerald-500/20 bg-emerald-500/5 p-3.5 text-xs text-emerald-300">
                <span className="font-bold block mb-0.5">Empirical Margin Calibration</span>
                These rate cards power the 5-Action Decision Engine and Settled Contribution Ledger.
              </div>

              {economicsError && (
                <div className="flex items-center space-x-2 rounded-xl border border-rose-500/40 bg-rose-500/10 p-3 text-xs text-rose-300">
                  <AlertCircle className="h-4 w-4 shrink-0 text-rose-400" />
                  <span>{economicsError}</span>
                </div>
              )}

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div>
                  <label className="block text-xs font-semibold text-slate-300 mb-1">
                    Default Product COGS (%)
                  </label>
                  <div className="relative">
                    <input
                      type="number"
                      step="0.1"
                      value={cogsPercent}
                      onChange={(e) => setCogsPercent(e.target.value)}
                      className="w-full rounded-xl border border-slate-700 bg-slate-800/80 py-2 px-3 text-xs text-white focus:border-emerald-500 focus:outline-none"
                    />
                    <span className="absolute right-3 top-2 text-xs text-slate-400">%</span>
                  </div>
                  <span className="text-[10px] text-slate-500 mt-1 block">Catalog baseline product cost</span>
                </div>

                <div>
                  <label className="block text-xs font-semibold text-slate-300 mb-1">
                    Forward Shipping Cost (₹)
                  </label>
                  <div className="relative">
                    <input
                      type="number"
                      step="1"
                      value={forwardShipping}
                      onChange={(e) => setForwardShipping(e.target.value)}
                      className="w-full rounded-xl border border-slate-700 bg-slate-800/80 py-2 px-3 text-xs text-white focus:border-emerald-500 focus:outline-none"
                    />
                    <span className="absolute right-3 top-2 text-xs text-slate-400">₹</span>
                  </div>
                  <span className="text-[10px] text-slate-500 mt-1 block">Carrier fee per outward shipment</span>
                </div>

                <div>
                  <label className="block text-xs font-semibold text-slate-300 mb-1">
                    Reverse Shipping (RTO) Cost (₹)
                  </label>
                  <div className="relative">
                    <input
                      type="number"
                      step="1"
                      value={reverseShipping}
                      onChange={(e) => setReverseShipping(e.target.value)}
                      className="w-full rounded-xl border border-slate-700 bg-slate-800/80 py-2 px-3 text-xs text-white focus:border-emerald-500 focus:outline-none"
                    />
                    <span className="absolute right-3 top-2 text-xs text-slate-400">₹</span>
                  </div>
                  <span className="text-[10px] text-slate-500 mt-1 block">Penalty charged on undelivered returns</span>
                </div>

                <div>
                  <label className="block text-xs font-semibold text-slate-300 mb-1">
                    Packaging & Box Cost (₹)
                  </label>
                  <div className="relative">
                    <input
                      type="number"
                      step="1"
                      value={packagingCost}
                      onChange={(e) => setPackagingCost(e.target.value)}
                      className="w-full rounded-xl border border-slate-700 bg-slate-800/80 py-2 px-3 text-xs text-white focus:border-emerald-500 focus:outline-none"
                    />
                    <span className="absolute right-3 top-2 text-xs text-slate-400">₹</span>
                  </div>
                  <span className="text-[10px] text-slate-500 mt-1 block">Corrugated box, flyer & inserts</span>
                </div>

                <div>
                  <label className="block text-xs font-semibold text-slate-300 mb-1">
                    COD Carrier Handling Surcharge (₹)
                  </label>
                  <div className="relative">
                    <input
                      type="number"
                      step="1"
                      value={codCarrierFee}
                      onChange={(e) => setCodCarrierFee(e.target.value)}
                      className="w-full rounded-xl border border-slate-700 bg-slate-800/80 py-2 px-3 text-xs text-white focus:border-emerald-500 focus:outline-none"
                    />
                    <span className="absolute right-3 top-2 text-xs text-slate-400">₹</span>
                  </div>
                  <span className="text-[10px] text-slate-500 mt-1 block">Cash handling surcharge from courier</span>
                </div>

                <div>
                  <label className="block text-xs font-semibold text-slate-300 mb-1">
                    COD Fee Incurred On
                  </label>
                  <select
                    value={codFeeIncurredOn}
                    onChange={(e) => setCodFeeIncurredOn(e.target.value)}
                    className="w-full rounded-xl border border-slate-700 bg-slate-800/80 py-2 px-3 text-xs text-white focus:border-emerald-500 focus:outline-none"
                  >
                    <option value="UPON_DELIVERY_ONLY">Upon Delivery Only (Refunded or waived if RTO)</option>
                    <option value="UPON_MANIFEST">Upon Manifest (Charged upon dispatch/attempt 1)</option>
                  </select>
                  <span className="text-[10px] text-slate-500 mt-1 block">Matches your 3PL carrier agreement</span>
                </div>
              </div>
            </div>
          )}

          {step === 3 && (
            <div className="space-y-4">
              <p className="text-xs text-slate-300">
                Choose how your store will stream incoming customer orders into ProfitGuard:
              </p>

              <div className="space-y-3">
                <div
                  onClick={() => setPreferredIngestion('CSV')}
                  className={`p-4 rounded-xl border cursor-pointer transition ${
                    preferredIngestion === 'CSV'
                      ? 'border-emerald-500 bg-emerald-500/10'
                      : 'border-slate-800 bg-slate-800/40 hover:border-slate-700'
                  }`}
                >
                  <div className="flex items-center justify-between mb-1.5">
                    <span className="text-xs font-bold text-white flex items-center gap-2">
                      <FileSpreadsheet className="h-4 w-4 text-emerald-400" />
                      2-Stage CSV Bulk Ingestion (Recommended)
                    </span>
                    <span className="text-[10px] uppercase font-bold text-emerald-400 bg-emerald-500/20 px-2 py-0.5 rounded">
                      Production Ready
                    </span>
                  </div>
                  <p className="text-[11px] text-slate-400">
                    Upload batches from your Shopify, WooCommerce, or warehouse CSV exports. Previews validation errors before committing to the database.
                  </p>
                </div>

                <div
                  onClick={() => setPreferredIngestion('WEBHOOK')}
                  className={`p-4 rounded-xl border cursor-pointer transition ${
                    preferredIngestion === 'WEBHOOK'
                      ? 'border-emerald-500 bg-emerald-500/10'
                      : 'border-slate-800 bg-slate-800/40 hover:border-slate-700'
                  }`}
                >
                  <div className="flex items-center justify-between mb-1.5">
                    <span className="text-xs font-bold text-white flex items-center gap-2">
                      <Webhook className="h-4 w-4 text-emerald-400" />
                      REST API & Automated Webhooks
                    </span>
                    <span className="text-[10px] uppercase font-bold text-emerald-400 bg-emerald-500/20 px-2 py-0.5 rounded">
                      Production Ready
                    </span>
                  </div>
                  <p className="text-[11px] text-slate-400">
                    Push orders automatically at checkout via <code>POST /api/v1/orders/webhook</code>. Includes HMAC signature verification.
                  </p>
                </div>

                <div
                  onClick={() => setPreferredIngestion('MANUAL')}
                  className={`p-4 rounded-xl border cursor-pointer transition ${
                    preferredIngestion === 'MANUAL'
                      ? 'border-emerald-500 bg-emerald-500/10'
                      : 'border-slate-800 bg-slate-800/40 hover:border-slate-700'
                  }`}
                >
                  <div className="flex items-center justify-between mb-1.5">
                    <span className="text-xs font-bold text-white flex items-center gap-2">
                      <Package className="h-4 w-4 text-emerald-400" />
                      Single Order Manual Creation
                    </span>
                    <span className="text-[10px] uppercase font-bold text-slate-400 bg-slate-800 px-2 py-0.5 rounded">
                      Direct Entry & Operations
                    </span>
                  </div>
                  <p className="text-[11px] text-slate-400">
                    Create individual customer orders manually from the dashboard to evaluate pre-dispatch risk and trigger recovery interventions.
                  </p>
                </div>
              </div>
            </div>
          )}

          {step === 4 && (
            <div className="space-y-6 text-center py-4">
              <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-2xl bg-emerald-500/10 text-emerald-400 border border-emerald-500/30">
                <CheckCircle2 className="h-8 w-8" />
              </div>

              <div>
                <h3 className="text-lg font-bold text-white">Your Workspace is Configured & Protected</h3>
                <p className="text-xs text-slate-400 max-w-md mx-auto mt-1">
                  ProfitGuard AI is calibrated with your store economics. Every incoming order will be scored against real contribution profit.
                </p>
              </div>

              <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 text-left max-w-lg mx-auto">
                <div className="p-3 rounded-xl bg-slate-800/60 border border-slate-700/60">
                  <span className="text-[10px] text-slate-400 block">COGS Baseline</span>
                  <span className="text-xs font-bold text-white">{cogsPercent}%</span>
                </div>
                <div className="p-3 rounded-xl bg-slate-800/60 border border-slate-700/60">
                  <span className="text-[10px] text-slate-400 block">Forward Freight</span>
                  <span className="text-xs font-bold text-white">₹{forwardShipping}</span>
                </div>
                <div className="p-3 rounded-xl bg-slate-800/60 border border-slate-700/60">
                  <span className="text-[10px] text-slate-400 block">RTO Penalty</span>
                  <span className="text-xs font-bold text-rose-400">₹{reverseShipping}</span>
                </div>
                <div className="p-3 rounded-xl bg-slate-800/60 border border-slate-700/60">
                  <span className="text-[10px] text-slate-400 block">Packaging</span>
                  <span className="text-xs font-bold text-white">₹{packagingCost}</span>
                </div>
                <div className="p-3 rounded-xl bg-slate-800/60 border border-slate-700/60">
                  <span className="text-[10px] text-slate-400 block">COD Surcharge</span>
                  <span className="text-xs font-bold text-amber-400">₹{codCarrierFee}</span>
                </div>
                <div className="p-3 rounded-xl bg-slate-800/60 border border-slate-700/60">
                  <span className="text-[10px] text-slate-400 block">Policy Guards</span>
                  <span className="text-xs font-bold text-emerald-400">Active</span>
                </div>
              </div>

              <div className="flex flex-col sm:flex-row items-center justify-center gap-3 pt-2">
                {preferredIngestion === 'CSV' && onOpenCSVImport && (
                  <button
                    onClick={() => {
                      handleFinish();
                      onOpenCSVImport();
                    }}
                    className="w-full sm:w-auto flex items-center justify-center space-x-1.5 rounded-xl border border-emerald-500/40 bg-emerald-500/10 px-4 py-2.5 text-xs font-bold text-emerald-300 hover:bg-emerald-500/20 transition"
                  >
                    <FileSpreadsheet className="h-4 w-4" />
                    <span>Import First CSV Batch</span>
                  </button>
                )}
                {preferredIngestion === 'MANUAL' && onOpenCreateOrder && (
                  <button
                    onClick={() => {
                      handleFinish();
                      onOpenCreateOrder();
                    }}
                    className="w-full sm:w-auto flex items-center justify-center space-x-1.5 rounded-xl border border-emerald-500/40 bg-emerald-500/10 px-4 py-2.5 text-xs font-bold text-emerald-300 hover:bg-emerald-500/20 transition"
                  >
                    <Package className="h-4 w-4" />
                    <span>Create First Order</span>
                  </button>
                )}
              </div>
            </div>
          )}
        </div>

        {/* Footer Navigation */}
        <div className="px-6 py-4 border-t border-slate-800 bg-slate-900/90 flex items-center justify-between">
          <div>
            {step > 1 && (
              <button
                type="button"
                onClick={() => setStep((prev) => (prev - 1) as any)}
                className="flex items-center space-x-1 text-xs font-semibold text-slate-400 hover:text-white transition"
              >
                <ArrowLeft className="h-3.5 w-3.5" />
                <span>Back</span>
              </button>
            )}
          </div>

          <div className="flex items-center space-x-3">
            {step === 1 && (
              <button
                type="button"
                onClick={() => setStep(2)}
                className="flex items-center space-x-1.5 rounded-xl bg-emerald-500 px-4 py-2 text-xs font-bold text-slate-950 hover:bg-emerald-400 transition"
              >
                <span>Continue to Unit Economics</span>
                <ArrowRight className="h-3.5 w-3.5" />
              </button>
            )}

            {step === 2 && (
              <button
                type="button"
                disabled={isSavingEconomics}
                onClick={handleSaveEconomics}
                className="flex items-center space-x-1.5 rounded-xl bg-emerald-500 px-4 py-2 text-xs font-bold text-slate-950 hover:bg-emerald-400 transition disabled:opacity-50"
              >
                <span>{isSavingEconomics ? 'Saving Economics...' : 'Save & Configure Ingestion'}</span>
                <ArrowRight className="h-3.5 w-3.5" />
              </button>
            )}

            {step === 3 && (
              <button
                type="button"
                onClick={() => setStep(4)}
                className="flex items-center space-x-1.5 rounded-xl bg-emerald-500 px-4 py-2 text-xs font-bold text-slate-950 hover:bg-emerald-400 transition"
              >
                <span>Review & Launch</span>
                <ArrowRight className="h-3.5 w-3.5" />
              </button>
            )}

            {step === 4 && (
              <button
                type="button"
                onClick={handleFinish}
                className="flex items-center space-x-1.5 rounded-xl bg-emerald-500 px-5 py-2.5 text-xs font-bold text-slate-950 hover:bg-emerald-400 shadow-lg shadow-emerald-500/25 transition"
              >
                <span>Launch Command Center</span>
                <ArrowRight className="h-4 w-4" />
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
