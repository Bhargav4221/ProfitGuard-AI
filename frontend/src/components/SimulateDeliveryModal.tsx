'use client';

import React, { useState, useEffect, useMemo, useCallback } from 'react';
import {
  Truck,
  X,
  Loader2,
  AlertCircle,
  AlertTriangle,
  CheckCircle2,
  ArrowRight,
  Clock,
  RotateCcw,
  Ban,
  Package,
  History,
  ShieldCheck,
  Check,
  Play,
  RotateCw,
} from 'lucide-react';
import { Order, DeliveryEvent } from '@/types';
import {
  simulateDeliveryEvent,
  fetchOrderDeliveryEvents,
  fetchOrderDetails,
  confirmOrder,
  resumeOrder,
} from '@/services/api';

interface SimulateDeliveryModalProps {
  order: Order | null;
  isOpen: boolean;
  onClose: () => void;
  onEventSimulated: () => void;
}

// Lifecycle sequence definition
const LIFECYCLE_STEPS = [
  { key: 'PENDING', label: 'Pending', desc: 'Awaiting Evaluation / Confirmation' },
  { key: 'CONFIRMED', label: 'Confirmed', desc: 'Order Confirmed' },
  { key: 'READY_TO_SHIP', label: 'Ready to Ship', desc: 'Label Generated / Packed' },
  { key: 'SHIPPED', label: 'Shipped', desc: 'Handed to Courier' },
  { key: 'OUT_FOR_DELIVERY', label: 'Out for Delivery', desc: 'With Courier Agent' },
  { key: 'NDR', label: 'NDR / Failed', desc: 'Delivery Attempt Failed' },
  { key: 'DELIVERED', label: 'Delivered', desc: 'Terminal Settlement' },
];

// Mapping each incoming courier scan event to resulting Order.status in backend
export const EVENT_TO_STATUS_MAP: Record<string, string> = {
  CONFIRMED: 'CONFIRMED',
  ORDER_CONFIRMED: 'CONFIRMED',
  READY_TO_SHIP: 'READY_TO_SHIP',
  MANIFESTED: 'SHIPPED',
  PICKED_UP: 'SHIPPED',
  IN_TRANSIT: 'SHIPPED',
  SHIPPED: 'SHIPPED',
  OUT_FOR_DELIVERY: 'OUT_FOR_DELIVERY',
  DELIVERY_ATTEMPT_FAILED: 'NDR',
  NDR: 'NDR',
  UNDELIVERED: 'NDR',
  DELIVERED: 'DELIVERED',
  RTO_INITIATED: 'RTO',
  RTO_IN_TRANSIT: 'RTO',
  RTO_DELIVERED: 'RTO',
  RTO: 'RTO',
  HOLD: 'HOLD',
  CANCELLED: 'CANCELLED',
};

// Permitted backend target statuses from current Order.status
// Mirroring backend DeliveryService.ALLOWED_TRANSITIONS
export const ALLOWED_STATUS_TRANSITIONS: Record<string, string[]> = {
  PENDING: ['CONFIRMED', 'HOLD', 'CANCELLED'],
  CONFIRMED: ['READY_TO_SHIP', 'HOLD', 'CANCELLED'],
  HOLD: ['CONFIRMED', 'READY_TO_SHIP', 'CANCELLED'],
  READY_TO_SHIP: ['SHIPPED', 'HOLD', 'CANCELLED'],
  SHIPPED: ['OUT_FOR_DELIVERY', 'DELIVERED', 'NDR', 'RTO'],
  OUT_FOR_DELIVERY: ['DELIVERED', 'NDR', 'RTO'],
  NDR: ['OUT_FOR_DELIVERY', 'DELIVERED', 'RTO', 'CANCELLED'],
  DELIVERED: [],
  RTO: [],
  CANCELLED: [],
};

// Helper checking if an event is permitted from current status
export function isEventPermitted(currentStatus: string, eventType: string): boolean {
  const targetStatus = EVENT_TO_STATUS_MAP[eventType] || eventType;
  const allowedTargets = ALLOWED_STATUS_TRANSITIONS[currentStatus] || [];
  return allowedTargets.includes(targetStatus);
}

