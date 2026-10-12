'use client';

import React from 'react';
import {
  ShieldCheck,
  TrendingUp,
  Truck,
  RotateCcw,
  Receipt,
  FileSpreadsheet,
  Webhook,
  CheckCircle2,
  AlertTriangle,
  ArrowRight,
  Sparkles,
  BarChart3,
  Layers,
  Percent,
  Clock,
  ShieldAlert,
  ChevronRight,
  ExternalLink,
} from 'lucide-react';

interface LandingViewProps {
  onOpenAuth: (initialTab?: 'LOGIN' | 'REGISTER') => void;
}

export const LandingView: React.FC<LandingViewProps> = ({ onOpenAuth }) => {
  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 selection:bg-emerald-500 selection:text-slate-950">
      {/* Top Navigation */}
      <header className="sticky top-0 z-50 border-b border-slate-800/80 bg-slate-950/80 backdrop-blur-md">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
          <div className="flex items-center space-x-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-emerald-500 text-slate-950 font-black shadow-lg shadow-emerald-500/20">
              <ShieldCheck className="h-6 w-6" />
            </div>
            <div>
              <span className="text-base font-extrabold tracking-tight text-white flex items-center gap-1.5">
                ProfitGuard AI
                <span className="text-[10px] font-bold uppercase tracking-widest px-1.5 py-0.5 rounded bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                  D2C SaaS
                </span>
              </span>
            </div>
          </div>

          <nav className="hidden md:flex items-center space-x-8 text-xs font-semibold text-slate-400">
            <a href="#features" className="hover:text-white transition">Features</a>
            <a href="#decision-engine" className="hover:text-white transition">Decision Engine</a>
            <a href="#ndr-recovery" className="hover:text-white transition">NDR Recovery</a>
            <a href="#ledger" className="hover:text-white transition">Contribution Ledger</a>
            <a href="#integrations" className="hover:text-white transition">Integrations</a>
          </nav>

          <div className="flex items-center space-x-3">
            <button
              onClick={() => onOpenAuth('LOGIN')}
              className="text-xs font-semibold text-slate-300 hover:text-white px-3.5 py-2 rounded-lg hover:bg-slate-800 transition"
            >
              Sign In
            </button>
            <button
              onClick={() => onOpenAuth('REGISTER')}
              className="flex items-center space-x-1.5 text-xs font-bold bg-emerald-500 hover:bg-emerald-400 text-slate-950 px-4 py-2 rounded-lg shadow-md shadow-emerald-500/20 transition"
            >
              <span>Get Started</span>
              <ArrowRight className="h-3.5 w-3.5" />
            </button>
          </div>
        </div>
      </header>

      {/* Hero Section */}
      <section className="relative pt-20 pb-24 overflow-hidden border-b border-slate-800">
        <div className="absolute inset-0 bg-[radial-gradient(ellipse_70%_70%_at_50%_-10%,rgba(16,185,129,0.18),rgba(2,6,23,0))] pointer-events-none" />

        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 text-center relative z-10">
          <div className="inline-flex items-center space-x-2 rounded-full border border-emerald-500/30 bg-emerald-500/10 px-3.5 py-1 text-xs font-semibold text-emerald-400 mb-6 backdrop-blur">
            <Sparkles className="h-3.5 w-3.5 text-emerald-400" />
            <span>Built Specifically for Indian D2C Merchants & E-Commerce Brands</span>
          </div>

          <h1 className="text-4xl sm:text-5xl lg:text-6xl font-black tracking-tight text-white max-w-4xl mx-auto leading-tight sm:leading-none">
            Stop Bleeding Contribution Margin to{' '}
            <span className="text-transparent bg-clip-text bg-gradient-to-r from-emerald-400 via-teal-300 to-emerald-200">
              COD RTO Losses.
            </span>
          </h1>

          <p className="mt-6 text-sm sm:text-base text-slate-400 max-w-2xl mx-auto leading-relaxed">
            Predict delivery failure risk before dispatch, evaluate profit-maximizing candidate actions with empirical unit economics, and recover failed delivery attempts through structured NDR workflows.
          </p>

          <div className="mt-8 flex flex-col sm:flex-row items-center justify-center gap-3.5">
            <button
              onClick={() => onOpenAuth('REGISTER')}
              className="w-full sm:w-auto flex items-center justify-center space-x-2 rounded-xl bg-emerald-500 px-6 py-3.5 text-xs font-bold text-slate-950 shadow-xl shadow-emerald-500/25 hover:bg-emerald-400 transition"
            >
              <span>Open Merchant Workspace</span>
              <ArrowRight className="h-4 w-4" />
            </button>
            <button
              onClick={() => onOpenAuth('LOGIN')}
              className="w-full sm:w-auto flex items-center justify-center space-x-2 rounded-xl border border-slate-700 bg-slate-900/80 px-6 py-3.5 text-xs font-bold text-slate-200 hover:bg-slate-800 transition backdrop-blur"
            >
              <span>Sign In to Existing Store</span>
            </button>
          </div>

          {/* Quick Stats Strip */}
          <div className="mt-16 grid grid-cols-2 md:grid-cols-4 gap-4 max-w-4xl mx-auto text-left">
            <div className="p-4 rounded-xl border border-slate-800 bg-slate-900/60 backdrop-blur">
              <span className="text-[11px] font-semibold text-slate-400 block">Average RTO Cost / Return</span>
              <span className="text-xl font-bold text-white mt-1 block">₹140 – ₹220</span>
              <span className="text-[10px] text-rose-400 mt-1 flex items-center gap-1">
                Forward + Reverse + Packaging
              </span>
            </div>
            <div className="p-4 rounded-xl border border-slate-800 bg-slate-900/60 backdrop-blur">
              <span className="text-[11px] font-semibold text-slate-400 block">Indian COD Failure Rate</span>
              <span className="text-xl font-bold text-white mt-1 block">22% – 34%</span>
              <span className="text-[10px] text-amber-400 mt-1 flex items-center gap-1">
                Major logistics drag
              </span>
            </div>
            <div className="p-4 rounded-xl border border-slate-800 bg-slate-900/60 backdrop-blur">
              <span className="text-[11px] font-semibold text-slate-400 block">Candidate Actions Evaluated</span>
              <span className="text-xl font-bold text-emerald-400 mt-1 block">5 Pre-Dispatch</span>
              <span className="text-[10px] text-slate-400 mt-1 flex items-center gap-1">
                Profit-maximizing triage
              </span>
            </div>
            <div className="p-4 rounded-xl border border-slate-800 bg-slate-900/60 backdrop-blur">
              <span className="text-[11px] font-semibold text-slate-400 block">Financial Accounting</span>
              <span className="text-xl font-bold text-white mt-1 block">Settled Ledger</span>
              <span className="text-[10px] text-emerald-400 mt-1 flex items-center gap-1">
                Expected vs Realized margin
              </span>
            </div>
          </div>
        </div>
      </section>

      {/* Problem Section */}
      <section className="py-20 border-b border-slate-800 bg-slate-900/40">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="text-center max-w-3xl mx-auto mb-14">
            <span className="text-xs font-bold text-rose-400 uppercase tracking-wider block mb-2">The Hidden D2C Crisis</span>
            <h2 className="text-2xl sm:text-3xl font-extrabold text-white tracking-tight">
              Why Blind Fulfillment Destroys D2C Margins
            </h2>
            <p className="mt-3 text-xs sm:text-sm text-slate-400">
              When an order fails delivery, you don&apos;t just lose the sale—you pay freight carriers twice, lose damaged inventory, and incur non-refundable COD handling penalties.
            </p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            <div className="p-6 rounded-2xl border border-slate-800 bg-slate-900/70">
              <div className="h-10 w-10 rounded-xl bg-rose-500/10 text-rose-400 flex items-center justify-center mb-4">
                <RotateCcw className="h-5 w-5" />
              </div>
              <h3 className="text-sm font-bold text-white mb-2">Double Logistics Leakage</h3>
              <p className="text-xs text-slate-400 leading-relaxed">
                Carriers charge ₹60–₹90 for forward freight and another ₹60–₹90 for RTO reverse shipping, completely eliminating the product contribution margin.
              </p>
            </div>

            <div className="p-6 rounded-2xl border border-slate-800 bg-slate-900/70">
              <div className="h-10 w-10 rounded-xl bg-amber-500/10 text-amber-400 flex items-center justify-center mb-4">
                <AlertTriangle className="h-5 w-5" />
              </div>
              <h3 className="text-sm font-bold text-white mb-2">Carrier Surcharges & Damage</h3>
              <p className="text-xs text-slate-400 leading-relaxed">
                COD collection surcharges (₹35–₹50) are incurred regardless of whether the delivery succeeds, while multi-week transit cycles damage packaging and perishables.
              </p>
            </div>

            <div className="p-6 rounded-2xl border border-slate-800 bg-slate-900/70">
              <div className="h-10 w-10 rounded-xl bg-blue-500/10 text-blue-400 flex items-center justify-center mb-4">
                <Layers className="h-5 w-5" />
              </div>
              <h3 className="text-sm font-bold text-white mb-2">Crude Pincode Blacklists</h3>
              <p className="text-xs text-slate-400 leading-relaxed">
                Traditional tools merely block entire pincodes, rejecting profitable genuine buyers and destroying top-line revenue without measuring real unit economics.
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* Core Platform Pillars */}
      <section id="features" className="py-20 border-b border-slate-800">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="text-center max-w-3xl mx-auto mb-16">
            <span className="text-xs font-bold text-emerald-400 uppercase tracking-wider block mb-2">The Solution</span>
            <h2 className="text-2xl sm:text-3xl font-extrabold text-white tracking-tight">
              An End-to-End Profit Protection Architecture
            </h2>
            <p className="mt-3 text-xs sm:text-sm text-slate-400">
              ProfitGuard AI operates across the complete order journey: from pre-dispatch risk assessment to logistics transitions, NDR recovery, and settled reconciliation.
            </p>
          </div>

          <div className="space-y-12">
            {/* Pillar 1 */}
            <div id="decision-engine" className="grid grid-cols-1 lg:grid-cols-2 gap-8 items-center rounded-2xl border border-slate-800 bg-slate-900/50 p-6 sm:p-8">
              <div>
                <div className="inline-flex items-center space-x-1.5 rounded-md bg-emerald-500/10 text-emerald-400 px-2.5 py-1 text-[11px] font-bold mb-3 border border-emerald-500/20">
                  <BarChart3 className="h-3.5 w-3.5" />
                  Pillar 1: Pre-Dispatch Evaluation
                </div>
                <h3 className="text-xl font-bold text-white mb-3">
                  5-Action Profit Decision Engine
                </h3>
                <p className="text-xs text-slate-300 leading-relaxed mb-4">
                  Rather than a binary cancel/ship rule, ProfitGuard evaluates five distinct candidate actions to maximize mathematical Expected Contribution (EC):
                </p>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5 text-xs text-slate-300 mb-6">
                  <div className="p-2.5 rounded-lg bg-slate-800/80 border border-slate-700">
                    <span className="font-bold text-emerald-400 block">SHIP_AS_IS</span>
                    <span className="text-[11px] text-slate-400">Low risk, maximum immediate margin.</span>
                  </div>
                  <div className="p-2.5 rounded-lg bg-slate-800/80 border border-slate-700">
                    <span className="font-bold text-teal-400 block">VERIFY_OTP</span>
                    <span className="text-[11px] text-slate-400">Fast customer intent confirmation.</span>
                  </div>
                  <div className="p-2.5 rounded-lg bg-slate-800/80 border border-slate-700">
                    <span className="font-bold text-blue-400 block">INCENTIVIZE_PREPAID</span>
                    <span className="text-[11px] text-slate-400">Convert COD to prepaid with discounts.</span>
                  </div>
                  <div className="p-2.5 rounded-lg bg-slate-800/80 border border-slate-700">
                    <span className="font-bold text-amber-400 block">MANUAL_REVIEW</span>
                    <span className="text-[11px] text-slate-400">High basket value edge cases.</span>
                  </div>
                  <div className="p-2.5 rounded-lg bg-slate-800/80 border border-slate-700 sm:col-span-2">
                    <span className="font-bold text-rose-400 block">HOLD_CANCEL</span>
                    <span className="text-[11px] text-slate-400">Certain RTO loss where fulfillment burns negative contribution.</span>
                  </div>
                </div>
                <div className="text-[11px] text-slate-400 flex items-center gap-1.5">
                  <CheckCircle2 className="h-4 w-4 text-emerald-400 shrink-0" />
                  Applies policy guardrails: never auto-cancels high-value orders without manual approval.
                </div>
              </div>
              <div className="rounded-xl border border-slate-700 bg-slate-950 p-5 font-mono text-xs shadow-inner">
                <div className="flex items-center justify-between pb-3 border-b border-slate-800 text-[11px] text-slate-400">
                  <span>DECISION_EVALUATION</span>
                  <span className="text-emerald-400 font-bold">OPTIMAL_ACTION: VERIFY_OTP</span>
                </div>
                <div className="mt-4 space-y-2 text-[11px]">
                  <div className="flex justify-between py-1 border-b border-slate-900">
                    <span className="text-slate-400">Order ID:</span>
                    <span className="text-white">ORD-94281 (COD)</span>
                  </div>
                  <div className="flex justify-between py-1 border-b border-slate-900">
                    <span className="text-slate-400">Gross Value:</span>
                    <span className="text-white">₹1,899.00</span>
                  </div>
                  <div className="flex justify-between py-1 border-b border-slate-900">
                    <span className="text-slate-400">Estimated Delivery Risk:</span>
                    <span className="text-amber-400">0.42 (Tier 3 COD Risk)</span>
                  </div>
                  <div className="flex justify-between py-1 border-b border-slate-900">
                    <span className="text-slate-400">EC (SHIP_AS_IS):</span>
                    <span className="text-slate-300">₹312.40</span>
                  </div>
                  <div className="flex justify-between py-1 border-b border-slate-900">
                    <span className="text-slate-400">EC (VERIFY_OTP):</span>
                    <span className="text-emerald-400 font-bold">₹548.80 (+₹236.40 Lift)</span>
                  </div>
                  <div className="flex justify-between py-1">
                    <span className="text-slate-400">EC (HOLD_CANCEL):</span>
                    <span className="text-rose-400">₹0.00</span>
                  </div>
                </div>
              </div>
            </div>

            {/* Pillar 2 */}
            <div id="ndr-recovery" className="grid grid-cols-1 lg:grid-cols-2 gap-8 items-center rounded-2xl border border-slate-800 bg-slate-900/50 p-6 sm:p-8">
              <div className="order-2 lg:order-1 rounded-xl border border-slate-700 bg-slate-950 p-5 font-mono text-xs shadow-inner">
                <div className="flex items-center justify-between pb-3 border-b border-slate-800 text-[11px] text-slate-400">
                  <span>NDR_CASE_MANAGEMENT</span>
                  <span className="text-amber-400 font-bold">CASE #NDR-7319 • OPEN</span>
                </div>
                <div className="mt-4 space-y-2 text-[11px]">
                  <div className="flex justify-between py-1 border-b border-slate-900">
                    <span className="text-slate-400">Failure Reason:</span>
                    <span className="text-rose-400">CUSTOMER_UNAVAILABLE</span>
                  </div>
                  <div className="flex justify-between py-1 border-b border-slate-900">
                    <span className="text-slate-400">Attempt Count:</span>
                    <span className="text-white">1 of 3</span>
                  </div>
                  <div className="flex justify-between py-1 border-b border-slate-900">
                    <span className="text-slate-400">Recommended Action:</span>
                    <span className="text-teal-400 font-bold">SCHEDULE_REATTEMPT</span>
                  </div>
                  <div className="flex justify-between py-1 border-b border-slate-900">
                    <span className="text-slate-400">Expected Recovery Lift:</span>
                    <span className="text-emerald-400 font-bold">₹420.50</span>
                  </div>
                  <div className="flex justify-between py-1">
                    <span className="text-slate-400">Intervention Log:</span>
                    <span className="text-slate-300">WhatsApp sent & Delivery window confirmed</span>
                  </div>
                </div>
              </div>
              <div className="order-1 lg:order-2">
                <div className="inline-flex items-center space-x-1.5 rounded-md bg-teal-500/10 text-teal-400 px-2.5 py-1 text-[11px] font-bold mb-3 border border-teal-500/20">
                  <Truck className="h-3.5 w-3.5" />
                  Pillar 2: NDR Recovery Hub
                </div>
                <h3 className="text-xl font-bold text-white mb-3">
                  Turn Failed Deliveries into Completed Cash
                </h3>
                <p className="text-xs text-slate-300 leading-relaxed mb-4">
                  When a courier reports a delivery failure (Customer Unavailable, Door Closed, Incorrect Address), ProfitGuard immediately opens an operational NDR case to intervene before the package is flagged RTO.
                </p>
                <ul className="space-y-2 text-xs text-slate-300 mb-6">
                  <li className="flex items-start gap-2">
                    <CheckCircle2 className="h-4 w-4 text-teal-400 shrink-0 mt-0.5" />
                    <span><strong>Customer Re-engagement:</strong> Automatic SMS & WhatsApp verification to capture alternate phone numbers or corrected street addresses.</span>
                  </li>
                  <li className="flex items-start gap-2">
                    <CheckCircle2 className="h-4 w-4 text-teal-400 shrink-0 mt-0.5" />
                    <span><strong>Carrier Reattempt API:</strong> Schedules courier reattempts on dates confirmed by the buyer.</span>
                  </li>
                  <li className="flex items-start gap-2">
                    <CheckCircle2 className="h-4 w-4 text-teal-400 shrink-0 mt-0.5" />
                    <span><strong>Honest Lift Accounting:</strong> Prevents double-counting by measuring net recovered margin against intervention overhead.</span>
                  </li>
                </ul>
              </div>
            </div>

            {/* Pillar 3 */}
            <div id="ledger" className="grid grid-cols-1 lg:grid-cols-2 gap-8 items-center rounded-2xl border border-slate-800 bg-slate-900/50 p-6 sm:p-8">
              <div>
                <div className="inline-flex items-center space-x-1.5 rounded-md bg-blue-500/10 text-blue-400 px-2.5 py-1 text-[11px] font-bold mb-3 border border-blue-500/20">
                  <Receipt className="h-3.5 w-3.5" />
                  Pillar 3: Financial Reconciliation
                </div>
                <h3 className="text-xl font-bold text-white mb-3">
                  True Settled Contribution Ledger
                </h3>
                <p className="text-xs text-slate-300 leading-relaxed mb-4">
                  Revenue is vanity, profit is sanity. ProfitGuard tracks the full financial reality of every order from estimated pre-dispatch profit to post-delivery bank settlement.
                </p>
                <div className="space-y-2 text-xs text-slate-300 mb-6">
                  <div className="p-3 rounded-xl bg-slate-800/80 border border-slate-700">
                    <span className="font-semibold text-white block mb-1">Standardized Unit Economics Configuration</span>
                    <span className="text-[11px] text-slate-400">
                      Configure your store&apos;s Default COGS %, Forward Shipping, Reverse Logistics penalty, Packaging costs, and COD handling fees to match your carrier rate cards.
                    </span>
                  </div>
                  <div className="p-3 rounded-xl bg-slate-800/80 border border-slate-700">
                    <span className="font-semibold text-white block mb-1">Contribution Variance Analysis</span>
                    <span className="text-[11px] text-slate-400">
                      Identifies exactly why realized margin differed from expected margin—whether due to RTO reverse freight, multiple courier attempts, or damaged goods.
                    </span>
                  </div>
                </div>
              </div>
              <div className="rounded-xl border border-slate-700 bg-slate-950 p-5 font-mono text-xs shadow-inner">
                <div className="flex items-center justify-between pb-3 border-b border-slate-800 text-[11px] text-slate-400">
                  <span>FINANCIAL_RECONCILIATION</span>
                  <span className="text-emerald-400 font-bold">STATUS: RECONCILED</span>
                </div>
                <div className="mt-4 space-y-2 text-[11px]">
                  <div className="flex justify-between py-1 border-b border-slate-900">
                    <span className="text-slate-400">Order GMV:</span>
                    <span className="text-white">₹2,499.00</span>
                  </div>
                  <div className="flex justify-between py-1 border-b border-slate-900">
                    <span className="text-slate-400">Product COGS (35%):</span>
                    <span className="text-rose-400">-₹874.65</span>
                  </div>
                  <div className="flex justify-between py-1 border-b border-slate-900">
                    <span className="text-slate-400">Forward Shipping:</span>
                    <span className="text-rose-400">-₹70.00</span>
                  </div>
                  <div className="flex justify-between py-1 border-b border-slate-900">
                    <span className="text-slate-400">COD Carrier Fee:</span>
                    <span className="text-rose-400">-₹40.00</span>
                  </div>
                  <div className="flex justify-between py-1 border-b border-slate-900">
                    <span className="text-slate-400">Packaging & Handling:</span>
                    <span className="text-rose-400">-₹20.00</span>
                  </div>
                  <div className="flex justify-between py-1.5 font-bold">
                    <span className="text-white">Realized Contribution:</span>
                    <span className="text-emerald-400">₹1,494.35 (59.8%)</span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Integrations Section */}
      <section id="integrations" className="py-20 border-b border-slate-800 bg-slate-900/40">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="text-center max-w-3xl mx-auto mb-14">
            <span className="text-xs font-bold text-emerald-400 uppercase tracking-wider block mb-2">Connect Your Store</span>
            <h2 className="text-2xl sm:text-3xl font-extrabold text-white tracking-tight">
              Flexible, Transparent Ingestion Options
            </h2>
            <p className="mt-3 text-xs sm:text-sm text-slate-400">
              Integrate with your existing storefront and warehouse management system with zero lock-in.
            </p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            <div className="p-6 rounded-2xl border border-emerald-500/40 bg-slate-900/80 relative">
              <div className="absolute top-4 right-4 text-[10px] font-bold px-2 py-0.5 rounded bg-emerald-500/20 text-emerald-400 border border-emerald-500/30 uppercase">
                Active & Live
              </div>
              <div className="h-10 w-10 rounded-xl bg-emerald-500/10 text-emerald-400 flex items-center justify-center mb-4">
                <FileSpreadsheet className="h-5 w-5" />
              </div>
              <h3 className="text-sm font-bold text-white mb-2">2-Stage CSV Bulk Ingestion</h3>
              <p className="text-xs text-slate-400 leading-relaxed mb-4">
                Upload order batches from Shopify, WooCommerce, or Custom ERP exports. Validate column mapping and errors in Stage 1 before committing to your tenant database in Stage 2.
              </p>
              <div className="text-[11px] font-semibold text-emerald-400 flex items-center gap-1">
                <CheckCircle2 className="h-3.5 w-3.5" />
                Atomic duplicate detection included
              </div>
            </div>

            <div className="p-6 rounded-2xl border border-emerald-500/40 bg-slate-900/80 relative">
              <div className="absolute top-4 right-4 text-[10px] font-bold px-2 py-0.5 rounded bg-emerald-500/20 text-emerald-400 border border-emerald-500/30 uppercase">
                Active & Live
              </div>
              <div className="h-10 w-10 rounded-xl bg-emerald-500/10 text-emerald-400 flex items-center justify-center mb-4">
                <Webhook className="h-5 w-5" />
              </div>
              <h3 className="text-sm font-bold text-white mb-2">REST API & Webhooks</h3>
              <p className="text-xs text-slate-400 leading-relaxed mb-4">
                Push orders programmatically via authenticated REST endpoints. Full HMAC-SHA256 signature verification and OpenAPI schema compliance.
              </p>
              <div className="text-[11px] font-semibold text-emerald-400 flex items-center gap-1">
                <CheckCircle2 className="h-3.5 w-3.5" />
                POST /api/v1/orders/webhook
              </div>
            </div>

            <div className="p-6 rounded-2xl border border-slate-800 bg-slate-900/60 relative">
              <div className="absolute top-4 right-4 text-[10px] font-bold px-2 py-0.5 rounded bg-slate-800 text-slate-400 border border-slate-700 uppercase">
                App In Review
              </div>
              <div className="h-10 w-10 rounded-xl bg-slate-800 text-slate-300 flex items-center justify-center mb-4">
                <Sparkles className="h-5 w-5" />
              </div>
              <h3 className="text-sm font-bold text-white mb-2">Native Shopify App</h3>
              <p className="text-xs text-slate-400 leading-relaxed mb-4">
                One-click install app for Shopify Plus & Advanced merchants. Real-time checkout order webhooks and automated tag updates. Available via private app configuration.
              </p>
              <div className="text-[11px] font-semibold text-slate-400 flex items-center gap-1">
                <Clock className="h-3.5 w-3.5" />
                Private webhook setup ready today
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* CTA Section */}
      <section className="py-20 border-b border-slate-800 relative overflow-hidden">
        <div className="absolute inset-0 bg-[radial-gradient(ellipse_60%_60%_at_50%_50%,rgba(16,185,129,0.12),rgba(2,6,23,0))] pointer-events-none" />

        <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 text-center relative z-10">
          <h2 className="text-3xl sm:text-4xl font-extrabold text-white tracking-tight">
            Take Control of Your Store&apos;s Bottom-Line Contribution Profit
          </h2>
          <p className="mt-4 text-xs sm:text-sm text-slate-400 max-w-xl mx-auto">
            Join high-growth D2C merchants evaluating pre-dispatch risk, stopping bad COD dispatches, and recovering failed deliveries.
          </p>

          <div className="mt-8 flex flex-col sm:flex-row items-center justify-center gap-4">
            <button
              onClick={() => onOpenAuth('REGISTER')}
              className="w-full sm:w-auto flex items-center justify-center space-x-2 rounded-xl bg-emerald-500 px-8 py-3.5 text-xs font-bold text-slate-950 shadow-xl shadow-emerald-500/25 hover:bg-emerald-400 transition"
            >
              <span>Get Started with ProfitGuard AI</span>
              <ArrowRight className="h-4 w-4" />
            </button>
            <button
              onClick={() => onOpenAuth('LOGIN')}
              className="w-full sm:w-auto flex items-center justify-center space-x-2 rounded-xl border border-slate-700 bg-slate-900/80 px-6 py-3.5 text-xs font-bold text-slate-200 hover:bg-slate-800 transition"
            >
              <span>Sign In to Your Workspace</span>
            </button>
          </div>
        </div>
      </section>

      {/* SaaS Footer */}
      <footer className="py-12 bg-slate-950 text-slate-400 text-xs">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-8 mb-8">
            <div>
              <span className="font-bold text-white block mb-3">Product</span>
              <ul className="space-y-2 text-slate-400">
                <li><a href="#decision-engine" className="hover:text-white transition">5-Action Decision Engine</a></li>
                <li><a href="#ndr-recovery" className="hover:text-white transition">NDR Recovery Hub</a></li>
                <li><a href="#ledger" className="hover:text-white transition">Realized Contribution Ledger</a></li>
                <li><a href="#integrations" className="hover:text-white transition">2-Stage CSV Ingestion</a></li>
              </ul>
            </div>
            <div>
              <span className="font-bold text-white block mb-3">Integrations</span>
              <ul className="space-y-2 text-slate-400">
                <li><a href="#integrations" className="hover:text-white transition">Shopify Webhooks</a></li>
                <li><a href="#integrations" className="hover:text-white transition">WooCommerce (Roadmap)</a></li>
                <li><a href="#integrations" className="hover:text-white transition">Delhivery & Blue Dart 3PLs</a></li>
                <li><a href="#integrations" className="hover:text-white transition">Custom REST Ingestion</a></li>
              </ul>
            </div>
            <div>
              <span className="font-bold text-white block mb-3">Economics</span>
              <ul className="space-y-2 text-slate-400">
                <li><span>COD Carrier Surcharges</span></li>
                <li><span>Forward & Reverse Logistics</span></li>
                <li><span>COGS Margin Attribution</span></li>
                <li><span>Shrinkage & Damage Reserves</span></li>
              </ul>
            </div>
            <div>
              <span className="font-bold text-white block mb-3">Security & Compliance</span>
              <ul className="space-y-2 text-slate-400">
                <li><span>Multi-Tenant Schema Isolation</span></li>
                <li><span>Role-Based Access Control</span></li>
                <li><span>Audit Trail Event Logging</span></li>
                <li><span>Encrypted Credentials</span></li>
              </ul>
            </div>
          </div>

          <div className="pt-8 border-t border-slate-900 flex flex-col sm:flex-row items-center justify-between text-[11px] text-slate-500">
            <p>© {new Date().getFullYear()} ProfitGuard AI. All rights reserved. Built for Indian D2C Commerce.</p>
            <div className="mt-4 sm:mt-0 flex items-center space-x-6">
              <span>Tenant Data Isolated</span>
              <span>•</span>
              <span>REST API v1</span>
              <span>•</span>
              <span>FastAPI & Next.js Engine</span>
            </div>
          </div>
        </div>
      </footer>
    </div>
  );
};
