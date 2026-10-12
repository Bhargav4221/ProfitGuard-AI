'use client';

import React, { useState, useEffect } from 'react';
import {
  ShieldAlert,
  CheckCircle,
  XCircle,
  AlertTriangle,
  ArrowRight,
  TrendingUp,
  X,
  Loader2,
  DollarSign,
  Info,
  Sliders,
  Send,
  PhoneCall,
  Check,
  MessageSquare,
} from 'lucide-react';
import { Order, OrderEvaluation, ActionEvaluation, WhatsAppMessage } from '@/types';
import {
  evaluateOrder,
  fetchOrderDecision,
  recordOrderDecision,
  recordInterventionOutcome,
  sendWhatsAppOrderOtp,
  fetchWhatsAppMessages,
} from '@/services/api';

interface OrderDecisionModalProps {
  order: Order | null;
  isOpen: boolean;
  onClose: () => void;
  onDecisionUpdated: () => void;
}

export const OrderDecisionModal: React.FC<OrderDecisionModalProps> = ({
  order,
  isOpen,
  onClose,
  onDecisionUpdated,
}) => {
  const [evaluation, setEvaluation] = useState<OrderEvaluation | null>(null);
  const [orderMessages, setOrderMessages] = useState<WhatsAppMessage[]>([]);
  const [isSendingWhatsApp, setIsSendingWhatsApp] = useState(false);
  const [whatsAppFeedback, setWhatsAppFeedback] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  // Override controls state
  const [showOverride, setShowOverride] = useState(false);
  const [selectedOverrideAction, setSelectedOverrideAction] = useState<string>('SHIP_AS_IS');
  const [overrideReason, setOverrideReason] = useState<string>('');

  // Intervention outcome notes
  const [outcomeNotes, setOutcomeNotes] = useState<string>('');

  useEffect(() => {
    if (isOpen && order) {
      loadOrEvaluate();
      loadWhatsAppMessages();
    } else {
      setEvaluation(null);
      setOrderMessages([]);
      setWhatsAppFeedback(null);
      setShowOverride(false);
      setOverrideReason('');
      setErrorMsg(null);
    }
  }, [isOpen, order]);

  const loadWhatsAppMessages = async () => {
    if (!order) return;
    try {
      const res = await fetchWhatsAppMessages({ orderId: order.id });
      setOrderMessages(res.items || []);
    } catch {
      // Graceful fallback
    }
  };

  const handleSendWhatsAppOtp = async () => {
    if (!order) return;
    setIsSendingWhatsApp(true);
    setWhatsAppFeedback(null);
    setErrorMsg(null);
    try {
      const res = await sendWhatsAppOrderOtp(order.id);
      setWhatsAppFeedback(`WhatsApp confirmation sent (${res.status}) to ${res.recipient_phone}!`);
      loadWhatsAppMessages();
      loadOrEvaluate();
    } catch (err: any) {
      setErrorMsg(err.message || 'Failed to dispatch WhatsApp OTP.');
    } finally {
      setIsSendingWhatsApp(false);
    }
  };

  const loadOrEvaluate = async () => {
    if (!order) return;
    setIsLoading(true);
    setErrorMsg(null);
    try {
      // First try fetching existing decision
      try {
        const existing = await fetchOrderDecision(order.id);
        setEvaluation(existing);
        setIsLoading(false);
        return;
      } catch {
        // If not evaluated yet, trigger evaluate
      }
      const evalResult = await evaluateOrder(order.id);
      setEvaluation(evalResult);
    } catch (err: any) {
      setErrorMsg(err.message || 'Failed to evaluate order risk and decisions.');
    } finally {
      setIsLoading(false);
    }
  };

  const handleAcceptRecommendation = async () => {
    if (!order || !evaluation) return;
    setIsSubmitting(true);
    setErrorMsg(null);
    try {
      const updated = await recordOrderDecision(order.id, evaluation.recommended_action);
      setEvaluation(updated);
      onDecisionUpdated();
    } catch (err: any) {
      setErrorMsg(err.message || 'Failed to accept recommendation.');
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleRecordOverride = async () => {
    if (!order) return;
    if (!overrideReason.trim()) {
      setErrorMsg('An override reason is strictly required when choosing an alternative action.');
      return;
    }
    setIsSubmitting(true);
    setErrorMsg(null);
    try {
      const updated = await recordOrderDecision(order.id, selectedOverrideAction, overrideReason.trim());
      setEvaluation(updated);
      setShowOverride(false);
      setOverrideReason('');
      onDecisionUpdated();
    } catch (err: any) {
      setErrorMsg(err.message || 'Failed to record decision override.');
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleInterventionOutcome = async (outcome: string) => {
    if (!order) return;
    setIsSubmitting(true);
    setErrorMsg(null);
    try {
      const updated = await recordInterventionOutcome(order.id, outcome, outcomeNotes.trim() || undefined);
      setEvaluation(updated);
      setOutcomeNotes('');
      onDecisionUpdated();
    } catch (err: any) {
      setErrorMsg(err.message || 'Failed to record intervention outcome.');
    } finally {
      setIsSubmitting(false);
    }
  };

  if (!isOpen || !order) return null;

  const getRiskBadge = (tier: string) => {
    switch (tier) {
      case 'LOW':
        return <span className="rounded-full bg-emerald-100 px-2.5 py-0.5 text-xs font-bold text-emerald-800">LOW RISK</span>;
      case 'MEDIUM':
        return <span className="rounded-full bg-blue-100 px-2.5 py-0.5 text-xs font-bold text-blue-800">MEDIUM RISK</span>;
      case 'HIGH':
        return <span className="rounded-full bg-amber-100 px-2.5 py-0.5 text-xs font-bold text-amber-800">HIGH RISK</span>;
      default:
        return <span className="rounded-full bg-rose-100 px-2.5 py-0.5 text-xs font-bold text-rose-800">CRITICAL RISK</span>;
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm">
      <div className="relative flex max-h-[92vh] w-full max-w-5xl flex-col rounded-xl bg-white shadow-2xl">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-slate-200 px-6 py-4">
          <div className="flex items-center space-x-3">
            <div className="rounded-lg bg-emerald-50 p-2 text-emerald-600">
              <ShieldAlert className="h-6 w-6" />
            </div>
            <div>
              <div className="flex items-center space-x-2">
                <h2 className="text-xl font-bold text-slate-900">
                  Decision Engine: {order.external_order_id}
                </h2>
                <span className="rounded bg-slate-100 px-2 py-0.5 font-mono text-xs font-semibold text-slate-700">
                  {order.payment_method}
                </span>
                <span className="rounded bg-slate-100 px-2 py-0.5 font-sans text-xs font-medium text-slate-700">
                  GMV: ₹{parseFloat(order.order_value).toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                </span>
              </div>
              <p className="text-xs text-slate-500">
                Customer: <span className="font-semibold text-slate-700">{order.customer_name || '—'}</span> | Phone: {order.customer_phone || '—'} | City: {order.shipping_city || '—'} (PIN: {order.shipping_pincode || '—'})
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="rounded-lg p-2 text-slate-400 hover:bg-slate-100 hover:text-slate-600"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto px-6 py-6 space-y-6">
          {errorMsg && (
            <div className="flex items-start space-x-3 rounded-lg border border-red-200 bg-red-50 p-4 text-red-800">
              <XCircle className="mt-0.5 h-5 w-5 flex-shrink-0 text-red-500" />
              <div className="text-sm font-medium">{errorMsg}</div>
            </div>
          )}

          {isLoading ? (
            <div className="flex flex-col items-center justify-center py-20 text-slate-400 space-y-3">
              <Loader2 className="h-8 w-8 animate-spin text-emerald-600" />
              <p className="text-sm font-medium">Evaluating 5 candidate actions and economic payoffs...</p>
            </div>
          ) : evaluation ? (
            <>
              {/* Recommendation Banner */}
              <div className="rounded-xl border border-emerald-200 bg-emerald-50/70 p-5 shadow-sm">
                <div className="flex flex-wrap items-center justify-between gap-4">
                  <div>
                    <div className="flex items-center space-x-2">
                      <span className="text-xs font-semibold uppercase tracking-wider text-emerald-800">
                        Optimal Recommendation [ESTIMATED]
                      </span>
                      {getRiskBadge(evaluation.risk_tier)}
                    </div>
                    <div className="mt-1 flex items-center space-x-3">
                      <h3 className="text-2xl font-black text-emerald-950 font-mono">
                        {evaluation.recommended_action}
                      </h3>
                      {evaluation.recommended_lift !== '0.00' && (
                        <span className="flex items-center space-x-1 rounded-full bg-emerald-200/80 px-2.5 py-0.5 text-xs font-bold text-emerald-900">
                          <TrendingUp className="h-3.5 w-3.5" />
                          <span>+₹{evaluation.recommended_lift} Lift over Ship As-Is</span>
                        </span>
                      )}
                    </div>
                    <p className="mt-2 text-sm text-emerald-900 font-medium">
                      {evaluation.explanation_data.primary_reason}
                    </p>
                    {evaluation.ml_operating_mode && (
                      <div className="mt-3 flex flex-wrap items-center gap-2 text-xs border-t border-emerald-200/60 pt-2.5">
                        <span className={`inline-flex items-center gap-1 rounded px-2 py-0.5 font-bold ${
                          evaluation.ml_operating_mode !== 'DISABLED'
                            ? 'bg-emerald-100 text-emerald-800'
                            : 'bg-slate-200 text-slate-700'
                        }`}>
                          {evaluation.ml_operating_mode !== 'DISABLED' ? 'ML Inference Active' : 'ML Inference Unavailable'}
                        </span>
                        <span className="rounded bg-white/80 px-2 py-0.5 font-medium text-slate-700 border border-slate-200">
                          Policy: {evaluation.decision_policy_version || 'v1.1-ml-assisted'}
                        </span>
                        {evaluation.recommended_action_deterministic && evaluation.recommended_action_ml_assisted && (
                          <span className="text-slate-600 text-[11px]">
                            Rule: <strong className="text-slate-800">{evaluation.recommended_action_deterministic}</strong> | ML Score: <strong className="text-slate-800">{evaluation.recommended_action_ml_assisted}</strong>
                          </span>
                        )}
                        <span className="text-[11px] text-amber-800 font-medium">
                          • Advisory decision support (governance gate restricts automated cancellation)
                        </span>
                      </div>
                    )}
                  </div>

                  {/* Financial Metrics Summary */}
                  <div className="flex items-center gap-4 text-right">
                    <div className="rounded-lg bg-white/80 p-3 shadow-xs">
                      <div className="text-[10px] font-semibold uppercase text-slate-500">Expected Contribution</div>
                      <div className="text-lg font-bold text-slate-900">₹{evaluation.best_ec}</div>
                      <div className="text-[9px] text-slate-400">[ESTIMATED]</div>
                    </div>
                    <div className="rounded-lg bg-white/80 p-3 shadow-xs">
                      <div className="text-[10px] font-semibold uppercase text-slate-500">Profit at Risk (PaR)</div>
                      <div className="text-lg font-bold text-rose-600">₹{evaluation.profit_at_risk}</div>
                      <div className="text-[9px] text-slate-400">[ESTIMATED]</div>
                    </div>
                    <div className="rounded-lg bg-white/80 p-3 shadow-xs">
                      <div className="text-[10px] font-semibold uppercase text-slate-500">Baseline RTO Risk</div>
                      <div className="text-lg font-bold text-amber-600">
                        {Math.round(parseFloat(evaluation.baseline_p_rto) * 100)}%
                      </div>
                      <div className="text-[9px] text-slate-400">Uncertainty: {evaluation.uncertainty_score}</div>
                    </div>
                  </div>
                </div>

                {/* Decision Execution Bar */}
                <div className="mt-5 flex items-center justify-between border-t border-emerald-200/80 pt-4">
                  <div className="flex items-center space-x-2 text-xs text-emerald-900">
                    <span className="font-semibold">Status:</span>
                    <span className="rounded bg-white px-2 py-0.5 font-bold shadow-xs">
                      {evaluation.decision_status}
                    </span>
                    {evaluation.selected_action && (
                      <span className="text-slate-600">
                        (Selected: <strong className="text-slate-800">{evaluation.selected_action}</strong>)
                      </span>
                    )}
                  </div>

                  <div className="flex items-center space-x-3">
                    {evaluation.decision_status === 'EVALUATED' && (
                      <>
                        <button
                          type="button"
                          onClick={() => setShowOverride(!showOverride)}
                          className="rounded-lg border border-slate-300 bg-white px-3.5 py-2 text-xs font-semibold text-slate-700 hover:bg-slate-50"
                        >
                          {showOverride ? 'Cancel Override' : 'Override Action...'}
                        </button>
                        <button
                          type="button"
                          disabled={isSubmitting}
                          onClick={handleAcceptRecommendation}
                          className="flex items-center space-x-2 rounded-lg bg-emerald-600 px-5 py-2 text-xs font-bold text-white shadow-sm hover:bg-emerald-700 disabled:opacity-50"
                        >
                          {isSubmitting ? (
                            <Loader2 className="h-4 w-4 animate-spin" />
                          ) : (
                            <Check className="h-4 w-4" />
                          )}
                          <span>Accept Recommendation</span>
                        </button>
                      </>
                    )}
                  </div>
                </div>

                {/* Override Dropdown Form */}
                {showOverride && (
                  <div className="mt-4 rounded-lg border border-amber-200 bg-amber-50/60 p-4 space-y-3">
                    <h4 className="text-xs font-bold text-amber-900 uppercase">
                      Override Recommendation with Authorized Alternative
                    </h4>
                    <div className="grid grid-cols-2 gap-3">
                      <div>
                        <label className="text-xs font-semibold text-slate-700">Select Alternative Action:</label>
                        <select
                          value={selectedOverrideAction}
                          onChange={(e) => setSelectedOverrideAction(e.target.value)}
                          className="mt-1 w-full rounded-lg border border-slate-300 bg-white p-2 text-xs font-medium text-slate-800 focus:outline-none"
                        >
                          <option value="SHIP_AS_IS">SHIP_AS_IS</option>
                          <option value="VERIFY_OTP">VERIFY_OTP</option>
                          <option value="INCENTIVIZE_PREPAID">INCENTIVIZE_PREPAID</option>
                          <option value="MANUAL_REVIEW">MANUAL_REVIEW</option>
                          <option value="HOLD_CANCEL">HOLD_CANCEL</option>
                        </select>
                      </div>
                      <div>
                        <label className="text-xs font-semibold text-slate-700">Override Rationale (Mandatory):</label>
                        <input
                          type="text"
                          value={overrideReason}
                          onChange={(e) => setOverrideReason(e.target.value)}
                          placeholder="e.g. Customer verified address via WhatsApp support..."
                          className="mt-1 w-full rounded-lg border border-slate-300 bg-white p-2 text-xs text-slate-800 focus:outline-none"
                        />
                      </div>
                    </div>
                    <div className="flex justify-end">
                      <button
                        type="button"
                        disabled={isSubmitting || !overrideReason.trim()}
                        onClick={handleRecordOverride}
                        className="rounded-lg bg-amber-600 px-4 py-1.5 text-xs font-bold text-white shadow hover:bg-amber-700 disabled:opacity-50"
                      >
                        Confirm Override
                      </button>
                    </div>
                  </div>
                )}
              </div>

              {/* Pre-Dispatch Intervention Resolution Card */}
              {evaluation.intervention_status !== 'NONE' && (
                <div className="rounded-xl border border-blue-200 bg-blue-50/50 p-4 space-y-3">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center space-x-2">
                      <PhoneCall className="h-4 w-4 text-blue-600" />
                      <h4 className="text-sm font-bold text-blue-950">Pre-Dispatch Intervention Outcome</h4>
                      <span className="rounded bg-blue-100 px-2 py-0.5 text-xs font-bold text-blue-800">
                        {evaluation.intervention_status}
                      </span>
                    </div>
                  </div>

                  {evaluation.intervention_status === 'PENDING' && (
                    <div className="space-y-3 pt-2">
                      <p className="text-xs text-slate-600">
                        Record the outcome after sending OTP, dispatching prepaid offer, or conducting manual customer verification:
                      </p>
                      <input
                        type="text"
                        value={outcomeNotes}
                        onChange={(e) => setOutcomeNotes(e.target.value)}
                        placeholder="Optional intervention notes (e.g. Verified landmark, customer confirmed via call)..."
                        className="w-full rounded-lg border border-slate-300 bg-white p-2 text-xs text-slate-800 focus:outline-none"
                      />
                      <div className="flex flex-wrap gap-2">
                        {evaluation.selected_action === 'VERIFY_OTP' && (
                          <div className="w-full space-y-3">
                            <div className="rounded-xl border border-emerald-200 bg-emerald-50/70 p-3.5 space-y-2">
                              <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2">
                                <div>
                                  <div className="flex items-center space-x-2">
                                    <MessageSquare className="h-4 w-4 text-emerald-700" />
                                    <span className="text-xs font-bold text-emerald-950">
                                      WhatsApp Pre-Dispatch OTP Verification
                                    </span>
                                  </div>
                                  <p className="text-[11px] text-emerald-800 mt-0.5">
                                    Dispatches official WhatsApp template with 1-click confirmation buttons to customer.
                                  </p>
                                </div>
                                <button
                                  type="button"
                                  onClick={handleSendWhatsAppOtp}
                                  disabled={isSendingWhatsApp}
                                  className="inline-flex items-center space-x-1.5 rounded-lg bg-emerald-600 px-3 py-1.5 text-xs font-bold text-white shadow-xs hover:bg-emerald-700 transition shrink-0 disabled:opacity-50"
                                >
                                  {isSendingWhatsApp ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Send className="h-3.5 w-3.5" />}
                                  <span>Send WhatsApp OTP</span>
                                </button>
                              </div>

                              {whatsAppFeedback && (
                                <p className="text-[11px] font-semibold text-emerald-900 bg-emerald-100/80 px-2 py-1 rounded flex items-center space-x-1.5">
                                  <CheckCircle className="h-3.5 w-3.5 text-emerald-700" />
                                  <span>{whatsAppFeedback}</span>
                                </p>
                              )}

                              {orderMessages.length > 0 && (
                                <div className="pt-2 border-t border-emerald-200/60 space-y-1">
                                  <span className="text-[10px] uppercase font-bold text-emerald-900 tracking-wider">
                                    Message Delivery Receipts
                                  </span>
                                  <div className="space-y-1 max-h-24 overflow-y-auto">
                                    {orderMessages.map((m) => (
                                      <div key={m.id} className="flex items-center justify-between text-[11px] bg-white p-2 rounded-lg border border-emerald-100 shadow-2xs">
                                        <div className="flex items-center space-x-2">
                                          <span className="font-mono text-slate-800 font-semibold">{m.recipient_phone}</span>
                                          <span className="text-[10px] text-slate-400">({m.direction})</span>
                                        </div>
                                        <div className="flex items-center space-x-2">
                                          <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                                            m.status === 'DELIVERED' || m.status === 'READ'
                                              ? 'bg-emerald-100 text-emerald-800'
                                              : m.status === 'SENT'
                                              ? 'bg-sky-100 text-sky-800'
                                              : m.status === 'FAILED'
                                              ? 'bg-rose-100 text-rose-800'
                                              : 'bg-slate-100 text-slate-800'
                                          }`}>
                                            {m.status}
                                          </span>
                                          <span className="font-mono text-[10px] text-slate-500">₹{m.intervention_cost}</span>
                                        </div>
                                      </div>
                                    ))}
                                  </div>
                                </div>
                              )}
                            </div>

                            <div className="flex flex-wrap gap-2">
                              <button
                                type="button"
                                onClick={() => handleInterventionOutcome('OTP_VERIFIED')}
                                className="rounded-lg bg-emerald-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-emerald-700"
                              >
                                OTP Verified (Confirm Order)
                              </button>
                              <button
                                type="button"
                                onClick={() => handleInterventionOutcome('OTP_FAILED')}
                                className="rounded-lg bg-rose-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-rose-700"
                              >
                                OTP Expired / Failed (Cancel Order)
                              </button>
                            </div>
                          </div>
                        )}
                        {evaluation.selected_action === 'INCENTIVIZE_PREPAID' && (
                          <>
                            <button
                              type="button"
                              onClick={() => handleInterventionOutcome('PREPAID_CONVERTED')}
                              className="rounded-lg bg-emerald-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-emerald-700"
                            >
                              Customer Paid Online (Convert to Prepaid)
                            </button>
                            <button
                              type="button"
                              onClick={() => handleInterventionOutcome('PREPAID_DECLINED')}
                              className="rounded-lg bg-slate-700 px-3 py-1.5 text-xs font-semibold text-white hover:bg-slate-800"
                            >
                              Declined Offer (Ship as Normal COD)
                            </button>
                          </>
                        )}
                        {evaluation.selected_action === 'MANUAL_REVIEW' && (
                          <>
                            <button
                              type="button"
                              onClick={() => handleInterventionOutcome('MANUAL_APPROVED')}
                              className="rounded-lg bg-emerald-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-emerald-700"
                            >
                              Agent Approved (Confirm Order)
                            </button>
                            <button
                              type="button"
                              onClick={() => handleInterventionOutcome('MANUAL_REJECTED')}
                              className="rounded-lg bg-rose-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-rose-700"
                            >
                              Agent Rejected / Fake Order (Cancel)
                            </button>
                          </>
                        )}
                      </div>
                    </div>
                  )}
                </div>
              )}

              {/* 5-Action Candidate Comparison Table */}
              <div>
                <div className="mb-2 flex items-center justify-between">
                  <h4 className="text-sm font-bold text-slate-800">
                    5-Action Expected Contribution Comparison [ESTIMATED]
                  </h4>
                  <span className="text-[11px] text-slate-400">
                    Intervention costs deducted exactly once
                  </span>
                </div>
                <div className="overflow-x-auto rounded-xl border border-slate-200">
                  <table className="w-full text-left text-xs">
                    <thead className="border-b bg-slate-50 font-semibold text-slate-600">
                      <tr>
                        <th className="px-4 py-3">Action</th>
                        <th className="px-4 py-3">Policy Eligibility</th>
                        <th className="px-4 py-3">Intervention Cost</th>
                        <th className="px-4 py-3">Expected Contribution (EC)</th>
                        <th className="px-4 py-3">Incremental Lift</th>
                        <th className="px-4 py-3">Key Probability Assumptions</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100 font-mono">
                      {evaluation.comparison_data.map((actionItem) => (
                        <tr
                          key={actionItem.action}
                          className={`transition ${
                            actionItem.is_recommended ? 'bg-emerald-50/50 font-bold' : 'hover:bg-slate-50/50'
                          }`}
                        >
                          <td className="px-4 py-3">
                            <div className="flex items-center space-x-2">
                              <span className="font-sans font-bold text-slate-900">{actionItem.action}</span>
                              {actionItem.is_recommended && (
                                <span className="rounded bg-emerald-100 px-1.5 py-0.5 text-[10px] font-bold text-emerald-800">
                                  RECOMMENDED
                                </span>
                              )}
                            </div>
                          </td>
                          <td className="px-4 py-3 font-sans">
                            {actionItem.is_policy_eligible ? (
                              <span className="inline-flex items-center text-emerald-700">
                                <CheckCircle className="mr-1 h-3.5 w-3.5" /> Eligible
                              </span>
                            ) : (
                              <span
                                className="inline-flex items-center text-slate-400"
                                title={actionItem.disqualification_reason}
                              >
                                <XCircle className="mr-1 h-3.5 w-3.5 text-slate-400" /> Disqualified
                              </span>
                            )}
                          </td>
                          <td className="px-4 py-3 text-slate-700">
                            ₹{actionItem.intervention_cost}
                          </td>
                          <td className="px-4 py-3 text-slate-900 font-bold">
                            ₹{actionItem.expected_contribution}
                          </td>
                          <td className="px-4 py-3">
                            {parseFloat(actionItem.lift_vs_ship_as_is) > 0 ? (
                              <span className="text-emerald-700">+₹{actionItem.lift_vs_ship_as_is}</span>
                            ) : parseFloat(actionItem.lift_vs_ship_as_is) < 0 ? (
                              <span className="text-rose-600">₹{actionItem.lift_vs_ship_as_is}</span>
                            ) : (
                              <span className="text-slate-400">—</span>
                            )}
                          </td>
                          <td className="px-4 py-3 font-sans text-[11px] text-slate-600">
                            {Object.entries(actionItem.probabilities).map(([k, v]) => (
                              <span key={k} className="mr-2 inline-block">
                                {k}: <strong className="font-mono text-slate-800">{v}</strong>
                              </span>
                            ))}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>

              {/* Triggered Rules & Policy Guards Grid */}
              <div className="grid grid-cols-2 gap-4">
                {/* Triggered Rules */}
                <div className="rounded-xl border border-slate-200 bg-white p-4">
                  <h4 className="mb-3 text-xs font-bold uppercase tracking-wider text-slate-600">
                    Triggered Risk Rules ({evaluation.explanation_data.triggered_rules.length})
                  </h4>
                  <div className="space-y-2.5">
                    {evaluation.explanation_data.triggered_rules.map((rule, idx) => (
                      <div key={idx} className="rounded-lg bg-slate-50 p-2.5 text-xs">
                        <div className="flex items-center justify-between">
                          <span className="font-semibold text-slate-800">{rule.factor}</span>
                          <span className="font-mono font-bold text-amber-700">{rule.risk_delta}</span>
                        </div>
                        <p className="mt-1 text-[11px] text-slate-500">{rule.description}</p>
                      </div>
                    ))}
                  </div>
                </div>

                {/* Policy Guards & Disclosures */}
                <div className="rounded-xl border border-slate-200 bg-white p-4">
                  <h4 className="mb-3 text-xs font-bold uppercase tracking-wider text-slate-600">
                    Merchant Policy Guards & Assumptions [CONFIGURED]
                  </h4>
                  <div className="space-y-2.5">
                    {evaluation.explanation_data.policy_guards.map((guard, idx) => (
                      <div key={idx} className="rounded-lg bg-slate-50 p-2.5 text-xs">
                        <div className="flex items-center space-x-1.5">
                          {guard.passed ? (
                            <CheckCircle className="h-3.5 w-3.5 text-emerald-600" />
                          ) : (
                            <AlertTriangle className="h-3.5 w-3.5 text-amber-600" />
                          )}
                          <span className="font-semibold text-slate-800">{guard.guard_name}</span>
                        </div>
                        <p className="mt-1 text-[11px] text-slate-500">{guard.detail}</p>
                      </div>
                    ))}
                    <div className="border-t border-slate-100 pt-2 text-[10px] text-slate-400">
                      Accounting Mode: {evaluation.explanation_data.financial_assumptions.tax_accounting_mode} | COGS: ₹{evaluation.explanation_data.financial_assumptions.cogs_amount} | COD Fee Incurred: {evaluation.explanation_data.financial_assumptions.cod_fee_incurred_on}
                    </div>
                    <div className="rounded-lg bg-amber-50/80 border border-amber-200/70 p-2.5 text-xs">
                      <div className="flex items-center text-[11px] font-semibold text-amber-900 mb-0.5">
                        <Info className="h-3.5 w-3.5 mr-1 text-amber-700 inline" />
                        Operational Decision Assumptions
                      </div>
                      <p className="text-[10px] text-amber-800 leading-relaxed">
                        Expected contribution projections are computed from merchant economics rate cards and operational baseline assumptions (e.g., OTP confirmation, prepaid conversion), not machine-learned predictions.
                      </p>
                    </div>
                  </div>
                </div>
              </div>
            </>
          ) : null}
        </div>
      </div>
    </div>
  );
};