// Logical recommended next event to guide the user seamlessly
export const RECOMMENDED_NEXT_EVENT: Record<string, string> = {
  PENDING: 'CONFIRMED',
  CONFIRMED: 'READY_TO_SHIP',
  HOLD: 'CONFIRMED',
  READY_TO_SHIP: 'SHIPPED',
  SHIPPED: 'OUT_FOR_DELIVERY',
  OUT_FOR_DELIVERY: 'DELIVERY_ATTEMPT_FAILED',
  NDR: 'OUT_FOR_DELIVERY',
};

export const ALL_EVENTS = [
  { value: 'CONFIRMED', label: 'CONFIRMED — Order Confirmed by Merchant', target: 'CONFIRMED' },
  { value: 'READY_TO_SHIP', label: 'READY_TO_SHIP — Packed & Manifested', target: 'READY_TO_SHIP' },
  { value: 'SHIPPED', label: 'SHIPPED — Carrier Picked Up Parcel', target: 'SHIPPED' },
  { value: 'OUT_FOR_DELIVERY', label: 'OUT_FOR_DELIVERY — Out with Delivery Rider', target: 'OUT_FOR_DELIVERY' },
  { value: 'DELIVERY_ATTEMPT_FAILED', label: 'DELIVERY_ATTEMPT_FAILED — Delivery Attempt Failed (Creates NDR Case)', target: 'NDR' },
  { value: 'DELIVERED', label: 'DELIVERED — Successfully Handed to Customer', target: 'DELIVERED' },
  { value: 'RTO', label: 'RTO — Returned to Origin', target: 'RTO' },
  { value: 'HOLD', label: 'HOLD — Place on Operational Hold', target: 'HOLD' },
  { value: 'CANCELLED', label: 'CANCELLED — Cancel Order', target: 'CANCELLED' },
];

