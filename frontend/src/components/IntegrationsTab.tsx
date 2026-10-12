'use client';

import React, { useState, useEffect } from 'react';
import {
  FileSpreadsheet,
  Webhook,
  Sparkles,
  CheckCircle2,
  Copy,
  ExternalLink,
  ShieldCheck,
  Code2,
  Terminal,
  UploadCloud,
  History,
  Layers,
  ArrowRight,
  BookOpen,
  ChevronDown,
  ChevronUp,
  MessageSquare,
} from 'lucide-react';
import { ShopifyStoreConfig, WhatsAppConfig } from '@/types';
import { fetchShopifyStoreConfig, fetchWhatsAppConfig } from '@/services/api';
import { ShopifyWebhookGuideModal } from '@/components/ShopifyWebhookGuideModal';
import { WhatsAppGuideModal } from '@/components/WhatsAppGuideModal';

interface IntegrationsTabProps {
  orgId: string;
  onOpenCSVImport: () => void;
  onOpenImportHistory: () => void;
}

export const IntegrationsTab: React.FC<IntegrationsTabProps> = ({
  orgId,
  onOpenCSVImport,
  onOpenImportHistory,
}) => {
  const [copiedSnippet, setCopiedSnippet] = useState(false);
  const [activeCodeTab, setActiveCodeTab] = useState<'CURL' | 'PAYLOAD'>('CURL');
  const [isShopifyGuideOpen, setIsShopifyGuideOpen] = useState(false);
  const [shopifyConfig, setShopifyConfig] = useState<ShopifyStoreConfig | null>(null);
  const [isWhatsAppGuideOpen, setIsWhatsAppGuideOpen] = useState(false);
  const [whatsAppConfig, setWhatsAppConfig] = useState<WhatsAppConfig | null>(null);
  const [isDocsExpanded, setIsDocsExpanded] = useState(true);

  const webhookEndpoint = `${typeof window !== 'undefined' ? window.location.origin.replace(':3000', ':8000') : 'http://localhost:8000'}/api/v1/orders/webhook`;

  const loadShopifyConfig = async () => {
    try {
      const conf = await fetchShopifyStoreConfig();
      setShopifyConfig(conf);
    } catch {
      // Graceful fallback
    }
  };

  const loadWhatsAppConfig = async () => {
    try {
      const conf = await fetchWhatsAppConfig();
      setWhatsAppConfig(conf);
    } catch {
      // Graceful fallback
    }
  };

  useEffect(() => {
    loadShopifyConfig();
    loadWhatsAppConfig();
  }, []);

  const curlSnippet = `curl -X POST "${webhookEndpoint}" \\
  -H "Content-Type: application/json" \\
  -H "X-Org-ID: ${orgId || 'your-org-id'}" \\
  -H "X-PG-Signature: <computed_hmac_sha256>" \\
  -d '{
    "external_order_id": "ORD-10928",
    "order_value": 1499.00,
    "payment_method": "COD",
    "customer_name": "Kavita Rao",
    "customer_phone": "+919876543210",
    "shipping_city": "Bengaluru",
    "shipping_pincode": "560001",
    "items": [
      {"product_name": "Premium Cotton Kurti", "quantity": 1, "unit_price": 1499.00}
    ]
  }'`;

  const payloadSnippet = `{
  "external_order_id": "ORD-10928",
  "order_value": 1499.00,
  "payment_method": "COD",
  "customer_name": "Kavita Rao",
  "customer_phone": "+919876543210",
  "shipping_address1": "Flat 402, Green Glen Heights",
  "shipping_city": "Bengaluru",
  "shipping_state": "Karnataka",
  "shipping_pincode": "560001",
  "items": [
    {
      "product_name": "Premium Cotton Kurti",
      "sku": "KURTI-BLU-M",
      "quantity": 1,
      "unit_price": 1499.00,
      "unit_cost": 520.00
    }
  ]
}`;

  const copyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text);
    setCopiedSnippet(true);
    setTimeout(() => setCopiedSnippet(false), 2000);
  };

  const isWhatsAppConfigured = Boolean(
    whatsAppConfig &&
    whatsAppConfig.phone_number_id &&
    whatsAppConfig.status !== 'NOT_CONFIGURED' &&
    whatsAppConfig.status !== 'DISCONNECTED' &&
    whatsAppConfig.operating_mode !== 'MOCK'
  );

  const isWhatsAppLiveVerified = Boolean(
    isWhatsAppConfigured &&
    whatsAppConfig?.operating_mode === 'LIVE' &&
    whatsAppConfig?.status === 'ACTIVE' &&
    (whatsAppConfig?.verified_name || whatsAppConfig?.last_webhook_received_at)
  );

  return (
    <div className="space-y-6">
      {/* Top Banner */}
      <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
          <div>
            <div className="flex items-center space-x-2">
              <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-emerald-100 text-emerald-800">
                <Layers className="h-4 w-4" />
              </span>
              <h2 className="text-lg font-bold text-slate-900">Store & Order Ingestion Hub</h2>
            </div>
            <p className="mt-1 text-xs text-slate-500 max-w-2xl">
              Connect your storefront and 3PL carriers to stream orders directly into ProfitGuard AI.
              Transparent integration status guarantees accurate production and test telemetry.
            </p>
          </div>
          <div className="flex items-center space-x-2.5">
            <button
              onClick={onOpenCSVImport}
              className="inline-flex items-center space-x-1.5 rounded-xl bg-emerald-600 px-3.5 py-2 text-xs font-bold text-white shadow-sm hover:bg-emerald-700 transition"
            >
              <UploadCloud className="h-4 w-4" />
              <span>Import Orders CSV</span>
            </button>
            <button
              onClick={onOpenImportHistory}
              className="inline-flex items-center space-x-1.5 rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-xs font-semibold text-slate-700 hover:bg-slate-100 transition"
            >
              <History className="h-4 w-4" />
              <span>Batch Logs</span>
            </button>
          </div>
        </div>
      </div>

      {/* Integration Channels Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-5">
        {/* Channel 1: CSV */}
        <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between mb-3">
              <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-emerald-50 text-emerald-700">
                <FileSpreadsheet className="h-5 w-5" />
              </div>
              <span className="inline-flex items-center gap-1 rounded-full bg-emerald-50 px-2.5 py-0.5 text-[11px] font-bold text-emerald-700 border border-emerald-200">
                <CheckCircle2 className="h-3 w-3" />
                Active & Live
              </span>
            </div>
            <h3 className="text-sm font-bold text-slate-900 mb-1">Two-Stage CSV Bulk Ingestion</h3>
            <p className="text-xs text-slate-500 leading-relaxed mb-4">
              Upload orders from Shopify, WooCommerce, or Custom ERP exports. Validates row-level data and shows an error preview before committing.
            </p>
            <div className="space-y-1.5 text-[11px] text-slate-600 mb-4 bg-slate-50 p-2.5 rounded-lg border border-slate-100">
              <div className="flex items-center justify-between">
                <span>Stage 1: Validation & Preview</span>
                <span className="text-emerald-700 font-semibold">Enabled</span>
              </div>
              <div className="flex items-center justify-between">
                <span>Stage 2: Idempotent Commit</span>
                <span className="text-emerald-700 font-semibold">Enabled</span>
              </div>
              <div className="flex items-center justify-between">
                <span>Duplicate Prevention</span>
                <span className="text-emerald-700 font-semibold">Enforced</span>
              </div>
            </div>
          </div>
          <button
            onClick={onOpenCSVImport}
            className="w-full flex items-center justify-center space-x-1.5 rounded-xl border border-emerald-300 bg-emerald-50 py-2 text-xs font-bold text-emerald-800 hover:bg-emerald-100 transition"
          >
            <span>Launch CSV Importer</span>
            <ArrowRight className="h-3.5 w-3.5" />
          </button>
        </div>

        {/* Channel 2: REST Webhooks */}
        <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between mb-3">
              <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-teal-50 text-teal-700">
                <Webhook className="h-5 w-5" />
              </div>
              <span className="inline-flex items-center gap-1 rounded-full bg-emerald-50 px-2.5 py-0.5 text-[11px] font-bold text-emerald-700 border border-emerald-200">
                <CheckCircle2 className="h-3 w-3" />
                Active & Live
              </span>
            </div>
            <h3 className="text-sm font-bold text-slate-900 mb-1">REST API & Real-Time Webhooks</h3>
            <p className="text-xs text-slate-500 leading-relaxed mb-4">
              Push orders in real time directly upon checkout. Supports HMAC signature verification and tenant-scoped security.
            </p>
            <div className="space-y-1.5 text-[11px] text-slate-600 mb-4 bg-slate-50 p-2.5 rounded-lg border border-slate-100">
              <div className="flex items-center justify-between">
                <span>Endpoint</span>
                <span className="font-mono text-[10px] text-slate-800">/orders/webhook</span>
              </div>
              <div className="flex items-center justify-between">
                <span>Security</span>
                <span className="text-teal-700 font-semibold">HMAC-SHA256</span>
              </div>
              <div className="flex items-center justify-between">
                <span>Risk Decision</span>
                <span className="text-emerald-700 font-semibold">Auto-Triggered</span>
              </div>
            </div>
          </div>
          <a
            href="#custom-storefront-docs"
            onClick={() => setIsDocsExpanded(true)}
            className="w-full flex items-center justify-center space-x-1.5 rounded-xl border border-teal-300 bg-teal-50 py-2 text-xs font-bold text-teal-800 hover:bg-teal-100 transition text-center"
          >
            <span>API Documentation</span>
            <Code2 className="h-3.5 w-3.5" />
          </a>
        </div>

        {/* Channel 3: Shopify Native App */}
        <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between mb-3">
              <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-indigo-50 text-indigo-700">
                <Sparkles className="h-5 w-5" />
              </div>
              {shopifyConfig && shopifyConfig.status === 'ACTIVE' ? (
                <span className="inline-flex items-center gap-1 rounded-full bg-emerald-50 px-2.5 py-0.5 text-[11px] font-bold text-emerald-700 border border-emerald-200">
                  <CheckCircle2 className="h-3 w-3" />
                  Connected ({shopifyConfig.shop_domain})
                </span>
              ) : (
                <span className="inline-flex items-center gap-1 rounded-full bg-slate-100 px-2.5 py-0.5 text-[11px] font-bold text-slate-600 border border-slate-200">
                  Waiting for Credentials
                </span>
              )}
            </div>
            <h3 className="text-sm font-bold text-slate-900 mb-1">Shopify Storefront Connector</h3>
            <p className="text-xs text-slate-500 leading-relaxed mb-4">
              For Shopify stores, configure a private webhook from Shopify Admin → Notifications → Webhooks pointing to your ProfitGuard endpoint.
            </p>
            <div className="space-y-1.5 text-[11px] text-slate-600 mb-4 bg-slate-50 p-2.5 rounded-lg border border-slate-100">
              <div className="flex items-center justify-between">
                <span>Topic</span>
                <span className="font-mono text-[10px] text-slate-800">orders/create</span>
              </div>
              <div className="flex items-center justify-between">
                <span>Format</span>
                <span className="font-mono text-[10px] text-slate-800">JSON</span>
              </div>
              <div className="flex items-center justify-between">
                <span>Tagging Sync</span>
                <span className="text-indigo-700 font-semibold">Supported</span>
              </div>
            </div>
          </div>
          <button
            type="button"
            onClick={() => setIsShopifyGuideOpen(true)}
            className="w-full flex items-center justify-center space-x-1.5 rounded-xl border border-indigo-200 bg-indigo-50 py-2 text-xs font-bold text-indigo-800 hover:bg-indigo-100 transition shadow-xs"
          >
            <span>Webhook Setup Guide</span>
            <ArrowRight className="h-3.5 w-3.5" />
          </button>
        </div>

        {/* Channel 4: Meta WhatsApp Cloud API */}
        <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between mb-3">
              <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-emerald-50 text-emerald-700">
                <MessageSquare className="h-5 w-5" />
              </div>
              {!isWhatsAppConfigured ? (
                <span className="inline-flex items-center gap-1 rounded-full bg-slate-100 px-2.5 py-0.5 text-[11px] font-bold text-slate-600 border border-slate-200">
                  Setup Required
                </span>
              ) : whatsAppConfig?.operating_mode === 'META_TEST' ? (
                <span className="inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-[11px] font-bold border bg-amber-50 text-amber-800 border-amber-200">
                  <CheckCircle2 className="h-3 w-3" />
                  Test Environment
                </span>
              ) : isWhatsAppLiveVerified ? (
                <span className="inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-[11px] font-bold border bg-emerald-50 text-emerald-800 border-emerald-200">
                  <CheckCircle2 className="h-3 w-3" />
                  Connected
                </span>
              ) : (
                <span className="inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-[11px] font-bold border bg-sky-50 text-sky-800 border-sky-200">
                  Awaiting Verification
                </span>
              )}
            </div>
            <h3 className="text-sm font-bold text-slate-900 mb-1">WhatsApp Cloud API</h3>
            <p className="text-xs text-slate-500 leading-relaxed mb-4">
              Pre-dispatch COD confirmation, OTP verification, and NDR customer recovery with real-time delivery receipts.
            </p>
            <div className="space-y-1.5 text-[11px] text-slate-600 mb-4 bg-slate-50 p-2.5 rounded-lg border border-slate-100">
              <div className="flex items-center justify-between">
                <span>{isWhatsAppConfigured ? 'Connection Mode' : 'Connection Status'}</span>
                <span className={`font-semibold ${isWhatsAppConfigured ? 'text-slate-800' : 'text-slate-600'}`}>
                  {isWhatsAppConfigured
                    ? whatsAppConfig?.operating_mode === 'LIVE'
                      ? 'WhatsApp Business Cloud API'
                      : 'Meta Test Environment'
                    : 'Setup Required'}
                </span>
              </div>
              <div className="flex items-center justify-between">
                <span>Phone Number ID</span>
                <span className="font-mono text-[10px] text-slate-800 truncate max-w-[120px]">
                  {isWhatsAppConfigured && whatsAppConfig?.phone_number_id
                    ? whatsAppConfig.phone_number_id
                    : 'Not Configured'}
                </span>
              </div>
              <div className="flex items-center justify-between">
                <span>Webhook Health</span>
                <span className="text-emerald-700 font-semibold">HMAC-Protected</span>
              </div>
            </div>
          </div>
          <button
            type="button"
            onClick={() => setIsWhatsAppGuideOpen(true)}
            className="w-full flex items-center justify-center space-x-1.5 rounded-xl border border-emerald-300 bg-emerald-50 py-2 text-xs font-bold text-emerald-800 hover:bg-emerald-100 transition shadow-xs"
          >
            <span>Configure & Test WhatsApp</span>
            <ArrowRight className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>

      {/* Custom Storefront Integration Section */}
      <div id="custom-storefront-docs" className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between pb-4 border-b border-slate-200 gap-3">
          <div>
            <h3 className="text-sm font-bold text-slate-900 flex items-center gap-2">
              <Terminal className="h-4 w-4 text-emerald-600" />
              Custom Storefront Integration
            </h3>
            <p className="text-xs text-slate-500 mt-0.5 max-w-2xl leading-relaxed">
              Connect your ecommerce platform, order management system, or warehouse software to ProfitGuard AI for automated order processing and risk analysis.
            </p>
          </div>

          <div className="flex items-center space-x-2">
            <button
              type="button"
              onClick={() => setIsDocsExpanded(!isDocsExpanded)}
              className="inline-flex items-center space-x-1 rounded-lg border border-slate-200 bg-slate-50 px-2.5 py-1 text-xs font-semibold text-slate-700 hover:bg-slate-100 transition"
            >
              <BookOpen className="h-3.5 w-3.5 text-slate-500" />
              <span>{isDocsExpanded ? 'Collapse Docs' : 'API Documentation'}</span>
              {isDocsExpanded ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
            </button>
          </div>
        </div>

        {isDocsExpanded && (
          <div className="pt-4 space-y-4">
            <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 bg-slate-50 p-3.5 rounded-xl border border-slate-100">
              <div className="text-xs">
                <span className="text-slate-400 block text-[10px] uppercase font-bold tracking-wider">Target Endpoint</span>
                <span className="font-mono font-bold text-slate-800">{webhookEndpoint}</span>
              </div>
              <div className="flex items-center space-x-2">
                <div className="flex rounded-lg border border-slate-200 bg-white p-0.5 text-xs font-semibold">
                  <button
                    onClick={() => setActiveCodeTab('CURL')}
                    className={`px-3 py-1 rounded-md transition ${
                      activeCodeTab === 'CURL'
                        ? 'bg-emerald-600 text-white shadow-xs'
                        : 'text-slate-500 hover:text-slate-800'
                    }`}
                  >
                    cURL Request
                  </button>
                  <button
                    onClick={() => setActiveCodeTab('PAYLOAD')}
                    className={`px-3 py-1 rounded-md transition ${
                      activeCodeTab === 'PAYLOAD'
                        ? 'bg-emerald-600 text-white shadow-xs'
                        : 'text-slate-500 hover:text-slate-800'
                    }`}
                  >
                    JSON Payload
                  </button>
                </div>

                <button
                  onClick={() => copyToClipboard(activeCodeTab === 'CURL' ? curlSnippet : payloadSnippet)}
                  className="inline-flex items-center space-x-1 rounded-lg border border-slate-200 bg-white px-2.5 py-1 text-xs font-semibold text-slate-700 hover:bg-slate-50 transition shadow-xs"
                >
                  {copiedSnippet ? (
                    <>
                      <CheckCircle2 className="h-3.5 w-3.5 text-emerald-600" />
                      <span className="text-emerald-700 font-bold">Copied!</span>
                    </>
                  ) : (
                    <>
                      <Copy className="h-3.5 w-3.5 text-slate-500" />
                      <span>Copy</span>
                    </>
                  )}
                </button>
              </div>
            </div>

            <div className="rounded-xl bg-slate-950 p-4 font-mono text-xs text-slate-200 overflow-x-auto shadow-inner">
              <pre>{activeCodeTab === 'CURL' ? curlSnippet : payloadSnippet}</pre>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-3 text-xs text-slate-600 pt-3 border-t border-slate-100">
              <div className="flex items-start space-x-2">
                <ShieldCheck className="h-4 w-4 text-emerald-600 shrink-0 mt-0.5" />
                <span><strong>Tenant Isolated:</strong> Every request is securely scoped to your organization via <code className="font-mono text-slate-800">X-Org-ID</code>.</span>
              </div>
              <div className="flex items-start space-x-2">
                <CheckCircle2 className="h-4 w-4 text-emerald-600 shrink-0 mt-0.5" />
                <span><strong>Idempotency:</strong> Re-sent external order IDs safely return existing records without duplication.</span>
              </div>
              <div className="flex items-start space-x-2">
                <Sparkles className="h-4 w-4 text-emerald-600 shrink-0 mt-0.5" />
                <span><strong>Instant Risk Scoring:</strong> Automatically evaluates pre-dispatch Expected Contribution across 5 candidate actions.</span>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Shopify Webhook Setup Guide Modal */}
      <ShopifyWebhookGuideModal
        isOpen={isShopifyGuideOpen}
        onClose={() => setIsShopifyGuideOpen(false)}
        onConfigUpdated={loadShopifyConfig}
      />

      {/* Meta WhatsApp Business Cloud API Guide Modal */}
      <WhatsAppGuideModal
        isOpen={isWhatsAppGuideOpen}
        onClose={() => setIsWhatsAppGuideOpen(false)}
        onConfigUpdated={loadWhatsAppConfig}
      />
    </div>
  );
};
