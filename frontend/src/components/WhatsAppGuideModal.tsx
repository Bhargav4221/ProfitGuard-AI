'use client';

import React, { useState, useEffect } from 'react';
import {
  X,
  MessageSquare,
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
  Send,
  Radio,
  FileText,
  UserX,
  Smartphone,
} from 'lucide-react';
import {
  WhatsAppConfig,
  WhatsAppMessage,
  WhatsAppOptOut,
  WhatsAppTestResult,
} from '@/types';
import {
  fetchWhatsAppConfig,
  configureWhatsApp,
  disconnectWhatsApp,
  testWhatsAppConnection,
  sendWhatsAppTestMessage,
  fetchWhatsAppMessages,
  fetchWhatsAppOptOuts,
} from '@/services/api';

interface WhatsAppGuideModalProps {
  isOpen: boolean;
  onClose: () => void;
  onConfigUpdated?: () => void;
}

export const WhatsAppGuideModal: React.FC<WhatsAppGuideModalProps> = ({
  isOpen,
  onClose,
  onConfigUpdated,
}) => {
  const [activeTab, setActiveTab] = useState<'CONFIG' | 'GUIDE' | 'LOGS' | 'OPTOUTS'>('CONFIG');
  const [config, setConfig] = useState<WhatsAppConfig | null>(null);
  const [messages, setMessages] = useState<WhatsAppMessage[]>([]);
  const [optOuts, setOptOuts] = useState<WhatsAppOptOut[]>([]);
  const [testResult, setTestResult] = useState<WhatsAppTestResult | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [isTesting, setIsTesting] = useState(false);
  const [isSendingTest, setIsSendingTest] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  // Form State
  const [phoneNumberId, setPhoneNumberId] = useState('');
  const [businessAccountId, setBusinessAccountId] = useState('');
  const [accessToken, setAccessToken] = useState('');
  const [appSecret, setAppSecret] = useState('');
  const [operatingMode, setOperatingMode] = useState<'MOCK' | 'META_TEST' | 'LIVE'>('MOCK');
  const [verifyToken, setVerifyToken] = useState('profitguard_whatsapp_verify_token_default');

  // Test Message State
  const [testPhone, setTestPhone] = useState('');
  const [testMessageText, setTestMessageText] = useState('Hello! This is a verification test from ProfitGuard AI WhatsApp integration.');

  const [copiedKey, setCopiedKey] = useState<string | null>(null);

  const webhookCallbackUrl = `${
    typeof window !== 'undefined' ? window.location.origin.replace(':3000', ':8000') : 'http://localhost:8000'
  }/api/v1/integrations/whatsapp/webhook`;

  const loadData = async () => {
    setIsLoading(true);
    setErrorMsg(null);
    try {
      const conf = await fetchWhatsAppConfig();
      if (conf) {
        setConfig(conf);
        setPhoneNumberId(conf.phone_number_id || '');
        setBusinessAccountId(conf.business_account_id || '');
        setOperatingMode(conf.operating_mode || 'MOCK');
        if (conf.webhook_verify_token) setVerifyToken(conf.webhook_verify_token);
      }
      const msgRes = await fetchWhatsAppMessages({ page: 1, pageSize: 15 });
      setMessages(msgRes.items || []);

      const opts = await fetchWhatsAppOptOuts();
      setOptOuts(opts || []);
    } catch (err: any) {
      setErrorMsg(err.message || 'Failed to load WhatsApp data.');
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    if (isOpen) {
      loadData();
    }
  }, [isOpen]);

  const copyToClipboard = (text: string, key: string) => {
    navigator.clipboard.writeText(text);
    setCopiedKey(key);
    setTimeout(() => setCopiedKey(null), 2000);
  };

  const handleSaveConfig = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!phoneNumberId.trim()) {
      setErrorMsg('Phone Number ID is required.');
      return;
    }
    setIsSaving(true);
    setErrorMsg(null);
    setSuccessMsg(null);

    try {
      const updated = await configureWhatsApp({
        phone_number_id: phoneNumberId.trim(),
        business_account_id: businessAccountId.trim() || undefined,
        access_token: accessToken.trim() || undefined,
        app_secret: appSecret.trim() || undefined,
        webhook_verify_token: verifyToken.trim() || undefined,
        operating_mode: operatingMode,
      });
      setConfig(updated);
      setSuccessMsg('WhatsApp credentials and operating mode saved securely.');
      setAccessToken('');
      setAppSecret('');
      if (onConfigUpdated) onConfigUpdated();
    } catch (err: any) {
      setErrorMsg(err.message || 'Failed to save WhatsApp settings.');
    } finally {
      setIsSaving(false);
    }
  };

  const handleTestConnection = async () => {
    setIsTesting(true);
    setTestResult(null);
    setErrorMsg(null);
    try {
      const res = await testWhatsAppConnection();
      setTestResult(res);
      if (res.connected) {
        setSuccessMsg(res.message);
      } else {
        setErrorMsg(res.message);
      }
    } catch (err: any) {
      setErrorMsg(err.message || 'Diagnostic connection test failed.');
    } finally {
      setIsTesting(false);
    }
  };

  const handleSendTestMessage = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!testPhone.trim()) {
      setErrorMsg('Please enter a valid recipient phone number in international format (+91...)');
      return;
    }
    setIsSendingTest(true);
    setErrorMsg(null);
    setSuccessMsg(null);

    try {
      const res = await sendWhatsAppTestMessage(testPhone.trim(), testMessageText.trim());
      setSuccessMsg(`Test message dispatched successfully! Status: ${res.status} (ID: ${res.wamid || res.id})`);
      // Reload logs
      const msgRes = await fetchWhatsAppMessages({ page: 1, pageSize: 15 });
      setMessages(msgRes.items || []);
    } catch (err: any) {
      setErrorMsg(err.message || 'Failed to dispatch test message.');
    } finally {
      setIsSendingTest(false);
    }
  };

  const handleDisconnect = async () => {
    if (!confirm('Are you sure you want to disconnect WhatsApp and revoke stored credentials?')) return;
    setIsLoading(true);
    try {
      await disconnectWhatsApp();
      setConfig(null);
      setPhoneNumberId('');
      setBusinessAccountId('');
      setAccessToken('');
      setAppSecret('');
      setSuccessMsg('WhatsApp integration disconnected.');
      if (onConfigUpdated) onConfigUpdated();
    } catch (err: any) {
      setErrorMsg(err.message || 'Failed to disconnect.');
    } finally {
      setIsLoading(false);
    }
  };

  const isConfigured = Boolean(
    config &&
    config.phone_number_id &&
    config.status !== 'NOT_CONFIGURED' &&
    config.status !== 'DISCONNECTED' &&
    config.operating_mode !== 'MOCK'
  );

  const isLiveVerified = Boolean(
    isConfigured &&
    config?.operating_mode === 'LIVE' &&
    config?.status === 'ACTIVE' &&
    (config?.verified_name || config?.last_webhook_received_at)
  );

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/60 p-4 backdrop-blur-sm animate-in fade-in duration-200">
      <div className="flex max-h-[92vh] w-full max-w-4xl flex-col rounded-2xl bg-white shadow-2xl border border-slate-200 overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-slate-200 bg-slate-50/80 px-6 py-4">
          <div className="flex items-center space-x-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-emerald-600 text-white shadow-md shadow-emerald-600/20">
              <MessageSquare className="h-5 w-5" />
            </div>
            <div>
              <div className="flex items-center space-x-2">
                <h2 className="text-base font-bold text-slate-900">
                  Meta WhatsApp Business Cloud API
                </h2>
                {!isConfigured ? (
                  <span className="inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-[10px] font-bold border bg-slate-100 text-slate-600 border-slate-300">
                    Setup Required
                  </span>
                ) : config?.operating_mode === 'META_TEST' ? (
                  <span className="inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-[10px] font-bold border bg-amber-50 text-amber-800 border-amber-300">
                    Test Environment
                  </span>
                ) : isLiveVerified ? (
                  <span className="inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-[10px] font-bold border bg-emerald-50 text-emerald-800 border-emerald-300">
                    Connected
                  </span>
                ) : (
                  <span className="inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-[10px] font-bold border bg-sky-50 text-sky-800 border-sky-300">
                    Awaiting Verification
                  </span>
                )}
              </div>
              <p className="text-xs text-slate-500">
                Official Meta Cloud API connectivity for pre-dispatch COD OTP confirmation and NDR delivery recovery.
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

        {/* Diagnostic Banner */}
        <div className="bg-slate-100/70 border-b border-slate-200 px-6 py-2.5 flex items-center justify-between text-xs">
          <div className="flex items-center space-x-4 text-slate-600">
            <span>
              Phone Number ID:{' '}
              <strong className="text-slate-800 font-mono">
                {isConfigured && config?.phone_number_id ? config.phone_number_id : 'Not Configured'}
              </strong>
            </span>
            <span>
              Verified Name:{' '}
              <strong className="text-slate-800 font-mono">
                {config?.verified_name || 'Unverified'}
              </strong>
            </span>
            <span>
              Webhook Health:{' '}
              <strong className="text-emerald-700">
                {config?.last_webhook_received_at ? 'Active' : 'Awaiting Events'}
              </strong>
            </span>
          </div>
          <button
            onClick={handleTestConnection}
            disabled={isTesting}
            className="inline-flex items-center space-x-1.5 rounded-lg border border-slate-300 bg-white px-2.5 py-1 text-[11px] font-semibold text-slate-700 hover:bg-slate-50 transition shadow-xs disabled:opacity-50"
          >
            <RefreshCw className={`h-3 w-3 ${isTesting ? 'animate-spin' : ''}`} />
            <span>Test Connection</span>
          </button>
        </div>

        {/* Feedback Messages */}
        {errorMsg && (
          <div className="mx-6 mt-4 flex items-center space-x-2 rounded-xl border border-rose-200 bg-rose-50 p-3 text-xs text-rose-700">
            <AlertTriangle className="h-4 w-4 shrink-0" />
            <span>{errorMsg}</span>
          </div>
        )}
        {successMsg && (
          <div className="mx-6 mt-4 flex items-center space-x-2 rounded-xl border border-emerald-200 bg-emerald-50 p-3 text-xs text-emerald-800">
            <CheckCircle2 className="h-4 w-4 shrink-0" />
            <span>{successMsg}</span>
          </div>
        )}

        {/* Tabs Bar */}
        <div className="flex border-b border-slate-200 px-6 bg-white">
          <button
            onClick={() => setActiveTab('CONFIG')}
            className={`border-b-2 py-3 px-3 text-xs font-bold transition flex items-center space-x-1.5 ${
              activeTab === 'CONFIG'
                ? 'border-emerald-600 text-emerald-800'
                : 'border-transparent text-slate-500 hover:text-slate-800'
            }`}
          >
            <Lock className="h-3.5 w-3.5" />
            <span>Configuration & Credentials</span>
          </button>
          <button
            onClick={() => setActiveTab('GUIDE')}
            className={`border-b-2 py-3 px-3 text-xs font-bold transition flex items-center space-x-1.5 ${
              activeTab === 'GUIDE'
                ? 'border-emerald-600 text-emerald-800'
                : 'border-transparent text-slate-500 hover:text-slate-800'
            }`}
          >
            <FileText className="h-3.5 w-3.5" />
            <span>Meta Setup Guide</span>
          </button>
          <button
            onClick={() => setActiveTab('LOGS')}
            className={`border-b-2 py-3 px-3 text-xs font-bold transition flex items-center space-x-1.5 ${
              activeTab === 'LOGS'
                ? 'border-emerald-600 text-emerald-800'
                : 'border-transparent text-slate-500 hover:text-slate-800'
            }`}
          >
            <Radio className="h-3.5 w-3.5" />
            <span>Message Deliveries ({messages.length})</span>
          </button>
          <button
            onClick={() => setActiveTab('OPTOUTS')}
            className={`border-b-2 py-3 px-3 text-xs font-bold transition flex items-center space-x-1.5 ${
              activeTab === 'OPTOUTS'
                ? 'border-emerald-600 text-emerald-800'
                : 'border-transparent text-slate-500 hover:text-slate-800'
            }`}
          >
            <UserX className="h-3.5 w-3.5" />
            <span>Opt-Out Registry ({optOuts.length})</span>
          </button>
        </div>

        {/* Content Area */}
        <div className="flex-1 overflow-y-auto p-6 space-y-6">
          {/* TAB 1: CONFIG */}
          {activeTab === 'CONFIG' && (
            <div className="space-y-6">
              <form onSubmit={handleSaveConfig} className="space-y-4">
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div>
                    <label className="block text-xs font-bold text-slate-700 mb-1">
                      Connection Mode
                    </label>
                    <select
                      value={operatingMode}
                      onChange={(e) => setOperatingMode(e.target.value as any)}
                      className="w-full rounded-xl border border-slate-300 p-2.5 text-xs text-slate-900 bg-white focus:ring-2 focus:ring-emerald-500 focus:outline-none"
                    >
                      <option value="MOCK">Local Development (Offline Test — Zero External Fees)</option>
                      <option value="META_TEST">Meta Test Environment (Meta Sandbox Test Numbers)</option>
                      <option value="LIVE">WhatsApp Business Cloud API (Production Verified)</option>
                    </select>
                    <p className="mt-1 text-[11px] text-slate-500">
                      Local mode allows end-to-end testing without external network or WhatsApp billing fees.
                    </p>
                  </div>

                  <div>
                    <label className="block text-xs font-bold text-slate-700 mb-1">
                      Phone Number ID <span className="text-rose-500">*</span>
                    </label>
                    <input
                      type="text"
                      value={phoneNumberId}
                      onChange={(e) => setPhoneNumberId(e.target.value)}
                      placeholder="e.g. 104928172948192"
                      className="w-full rounded-xl border border-slate-300 p-2.5 text-xs text-slate-900 font-mono focus:ring-2 focus:ring-emerald-500 focus:outline-none"
                    />
                    <p className="mt-1 text-[11px] text-slate-500">
                      Found in Meta App Dashboard → WhatsApp → API Setup.
                    </p>
                  </div>

                  <div>
                    <label className="block text-xs font-bold text-slate-700 mb-1">
                      WhatsApp Business Account (WABA) ID
                    </label>
                    <input
                      type="text"
                      value={businessAccountId}
                      onChange={(e) => setBusinessAccountId(e.target.value)}
                      placeholder="e.g. 103847291827461"
                      className="w-full rounded-xl border border-slate-300 p-2.5 text-xs text-slate-900 font-mono focus:ring-2 focus:ring-emerald-500 focus:outline-none"
                    />
                  </div>

                  <div>
                    <label className="block text-xs font-bold text-slate-700 mb-1">
                      Webhook Verify Token
                    </label>
                    <div className="flex space-x-1.5">
                      <input
                        type="text"
                        value={verifyToken}
                        onChange={(e) => setVerifyToken(e.target.value)}
                        className="w-full rounded-xl border border-slate-300 p-2.5 text-xs text-slate-900 font-mono focus:ring-2 focus:ring-emerald-500 focus:outline-none"
                      />
                      <button
                        type="button"
                        onClick={() => copyToClipboard(verifyToken, 'verifyToken')}
                        className="rounded-xl border border-slate-300 px-3 py-2 text-xs text-slate-600 hover:bg-slate-100 transition"
                      >
                        {copiedKey === 'verifyToken' ? <CheckCircle2 className="h-4 w-4 text-emerald-600" /> : <Copy className="h-4 w-4" />}
                      </button>
                    </div>
                  </div>

                  <div>
                    <label className="block text-xs font-bold text-slate-700 mb-1">
                      System User Access Token
                    </label>
                    <input
                      type="password"
                      value={accessToken}
                      onChange={(e) => setAccessToken(e.target.value)}
                      placeholder={config?.has_access_token ? '•••••••••••••••• (Encrypted in DB)' : 'Paste EAAB... token'}
                      className="w-full rounded-xl border border-slate-300 p-2.5 text-xs text-slate-900 font-mono focus:ring-2 focus:ring-emerald-500 focus:outline-none"
                    />
                    <p className="mt-1 text-[11px] text-slate-500">
                      Encrypted with AES-256-GCM. Permanent token with whatsapp_business_messaging scope.
                    </p>
                  </div>

                  <div>
                    <label className="block text-xs font-bold text-slate-700 mb-1">
                      Meta App Secret (for Webhook Signature Verification)
                    </label>
                    <input
                      type="password"
                      value={appSecret}
                      onChange={(e) => setAppSecret(e.target.value)}
                      placeholder={config?.has_app_secret ? '•••••••••••••••• (Encrypted in DB)' : 'Paste Meta App Secret'}
                      className="w-full rounded-xl border border-slate-300 p-2.5 text-xs text-slate-900 font-mono focus:ring-2 focus:ring-emerald-500 focus:outline-none"
                    />
                    <p className="mt-1 text-[11px] text-slate-500">
                      Used to cryptographically verify incoming X-Hub-Signature-256 headers.
                    </p>
                  </div>
                </div>

                <div className="flex items-center justify-between pt-2">
                  <button
                    type="submit"
                    disabled={isSaving}
                    className="inline-flex items-center space-x-1.5 rounded-xl bg-emerald-600 px-5 py-2.5 text-xs font-bold text-white shadow-sm hover:bg-emerald-700 transition disabled:opacity-50"
                  >
                    {isSaving ? <RefreshCw className="h-4 w-4 animate-spin" /> : <ShieldCheck className="h-4 w-4" />}
                    <span>Save Configuration</span>
                  </button>
                  {config && (
                    <button
                      type="button"
                      onClick={handleDisconnect}
                      className="text-xs font-semibold text-rose-600 hover:text-rose-800 transition"
                    >
                      Disconnect WhatsApp
                    </button>
                  )}
                </div>
              </form>

              {/* Webhook Endpoint Callback Card */}
              <div className="rounded-xl border border-slate-200 bg-slate-50 p-4">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-xs font-bold text-slate-700 flex items-center space-x-1.5">
                    <Radio className="h-4 w-4 text-emerald-600" />
                    <span>Your Webhook Callback URL</span>
                  </span>
                  <button
                    onClick={() => copyToClipboard(webhookCallbackUrl, 'webhookUrl')}
                    className="inline-flex items-center space-x-1 text-xs text-emerald-700 hover:text-emerald-900 font-semibold"
                  >
                    {copiedKey === 'webhookUrl' ? <CheckCircle2 className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
                    <span>{copiedKey === 'webhookUrl' ? 'Copied' : 'Copy URL'}</span>
                  </button>
                </div>
                <div className="rounded-lg bg-slate-900 p-2.5 text-xs font-mono text-emerald-400 break-all select-all">
                  {webhookCallbackUrl}
                </div>
                <p className="mt-2 text-[11px] text-slate-500">
                  Configure this exact URL and your Verify Token in the Meta Developer Portal under WhatsApp → Configuration.
                </p>
              </div>

              {/* Test Message Dispatch Card */}
              <div className="rounded-xl border border-slate-200 bg-white p-4">
                <h3 className="text-xs font-bold text-slate-900 mb-2 flex items-center space-x-1.5">
                  <Send className="h-4 w-4 text-emerald-600" />
                  <span>Send a Diagnostic Test Message</span>
                </h3>
                <form onSubmit={handleSendTestMessage} className="grid grid-cols-1 md:grid-cols-3 gap-3">
                  <div className="md:col-span-1">
                    <label className="block text-[11px] font-semibold text-slate-600 mb-1">
                      Recipient Phone (E.164)
                    </label>
                    <input
                      type="text"
                      value={testPhone}
                      onChange={(e) => setTestPhone(e.target.value)}
                      placeholder="+919876543210"
                      className="w-full rounded-xl border border-slate-300 p-2 text-xs font-mono text-slate-900 focus:outline-none"
                    />
                  </div>
                  <div className="md:col-span-2">
                    <label className="block text-[11px] font-semibold text-slate-600 mb-1">
                      Message Text
                    </label>
                    <div className="flex space-x-2">
                      <input
                        type="text"
                        value={testMessageText}
                        onChange={(e) => setTestMessageText(e.target.value)}
                        className="w-full rounded-xl border border-slate-300 p-2 text-xs text-slate-900 focus:outline-none"
                      />
                      <button
                        type="submit"
                        disabled={isSendingTest}
                        className="inline-flex items-center space-x-1.5 rounded-xl bg-slate-900 px-4 py-2 text-xs font-bold text-white hover:bg-slate-800 transition shrink-0 disabled:opacity-50"
                      >
                        {isSendingTest ? <RefreshCw className="h-3.5 w-3.5 animate-spin" /> : <Send className="h-3.5 w-3.5" />}
                        <span>Send</span>
                      </button>
                    </div>
                  </div>
                </form>
              </div>
            </div>
          )}

          {/* TAB 2: GUIDE */}
          {activeTab === 'GUIDE' && (
            <div className="space-y-6 text-xs text-slate-700 leading-relaxed">
              <div className="rounded-xl border border-emerald-200 bg-emerald-50/60 p-4">
                <h3 className="text-sm font-bold text-emerald-950 mb-1">
                  Meta WhatsApp Business Cloud API Integration Steps
                </h3>
                <p className="text-xs text-emerald-900">
                  Follow these 5 steps to connect your official Meta Business Account or Test Sandbox with ProfitGuard AI.
                </p>
              </div>

              <div className="space-y-4">
                <div className="rounded-xl border border-slate-200 p-4 space-y-2">
                  <div className="flex items-center space-x-2">
                    <span className="flex h-6 w-6 items-center justify-center rounded-full bg-slate-900 text-white font-bold text-xs">
                      1
                    </span>
                    <h4 className="font-bold text-slate-900">Create Meta App in Developers Portal</h4>
                  </div>
                  <p className="text-slate-600 pl-8">
                    Go to <a href="https://developers.facebook.com" target="_blank" rel="noreferrer" className="text-emerald-700 underline font-semibold">developers.facebook.com</a> → My Apps → Create App.
                    Choose <strong className="text-slate-900">Other</strong> → App Type: <strong className="text-slate-900">Business</strong>.
                  </p>
                </div>

                <div className="rounded-xl border border-slate-200 p-4 space-y-2">
                  <div className="flex items-center space-x-2">
                    <span className="flex h-6 w-6 items-center justify-center rounded-full bg-slate-900 text-white font-bold text-xs">
                      2
                    </span>
                    <h4 className="font-bold text-slate-900">Add WhatsApp Product & Retrieve Phone Number ID</h4>
                  </div>
                  <p className="text-slate-600 pl-8">
                    In your App Dashboard, click <strong className="text-slate-900">Add Product</strong> → <strong className="text-slate-900">WhatsApp</strong>.
                    Navigate to <strong className="text-slate-900">API Setup</strong> to find your <strong className="text-slate-900 font-mono">Phone Number ID</strong> and <strong className="text-slate-900 font-mono">WhatsApp Business Account ID</strong>.
                  </p>
                </div>

                <div className="rounded-xl border border-slate-200 p-4 space-y-2">
                  <div className="flex items-center space-x-2">
                    <span className="flex h-6 w-6 items-center justify-center rounded-full bg-slate-900 text-white font-bold text-xs">
                      3
                    </span>
                    <h4 className="font-bold text-slate-900">Configure Webhook Callback & Verify Token</h4>
                  </div>
                  <p className="text-slate-600 pl-8">
                    Navigate to <strong className="text-slate-900">WhatsApp → Configuration</strong>. Click <strong className="text-slate-900">Edit</strong> under Webhook.
                    Paste your Callback URL and Verify Token from the Configuration tab.
                    Click <strong className="text-slate-900">Verify and Save</strong>. Under Webhook fields, click <strong className="text-slate-900">Manage</strong> and subscribe to <strong className="text-emerald-700 font-semibold font-mono">messages</strong>.
                  </p>
                </div>

                <div className="rounded-xl border border-slate-200 p-4 space-y-2">
                  <div className="flex items-center space-x-2">
                    <span className="flex h-6 w-6 items-center justify-center rounded-full bg-slate-900 text-white font-bold text-xs">
                      4
                    </span>
                    <h4 className="font-bold text-slate-900">Create System User & Permanent Token</h4>
                  </div>
                  <p className="text-slate-600 pl-8">
                    In <a href="https://business.facebook.com/settings" target="_blank" rel="noreferrer" className="text-emerald-700 underline font-semibold">Business Manager Settings</a> → Users → System Users.
                    Create an Admin System User. Click <strong className="text-slate-900">Generate New Token</strong>, select your App, and grant:
                    <strong className="text-slate-900 font-mono ml-1">whatsapp_business_messaging</strong> and <strong className="text-slate-900 font-mono ml-1">whatsapp_business_management</strong>.
                  </p>
                </div>

                <div className="rounded-xl border border-slate-200 p-4 space-y-2">
                  <div className="flex items-center space-x-2">
                    <span className="flex h-6 w-6 items-center justify-center rounded-full bg-slate-900 text-white font-bold text-xs">
                      5
                    </span>
                    <h4 className="font-bold text-slate-900">Set Up Approved Templates for COD & NDR</h4>
                  </div>
                  <p className="text-slate-600 pl-8">
                    WhatsApp requires utility templates for customer outreach outside the 24h window:
                    <br />
                    • <strong className="text-slate-900 font-mono">order_confirmation_cod</strong>: With buttons <strong className="text-emerald-700">CONFIRM_ORDER</strong> and <strong className="text-rose-700">CANCEL_ORDER</strong>.
                    <br />
                    • <strong className="text-slate-900 font-mono">ndr_delivery_recovery</strong>: For address re-verification and delivery rescheduling.
                  </p>
                </div>
              </div>
            </div>
          )}

          {/* TAB 3: LOGS */}
          {activeTab === 'LOGS' && (
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <h3 className="text-xs font-bold text-slate-900">
                  Recent Outbound & Inbound WhatsApp Transmissions
                </h3>
                <span className="text-[11px] text-slate-500">
                  Audited delivery receipts and provider timestamps
                </span>
              </div>

              {messages.length === 0 ? (
                <div className="rounded-xl border border-slate-200 bg-slate-50 py-12 text-center text-slate-500 text-xs">
                  No WhatsApp messages recorded yet. Send a test message or trigger COD verification to see delivery events.
                </div>
              ) : (
                <div className="overflow-x-auto rounded-xl border border-slate-200">
                  <table className="w-full text-left text-xs">
                    <thead className="border-b bg-slate-50 font-semibold text-slate-600">
                      <tr>
                        <th className="px-3.5 py-2.5">Time</th>
                        <th className="px-3.5 py-2.5">Direction</th>
                        <th className="px-3.5 py-2.5">Recipient / Sender</th>
                        <th className="px-3.5 py-2.5">Message / Template</th>
                        <th className="px-3.5 py-2.5">Status</th>
                        <th className="px-3.5 py-2.5">Cost</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100">
                      {messages.map((m) => (
                        <tr key={m.id} className="hover:bg-slate-50/70">
                          <td className="px-3.5 py-2 text-slate-500 font-mono text-[11px]">
                            {new Date(m.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
                          </td>
                          <td className="px-3.5 py-2">
                            <span
                              className={`rounded px-1.5 py-0.5 text-[10px] font-bold ${
                                m.direction === 'OUTBOUND'
                                  ? 'bg-blue-100 text-blue-800'
                                  : 'bg-emerald-100 text-emerald-800'
                              }`}
                            >
                              {m.direction}
                            </span>
                          </td>
                          <td className="px-3.5 py-2 font-mono text-[11px] text-slate-800">
                            {m.direction === 'OUTBOUND' ? m.recipient_phone : m.sender_phone}
                          </td>
                          <td className="px-3.5 py-2 text-slate-700 max-w-xs truncate" title={m.body_preview || ''}>
                            {m.body_preview || m.template_name || 'Template'}
                          </td>
                          <td className="px-3.5 py-2">
                            <span
                              className={`rounded px-2 py-0.5 text-[10px] font-bold ${
                                m.status === 'DELIVERED' || m.status === 'READ'
                                  ? 'bg-emerald-100 text-emerald-800'
                                  : m.status === 'SENT'
                                  ? 'bg-sky-100 text-sky-800'
                                  : m.status === 'FAILED'
                                  ? 'bg-rose-100 text-rose-800'
                                  : 'bg-slate-100 text-slate-800'
                              }`}
                            >
                              {m.status}
                            </span>
                          </td>
                          <td className="px-3.5 py-2 font-mono text-[11px] text-slate-600">
                            ₹{m.intervention_cost}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          )}

          {/* TAB 4: OPTOUTS */}
          {activeTab === 'OPTOUTS' && (
            <div className="space-y-4">
              <div className="rounded-xl border border-slate-200 bg-slate-50 p-4 text-xs text-slate-600 leading-relaxed">
                <p>
                  <strong className="text-slate-900">Compliance Invariant:</strong> Customers who reply with{' '}
                  <code className="bg-slate-200 px-1 py-0.5 rounded font-mono text-slate-900">STOP</code>,{' '}
                  <code className="bg-slate-200 px-1 py-0.5 rounded font-mono text-slate-900">UNSUBSCRIBE</code>, or{' '}
                  <code className="bg-slate-200 px-1 py-0.5 rounded font-mono text-slate-900">OPT OUT</code> are immediately registered here.
                  ProfitGuard AI strictly prevents dispatching any further automated WhatsApp messages to these numbers.
                </p>
              </div>

              {optOuts.length === 0 ? (
                <div className="rounded-xl border border-slate-200 bg-white py-10 text-center text-slate-400 text-xs">
                  No opted-out numbers. All recipient communications are currently active.
                </div>
              ) : (
                <div className="overflow-x-auto rounded-xl border border-slate-200">
                  <table className="w-full text-left text-xs">
                    <thead className="border-b bg-slate-50 font-semibold text-slate-600">
                      <tr>
                        <th className="px-4 py-2.5">Opted-Out Phone</th>
                        <th className="px-4 py-2.5">Opt-Out Timestamp</th>
                        <th className="px-4 py-2.5">Trigger Keyword / Reason</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100">
                      {optOuts.map((o) => (
                        <tr key={o.id}>
                          <td className="px-4 py-2 font-mono font-bold text-slate-900">{o.phone_number}</td>
                          <td className="px-4 py-2 text-slate-500 font-mono">{new Date(o.opted_out_at).toLocaleString()}</td>
                          <td className="px-4 py-2">
                            <span className="rounded bg-rose-50 px-2 py-0.5 text-[10px] font-bold text-rose-800 border border-rose-200">
                              {o.reason}
                            </span>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between border-t border-slate-200 bg-slate-50 px-6 py-3.5">
          <div className="flex items-center space-x-2 text-slate-500 text-xs">
            <ShieldCheck className="h-4 w-4 text-emerald-600" />
            <span>End-to-end encrypted credentials & HMAC webhook protection</span>
          </div>
          <button
            onClick={onClose}
            className="rounded-xl border border-slate-300 bg-white px-4 py-2 text-xs font-semibold text-slate-700 hover:bg-slate-100 transition shadow-xs"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
};
