'use client';

import React, { useState } from 'react';
import {
  X,
  Play,
  CheckCircle2,
  AlertCircle,
  RefreshCw,
  ArrowRight,
  ShieldCheck,
  Receipt,
  Sparkles,
  Truck,
  RotateCcw,
  Package,
} from 'lucide-react';
import { DemoJourneyResponse, DemoJourneyStep, Order } from '@/types';
import { runDemoJourney } from '@/services/api';

interface DemoJourneyModalProps {
  isOpen: boolean;
  onClose: () => void;
  onJourneyCompleted: () => void;
  onOpenLedger?: (orderId: string, externalId: string) => void;
}

export const DemoJourneyModal: React.FC<DemoJourneyModalProps> = ({
  isOpen,
  onClose,
  onJourneyCompleted,
  onOpenLedger,
}) => {
  const [isRunning, setIsRunning] = useState(false);
  const [journeyData, setJourneyData] = useState<DemoJourneyResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  if (!isOpen) return null;

  const handleStartJourney = async () => {
    setIsRunning(true);
    setError(null);
    try {
      const result = await runDemoJourney();
      setJourneyData(result);
      onJourneyCompleted();
    } catch (err: any) {
      setError(err.message || 'Failed to complete 8-step automated demo journey');
    } finally {
      setIsRunning(false);
    }
  };

  const getStepIcon = (step: number) => {
    switch (step) {
      case 1:
        return <Package className="h-4 w-4 text-blue-600" />;
      case 2:
        return <Sparkles className="h-4 w-4 text-emerald-600" />;
      case 3:
        return <ShieldCheck className="h-4 w-4 text-indigo-600" />;
      case 4:
        return <Truck className="h-4 w-4 text-amber-600" />;
      case 5:
        return <RotateCcw className="h-4 w-4 text-rose-600" />;
      case 6:
        return <RefreshCw className="h-4 w-4 text-purple-600" />;
      case 7:
        return <CheckCircle2 className="h-4 w-4 text-emerald-600" />;
      case 8:
        return <Receipt className="h-4 w-4 text-purple-700" />;
      default:
        return <CheckCircle2 className="h-4 w-4 text-slate-600" />;
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/60 p-4 backdrop-blur-sm">
      <div className="relative w-full max-w-3xl max-h-[92vh] flex flex-col rounded-2xl bg-white shadow-2xl border border-slate-200 overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-slate-100 bg-slate-50/80 px-6 py-4">
          <div className="flex items-center space-x-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-purple-600 text-white shadow-md shadow-purple-500/20">
              <Play className="h-5 w-5 ml-0.5" />
            </div>
            <div>
              <div className="flex items-center space-x-2">
                <h2 className="text-lg font-bold text-slate-900">8-Step End-to-End User Journey Runner</h2>
                <span className="rounded-full bg-purple-100 px-2.5 py-0.5 text-xs font-bold text-purple-800">
                  DEMO HARNESS
                </span>
              </div>
              <p className="text-xs text-slate-500">
                Automated demonstration: Ingestion → Risk Engine → Verification → Dispatch → NDR Rescue → Delivered → Reconciled
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

        {/* Body */}
        <div className="overflow-y-auto p-6 space-y-6">
          {error && (
            <div className="flex items-center space-x-2 rounded-xl bg-rose-50 border border-rose-200 p-3.5 text-xs text-rose-700">
              <AlertCircle className="h-4 w-4 shrink-0 text-rose-500" />
              <span>{error}</span>
            </div>
          )}

          {!journeyData && !isRunning && (
            <div className="rounded-xl border border-purple-200 bg-purple-50/50 p-6 text-center space-y-4">
              <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-2xl bg-purple-100 text-purple-700">
                <Sparkles className="h-7 w-7" />
              </div>
              <div className="max-w-md mx-auto space-y-1">
                <h3 className="text-base font-bold text-slate-900">Execute Complete 8-Step Lifecycle</h3>
                <p className="text-xs text-slate-600 leading-relaxed">
                  This runner automatically creates a high-risk COD order, runs the 5-action decision engine, confirms WhatsApp OTP verification, simulates dispatch, handles delivery failure with NDR triage, executes recovery reattempt, and produces the authoritative settled realized contribution ledger.
                </p>
              </div>
              <button
                type="button"
                onClick={handleStartJourney}
                className="inline-flex items-center space-x-2 rounded-xl bg-purple-600 px-6 py-2.5 text-xs font-bold text-white shadow-lg shadow-purple-600/30 hover:bg-purple-700 transition"
              >
                <Play className="h-4 w-4" />
                <span>Execute Complete 8-Step Journey</span>
              </button>
            </div>
          )}

          {isRunning && (
            <div className="flex flex-col items-center justify-center py-16 space-y-3">
              <RefreshCw className="h-8 w-8 animate-spin text-purple-600" />
              <p className="text-sm font-semibold text-slate-800">Executing 8-step lifecycle pipeline...</p>
              <p className="text-xs text-slate-500">Creating order, running decision engine, scheduling NDR rescue, settling ledger</p>
            </div>
          )}

          {journeyData && (
            <div className="space-y-6">
              {/* Success Banner */}
              <div className="rounded-xl border border-emerald-200 bg-emerald-50/80 p-4">
                <div className="flex items-center justify-between">
                  <div className="flex items-center space-x-3">
                    <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-emerald-100 text-emerald-700">
                      <CheckCircle2 className="h-5 w-5" />
                    </div>
                    <div>
                      <h4 className="text-sm font-bold text-emerald-950">
                        All 8 Journey Steps Completed Successfully
                      </h4>
                      <p className="text-xs text-emerald-700">
                        Order #{journeyData.final_reconciliation.order_value ? 'DEMO-COD-JOURNEY-001' : 'DEMO'} settled with authoritative Realized Contribution ₹{journeyData.final_reconciliation.realized_contribution}
                      </p>
                    </div>
                  </div>
                  <div className="text-right">
                    <span className="inline-block rounded-full bg-emerald-100 border border-emerald-300 px-2.5 py-0.5 text-xs font-bold text-emerald-800">
                      SETTLED
                    </span>
                  </div>
                </div>
              </div>

              {/* Step by Step Timeline */}
              <div className="space-y-3">
                <h4 className="text-xs font-bold uppercase tracking-wider text-slate-500">
                  Execution Transcript (8 Steps)
                </h4>
                <div className="divide-y divide-slate-100 rounded-xl border border-slate-200 bg-slate-50/50 overflow-hidden">
                  {journeyData.transcript.map((item: DemoJourneyStep) => (
                    <div key={item.step} className="p-4 bg-white hover:bg-slate-50 transition">
                      <div className="flex items-start space-x-3">
                        <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-slate-100 border border-slate-200 mt-0.5">
                          {getStepIcon(item.step)}
                        </div>
                        <div className="flex-1 space-y-1">
                          <div className="flex items-center justify-between">
                            <span className="text-xs font-bold text-slate-900">
                              Step {item.step}: {item.title}
                            </span>
                            {item.order_status && (
                              <span className="rounded bg-slate-100 px-2 py-0.5 text-[10px] font-semibold text-slate-700">
                                Status: {item.order_status}
                              </span>
                            )}
                          </div>
                          <p className="text-xs text-slate-600 leading-relaxed">
                            {item.details}
                          </p>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between border-t border-slate-100 bg-slate-50/80 px-6 py-3.5">
          {journeyData && (
            <button
              onClick={handleStartJourney}
              disabled={isRunning}
              className="inline-flex items-center space-x-1.5 rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-xs font-semibold text-slate-700 shadow-sm hover:bg-slate-50 transition"
            >
              <RefreshCw className={`h-3.5 w-3.5 ${isRunning ? 'animate-spin' : ''}`} />
              <span>Rerun Journey</span>
            </button>
          )}
          {!journeyData && <div />}
          <div className="flex items-center space-x-2">
            <button
              onClick={onClose}
              className="rounded-lg bg-slate-900 px-4 py-1.5 text-xs font-semibold text-white shadow-sm hover:bg-slate-800 transition"
            >
              Close
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