export const SimulateDeliveryModal: React.FC<SimulateDeliveryModalProps> = ({
  order,
  isOpen,
  onClose,
  onEventSimulated,
}) => {
  // Local active order state to reactively update without waiting for parent re-render
  const [activeOrder, setActiveOrder] = useState<Order | null>(order);

  useEffect(() => {
    setActiveOrder(order);
  }, [order]);

  const currentStatus = activeOrder?.status || 'PENDING';
  const isTerminal = ['DELIVERED', 'RTO', 'CANCELLED'].includes(currentStatus);

  const defaultEvent = useMemo(() => {
    const rec = RECOMMENDED_NEXT_EVENT[currentStatus];
    if (rec && isEventPermitted(currentStatus, rec)) return rec;
    const permitted = ALL_EVENTS.find((e) => isEventPermitted(currentStatus, e.value));
    return permitted ? permitted.value : 'CONFIRMED';
  }, [currentStatus]);

  const [eventType, setEventType] = useState<string>(defaultEvent);
  const [reasonCode, setReasonCode] = useState<string>('CUSTOMER_UNAVAILABLE');
  const [carrierName, setCarrierName] = useState<string>(activeOrder?.courier_name || 'Delhivery (Simulated)');
  const [location, setLocation] = useState<string>(activeOrder?.shipping_city ? `${activeOrder.shipping_city} Hub` : 'Regional Delivery Hub');
  const [notes, setNotes] = useState<string>('');
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  // Delivery Events History
  const [events, setEvents] = useState<DeliveryEvent[]>([]);
  const [isLoadingEvents, setIsLoadingEvents] = useState<boolean>(false);

  // Recompute defaults when activeOrder changes
  useEffect(() => {
    if (activeOrder && isOpen) {
      setEventType(defaultEvent);
      setCarrierName(activeOrder.courier_name || 'Delhivery (Simulated)');
      setLocation(activeOrder.shipping_city ? `${activeOrder.shipping_city} Hub` : 'Regional Delivery Hub');
      setErrorMsg(null);
      setSuccessMsg(null);
      loadEvents(activeOrder.id);
    }
  }, [activeOrder?.id, activeOrder?.status, isOpen, defaultEvent]);

  const loadEvents = useCallback(async (orderId: string) => {
    setIsLoadingEvents(true);
    try {
      const data = await fetchOrderDeliveryEvents(orderId);
      setEvents(data);
    } catch {
      setEvents([]);
    } finally {
      setIsLoadingEvents(false);
    }
  }, []);

  if (!isOpen || !activeOrder) return null;

  const refreshCurrentOrder = async (orderId: string) => {
    try {
      const fresh = await fetchOrderDetails(orderId);
      setActiveOrder(fresh);
    } catch {
      // Ignore if fetch fails
    }
  };

  const handleSimulateSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsSubmitting(true);
    setErrorMsg(null);
    setSuccessMsg(null);

    try {
      await simulateDeliveryEvent({
        order_id: activeOrder.id,
        event_type: eventType,
        reason_code: eventType === 'DELIVERY_ATTEMPT_FAILED' ? reasonCode : undefined,
        carrier_name: carrierName,
        location: location,
        notes: notes || (eventType === 'DELIVERY_ATTEMPT_FAILED' ? `Delivery attempt failed: ${reasonCode}` : undefined),
      });

      if (eventType === 'DELIVERY_ATTEMPT_FAILED') {
        setSuccessMsg('[SIMULATED] Recorded failed delivery attempt. NDR Case initialized in NDR Hub.');
      } else {
        setSuccessMsg(`[SIMULATED] Successfully dispatched scan: ${eventType}`);
      }

      await refreshCurrentOrder(activeOrder.id);
      await loadEvents(activeOrder.id);
      onEventSimulated();
    } catch (err: any) {
      setErrorMsg(err.message || 'Simulation transition failed.');
    } finally {
      setIsSubmitting(false);
    }
  };

  // Direct 1-click failed delivery simulation for OUT_FOR_DELIVERY state
  const handleDirectNDRFail = async (reason: string) => {
    setIsSubmitting(true);
    setErrorMsg(null);
    setSuccessMsg(null);

    try {
      await simulateDeliveryEvent({
        order_id: activeOrder.id,
        event_type: 'DELIVERY_ATTEMPT_FAILED',
        reason_code: reason,
        carrier_name: carrierName,
        location: location,
        notes: `Rider doorstep attempt failed: ${reason}`,
      });

      setSuccessMsg('[SIMULATED] Recorded failed delivery attempt. NDR Case initialized in NDR Hub.');
      await refreshCurrentOrder(activeOrder.id);
      await loadEvents(activeOrder.id);
      onEventSimulated();
    } catch (err: any) {
      setErrorMsg(err.message || 'Failed to record delivery attempt failure.');
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleQuickConfirm = async () => {
    setIsSubmitting(true);
    setErrorMsg(null);
    try {
      await confirmOrder(activeOrder.id);
      setSuccessMsg('Order confirmed successfully.');
      await refreshCurrentOrder(activeOrder.id);
      await loadEvents(activeOrder.id);
      onEventSimulated();
    } catch (err: any) {
      setErrorMsg(err.message || 'Failed to confirm order.');
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleQuickResume = async () => {
    setIsSubmitting(true);
    setErrorMsg(null);
    try {
      await resumeOrder(activeOrder.id);
      setSuccessMsg('Order resumed back to CONFIRMED.');
      await refreshCurrentOrder(activeOrder.id);
      await loadEvents(activeOrder.id);
      onEventSimulated();
    } catch (err: any) {
      setErrorMsg(err.message || 'Failed to resume order.');
    } finally {
      setIsSubmitting(false);
    }
  };

  const currentStepIndex = LIFECYCLE_STEPS.findIndex((s) => s.key === currentStatus);
  const isSelectedEventPermitted = isEventPermitted(currentStatus, eventType);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/60 p-4 backdrop-blur-sm animate-in fade-in duration-200">
      <div className="w-full max-w-2xl max-h-[92vh] flex flex-col rounded-2xl bg-white shadow-2xl border border-slate-200 overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-slate-200 bg-slate-50/90 px-6 py-4">
          <div className="flex items-center space-x-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-blue-600 text-white shadow-md shadow-blue-500/20">
              <Truck className="h-5 w-5" />
            </div>
            <div>
              <div className="flex items-center space-x-2">
                <h3 className="text-base font-bold text-slate-900">Delivery Lifecycle Simulator</h3>
                <span className="rounded bg-blue-100 border border-blue-200 px-2 py-0.5 text-[10px] font-mono font-bold text-blue-800">
                  [SIMULATED]
                </span>
              </div>
              <p className="text-xs text-slate-500">
                Order <strong className="text-slate-800 font-mono">#{activeOrder.external_order_id}</strong> •{' '}
                {activeOrder.customer_name || 'Customer'} • {activeOrder.shipping_city || 'India'} (
                <span className="font-semibold text-slate-700">{activeOrder.payment_method}</span> ₹
                {parseFloat(activeOrder.order_value).toLocaleString('en-IN')})
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-200 transition"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {/* Modal Scrollable Content */}
        <div className="flex-1 overflow-y-auto p-6 space-y-5">
          {/* Status Overview Card */}
          <div className="rounded-xl border border-slate-200 bg-slate-50/70 p-4">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <span className="text-[11px] font-semibold uppercase tracking-wider text-slate-400">Current Status</span>
                <div className="flex items-center space-x-2 mt-1">
                  <span
                    className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-bold ${
                      currentStatus === 'DELIVERED'
                        ? 'bg-emerald-100 text-emerald-800'
                        : currentStatus === 'NDR'
                        ? 'bg-rose-100 text-rose-800'
                        : currentStatus === 'OUT_FOR_DELIVERY'
                        ? 'bg-amber-100 text-amber-900 border border-amber-300'
                        : currentStatus === 'HOLD'
                        ? 'bg-amber-100 text-amber-800'
                        : currentStatus === 'CANCELLED' || currentStatus === 'RTO'
                        ? 'bg-slate-200 text-slate-700'
                        : 'bg-blue-100 text-blue-800'
                    }`}
                  >
                    <span className="h-2 w-2 rounded-full bg-current" />
                    {currentStatus}
                  </span>
                  <span className="text-xs text-slate-500 font-medium">
                    Fulfillment: <strong className="text-slate-700 font-semibold">{activeOrder.fulfillment_status}</strong>
                  </span>
                </div>
              </div>

              {/* Contextual Guidance / Quick Actions */}
              <div>
                {currentStatus === 'PENDING' && (
                  <button
                    type="button"
                    onClick={handleQuickConfirm}
                    disabled={isSubmitting}
                    className="inline-flex items-center space-x-1.5 rounded-lg bg-emerald-600 px-3.5 py-1.5 text-xs font-bold text-white shadow-sm hover:bg-emerald-700 transition disabled:opacity-50"
                  >
                    {isSubmitting ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Check className="h-3.5 w-3.5" />}
                    <span>Confirm Order Now</span>
                  </button>
                )}
                {currentStatus === 'HOLD' && (
                  <button
                    type="button"
                    onClick={handleQuickResume}
                    disabled={isSubmitting}
                    className="inline-flex items-center space-x-1.5 rounded-lg bg-amber-600 px-3.5 py-1.5 text-xs font-bold text-white shadow-sm hover:bg-amber-700 transition disabled:opacity-50"
                  >
                    {isSubmitting ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <RotateCw className="h-3.5 w-3.5" />}
                    <span>Resume Order to Confirmed</span>
                  </button>
                )}
                {isTerminal && (
                  <span className="text-xs font-semibold text-slate-500 bg-slate-200 px-2.5 py-1 rounded-lg">
                    Terminal State Reached
                  </span>
                )}
              </div>
            </div>

            {/* Lifecycle Flow Stepper */}
            <div className="mt-4 pt-3 border-t border-slate-200">
              <div className="text-[10px] font-bold uppercase tracking-wider text-slate-400 mb-2">
                Permitted Order Lifecycle Sequence
              </div>
              <div className="grid grid-cols-4 sm:grid-cols-7 gap-1.5 text-center">
                {LIFECYCLE_STEPS.map((step, idx) => {
                  const isCurrent = step.key === currentStatus;
                  const isPast =
                    currentStepIndex !== -1 && idx < currentStepIndex && currentStatus !== 'HOLD' && currentStatus !== 'CANCELLED';
                  const isPermittedTarget = isEventPermitted(currentStatus, step.key);

                  return (
                    <div
                      key={step.key}
                      className={`flex flex-col items-center p-1.5 rounded-lg border text-[10px] transition ${
                        isCurrent
                          ? 'border-blue-500 bg-blue-50 font-bold text-blue-900 ring-2 ring-blue-400/40'
                          : isPast
                          ? 'border-emerald-200 bg-emerald-50/60 font-semibold text-emerald-800'
                          : isPermittedTarget
                          ? 'border-slate-300 bg-white font-medium text-slate-700 hover:border-blue-300'
                          : 'border-slate-100 bg-slate-100/70 text-slate-400'
                      }`}
                    >
                      <div className="mb-1 flex h-4 w-4 items-center justify-center rounded-full text-[9px]">
                        {isPast ? (
                          <CheckCircle2 className="h-3.5 w-3.5 text-emerald-600" />
                        ) : isCurrent ? (
                          <span className="h-2 w-2 rounded-full bg-blue-600 animate-pulse" />
                        ) : (
                          <span className="text-slate-400">{idx + 1}</span>
                        )}
                      </div>
                      <span className="truncate w-full">{step.label}</span>
                    </div>
                  );
                })}
              </div>
            </div>
          </div>

          {/* Feedback banners */}
          {errorMsg && (
            <div className="flex items-start space-x-2 rounded-xl bg-rose-50 border border-rose-200 p-3 text-xs text-rose-800">
              <AlertCircle className="h-4 w-4 text-rose-600 shrink-0 mt-0.5" />
              <div>
                <strong>Transition Rejected:</strong> {errorMsg}
              </div>
            </div>
          )}

          {successMsg && (
            <div className="flex items-start space-x-2 rounded-xl bg-emerald-50 border border-emerald-200 p-3 text-xs text-emerald-800">
              <CheckCircle2 className="h-4 w-4 text-emerald-600 shrink-0 mt-0.5" />
              <div>{successMsg}</div>
            </div>
          )}

          {/* SPECIAL SECTION: OUT_FOR_DELIVERY Dedicated NDR Trigger Section */}
          {currentStatus === 'OUT_FOR_DELIVERY' && (
            <div className="rounded-xl border border-rose-200 bg-rose-50/80 p-4 space-y-3 shadow-sm">
              <div className="flex items-center justify-between">
                <div className="flex items-center space-x-2">
                  <AlertTriangle className="h-4 w-4 text-rose-600" />
                  <h4 className="text-xs font-bold uppercase tracking-wider text-rose-950">
                    Active Delivery In Progress — Choose Outcome
                  </h4>
                </div>
                <span className="rounded bg-rose-200/90 text-rose-900 px-2 py-0.5 text-[10px] font-mono font-bold">
                  OUT_FOR_DELIVERY
                </span>
              </div>
              <p className="text-xs text-rose-800">
                The parcel is currently with the delivery rider. You can simulate a failed delivery attempt to trigger an NDR case in the NDR Recovery Hub, or record a successful doorstep delivery.
              </p>

              <div className="pt-1 flex flex-wrap items-center gap-2.5">
                {/* Primary Button: Record Failed Delivery Attempt (Create NDR) */}
                <button
                  type="button"
                  onClick={() => {
                    setEventType('DELIVERY_ATTEMPT_FAILED');
                    // Focus or preset default note
                    if (!notes) {
                      setNotes(`Rider doorstep attempt failed: ${reasonCode}`);
                    }
                  }}
                  className={`inline-flex items-center space-x-1.5 rounded-lg px-3.5 py-2 text-xs font-bold shadow-sm transition ${
                    eventType === 'DELIVERY_ATTEMPT_FAILED'
                      ? 'bg-rose-700 text-white ring-2 ring-rose-500/40'
                      : 'bg-white border border-rose-300 text-rose-800 hover:bg-rose-100'
                  }`}
                >
                  <AlertCircle className="h-3.5 w-3.5" />
                  <span>Record Failed Delivery Attempt (Create NDR)</span>
                </button>

                {/* Direct Alternative: Deliver */}
                <button
                  type="button"
                  onClick={() => {
                    setEventType('DELIVERED');
                  }}
                  className={`inline-flex items-center space-x-1.5 rounded-lg px-3.5 py-2 text-xs font-bold shadow-sm transition ${
                    eventType === 'DELIVERED'
                      ? 'bg-emerald-700 text-white ring-2 ring-emerald-500/40'
                      : 'bg-white border border-emerald-300 text-emerald-800 hover:bg-emerald-100'
                  }`}
                >
                  <CheckCircle2 className="h-3.5 w-3.5" />
                  <span>Record Successful Delivery</span>
                </button>
              </div>
            </div>
          )}

          {/* Simulation Form */}
          {!isTerminal ? (
            <form onSubmit={handleSimulateSubmit} className="space-y-4 rounded-xl border border-slate-200 p-4 bg-white">
              <div className="flex items-center justify-between">
                <h4 className="text-xs font-bold uppercase tracking-wider text-slate-700">
                  Simulate Courier Scan Event
                </h4>
                <span className="text-[11px] text-slate-500">
                  Current state: <strong className="text-blue-700">{currentStatus}</strong>
                </span>
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">Target Scan Event</label>
                <select
                  value={eventType}
                  onChange={(e) => setEventType(e.target.value)}
                  className="w-full rounded-lg border border-slate-300 p-2.5 text-xs text-slate-800 bg-white focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
                >
                  {ALL_EVENTS.map((ev) => {
                    const isPermitted = isEventPermitted(currentStatus, ev.value);
                    return (
                      <option
                        key={ev.value}
                        value={ev.value}
                        disabled={!isPermitted}
                        className={!isPermitted ? 'text-slate-400 bg-slate-50' : 'text-slate-900 font-medium'}
                      >
                        {ev.label} {isPermitted ? '✓ (Permitted Next Step)' : `✗ (Blocked from ${currentStatus})`}
                      </option>
                    );
                  })}
                </select>
                <p className="mt-1 text-[11px] text-slate-500">
                  Permitted transitions from {currentStatus}:{' '}
                  <span className="font-semibold text-slate-700">
                    {(ALLOWED_STATUS_TRANSITIONS[currentStatus] || []).join(', ') || 'None (Terminal State)'}
                  </span>
                </p>
              </div>

              {/* NDR Reason Collector: Shown whenever DELIVERY_ATTEMPT_FAILED is selected */}
              {eventType === 'DELIVERY_ATTEMPT_FAILED' && (
                <div className="rounded-lg bg-rose-50/80 border border-rose-300 p-3 space-y-2">
                  <div className="flex items-center justify-between">
                    <label className="block text-xs font-bold text-rose-900">
                      NDR Failure Reason Code (Trigger for NDR Recovery Case)
                    </label>
                    <span className="rounded bg-rose-200 px-1.5 py-0.5 text-[9px] font-bold text-rose-800">
                      Required for NDR
                    </span>
                  </div>
                  <select
                    value={reasonCode}
                    onChange={(e) => setReasonCode(e.target.value)}
                    className="w-full rounded-lg border border-rose-300 p-2 text-xs text-rose-900 bg-white focus:ring-1 focus:ring-rose-500"
                  >
                    <option value="CUSTOMER_UNAVAILABLE">CUSTOMER_UNAVAILABLE — Customer Not Home / Door Locked</option>
                    <option value="INCORRECT_ADDRESS">INCORRECT_ADDRESS — Address Incomplete / Landmark Missing</option>
                    <option value="CUSTOMER_UNREACHABLE">CUSTOMER_UNREACHABLE — Phone Switched Off / No Response</option>
                    <option value="DELIVERY_RESCHEDULE_REQUESTED">DELIVERY_RESCHEDULE_REQUESTED — Customer Requested Next-Day</option>
                    <option value="COD_AMOUNT_NOT_READY">COD_AMOUNT_NOT_READY — Customer Lacked Cash for COD</option>
                    <option value="CUSTOMER_REFUSED">CUSTOMER_REFUSED — Customer Rejected Parcel on Doorstep</option>
                  </select>
                  <p className="text-[10px] text-rose-700">
                    Recording this scan will move the order to <strong>NDR</strong> and automatically initialize an NDR Case in the NDR Recovery Hub with estimated recovery lift.
                  </p>
                </div>
              )}

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-semibold text-slate-700 mb-1">Carrier Provider</label>
                  <input
                    type="text"
                    value={carrierName}
                    onChange={(e) => setCarrierName(e.target.value)}
                    className="w-full rounded-lg border border-slate-300 p-2 text-xs text-slate-800"
                  />
                </div>
                <div>
                  <label className="block text-xs font-semibold text-slate-700 mb-1">Scan Location / Hub</label>
                  <input
                    type="text"
                    value={location}
                    onChange={(e) => setLocation(e.target.value)}
                    className="w-full rounded-lg border border-slate-300 p-2 text-xs text-slate-800"
                  />
                </div>
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-700 mb-1">Courier Operational Notes</label>
                <input
                  type="text"
                  value={notes}
                  onChange={(e) => setNotes(e.target.value)}
                  placeholder={
                    eventType === 'DELIVERY_ATTEMPT_FAILED'
                      ? 'e.g. Courier rider reported gate locked; attempted phone call with no response'
                      : 'e.g. Courier rider dispatched for delivery'
                  }
                  className="w-full rounded-lg border border-slate-300 p-2 text-xs text-slate-800"
                />
              </div>

              <div className="pt-2 flex justify-end space-x-2">
                <button
                  type="button"
                  onClick={onClose}
                  className="rounded-lg border border-slate-300 bg-white px-3.5 py-2 text-xs font-semibold text-slate-700 hover:bg-slate-50 transition"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={isSubmitting || !isSelectedEventPermitted}
                  className={`inline-flex items-center space-x-1.5 rounded-lg px-4 py-2 text-xs font-bold text-white shadow-md transition disabled:opacity-40 ${
                    eventType === 'DELIVERY_ATTEMPT_FAILED'
                      ? 'bg-rose-600 hover:bg-rose-700 shadow-rose-600/20'
                      : 'bg-blue-600 hover:bg-blue-700 shadow-blue-500/20'
                  }`}
                >
                  {isSubmitting ? (
                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  ) : eventType === 'DELIVERY_ATTEMPT_FAILED' ? (
                    <AlertCircle className="h-3.5 w-3.5" />
                  ) : (
                    <Play className="h-3.5 w-3.5 fill-current" />
                  )}
                  <span>
                    {eventType === 'DELIVERY_ATTEMPT_FAILED'
                      ? 'Record Failed Delivery Attempt (Create NDR)'
                      : `Dispatch Simulated Scan (${eventType})`}
                  </span>
                </button>
              </div>
            </form>
          ) : (
            <div className="rounded-xl border border-slate-200 bg-slate-50 p-6 text-center">
              <CheckCircle2 className="h-8 w-8 text-emerald-600 mx-auto mb-2" />
              <h4 className="text-sm font-bold text-slate-900">Order is in Terminal State ({currentStatus})</h4>
              <p className="text-xs text-slate-500 mt-1 max-w-sm mx-auto">
                No further delivery scans can be simulated for terminal orders to preserve audit trail integrity and prevent out-of-order mutations.
              </p>
            </div>
          )}

          {/* Delivery Audit History */}
          <div className="rounded-xl border border-slate-200 p-4 bg-slate-50/50 space-y-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center space-x-2">
                <History className="h-4 w-4 text-slate-500" />
                <h4 className="text-xs font-bold uppercase tracking-wider text-slate-700">
                  Delivery Event History & Audit Log
                </h4>
              </div>
              <span className="text-[11px] font-mono text-slate-500">
                {events.length} {events.length === 1 ? 'event' : 'events'} recorded
              </span>
            </div>

            {isLoadingEvents ? (
              <div className="py-4 text-center text-xs text-slate-400">Loading tracking history...</div>
            ) : events.length === 0 ? (
              <div className="py-4 text-center text-xs text-slate-400">
                No tracking scans recorded yet. Simulate a scan above to start the lifecycle.
              </div>
            ) : (
              <div className="space-y-2 max-h-48 overflow-y-auto pr-1">
                {events.map((evt) => (
                  <div
                    key={evt.id}
                    className="flex items-center justify-between rounded-lg border border-slate-200 bg-white p-2.5 text-xs shadow-sm"
                  >
                    <div className="flex items-center space-x-2.5">
                      <span className="font-mono font-bold text-slate-900">{evt.event_type}</span>
                      {evt.is_simulated && (
                        <span className="rounded bg-blue-50 border border-blue-200 px-1.5 py-0.2 text-[9px] font-mono font-bold text-blue-700">
                          [SIMULATED]
                        </span>
                      )}
                      <span className="text-slate-400">•</span>
                      <span className="text-slate-600 font-medium">{evt.carrier_name || 'Carrier'}</span>
                      {evt.reason_code && (
                        <span className="rounded bg-rose-50 border border-rose-200 text-rose-700 px-1.5 py-0.2 text-[10px] font-medium">
                          {evt.reason_code}
                        </span>
                      )}
                    </div>
                    <div className="text-right text-[11px] text-slate-500">
                      <div>{new Date(evt.occurred_at).toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit' })}</div>
                      <div className="text-[9px] text-slate-400">
                        {new Date(evt.occurred_at).toLocaleDateString('en-IN', { month: 'short', day: 'numeric' })}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Footer */}
        <div className="border-t border-slate-200 bg-slate-50 px-6 py-3 flex items-center justify-between text-xs text-slate-500">
          <div className="flex items-center space-x-1.5">
            <ShieldCheck className="h-4 w-4 text-emerald-600" />
            <span>State machine guarded: Out-of-order jumps prevented</span>
          </div>
          <button
            onClick={onClose}
            className="rounded-lg border border-slate-300 bg-white px-3 py-1.5 font-semibold text-slate-700 hover:bg-slate-100 transition"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
};
