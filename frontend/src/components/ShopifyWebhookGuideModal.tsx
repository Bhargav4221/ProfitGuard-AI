'use client';

import React, { useState, useEffect } from 'react';
import {
  X,
  Webhook,
  CheckCircle2,
  AlertTriangle,
  Copy,
  ExternalLink,
  ShieldCheck,
  ShieldAlert,
  Terminal,
  Lock,
  ArrowRight,
  RefreshCw,
  Info,
  Server,
  Layers,
} from 'lucide-react';
import { ShopifyStoreConfig, ShopifyWebhookDelivery } from '@/types';
import {
  fetchShopifyStoreConfig,
  configureShopifyStore,
  disconnectShopifyStore,
  fetchShopifyWebhooks,
} from '@/services/api';

interface ShopifyWebhookGuideModalProps {
  isOpen: boolean;
  onClose: () => void;
  onConfigUpdated?: () => void;
}

export const ShopifyWebhookGuideModal: React.FC<ShopifyWebhookGuideModalProps> = ({
  isOpen,
  onClose,
  onConfigUpdated,
}) => {
  const [config, setConfig] = useState<ShopifyStoreConfig | null>(null);
  const [deliveries, setDeliveries] = useState<ShopifyWebhookDelivery[]>([]);
  const [totalDeliveries, setTotalDeliveries] = useState(0);
  const [isLoading, setIsLoading] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [isDisconnecting, setIsDisconnecting] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  // Form state
  const [shopDomain, setShopDomain] = useState('');
  const [accessToken, setAccessToken] = useState('');
  const [webhookSecret, setWebhookSecret] = useState('');
  const [scopes, setScopes] = useState('read_orders,write_orders');
  const [isFormOpen, setIsFormOpen] = useState(false);

  // Copy feedback state
  const [copiedKey, setCopiedKey] = useState<string | null>(null);

  // Compute live webhook URL from deployment configuration
  const apiBase = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api/v1';
  const shopifyWebhookUrl = `${apiBase.replace(/\/+$/, '')}/integrations/shopify/webhook`;

  const copyToClipboard = (text: string, key: string) => {
    navigator.clipboard.writeText(text);
    setCopiedKey(key);
    setTimeout(() => setCopiedKey(null), 2500);
  };

  const loadData = async () => {
    setIsLoading(true);
    setErrorMsg(null);
    try {
      const [conf, webhooks] = await Promise.all([
        fetchShopifyStoreConfig().catch(() => null),
        fetchShopifyWebhooks(1, 5).catch(() => ({ items: [], total: 0, page: 1, page_size: 5 })),
      ]);
      setConfig(conf);
      if (conf) {
        setShopDomain(conf.shop_domain || '');
      }
      setDeliveries(webhooks.items || []);
      setTotalDeliveries(webhooks.total || 0);
    } catch (err: any) {
      setErrorMsg(err.message || 'Failed to load Shopify integration configuration.');
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    if (isOpen) {
      loadData();
      setSuccessMsg(null);
    } else {
      setErrorMsg(null);
      setSuccessMsg(null);
      setIsFormOpen(false);
      setAccessToken('');
      setWebhookSecret('');
    }
  }, [isOpen]);

  const handleSaveConfig = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!shopDomain.trim()) {
      setErrorMsg('Store domain is required (e.g. brand-name.myshopify.com).');
      return;
    }
    setIsSaving(true);
    setErrorMsg(null);
    setSuccessMsg(null);
    try {
      const updated = await configureShopifyStore({
        shop_domain: shopDomain.trim(),
        access_token: accessToken.trim() || undefined,
        webhook_secret: webhookSecret.trim() || undefined,
        scopes: scopes.trim() || undefined,
      });
      setConfig(updated);
      setSuccessMsg(`Shopify credentials saved for ${updated.shop_domain}. Webhook receiver ready.`);
      setIsFormOpen(false);
      setAccessToken('');
      setWebhookSecret('');
      if (onConfigUpdated) onConfigUpdated();
    } catch (err: any) {
      setErrorMsg(err.message || 'Failed to configure Shopify credentials.');
    } finally {
      setIsSaving(false);
    }
  };

  const handleDisconnect = async () => {
    if (!confirm('Are you sure you want to disconnect this Shopify store? Inbound webhooks will be rejected until re-configured.')) {
      return;
    }
    setIsDisconnecting(true);
    setErrorMsg(null);
    setSuccessMsg(null);
    try {
      await disconnectShopifyStore();
      setConfig(null);
      setShopDomain('');
      setSuccessMsg('Shopify store disconnected successfully.');
      if (onConfigUpdated) onConfigUpdated();
    } catch (err: any) {
      setErrorMsg(err.message || 'Failed to disconnect Shopify store.');
    } finally {
      setIsDisconnecting(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/70 p-4 backdrop-blur-sm overflow-y-auto">
      <div className="relative w-full max-w-4xl max-h-[92vh] flex flex-col rounded-2xl bg-white shadow-2xl border border-slate-200 overflow-hidden my-4">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-slate-200 px-6 py-4 bg-slate-50/70">
          <div className="flex items-center space-x-3">
            <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-indigo-100 text-indigo-700 shadow-sm">
              <Webhook className="h-5 w-5" />
            </span>
            <div>
              <h2 className="text-base font-bold text-slate-900 flex items-center gap-2">
                Shopify Webhook Setup Guide
                <span className="rounded bg-indigo-50 border border-indigo-200 px-2 py-0.5 text-[10px] font-bold text-indigo-800">
                  orders/create
                </span>
              </h2>
              <p className="text-xs text-slate-500">
                Step-by-step walkthrough to stream real-time Shopify orders into ProfitGuard AI
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

        {/* Content Body */}
        <div className="flex-1 overflow-y-auto px-6 py-5 space-y-6">
          {/* Notifications */}
          {errorMsg && (
            <div className="rounded-xl border border-rose-200 bg-rose-50 p-3.5 text-xs text-rose-800 flex items-center justify-between">
              <div className="flex items-center space-x-2">
                <AlertTriangle className="h-4 w-4 text-rose-600 shrink-0" />
                <span>{errorMsg}</span>
              </div>
              <button onClick={() => setErrorMsg(null)} className="font-bold underline text-rose-900">
                Dismiss
              </button>
            </div>
          )}

          {successMsg && (
            <div className="rounded-xl border border-emerald-200 bg-emerald-50 p-3.5 text-xs text-emerald-800 flex items-center justify-between">
              <div className="flex items-center space-x-2">
                <CheckCircle2 className="h-4 w-4 text-emerald-600 shrink-0" />
                <span>{successMsg}</span>
              </div>
              <button onClick={() => setSuccessMsg(null)} className="font-bold underline text-emerald-900">
                Dismiss
              </button>
            </div>
          )}

          {/* Section 1: Connection & Verification Status */}
          <div className="rounded-xl border border-slate-200 bg-slate-50/60 p-4">
            <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 pb-3 border-b border-slate-200">
              <div>
                <span className="text-[11px] font-bold uppercase tracking-wider text-slate-500 block">
                  Backend Integration Health
                </span>
                <div className="flex items-center space-x-2 mt-1">
                  {config && config.status === 'ACTIVE' ? (
                    <span className="inline-flex items-center gap-1.5 rounded-full bg-emerald-100 px-3 py-0.5 text-xs font-bold text-emerald-800">
                      <span className="h-2 w-2 rounded-full bg-emerald-600" />
                      Store Connected: {config.shop_domain}
                    </span>
                  ) : (
                    <span className="inline-flex items-center gap-1.5 rounded-full bg-amber-100 px-3 py-0.5 text-xs font-bold text-amber-800">
                      <span className="h-2 w-2 rounded-full bg-amber-600" />
                      Not Connected (Waiting for Credentials)
                    </span>
                  )}
                </div>
              </div>

              <div className="flex items-center space-x-2">
                <button
                  onClick={loadData}
                  disabled={isLoading}
                  className="inline-flex items-center space-x-1 rounded-lg border border-slate-200 bg-white px-2.5 py-1 text-xs font-semibold text-slate-600 hover:bg-slate-50 transition"
                >
                  <RefreshCw className={`h-3.5 w-3.5 ${isLoading ? 'animate-spin' : ''}`} />
                  <span>Refresh</span>
                </button>
                {config && config.status === 'ACTIVE' ? (
                  <button
                    onClick={handleDisconnect}
                    disabled={isDisconnecting}
                    className="rounded-lg border border-rose-200 bg-rose-50 px-2.5 py-1 text-xs font-semibold text-rose-700 hover:bg-rose-100 transition"
                  >
                    Disconnect Store
                  </button>
                ) : (
                  <button
                    onClick={() => setIsFormOpen(!isFormOpen)}
                    className="rounded-lg bg-indigo-600 px-3 py-1 text-xs font-bold text-white hover:bg-indigo-700 transition"
                  >
                    {isFormOpen ? 'Close Credentials' : 'Set Credentials'}
                  </button>
                )}
              </div>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 pt-3 text-xs text-slate-600">
              <div>
                <span className="text-slate-400 block text-[10px]">API Version</span>
                <span className="font-semibold text-slate-800">{config?.api_version || '2024-01'}</span>
              </div>
              <div>
                <span className="text-slate-400 block text-[10px]">Webhook Signature Secret</span>
                <span className="font-semibold text-slate-800">
                  {config?.has_webhook_secret ? 'Configured (Encrypted in DB)' : 'Not Set'}
                </span>
              </div>
              <div>
                <span className="text-slate-400 block text-[10px]">Live Webhook Delivery Status</span>
                <span className="font-semibold text-slate-800">
                  {totalDeliveries > 0
                    ? `${totalDeliveries} Deliveries Logged`
                    : 'Pending First Event (Not Yet Verified)'}
                </span>
              </div>
            </div>
          </div>

          {/* Optional Credentials Configuration Form */}
          {isFormOpen && (
            <form onSubmit={handleSaveConfig} className="rounded-xl border border-indigo-200 bg-indigo-50/50 p-4 space-y-3">
              <div className="flex items-center justify-between">
                <h4 className="text-xs font-bold uppercase tracking-wider text-indigo-950 flex items-center gap-1.5">
                  <Lock className="h-3.5 w-3.5 text-indigo-700" />
                  Configure Store Credentials
                </h4>
                <span className="text-[11px] text-slate-500">Tokens are encrypted before persistence</span>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div>
                  <label className="text-xs font-semibold text-slate-700 block">
                    Shopify Store Domain <span className="text-rose-500">*</span>
                  </label>
                  <input
                    type="text"
                    value={shopDomain}
                    onChange={(e) => setShopDomain(e.target.value)}
                    placeholder="my-store.myshopify.com"
                    className="mt-1 w-full rounded-lg border border-slate-300 bg-white p-2 text-xs font-mono text-slate-800 focus:outline-none focus:ring-2 focus:ring-indigo-500"
                    required
                  />
                </div>

                <div>
                  <label className="text-xs font-semibold text-slate-700 block">
                    Webhook Shared Secret (from Shopify App)
                  </label>
                  <input
                    type="password"
                    value={webhookSecret}
                    onChange={(e) => setWebhookSecret(e.target.value)}
                    placeholder="shpss_xxxxxxxxxxxxxx"
                    className="mt-1 w-full rounded-lg border border-slate-300 bg-white p-2 text-xs font-mono text-slate-800 focus:outline-none focus:ring-2 focus:ring-indigo-500"
                  />
                </div>

                <div className="sm:col-span-2">
                  <label className="text-xs font-semibold text-slate-700 block">
                    Admin API Access Token (Optional for Private App / Tag Sync)
                  </label>
                  <input
                    type="password"
                    value={accessToken}
                    onChange={(e) => setAccessToken(e.target.value)}
                    placeholder="shpat_xxxxxxxxxxxxxx"
                    className="mt-1 w-full rounded-lg border border-slate-300 bg-white p-2 text-xs font-mono text-slate-800 focus:outline-none focus:ring-2 focus:ring-indigo-500"
                  />
                </div>
              </div>

              <div className="flex items-center justify-end space-x-2 pt-2">
                <button
                  type="button"
                  onClick={() => setIsFormOpen(false)}
                  className="rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-xs font-semibold text-slate-700 hover:bg-slate-50 transition"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={isSaving}
                  className="rounded-lg bg-indigo-600 px-4 py-1.5 text-xs font-bold text-white shadow hover:bg-indigo-700 disabled:opacity-50 transition"
                >
                  {isSaving ? 'Saving...' : 'Save Credentials'}
                </button>
              </div>
            </form>
          )}

          {/* Section 2: Prerequisites & Infrastructure Notice */}
          <div className="rounded-xl border border-amber-200 bg-amber-50/60 p-4 space-y-2 text-xs text-amber-950">
            <div className="flex items-center space-x-2 font-bold text-amber-900">
              <Server className="h-4 w-4 text-amber-700 shrink-0" />
              <span>Infrastructure Prerequisites for Live Shopify Webhook Ingress</span>
            </div>
            <ul className="list-disc list-inside space-y-1 text-slate-700 pl-1">
              <li>
                <strong>Public HTTPS Requirement:</strong> Shopify cloud servers cannot deliver webhooks to <code className="bg-amber-100/80 px-1 py-0.5 rounded font-mono">localhost</code> or private LAN addresses. For local testing, route traffic via an HTTPS tunnel (e.g. Cloudflare Tunnel or ngrok) pointing to backend port 8000.
              </li>
              <li>
                <strong>Cryptographic HMAC Verification:</strong> Every inbound request must contain a valid <code className="bg-amber-100/80 px-1 py-0.5 rounded font-mono">X-Shopify-Hmac-Sha256</code> header calculated against the raw request payload.
              </li>
              <li>
                <strong>Shopify App Registration:</strong> You must create a Custom App under Shopify Admin &gt; Settings &gt; Apps and sales channels &gt; Develop apps.
              </li>
            </ul>
          </div>

          {/* Section 3: Generated Webhook Endpoint */}
          <div className="rounded-xl border border-slate-200 bg-white p-4 space-y-2 shadow-xs">
            <div className="flex items-center justify-between">
              <span className="text-xs font-bold uppercase tracking-wider text-slate-700 flex items-center gap-1.5">
                <Terminal className="h-3.5 w-3.5 text-indigo-600" />
                Target Webhook Receiver URL
              </span>
              <span className="text-[10px] text-slate-400">Generated from deployment environment</span>
            </div>

            <div className="flex items-center space-x-2">
              <div className="flex-1 rounded-lg bg-slate-950 px-3.5 py-2 font-mono text-xs text-emerald-400 overflow-x-auto select-all">
                {shopifyWebhookUrl}
              </div>
              <button
                type="button"
                onClick={() => copyToClipboard(shopifyWebhookUrl, 'URL')}
                className="flex items-center space-x-1.5 rounded-lg border border-slate-300 bg-slate-50 px-3 py-2 text-xs font-bold text-slate-700 hover:bg-slate-100 transition shrink-0"
              >
                {copiedKey === 'URL' ? (
                  <>
                    <CheckCircle2 className="h-3.5 w-3.5 text-emerald-600" />
                    <span className="text-emerald-700">Copied!</span>
                  </>
                ) : (
                  <>
                    <Copy className="h-3.5 w-3.5 text-slate-500" />
                    <span>Copy URL</span>
                  </>
                )}
              </button>
            </div>
            <p className="text-[11px] text-slate-500">
              Provide this exact URL when creating the webhook subscription in your Shopify store admin.
            </p>
          </div>

          {/* Section 4: Distinct Step-by-Step Instructions */}
          <div className="space-y-4">
            <h3 className="text-xs font-bold uppercase tracking-wider text-slate-500">
              Two-Step Configuration Flow
            </h3>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {/* Step 1 Card */}
              <div className="rounded-xl border border-slate-200 bg-white p-4 space-y-2.5">
                <div className="flex items-center space-x-2">
                  <span className="flex h-6 w-6 items-center justify-center rounded-full bg-slate-900 text-white font-bold text-xs">
                    1
                  </span>
                  <h4 className="text-xs font-bold text-slate-900">
                    In ProfitGuard AI: Register Store Credentials
                  </h4>
                </div>
                <p className="text-xs text-slate-500 leading-relaxed">
                  ProfitGuard AI uses your store domain to authenticate incoming payloads and verify HMAC signatures.
                </p>
                <div className="space-y-1.5 text-[11px] bg-slate-50 p-2.5 rounded-lg border border-slate-100">
                  <div className="flex items-center justify-between">
                    <span className="text-slate-500">Store Domain:</span>
                    <span className="font-mono text-slate-800 font-semibold">{config?.shop_domain || 'Not configured'}</span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-slate-500">Secret Encryption:</span>
                    <span className="text-emerald-700 font-semibold">Fernet 256-bit</span>
                  </div>
                </div>
                <button
                  type="button"
                  onClick={() => setIsFormOpen(true)}
                  className="w-full rounded-lg border border-slate-200 bg-slate-50 py-1.5 text-xs font-semibold text-slate-700 hover:bg-slate-100 transition"
                >
                  {config ? 'Update Credentials' : 'Add Store Credentials Now'}
                </button>
              </div>

              {/* Step 2 Card */}
              <div className="rounded-xl border border-slate-200 bg-white p-4 space-y-2.5">
                <div className="flex items-center space-x-2">
                  <span className="flex h-6 w-6 items-center justify-center rounded-full bg-indigo-600 text-white font-bold text-xs">
                    2
                  </span>
                  <h4 className="text-xs font-bold text-slate-900">
                    In Shopify Admin: Create Webhook Subscription
                  </h4>
                </div>
                <p className="text-xs text-slate-500 leading-relaxed">
                  Log in to your Shopify store admin and subscribe the target endpoint to new order events:
                </p>
                <div className="space-y-1 text-[11px] text-slate-600 bg-slate-50 p-2.5 rounded-lg border border-slate-100">
                  <div className="flex items-center justify-between">
                    <span>Navigation:</span>
                    <span className="font-medium text-slate-800">Settings → Notifications → Webhooks</span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span>Event Topic:</span>
                    <span className="font-mono font-bold text-indigo-700">Order creation (orders/create)</span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span>Format:</span>
                    <span className="font-mono font-bold text-slate-800">JSON</span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span>Webhook URL:</span>
                    <span className="text-slate-500 italic">Target URL from above</span>
                  </div>
                </div>
              </div>
            </div>
          </div>

          {/* Section 5: Delivery Verification & Audit */}
          <div className="rounded-xl border border-slate-200 bg-white p-4 space-y-3">
            <div className="flex items-center justify-between">
              <div>
                <h4 className="text-xs font-bold uppercase tracking-wider text-slate-700">
                  Recent Inbound Webhook Deliveries
                </h4>
                <p className="text-[11px] text-slate-500">
                  Audit log of HMAC-verified webhook requests received from Shopify
                </p>
              </div>
              <span className="rounded-full bg-slate-100 px-2.5 py-0.5 text-[11px] font-semibold text-slate-600">
                {totalDeliveries} Recorded
              </span>
            </div>

            {deliveries.length === 0 ? (
              <div className="rounded-lg border border-dashed border-slate-200 p-6 text-center text-slate-400">
                <Info className="h-6 w-6 mx-auto text-slate-300 mb-2" />
                <p className="text-xs font-medium text-slate-600">No Webhook Events Received Yet</p>
                <p className="text-[11px] text-slate-400 max-w-sm mx-auto mt-0.5">
                  Live webhook delivery has not been verified. Trigger a test notification from Shopify Admin or create a test checkout to confirm receipt.
                </p>
              </div>
            ) : (
              <div className="overflow-x-auto rounded-lg border border-slate-200">
                <table className="w-full text-left text-xs">
                  <thead className="border-b bg-slate-50 font-medium text-slate-600">
                    <tr>
                      <th className="px-3 py-2">Delivery ID</th>
                      <th className="px-3 py-2">Topic</th>
                      <th className="px-3 py-2">Shop</th>
                      <th className="px-3 py-2">Status</th>
                      <th className="px-3 py-2">Received At</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100 font-mono text-[11px]">
                    {deliveries.map((del) => (
                      <tr key={del.id} className="hover:bg-slate-50/60">
                        <td className="px-3 py-2 font-semibold text-slate-900 truncate max-w-[120px]">
                          {del.shopify_delivery_id}
                        </td>
                        <td className="px-3 py-2 text-indigo-700 font-bold">{del.topic}</td>
                        <td className="px-3 py-2 text-slate-600">{del.shop_domain}</td>
                        <td className="px-3 py-2">
                          <span
                            className={`rounded px-1.5 py-0.5 text-[10px] font-bold ${
                              del.status === 'PROCESSED'
                                ? 'bg-emerald-100 text-emerald-800'
                                : 'bg-rose-100 text-rose-800'
                            }`}
                          >
                            {del.status}
                          </span>
                        </td>
                        <td className="px-3 py-2 text-slate-500 font-sans">
                          {new Date(del.created_at).toLocaleString('en-IN', {
                            dateStyle: 'short',
                            timeStyle: 'short',
                          })}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>

        {/* Footer */}
        <div className="border-t border-slate-200 px-6 py-3.5 bg-slate-50 flex items-center justify-between">
          <span className="text-[11px] text-slate-500 flex items-center gap-1.5">
            <ShieldCheck className="h-3.5 w-3.5 text-emerald-600" />
            HMAC-SHA256 signature verification enforced on all inbound requests
          </span>
          <button
            onClick={onClose}
            className="rounded-xl bg-slate-900 px-4 py-1.5 text-xs font-bold text-white hover:bg-slate-800 transition"
          >
            Close Guide
          </button>
        </div>
      </div>
    </div>
  );
};
