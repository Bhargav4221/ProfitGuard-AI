'use client';

import React, { useState, useEffect } from 'react';
import {
  X,
  Plus,
  Package,
  IndianRupee,
  Truck,
  ShieldAlert,
  Sparkles,
  Info,
  CheckCircle2,
  AlertCircle,
} from 'lucide-react';
import { CreateOrderInput, Order } from '@/types';
import { createManualOrder, fetchMerchantEconomics } from '@/services/api';

interface CreateOrderModalProps {
  isOpen: boolean;
  onClose: () => void;
  onOrderCreated: (newOrder: Order) => void;
}

export const CreateOrderModal: React.FC<CreateOrderModalProps> = ({
  isOpen,
  onClose,
  onOrderCreated,
}) => {
  const [externalOrderId, setExternalOrderId] = useState('');
  const [orderValue, setOrderValue] = useState('1499.00');
  const [paymentMethod, setPaymentMethod] = useState<'COD' | 'PREPAID'>('COD');

  // Customer Details
  const [customerName, setCustomerName] = useState('Rohan Sharma');
  const [customerPhone, setCustomerPhone] = useState('9876543210');
  const [customerEmail, setCustomerEmail] = useState('rohan.sharma@example.com');
  const [shippingAddress1, setShippingAddress1] = useState('Flat 402, Lotus Greens, Indiranagar');
  const [shippingCity, setShippingCity] = useState('Bengaluru');
  const [shippingState, setShippingState] = useState('Karnataka');
  const [shippingPincode, setShippingPincode] = useState('560038');

  // Product & Economics
  const [productName, setProductName] = useState('Handcrafted Linen Shirt');
  const [sku, setSku] = useState('SHIRT-LINEN-WHT');
  const [unitCost, setUnitCost] = useState('450.00');
  const [forwardShippingCost, setForwardShippingCost] = useState('70.00');
  const [reverseShippingCost, setReverseShippingCost] = useState('65.00');
  const [packagingCost, setPackagingCost] = useState('20.00');

  // UI state
  const [loading, setLoading] = useState(false);
  const [errors, setErrors] = useState<Record<string, string>>({});

  useEffect(() => {
    if (isOpen) {
      // Auto-generate fresh unique order reference
      const randomSuffix = Math.floor(1000 + Math.random() * 9000);
      setExternalOrderId(`ORD-PG-${randomSuffix}`);
      setErrors({});

      // Fetch merchant configured defaults if available
      fetchMerchantEconomics()
        .then((eco) => {
          if (eco) {
            setForwardShippingCost(parseFloat(eco.forward_shipping_cost || '70').toFixed(2));
            setReverseShippingCost(parseFloat(eco.reverse_shipping_cost || '65').toFixed(2));
            setPackagingCost(parseFloat(eco.packaging_cost || '20').toFixed(2));
            const cogsPct = parseFloat(eco.default_cogs_percent || '30') / 100;
            const ov = parseFloat(orderValue || '1499');
            setUnitCost((ov * cogsPct).toFixed(2));
          }
        })
        .catch(() => {
          // Use standard defaults
        });
    }
  }, [isOpen]);

  // Recalculate default COGS when order value changes
  const handleOrderValueChange = (val: string) => {
    setOrderValue(val);
    const num = parseFloat(val);
    if (!isNaN(num) && num > 0) {
      setUnitCost((num * 0.3).toFixed(2));
    }
  };

  // Calculations for real-time margin preview
  const numOrderVal = parseFloat(orderValue) || 0;
  const numCogs = parseFloat(unitCost) || 0;
  const numFwdShip = parseFloat(forwardShippingCost) || 70;
  const numRevShip = parseFloat(reverseShippingCost) || 65;
  const numPkg = parseFloat(packagingCost) || 20;
  const numFee = paymentMethod === 'COD' ? 35.0 : Math.round(numOrderVal * 0.02 * 100) / 100 + 3.0;

  // Delivered Contribution = OrderValue - Fee - COGS - Packaging - FwdShipping
  const deliveredMargin = numOrderVal - numFee - numCogs - numPkg - numFwdShip;

  // RTO Loss = - FwdShipping - RevShipping - Packaging - (0.05 * COGS) - (COD Fee if manifested)
  const damageLoss = 0.05 * numCogs;
  const rtoLoss = -(numFwdShip + numRevShip + numPkg + damageLoss);

  // Profit at Risk = DeliveredMargin - RTO Loss
  const profitAtRisk = deliveredMargin - rtoLoss;

  const validate = (): boolean => {
    const newErrors: Record<string, string> = {};

    if (!externalOrderId.trim()) {
      newErrors.externalOrderId = 'Order reference is required';
    }

    const ov = parseFloat(orderValue);
    if (isNaN(ov) || ov <= 0) {
      newErrors.orderValue = 'Order value must be a positive number';
    }

    if (!customerName.trim()) {
      newErrors.customerName = 'Customer name is required';
    }

    const cleanPhone = customerPhone.replace(/[\s\-\(\)\.]+/g, '').replace(/^\+91|^91|^0/, '');
    if (!/^[6-9]\d{9}$/.test(cleanPhone)) {
      newErrors.customerPhone = 'Enter a valid 10-digit Indian mobile number (e.g. 9876543210)';
    }

    const cleanPincode = shippingPincode.trim();
    if (!/^[1-9][0-9]{5}$/.test(cleanPincode)) {
      newErrors.shippingPincode = 'Enter a valid 6-digit Indian postal pincode (e.g. 560038)';
    }

    const uc = parseFloat(unitCost);
    if (isNaN(uc) || uc < 0) {
      newErrors.unitCost = 'Product cost (COGS) cannot be negative';
    }

    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!validate()) return;

    setLoading(true);
    try {
      const payload: CreateOrderInput = {
        external_order_id: externalOrderId.trim(),
        order_value: parseFloat(orderValue).toFixed(2),
        payment_method: paymentMethod,
        customer_name: customerName.trim() || undefined,
        customer_phone: customerPhone.trim() || undefined,
        customer_email: customerEmail.trim() || undefined,
        shipping_address1: shippingAddress1.trim() || undefined,
        shipping_city: shippingCity.trim() || undefined,
        shipping_state: shippingState.trim() || undefined,
        shipping_pincode: shippingPincode.trim() || undefined,
        items: [
          {
            product_name: productName.trim() || 'General Merchandise',
            sku: sku.trim() || undefined,
            quantity: 1,
            unit_price: parseFloat(orderValue).toFixed(2),
            unit_cost: parseFloat(unitCost).toFixed(2),
          },
        ],
      };

      const createdOrder = await createManualOrder(payload);
      onOrderCreated(createdOrder);
      onClose();
    } catch (err: any) {
      setErrors({ form: err.message || 'Failed to create order' });
    } finally {
      setLoading(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/60 p-4 backdrop-blur-sm overflow-y-auto">
      <div className="relative w-full max-w-3xl rounded-2xl bg-white shadow-2xl border border-slate-200 my-8">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-slate-200 px-6 py-4">
          <div className="flex items-center space-x-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-emerald-600 text-white shadow-md shadow-emerald-500/20">
              <Plus className="h-5 w-5" />
            </div>
            <div>
              <h2 className="text-base font-bold text-slate-900">Create Order</h2>
              <p className="text-xs text-slate-500">
                Enter order details to evaluate pre-dispatch risk and optimal action recommendations
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="rounded-lg p-1.5 text-slate-400 hover:bg-slate-100 hover:text-slate-600 transition"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Form Body */}
        <form onSubmit={handleSubmit} className="p-6 space-y-6">
          {errors.form && (
            <div className="flex items-center space-x-2 rounded-xl border border-rose-200 bg-rose-50 p-3 text-xs text-rose-800">
              <AlertCircle className="h-4 w-4 shrink-0 text-rose-600" />
              <span>{errors.form}</span>
            </div>
          )}

          {/* Section 1: Order Reference & Payment */}
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">
                Order Reference <span className="text-rose-500">*</span>
              </label>
              <input
                type="text"
                value={externalOrderId}
                onChange={(e) => setExternalOrderId(e.target.value)}
                placeholder="e.g. ORD-1001"
                className={`w-full rounded-lg border px-3 py-2 text-xs font-mono text-slate-800 focus:outline-none focus:ring-1 ${
                  errors.externalOrderId
                    ? 'border-rose-400 focus:ring-rose-400'
                    : 'border-slate-300 focus:ring-emerald-500'
                }`}
              />
              {errors.externalOrderId && (
                <p className="mt-1 text-[11px] text-rose-600">{errors.externalOrderId}</p>
              )}
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">
                Order Value (GMV ₹) <span className="text-rose-500">*</span>
              </label>
              <div className="relative">
                <span className="absolute left-3 top-2 text-xs font-bold text-slate-400">₹</span>
                <input
                  type="number"
                  step="0.01"
                  min="1"
                  value={orderValue}
                  onChange={(e) => handleOrderValueChange(e.target.value)}
                  className={`w-full rounded-lg border pl-7 pr-3 py-2 text-xs font-bold text-slate-900 focus:outline-none focus:ring-1 ${
                    errors.orderValue
                      ? 'border-rose-400 focus:ring-rose-400'
                      : 'border-slate-300 focus:ring-emerald-500'
                  }`}
                />
              </div>
              {errors.orderValue && (
                <p className="mt-1 text-[11px] text-rose-600">{errors.orderValue}</p>
              )}
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">Payment Method</label>
              <div className="grid grid-cols-2 gap-2">
                <button
                  type="button"
                  onClick={() => setPaymentMethod('COD')}
                  className={`rounded-lg py-2 text-xs font-bold transition border ${
                    paymentMethod === 'COD'
                      ? 'border-amber-400 bg-amber-50 text-amber-800 ring-1 ring-amber-400'
                      : 'border-slate-200 bg-white text-slate-600 hover:bg-slate-50'
                  }`}
                >
                  Cash on Delivery
                </button>
                <button
                  type="button"
                  onClick={() => setPaymentMethod('PREPAID')}
                  className={`rounded-lg py-2 text-xs font-bold transition border ${
                    paymentMethod === 'PREPAID'
                      ? 'border-emerald-400 bg-emerald-50 text-emerald-800 ring-1 ring-emerald-400'
                      : 'border-slate-200 bg-white text-slate-600 hover:bg-slate-50'
                  }`}
                >
                  Prepaid (Online)
                </button>
              </div>
            </div>
          </div>

          {/* Section 2: Customer & Delivery Address */}
          <div className="rounded-xl border border-slate-200 bg-slate-50/60 p-4 space-y-3">
            <h3 className="text-xs font-bold uppercase tracking-wider text-slate-500">
              Customer & Delivery Address (Indian D2C Context)
            </h3>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
              <div>
                <label className="block text-[11px] font-medium text-slate-600 mb-0.5">Customer Name</label>
                <input
                  type="text"
                  value={customerName}
                  onChange={(e) => setCustomerName(e.target.value)}
                  className="w-full rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-xs text-slate-800"
                />
              </div>
              <div>
                <label className="block text-[11px] font-medium text-slate-600 mb-0.5">
                  Mobile (10 Digits) <span className="text-rose-500">*</span>
                </label>
                <input
                  type="tel"
                  value={customerPhone}
                  onChange={(e) => setCustomerPhone(e.target.value)}
                  placeholder="9876543210"
                  className={`w-full rounded-lg border bg-white px-3 py-1.5 text-xs text-slate-800 ${
                    errors.customerPhone ? 'border-rose-400' : 'border-slate-300'
                  }`}
                />
                {errors.customerPhone && (
                  <p className="mt-0.5 text-[10px] text-rose-600">{errors.customerPhone}</p>
                )}
              </div>
              <div>
                <label className="block text-[11px] font-medium text-slate-600 mb-0.5">Email Address</label>
                <input
                  type="email"
                  value={customerEmail}
                  onChange={(e) => setCustomerEmail(e.target.value)}
                  placeholder="customer@example.com"
                  className="w-full rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-xs text-slate-800"
                />
              </div>
            </div>

            <div className="grid grid-cols-1 gap-3 sm:grid-cols-4">
              <div className="sm:col-span-2">
                <label className="block text-[11px] font-medium text-slate-600 mb-0.5">Street Address</label>
                <input
                  type="text"
                  value={shippingAddress1}
                  onChange={(e) => setShippingAddress1(e.target.value)}
                  placeholder="House/Flat, Street, Locality"
                  className="w-full rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-xs text-slate-800"
                />
              </div>
              <div>
                <label className="block text-[11px] font-medium text-slate-600 mb-0.5">City & State</label>
                <input
                  type="text"
                  value={`${shippingCity}, ${shippingState}`}
                  onChange={(e) => {
                    const parts = e.target.value.split(',');
                    setShippingCity(parts[0]?.trim() || '');
                    if (parts[1]) setShippingState(parts[1].trim());
                  }}
                  className="w-full rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-xs text-slate-800"
                />
              </div>
              <div>
                <label className="block text-[11px] font-medium text-slate-600 mb-0.5">
                  Pincode (6 Digits) <span className="text-rose-500">*</span>
                </label>
                <input
                  type="text"
                  maxLength={6}
                  value={shippingPincode}
                  onChange={(e) => setShippingPincode(e.target.value)}
                  placeholder="560038"
                  className={`w-full rounded-lg border bg-white px-3 py-1.5 text-xs font-mono text-slate-800 ${
                    errors.shippingPincode ? 'border-rose-400' : 'border-slate-300'
                  }`}
                />
                {errors.shippingPincode && (
                  <p className="mt-0.5 text-[10px] text-rose-600">{errors.shippingPincode}</p>
                )}
              </div>
            </div>
          </div>

          {/* Section 3: Product & Cost Structure */}
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-4">
            <div className="sm:col-span-2">
              <label className="block text-xs font-semibold text-slate-700 mb-1">Product Description</label>
              <input
                type="text"
                value={productName}
                onChange={(e) => setProductName(e.target.value)}
                className="w-full rounded-lg border border-slate-300 px-3 py-2 text-xs text-slate-800"
              />
            </div>
            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">
                Product Cost / COGS (₹)
              </label>
              <input
                type="number"
                step="0.01"
                min="0"
                value={unitCost}
                onChange={(e) => setUnitCost(e.target.value)}
                className="w-full rounded-lg border border-slate-300 px-3 py-2 text-xs font-bold text-slate-800"
              />
              <span className="text-[10px] text-slate-400">
                Default: 30% of GMV [CONFIGURED]
              </span>
            </div>
            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">Logistics & Packaging</label>
              <div className="text-xs text-slate-600 py-2 font-mono">
                Fwd: ₹{forwardShippingCost} | Rev: ₹{reverseShippingCost}
              </div>
              <span className="text-[10px] text-slate-400">Carrier tariff [CONFIGURED]</span>
            </div>
          </div>

          {/* Section 4: Real-Time Economic Margin Preview Card */}
          <div className="rounded-xl border border-emerald-200 bg-emerald-50/60 p-4">
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs font-bold uppercase tracking-wider text-emerald-900 flex items-center gap-1.5">
                <Sparkles className="h-4 w-4 text-emerald-600" />
                Real-Time Economic Payoff Preview
              </span>
              <span className="rounded bg-emerald-100 px-2 py-0.5 text-[10px] font-bold text-emerald-800">
                DECIMAL ACCURATE
              </span>
            </div>

            <div className="grid grid-cols-1 gap-3 sm:grid-cols-3 text-xs">
              <div className="bg-white/80 rounded-lg p-2.5 border border-emerald-100">
                <span className="text-slate-500 text-[11px] block">Delivered Payoff</span>
                <span className="text-base font-extrabold text-emerald-700">
                  +₹{deliveredMargin.toFixed(2)}
                </span>
                <p className="text-[10px] text-slate-400 mt-0.5">
                  GMV - COGS - Packaging - Fwd Ship - Fee
                </p>
              </div>

              <div className="bg-white/80 rounded-lg p-2.5 border border-rose-100">
                <span className="text-slate-500 text-[11px] block">RTO Non-Acceptance Loss</span>
                <span className="text-base font-extrabold text-rose-600">
                  ₹{rtoLoss.toFixed(2)}
                </span>
                <p className="text-[10px] text-slate-400 mt-0.5">
                  - Fwd - Rev - Pkg - 5% Damage
                </p>
              </div>

              <div className="bg-white/80 rounded-lg p-2.5 border border-amber-100">
                <span className="text-slate-500 text-[11px] block">Profit at Risk</span>
                <span className="text-base font-extrabold text-amber-700">
                  ₹{profitAtRisk.toFixed(2)}
                </span>
                <p className="text-[10px] text-slate-400 mt-0.5">
                  Delivered Margin - RTO Payoff
                </p>
              </div>
            </div>
          </div>

          {/* Footer Actions */}
          <div className="flex items-center justify-end space-x-3 pt-3 border-t border-slate-200">
            <button
              type="button"
              onClick={onClose}
              className="rounded-lg border border-slate-300 bg-white px-4 py-2 text-xs font-semibold text-slate-700 hover:bg-slate-50 transition"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={loading}
              className="flex items-center space-x-1.5 rounded-lg bg-emerald-600 px-5 py-2 text-xs font-bold text-white shadow-md shadow-emerald-600/20 hover:bg-emerald-700 transition disabled:opacity-50"
            >
              <Plus className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
              <span>{loading ? 'Creating Order...' : 'Persist Order to Workspace'}</span>
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};
