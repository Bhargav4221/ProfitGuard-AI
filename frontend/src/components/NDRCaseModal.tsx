'use client';

import React, { useState, useEffect } from 'react';
import {
  ShieldAlert,
  CheckCircle,
  XCircle,
  AlertTriangle,
  RotateCcw,
  Clock,
  Phone,
  MessageSquare,
  MapPin,
  Calendar,
  Send,
  X,
  Loader2,
  TrendingUp,
  Info,
  DollarSign,
  ChevronRight,
  UserCheck,
} from 'lucide-react';
import { NDRCase, NDRRecommendation } from '@/types';
import {
  fetchNDRCase,
  fetchNDRRecommendation,
  recordNDRAction,
  sendWhatsAppNdrRecovery,
} from '@/services/api';

interface NDRCaseModalProps {
  caseId: string | null;
  isOpen: boolean;
  onClose: () => void;
  onCaseUpdated: () => void;
}

export const NDRCaseModal: React.FC<NDRCaseModalProps> = ({
  caseId,
  isOpen,
  onClose,
  onCaseUpdated,
}) => {
  const [ndrCase, setNdrCase] = useState<NDRCase | null>(null);
  const [recommendation, setRecommendation] = useState<NDRRecommendation | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  // Active action tab: 'CONTACT' | 'ADDRESS' | 'REATTEMPT' | 'ESCALATE' | 'RTO' | 'CLOSE'
  const [activeTab, setActiveTab] = useState<'CONTACT' | 'ADDRESS' | 'REATTEMPT' | 'ESCALATE' | 'RTO'>('CONTACT');

  // Form states
  const [contactMethod, setContactMethod] = useState<'WHATSAPP' | 'CALL' | 'SMS'>('WHATSAPP');
  const [customerResponse, setCustomerResponse] = useState('');
  const [updatedAddress1, setUpdatedAddress1] = useState('');
  const [updatedCity, setUpdatedCity] = useState('');
  const [updatedPincode, setUpdatedPincode] = useState('');
  const [updatedPhone, setUpdatedPhone] = useState('');
  const [reattemptDate, setReattemptDate] = useState('');
  const [closureReason, setClosureReason] = useState('');
  const [notes, setNotes] = useState('');

  useEffect(() => {
    if (isOpen && caseId) {
      loadCaseData(caseId);
    } else {
      setNdrCase(null);
      setRecommendation(null);
      setErrorMsg(null);
      setSuccessMsg(null);
    }
  }, [isOpen, caseId]);

  const loadCaseData = async (id: string) => {
    setIsLoading(true);
    setErrorMsg(null);
    try {
      const [caseData, recData] = await Promise.all([
        fetchNDRCase(id),
        fetchNDRRecommendation(id).catch(() => null),
      ]);
      setNdrCase(caseData);
      setRecommendation(recData);

      // Pre-fill address from existing case or order
      setUpdatedAddress1(caseData.updated_address1 || '');
      setUpdatedCity(caseData.updated_city || caseData.shipping_city || '');
      setUpdatedPincode(caseData.updated_pincode || caseData.shipping_pincode || '');
      setUpdatedPhone(caseData.updated_phone || caseData.customer_phone || '');
    } catch (err: any) {
      setErrorMsg(err.message || 'Failed to load NDR case');
    } finally {
      setIsLoading(false);
    }
  };

  const handleExecuteAction = async (actionType: string) => {
    if (!caseId) return;
    setIsSubmitting(true);
    setErrorMsg(null);
    setSuccessMsg(null);

    try {
      let payload: any = { action_type: actionType, notes: notes || undefined };

      if (actionType === 'CONTACT_CUSTOMER') {
        payload.contact_method = contactMethod;
        payload.customer_response = customerResponse || undefined;
        if (contactMethod === 'WHATSAPP') {
          try {
            await sendWhatsAppNdrRecovery(caseId, undefined, notes || undefined);
          } catch (waErr: any) {
            console.warn('WhatsApp recovery dispatch warning:', waErr);
          }
        }
      } else if (actionType === 'VERIFY_ADDRESS') {
        payload.updated_address1 = updatedAddress1 || undefined;
        payload.updated_city = updatedCity || undefined;
        payload.updated_pincode = updatedPincode || undefined;
        payload.updated_phone = updatedPhone || undefined;
      } else if (actionType === 'SCHEDULE_REATTEMPT') {
        payload.reattempt_date = reattemptDate ? new Date(reattemptDate).toISOString() : undefined;
      } else if (actionType === 'REQUEST_RTO' || actionType === 'CLOSE_CASE') {
        payload.closure_reason = closureReason || undefined;
      }

      const updated = await recordNDRAction(caseId, payload);
      setNdrCase(updated);
      setSuccessMsg(`Action ${actionType} recorded successfully!`);
      onCaseUpdated();
    } catch (err: any) {
      setErrorMsg(err.message || 'Action failed to submit');
    } finally {
      setIsSubmitting(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/60 p-4 backdrop-blur-sm animate-in fade-in duration-200">
      <div className="flex max-h-[92vh] w-full max-w-4xl flex-col rounded-2xl bg-white shadow-2xl border border-slate-200 overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-slate-200 bg-slate-50/80 px-6 py-4">
          <div className="flex items-center space-x-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-rose-600 text-white shadow-md shadow-rose-500/20">
              <RotateCcw className="h-5 w-5" />
            </div>
            <div>
              <div className="flex items-center space-x-2">
                <h3 className="text-base font-bold text-slate-900">
                  NDR Recovery Case: {ndrCase?.case_number || 'Loading...'}
                </h3>
                {ndrCase?.is_simulated && (
                  <span className="rounded bg-amber-100 px-2 py-0.5 text-[10px] font-bold text-amber-800">
                    [SIMULATED]
                  </span>
                )}
                <span
                  className={`rounded px-2 py-0.5 text-[10px] font-bold ${
                    ndrCase?.priority === 'HIGH'
                      ? 'bg-rose-100 text-rose-800'
                      : ndrCase?.priority === 'MEDIUM'
                      ? 'bg-amber-100 text-amber-800'
                      : 'bg-blue-100 text-blue-800'
                  }`}
                >
                  {ndrCase?.priority} PRIORITY
                </span>
              </div>
              <p className="text-xs text-slate-500">
                Order <span className="font-mono font-medium text-slate-700">{ndrCase?.order_external_id}</span> •{' '}
                Customer: <span className="font-medium text-slate-700">{ndrCase?.customer_name}</span> (
                {ndrCase?.customer_phone})
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-200 hover:text-slate-600 transition"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Modal Body */}
        <div className="flex-1 overflow-y-auto p-6 space-y-6">
          {isLoading ? (
            <div className="flex flex-col items-center justify-center py-16 space-y-3 text-slate-400">
              <Loader2 className="h-8 w-8 animate-spin text-rose-600" />
              <p className="text-sm">Loading recovery case & calculating economic lift...</p>
            </div>
          ) : errorMsg ? (
            <div className="rounded-xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-800 flex items-start space-x-3">
              <AlertTriangle className="h-5 w-5 flex-shrink-0 text-rose-600 mt-0.5" />
              <div>
                <p className="font-semibold">Error Loading Case</p>
                <p className="text-xs mt-0.5 text-rose-700">{errorMsg}</p>
              </div>
            </div>
          ) : ndrCase ? (
            <>
              {/* Success Notification */}
              {successMsg && (
                <div className="rounded-xl border border-emerald-200 bg-emerald-50 p-3.5 text-xs text-emerald-800 flex items-center space-x-2">
                  <CheckCircle className="h-4 w-4 text-emerald-600 flex-shrink-0" />
                  <span>{successMsg}</span>
                </div>
              )}

              {/* Status and Case Attributes Card */}
              <div className="grid grid-cols-1 md:grid-cols-4 gap-4 bg-slate-50 p-4 rounded-xl border border-slate-200 text-xs">
                <div>
                  <span className="text-slate-400 block font-medium">Case Status</span>
                  <span className="font-bold text-slate-800 uppercase mt-0.5 block">{ndrCase.status}</span>
                </div>
                <div>
                  <span className="text-slate-400 block font-medium">Failure Reason</span>
                  <span className="font-bold text-rose-700 mt-0.5 block">{ndrCase.reason_code}</span>
                </div>
                <div>
                  <span className="text-slate-400 block font-medium">Attempts Made</span>
                  <span className="font-bold text-slate-800 mt-0.5 block">{ndrCase.attempt_count} / 3</span>
                </div>
                <div>
                  <span className="text-slate-400 block font-medium">Order Value (GMV)</span>
                  <span className="font-bold text-slate-900 mt-0.5 block">
                    ₹{parseFloat(ndrCase.order_value || '0').toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                  </span>
                </div>
              </div>

              {/* Decision Support & Economic Recommendation Card */}
              {recommendation && (
                <div className="rounded-xl border border-emerald-200 bg-emerald-50/60 p-5 shadow-sm space-y-3">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center space-x-2">
                      <TrendingUp className="h-5 w-5 text-emerald-600" />
                      <span className="text-xs font-bold uppercase tracking-wider text-emerald-900">
                        AI Recovery Decision Support [ESTIMATED]
                      </span>
                    </div>
                    <span className="rounded-full bg-emerald-100 px-3 py-1 text-xs font-bold text-emerald-800">
                      Recommended: {recommendation.recommended_action}
                    </span>
                  </div>

                  <p className="text-xs text-slate-700 leading-relaxed">{recommendation.rationale}</p>

                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 pt-2 border-t border-emerald-200/80 text-xs">
                    <div>
                      <span className="text-slate-500 block text-[11px]">Recovery Lift (Δ Lift)</span>
                      <span className="text-base font-extrabold text-emerald-700">
                        +₹{parseFloat(recommendation.expected_recovery_lift).toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                      </span>
                    </div>
                    <div>
                      <span className="text-slate-500 block text-[11px]">Profit at Risk (PaR)</span>
                      <span className="text-sm font-bold text-slate-900">
                        ₹{parseFloat(recommendation.profit_at_risk).toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                      </span>
                    </div>
                    <div>
                      <span className="text-slate-500 block text-[11px]">Estimated Rescue Prob</span>
                      <span className="text-sm font-bold text-slate-900">
                        {Math.round(parseFloat(recommendation.estimated_rescue_prob) * 100)}%
                      </span>
                    </div>
                    <div>
                      <span className="text-slate-500 block text-[11px]">Intervention Cost</span>
                      <span className="text-sm font-bold text-slate-700">
                        ₹{parseFloat(recommendation.intervention_cost).toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                      </span>
                    </div>
                  </div>

                  <div className="text-[10px] text-slate-500 bg-white/70 p-2 rounded-lg border border-emerald-100">
                    <span className="font-semibold text-slate-700">Zero Double-Counting Notice: </span>
                    Forward shipping is sunk. Reverse shipping is avoided on successful rescue. Intervention cost deducted exactly once.
                  </div>
                </div>
              )}

              {/* Permitted Recovery Actions Section */}
              <div className="space-y-4">
                <div className="flex items-center justify-between border-b border-slate-200 pb-2">
                  <h4 className="text-sm font-bold text-slate-900">Permitted Recovery Actions</h4>
                  <span className="text-xs text-slate-400">Select intervention to execute</span>
                </div>

                {/* Action Tabs */}
                <div className="flex flex-wrap gap-2">
                  <button
                    type="button"
                    onClick={() => setActiveTab('CONTACT')}
                    className={`flex items-center space-x-1.5 px-3 py-2 rounded-lg text-xs font-semibold transition ${
                      activeTab === 'CONTACT'
                        ? 'bg-emerald-600 text-white shadow-sm'
                        : 'bg-slate-100 text-slate-700 hover:bg-slate-200'
                    }`}
                  >
                    <MessageSquare className="h-3.5 w-3.5" />
                    <span>Contact Customer</span>
                  </button>

                  <button
                    type="button"
                    onClick={() => setActiveTab('ADDRESS')}
                    className={`flex items-center space-x-1.5 px-3 py-2 rounded-lg text-xs font-semibold transition ${
                      activeTab === 'ADDRESS'
                        ? 'bg-emerald-600 text-white shadow-sm'
                        : 'bg-slate-100 text-slate-700 hover:bg-slate-200'
                    }`}
                  >
                    <MapPin className="h-3.5 w-3.5" />
                    <span>Verify Address</span>
                  </button>

                  <button
                    type="button"
                    onClick={() => setActiveTab('REATTEMPT')}
                    className={`flex items-center space-x-1.5 px-3 py-2 rounded-lg text-xs font-semibold transition ${
                      activeTab === 'REATTEMPT'
                        ? 'bg-emerald-600 text-white shadow-sm'
                        : 'bg-slate-100 text-slate-700 hover:bg-slate-200'
                    }`}
                  >
                    <Calendar className="h-3.5 w-3.5" />
                    <span>Schedule Reattempt</span>
                  </button>

                  <button
                    type="button"
                    onClick={() => setActiveTab('ESCALATE')}
                    className={`flex items-center space-x-1.5 px-3 py-2 rounded-lg text-xs font-semibold transition ${
                      activeTab === 'ESCALATE'
                        ? 'bg-amber-600 text-white shadow-sm'
                        : 'bg-slate-100 text-slate-700 hover:bg-slate-200'
                    }`}
                  >
                    <UserCheck className="h-3.5 w-3.5" />
                    <span>Escalate Review</span>
                  </button>

                  <button
                    type="button"
                    onClick={() => setActiveTab('RTO')}
                    className={`flex items-center space-x-1.5 px-3 py-2 rounded-lg text-xs font-semibold transition ${
                      activeTab === 'RTO'
                        ? 'bg-rose-600 text-white shadow-sm'
                        : 'bg-slate-100 text-slate-700 hover:bg-slate-200'
                    }`}
                  >
                    <XCircle className="h-3.5 w-3.5" />
                    <span>Initiate RTO</span>
                  </button>
                </div>

                {/* Tab Forms */}
                <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm space-y-4">
                  {activeTab === 'CONTACT' && (
                    <div className="space-y-3">
                      <div>
                        <label className="block text-xs font-semibold text-slate-700 mb-1">Contact Method</label>
                        <div className="flex space-x-3">
                          {(['WHATSAPP', 'CALL', 'SMS'] as const).map((m) => (
                            <label key={m} className="flex items-center space-x-2 text-xs text-slate-700 cursor-pointer">
                              <input
                                type="radio"
                                name="contactMethod"
                                checked={contactMethod === m}
                                onChange={() => setContactMethod(m)}
                                className="text-emerald-600 focus:ring-emerald-500"
                              />
                              <span>{m}</span>
                            </label>
                          ))}
                        </div>
                      </div>
                      <div>
                        <label className="block text-xs font-semibold text-slate-700 mb-1">Customer Response / Feedback</label>
                        <textarea
                          rows={2}
                          value={customerResponse}
                          onChange={(e) => setCustomerResponse(e.target.value)}
                          placeholder="e.g. Customer confirmed they were at work and requested delivery tomorrow after 3 PM"
                          className="w-full rounded-lg border border-slate-300 p-2.5 text-xs text-slate-800 focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500"
                        />
                      </div>
                      <button
                        type="button"
                        disabled={isSubmitting}
                        onClick={() => handleExecuteAction('CONTACT_CUSTOMER')}
                        className="inline-flex items-center space-x-2 rounded-lg bg-emerald-600 px-4 py-2 text-xs font-semibold text-white hover:bg-emerald-700 disabled:opacity-50"
                      >
                        {isSubmitting && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
                        <span>Record Customer Contact</span>
                      </button>
                    </div>
                  )}

                  {activeTab === 'ADDRESS' && (
                    <div className="space-y-3">
                      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                        <div className="md:col-span-2">
                          <label className="block text-xs font-semibold text-slate-700 mb-1">Corrected Street Address</label>
                          <input
                            type="text"
                            value={updatedAddress1}
                            onChange={(e) => setUpdatedAddress1(e.target.value)}
                            placeholder="Flat/House No, Building, Landmark"
                            className="w-full rounded-lg border border-slate-300 p-2.5 text-xs text-slate-800 focus:border-emerald-500"
                          />
                        </div>
                        <div>
                          <label className="block text-xs font-semibold text-slate-700 mb-1">City</label>
                          <input
                            type="text"
                            value={updatedCity}
                            onChange={(e) => setUpdatedCity(e.target.value)}
                            className="w-full rounded-lg border border-slate-300 p-2.5 text-xs text-slate-800"
                          />
                        </div>
                        <div>
                          <label className="block text-xs font-semibold text-slate-700 mb-1">Postal Pincode</label>
                          <input
                            type="text"
                            value={updatedPincode}
                            onChange={(e) => setUpdatedPincode(e.target.value)}
                            maxLength={6}
                            className="w-full rounded-lg border border-slate-300 p-2.5 text-xs text-slate-800"
                          />
                        </div>
                        <div>
                          <label className="block text-xs font-semibold text-slate-700 mb-1">Alternate Phone</label>
                          <input
                            type="text"
                            value={updatedPhone}
                            onChange={(e) => setUpdatedPhone(e.target.value)}
                            placeholder="10-digit mobile"
                            className="w-full rounded-lg border border-slate-300 p-2.5 text-xs text-slate-800"
                          />
                        </div>
                      </div>
                      <button
                        type="button"
                        disabled={isSubmitting}
                        onClick={() => handleExecuteAction('VERIFY_ADDRESS')}
                        className="inline-flex items-center space-x-2 rounded-lg bg-emerald-600 px-4 py-2 text-xs font-semibold text-white hover:bg-emerald-700 disabled:opacity-50"
                      >
                        {isSubmitting && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
                        <span>Update Delivery Address</span>
                      </button>
                    </div>
                  )}

                  {activeTab === 'REATTEMPT' && (
                    <div className="space-y-3">
                      <div>
                        <label className="block text-xs font-semibold text-slate-700 mb-1">Reattempt Date</label>
                        <input
                          type="datetime-local"
                          value={reattemptDate}
                          onChange={(e) => setReattemptDate(e.target.value)}
                          className="rounded-lg border border-slate-300 p-2.5 text-xs text-slate-800"
                        />
                      </div>
                      <button
                        type="button"
                        disabled={isSubmitting}
                        onClick={() => handleExecuteAction('SCHEDULE_REATTEMPT')}
                        className="inline-flex items-center space-x-2 rounded-lg bg-emerald-600 px-4 py-2 text-xs font-semibold text-white hover:bg-emerald-700 disabled:opacity-50"
                      >
                        {isSubmitting && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
                        <span>Confirm Courier Reattempt</span>
                      </button>
                    </div>
                  )}

                  {activeTab === 'ESCALATE' && (
                    <div className="space-y-3">
                      <p className="text-xs text-slate-600">
                        Escalate this order to a senior tele-calling operator. Marks priority as <strong>HIGH</strong>.
                      </p>
                      <button
                        type="button"
                        disabled={isSubmitting}
                        onClick={() => handleExecuteAction('ESCALATE_TO_MANUAL_REVIEW')}
                        className="inline-flex items-center space-x-2 rounded-lg bg-amber-600 px-4 py-2 text-xs font-semibold text-white hover:bg-amber-700 disabled:opacity-50"
                      >
                        {isSubmitting && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
                        <span>Escalate Case</span>
                      </button>
                    </div>
                  )}

                  {activeTab === 'RTO' && (
                    <div className="space-y-3">
                      <p className="text-xs text-rose-700">
                        Initiate return to origin immediately. Stops further reattempt charges and returns goods to warehouse.
                      </p>
                      <div>
                        <label className="block text-xs font-semibold text-slate-700 mb-1">RTO Reason</label>
                        <input
                          type="text"
                          value={closureReason}
                          onChange={(e) => setClosureReason(e.target.value)}
                          placeholder="e.g. Customer cancelled order / confirmed refusal"
                          className="w-full rounded-lg border border-slate-300 p-2.5 text-xs text-slate-800"
                        />
                      </div>
                      <button
                        type="button"
                        disabled={isSubmitting}
                        onClick={() => handleExecuteAction('REQUEST_RTO')}
                        className="inline-flex items-center space-x-2 rounded-lg bg-rose-600 px-4 py-2 text-xs font-semibold text-white hover:bg-rose-700 disabled:opacity-50"
                      >
                        {isSubmitting && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
                        <span>Initiate RTO</span>
                      </button>
                    </div>
                  )}
                </div>
              </div>

              {/* Action History Audit Timeline */}
              <div className="space-y-3 pt-2">
                <h4 className="text-xs font-bold uppercase tracking-wider text-slate-500">Case Audit Timeline</h4>
                {ndrCase.actions && ndrCase.actions.length > 0 ? (
                  <div className="space-y-2">
                    {ndrCase.actions.map((act) => (
                      <div key={act.id} className="flex items-start space-x-3 rounded-lg bg-slate-50 p-3 text-xs border border-slate-200">
                        <div className="h-2 w-2 rounded-full bg-emerald-500 mt-1.5 flex-shrink-0" />
                        <div className="flex-1">
                          <div className="flex items-center justify-between">
                            <span className="font-bold text-slate-900">{act.action_type}</span>
                            <span className="text-[10px] text-slate-400">
                              {new Date(act.created_at).toLocaleString('en-IN')}
                            </span>
                          </div>
                          <p className="text-slate-600 mt-0.5">{act.notes || JSON.stringify(act.action_details)}</p>
                          <span className="text-[10px] text-slate-400 mt-1 block">
                            Cost Incurred: ₹{parseFloat(act.intervention_cost).toFixed(2)}
                          </span>
                        </div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <p className="text-xs text-slate-400 italic">No interventions logged yet on this case.</p>
                )}
              </div>
            </>
          ) : null}
        </div>

        {/* Footer */}
        <div className="border-t border-slate-200 bg-slate-50 px-6 py-3.5 flex justify-end">
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg border border-slate-300 bg-white px-4 py-2 text-xs font-semibold text-slate-700 hover:bg-slate-50"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
};
