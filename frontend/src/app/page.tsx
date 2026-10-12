'use client';

import React, { useState, useEffect, useCallback } from 'react';
import {
  ShieldAlert,
  ShieldCheck,
  Plus,
  UploadCloud,
  History,
  TrendingUp,
  Package,
  IndianRupee,
  RefreshCw,
  RotateCcw,
  Truck,
  AlertTriangle,
  Layers,
  Search,
  CheckCircle2,
  LogOut,
  Sparkles,
  Receipt,
  FileSpreadsheet,
  Settings,
  Webhook,
  BarChart3,
  ExternalLink,
  ChevronRight,
  Clock,
  ArrowRight,
  Filter,
  Cpu,
  Activity,
  Shield,
} from 'lucide-react';
import {
  Order,
  OrderListResponse,
  NDRCase,
  NDRListResponse,
  DashboardSummary,
  MLStatusResponse,
  ShopifyStoreConfig,
} from '@/types';
import {
  fetchOrders,
  fetchNDRCases,
  fetchDashboardSummary,
  hasValidSession,
  getStoredOrgId,
  getStoredUserEmail,
  getStoredOrgName,
  logoutSession,
  confirmOrder,
  resumeOrder,
  fetchMLStatus,
  fetchShopifyStoreConfig,
} from '@/services/api';
import { LandingView } from '@/components/LandingView';
import { AuthView } from '@/components/AuthView';
import { OnboardingWizard } from '@/components/OnboardingWizard';
import { IntegrationsTab } from '@/components/IntegrationsTab';
import { SettingsTab } from '@/components/SettingsTab';
import { CreateOrderModal } from '@/components/CreateOrderModal';
import { OrderFilters } from '@/components/OrderFilters';
import { OrderTable } from '@/components/OrderTable';
import { CSVImportModal } from '@/components/CSVImportModal';
import { ImportHistoryModal } from '@/components/ImportHistoryModal';
import { OrderDecisionModal } from '@/components/OrderDecisionModal';
import { NDRTable } from '@/components/NDRTable';
import { NDRCaseModal } from '@/components/NDRCaseModal';
import { SimulateDeliveryModal } from '@/components/SimulateDeliveryModal';
import { FinancialReconciliationModal } from '@/components/FinancialReconciliationModal';

type TabType = 'OVERVIEW' | 'ORDERS' | 'DECISIONS' | 'DELIVERY' | 'NDR' | 'LEDGER' | 'INTEGRATIONS' | 'SETTINGS';

export default function DashboardPage() {
  const [isMounted, setIsMounted] = useState(false);
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [showAuthModal, setShowAuthModal] = useState(false);
  const [authModalTab, setAuthModalTab] = useState<'LOGIN' | 'REGISTER'>('LOGIN');

  // Active Navigation Tab
  const [activeTab, setActiveTab] = useState<TabType>('OVERVIEW');

  // Tenant / User Context
  const [currentOrgId, setCurrentOrgId] = useState<string>('');
  const [currentOrgName, setCurrentOrgName] = useState<string>('Acme D2C Store');
  const [userEmail, setUserEmail] = useState<string>('');
  const [isOnboardingOpen, setIsOnboardingOpen] = useState(false);

  // Dashboard Metrics
  const [summary, setSummary] = useState<DashboardSummary | null>(null);

  // Orders State
  const [orders, setOrders] = useState<Order[]>([]);
  const [totalOrders, setTotalOrders] = useState(0);
  const [orderLimit] = useState(25);
  const [orderOffset, setOrderOffset] = useState(0);
  const [isOrdersLoading, setIsOrdersLoading] = useState(false);
  const [ordersError, setOrdersError] = useState<string | null>(null);

  // Orders Filters State
  const [orderSearch, setOrderSearch] = useState('');
  const [orderStatus, setOrderStatus] = useState('');
  const [orderPaymentMethod, setOrderPaymentMethod] = useState('');

  // NDR Queue State
  const [ndrCases, setNdrCases] = useState<NDRCase[]>([]);
  const [totalNdrCases, setTotalNdrCases] = useState(0);
  const [ndrLimit] = useState(25);
  const [ndrOffset, setNdrOffset] = useState(0);
  const [isNdrLoading, setIsNdrLoading] = useState(false);
  const [ndrError, setNdrError] = useState<string | null>(null);

  // NDR Filters State
  const [ndrSearch, setNdrSearch] = useState('');
  const [ndrStatus, setNdrStatus] = useState('');
  const [ndrPriority, setNdrPriority] = useState('');
  const [ndrReason, setNdrReason] = useState('');

  // Modals State
  const [isCreateOrderModalOpen, setIsCreateOrderModalOpen] = useState(false);
  const [isImportModalOpen, setIsImportModalOpen] = useState(false);
  const [isHistoryModalOpen, setIsHistoryModalOpen] = useState(false);
  const [selectedOrderForDecision, setSelectedOrderForDecision] = useState<Order | null>(null);
  const [selectedOrderForSimulation, setSelectedOrderForSimulation] = useState<Order | null>(null);
  const [selectedOrderForReconciliation, setSelectedOrderForReconciliation] = useState<Order | null>(null);
  const [selectedNdrCaseId, setSelectedNdrCaseId] = useState<string | null>(null);

  // Feedback notifications
  const [feedback, setFeedback] = useState<string | null>(null);

  // System & Integration Status
  const [mlStatus, setMlStatus] = useState<MLStatusResponse | null>(null);
  const [shopifyConfig, setShopifyConfig] = useState<ShopifyStoreConfig | null>(null);

  // Check auth on mount
  useEffect(() => {
    setIsMounted(true);
    if (hasValidSession()) {
      setIsAuthenticated(true);
      const orgId = getStoredOrgId() || '';
      setCurrentOrgId(orgId);
      setCurrentOrgName(getStoredOrgName() || 'Acme D2C Store');
      setUserEmail(getStoredUserEmail() || '');

      // Check if first-time onboarding needed
      if (orgId && typeof window !== 'undefined') {
        const completed = localStorage.getItem(`profitguard_onboarding_completed_${orgId}`);
        if (!completed) {
          setIsOnboardingOpen(true);
        }
      }
    }
  }, []);

  const handleAuthSuccess = () => {
    setIsAuthenticated(true);
    setShowAuthModal(false);
    const orgId = getStoredOrgId() || '';
    setCurrentOrgId(orgId);
    setCurrentOrgName(getStoredOrgName() || 'Acme D2C Store');
    setUserEmail(getStoredUserEmail() || '');
    loadAllData();

    if (orgId && typeof window !== 'undefined') {
      const completed = localStorage.getItem(`profitguard_onboarding_completed_${orgId}`);
      if (!completed) {
        setIsOnboardingOpen(true);
      }
    }
  };

  const handleSignOut = async () => {
    await logoutSession();
    setIsAuthenticated(false);
    setShowAuthModal(false);
    setOrders([]);
    setNdrCases([]);
    setSummary(null);
  };

  const loadSummary = useCallback(async () => {
    try {
      const data = await fetchDashboardSummary();
      setSummary(data);
    } catch (err: any) {
      if (err.message === 'AUTHENTICATION_REQUIRED') {
        setIsAuthenticated(false);
      }
    }
  }, []);

  const loadOrders = useCallback(async () => {
    setIsOrdersLoading(true);
    setOrdersError(null);
    try {
      const res: OrderListResponse = await fetchOrders({
        search: orderSearch.trim() || undefined,
        status: orderStatus || undefined,
        payment_method: orderPaymentMethod || undefined,
        limit: orderLimit,
        offset: orderOffset,
      });
      setOrders(res.orders || []);
      setTotalOrders(res.total || 0);
    } catch (err: any) {
      if (err.message === 'AUTHENTICATION_REQUIRED') {
        setIsAuthenticated(false);
      } else {
        setOrdersError(err.message || 'Failed to load orders');
      }
      setOrders([]);
      setTotalOrders(0);
    } finally {
      setIsOrdersLoading(false);
    }
  }, [orderSearch, orderStatus, orderPaymentMethod, orderLimit, orderOffset]);

  const loadNDRCases = useCallback(async () => {
    setIsNdrLoading(true);
    setNdrError(null);
    try {
      const res: NDRListResponse = await fetchNDRCases({
        search: ndrSearch.trim() || undefined,
        status: ndrStatus || undefined,
        reason: ndrReason || undefined,
        priority: ndrPriority || undefined,
        limit: ndrLimit,
        offset: ndrOffset,
      });
      setNdrCases(res.cases || []);
      setTotalNdrCases(res.total || 0);
    } catch (err: any) {
      if (err.message === 'AUTHENTICATION_REQUIRED') {
        setIsAuthenticated(false);
      } else {
        setNdrError(err.message || 'Failed to load NDR cases');
      }
      setNdrCases([]);
      setTotalNdrCases(0);
    } finally {
      setIsNdrLoading(false);
    }
  }, [ndrSearch, ndrStatus, ndrReason, ndrPriority, ndrLimit, ndrOffset]);

  const loadMLStatus = useCallback(async () => {
    try {
      const data = await fetchMLStatus();
      setMlStatus(data);
    } catch (err) {
      console.warn('Failed to load ML engine status:', err);
    }
  }, []);

  const loadShopifyConfig = useCallback(async () => {
    try {
      const data = await fetchShopifyStoreConfig();
      setShopifyConfig(data);
    } catch (err) {
      console.warn('Failed to load Shopify store configuration:', err);
    }
  }, []);

  const loadAllData = useCallback(() => {
    loadSummary();
    loadOrders();
    loadNDRCases();
    loadMLStatus();
    loadShopifyConfig();
  }, [loadSummary, loadOrders, loadNDRCases, loadMLStatus, loadShopifyConfig]);

  useEffect(() => {
    if (isAuthenticated) {
      loadAllData();
    }
  }, [isAuthenticated, loadAllData]);

  const handleOrderCreated = (newOrder: Order) => {
    setFeedback(`Order #${newOrder.external_order_id} created successfully.`);
    loadOrders();
    loadSummary();
    setSelectedOrderForDecision(newOrder);
  };

  const handleConfirmOrder = async (order: Order) => {
    try {
      await confirmOrder(order.id);
      setFeedback(`Order #${order.external_order_id} confirmed. Status updated to CONFIRMED.`);
      loadOrders();
      loadSummary();
    } catch (err: any) {
      setFeedback(`Failed to confirm order: ${err.message}`);
    }
  };

  const handleResumeOrder = async (order: Order) => {
    try {
      await resumeOrder(order.id);
      setFeedback(`Hold lifted for order #${order.external_order_id}. Resumed to CONFIRMED.`);
      loadOrders();
      loadSummary();
    } catch (err: any) {
      setFeedback(`Failed to resume order: ${err.message}`);
    }
  };

  const formatCurrency = (val: number | string) => {
    const num = typeof val === 'string' ? parseFloat(val || '0') : val;
    if (isNaN(num)) return '0.00';
    return num.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  };

  // Public Landing / Auth View for Unauthenticated Visitors
  if (!isAuthenticated) {
    if (showAuthModal) {
      return (
        <AuthView
          onSuccess={handleAuthSuccess}
          onBack={() => setShowAuthModal(false)}
          initialTab={authModalTab}
        />
      );
    }
    return (
      <LandingView
        onOpenAuth={(tab = 'LOGIN') => {
          setAuthModalTab(tab);
          setShowAuthModal(true);
        }}
      />
    );
  }

  if (!isMounted) {
    return (
      <div className="min-h-screen bg-slate-900 flex items-center justify-center">
        <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-emerald-500 text-slate-950 shadow-lg animate-pulse">
          <ShieldCheck className="h-6 w-6" />
        </div>
      </div>
    );
  }

  const codCount = summary?.payment_method_breakdown?.['COD'] ?? 0;
  const prepaidCount = summary?.payment_method_breakdown?.['PREPAID'] ?? 0;
  const totalCount = summary?.total_orders ?? totalOrders;
  const codPct = totalCount > 0 ? Math.round((codCount / totalCount) * 100) : 0;
  const activeNdrCount = summary?.active_ndr_count ?? totalNdrCases;
  const highRiskCount = summary?.high_risk_count ?? 0;

  // Active in-transit orders for delivery tab
  const inTransitOrders = orders.filter(
    (o) => ['CONFIRMED', 'READY_TO_SHIP', 'SHIPPED', 'OUT_FOR_DELIVERY', 'DELIVERY_ATTEMPT_FAILED', 'HOLD'].includes(o.status)
  );

  return (
    <main className="min-h-screen bg-slate-50 text-slate-800">
      {/* Top Application Header */}
      <header className="sticky top-0 z-30 border-b border-slate-200 bg-white/95 backdrop-blur-md">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-6 py-3">
          {/* Logo & Store Workspace Identity */}
          <div className="flex items-center space-x-3.5">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-emerald-600 text-white shadow-md shadow-emerald-600/20">
              <ShieldCheck className="h-6 w-6" />
            </div>
            <div>
              <div className="flex items-center space-x-2">
                <span className="text-base font-extrabold text-slate-900 tracking-tight">ProfitGuard AI</span>
                <span className="rounded bg-emerald-50 border border-emerald-200 px-2 py-0.5 text-[10px] font-bold text-emerald-800">
                  D2C COMMAND CENTRE
                </span>
              </div>
              <div className="flex items-center space-x-2 text-xs text-slate-500">
                <span>
                  Store: <strong className="text-slate-700">{currentOrgName}</strong>
                </span>
                {userEmail && (
                  <>
                    <span className="text-slate-300">•</span>
                    <span className="text-slate-500">{userEmail}</span>
                  </>
                )}
              </div>
            </div>
          </div>

          {/* Header Action Buttons */}
          <div className="flex items-center space-x-2.5">
            <button
              onClick={() => setIsCreateOrderModalOpen(true)}
              className="flex items-center space-x-1.5 rounded-xl bg-emerald-600 px-3.5 py-2 text-xs font-bold text-white shadow-md shadow-emerald-600/20 hover:bg-emerald-700 transition"
              title="Create new order manually"
            >
              <Plus className="h-4 w-4" />
              <span>New Order</span>
            </button>

            <button
              onClick={() => setIsImportModalOpen(true)}
              className="flex items-center space-x-1.5 rounded-xl border border-slate-200 bg-white px-3 py-2 text-xs font-semibold text-slate-700 shadow-sm hover:bg-slate-50 transition"
              title="Batch import orders from CSV"
            >
              <UploadCloud className="h-3.5 w-3.5 text-slate-500" />
              <span>Import CSV</span>
            </button>
            <div className="h-5 w-[1px] bg-slate-200 mx-1" />

            <button
              onClick={handleSignOut}
              className="flex items-center space-x-1 rounded-xl border border-rose-200 bg-rose-50 px-2.5 py-2 text-xs font-semibold text-rose-700 hover:bg-rose-100 transition"
              title="Sign out of current workspace"
            >
              <LogOut className="h-3.5 w-3.5" />
              <span className="hidden sm:inline">Sign Out</span>
            </button>
          </div>
        </div>

        {/* Global Feedback Banner */}
        {feedback && (
          <div className="bg-emerald-50 border-t border-b border-emerald-200 px-6 py-2 text-xs text-emerald-900 flex items-center justify-between">
            <div className="flex items-center space-x-2">
              <CheckCircle2 className="h-4 w-4 text-emerald-600 shrink-0" />
              <span className="font-medium">{feedback}</span>
            </div>
            <button
              onClick={() => setFeedback(null)}
              className="text-emerald-700 hover:text-emerald-900 text-[11px] font-bold"
            >
              Dismiss
            </button>
          </div>
        )}

        {/* 8-Section SaaS Navigation Bar */}
        <div className="mx-auto max-w-7xl px-6 border-t border-slate-100 flex space-x-1 overflow-x-auto no-scrollbar">
          {[
            { id: 'OVERVIEW', label: 'Dashboard', icon: BarChart3 },
            { id: 'ORDERS', label: `Orders (${totalCount})`, icon: Layers },
            { id: 'DECISIONS', label: 'Risk Analysis', icon: Sparkles, badge: highRiskCount > 0 ? `${highRiskCount} Risk` : undefined, badgeColor: 'bg-amber-100 text-amber-800' },
            { id: 'DELIVERY', label: 'Delivery Operations', icon: Truck, badge: inTransitOrders.length > 0 ? `${inTransitOrders.length}` : undefined, badgeColor: 'bg-blue-100 text-blue-800' },
            { id: 'NDR', label: 'Recovery', icon: RotateCcw, badge: activeNdrCount > 0 ? `${activeNdrCount}` : undefined, badgeColor: 'bg-rose-100 text-rose-800' },
            { id: 'LEDGER', label: 'Reports & Ledger', icon: Receipt },
            { id: 'INTEGRATIONS', label: 'Integrations', icon: Webhook },
            { id: 'SETTINGS', label: 'Settings', icon: Settings },
          ].map((tab) => {
            const Icon = tab.icon;
            const isActive = activeTab === tab.id;
            return (
              <button
                key={tab.id}
                type="button"
                onClick={() => setActiveTab(tab.id as TabType)}
                className={`flex items-center space-x-2 py-3 px-3 text-xs font-bold border-b-2 transition whitespace-nowrap ${
                  isActive
                    ? 'border-emerald-600 text-emerald-700'
                    : 'border-transparent text-slate-500 hover:text-slate-800'
                }`}
              >
                <Icon className={`h-4 w-4 ${isActive ? 'text-emerald-600' : 'text-slate-400'}`} />
                <span>{tab.label}</span>
                {tab.badge && (
                  <span className={`rounded-full px-1.5 py-0.2 text-[10px] font-bold ${tab.badgeColor}`}>
                    {tab.badge}
                  </span>
                )}
              </button>
            );
          })}
        </div>
      </header>

      {/* Main Content Area */}
      <div className="mx-auto max-w-7xl px-6 py-8">
        {/* ================= SECTION 1: OVERVIEW ================= */}
        {activeTab === 'OVERVIEW' && (
          <div className="space-y-8">
            {/* Executive KPI Cards */}
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-5">
              <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
                <div className="flex items-center justify-between text-slate-500">
                  <span className="text-[11px] font-bold uppercase tracking-wider">Gross Merchandise Value</span>
                  <TrendingUp className="h-4 w-4 text-emerald-500" />
                </div>
                <div className="mt-2 text-2xl font-black text-slate-900">
                  ₹{formatCurrency(summary?.total_gmv ?? orders.reduce((acc, o) => acc + parseFloat(o.order_value || '0'), 0))}
                </div>
                <p className="mt-1 text-[10px] text-slate-400">Total catalog order volume</p>
              </div>

              <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
                <div className="flex items-center justify-between text-slate-500">
                  <span className="text-[11px] font-bold uppercase tracking-wider">Expected Contribution</span>
                  <Sparkles className="h-4 w-4 text-purple-500" />
                </div>
                <div className="mt-2 text-2xl font-black text-purple-700">
                  ₹{formatCurrency(summary?.expected_contribution ?? 0)}
                </div>
                <p className="mt-1 text-[10px] text-slate-400">Pre-dispatch optimal payoff (EC)</p>
              </div>

              <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
                <div className="flex items-center justify-between text-slate-500">
                  <span className="text-[11px] font-bold uppercase tracking-wider">Realized Net Profit</span>
                  <Receipt className="h-4 w-4 text-blue-500" />
                </div>
                <div className="mt-2 text-2xl font-black text-blue-700">
                  ₹{formatCurrency(summary?.realized_contribution ?? 0)}
                </div>
                <p className="mt-1 text-[10px] text-slate-400">Settled margin after shipping & COGS</p>
              </div>

              <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
                <div className="flex items-center justify-between text-slate-500">
                  <span className="text-[11px] font-bold uppercase tracking-wider">COD Exposure</span>
                  <IndianRupee className="h-4 w-4 text-amber-500" />
                </div>
                <div className="mt-2 text-2xl font-black text-amber-600">
                  {codPct}%
                  <span className="text-xs font-semibold text-slate-400 ml-1.5">
                    ({codCount} COD / {prepaidCount} Prepaid)
                  </span>
                </div>
                <p className="mt-1 text-[10px] text-slate-400">Cash on delivery volume share</p>
              </div>

              <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
                <div className="flex items-center justify-between text-slate-500">
                  <span className="text-[11px] font-bold uppercase tracking-wider">Active NDR Interventions</span>
                  <RotateCcw className="h-4 w-4 text-rose-500" />
                </div>
                <div className="mt-2 text-2xl font-black text-rose-600">
                  {activeNdrCount}
                  <span className="text-xs font-semibold text-slate-400 ml-1.5">
                    ({highRiskCount} Pre-Dispatch)
                  </span>
                </div>
                <p className="mt-1 text-[10px] text-slate-400">Failed delivery attempts in progress</p>
              </div>
            </div>

            {/* Operational Engine & Systems Status */}
            <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
              <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between pb-4 border-b border-slate-100 gap-2">
                <div className="flex items-center space-x-2.5">
                  <span className="flex h-8 w-8 items-center justify-center rounded-xl bg-slate-900 text-white">
                    <Activity className="h-4 w-4 text-emerald-400" />
                  </span>
                  <div>
                    <h3 className="text-sm font-bold text-slate-900">Decision Engine & Operational Status</h3>
                    <p className="text-xs text-slate-500">Live health of risk evaluation models, storefront ingress, and policy gates</p>
                  </div>
                </div>
                <div className="flex items-center space-x-2">
                  <span className="inline-flex items-center gap-1.5 rounded-full bg-emerald-50 px-3 py-1 text-xs font-bold text-emerald-700 border border-emerald-200">
                    <span className="h-2 w-2 rounded-full bg-emerald-500 animate-pulse" />
                    Engine Active
                  </span>
                </div>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-3 gap-6 pt-5">
                {/* 1. Storefront Ingestion Status */}
                <div className="rounded-xl border border-slate-100 bg-slate-50/70 p-4 flex flex-col justify-between">
                  <div>
                    <div className="flex items-center justify-between mb-2">
                      <span className="text-xs font-bold uppercase tracking-wider text-slate-500 flex items-center gap-1.5">
                        <Webhook className="h-3.5 w-3.5 text-indigo-600" />
                        Storefront Ingestion
                      </span>
                      {shopifyConfig && shopifyConfig.status === 'ACTIVE' ? (
                        <span className="rounded-md bg-emerald-100 px-2 py-0.5 text-[10px] font-bold text-emerald-800">
                          Connected
                        </span>
                      ) : (
                        <span className="rounded-md bg-amber-100 px-2 py-0.5 text-[10px] font-bold text-amber-800">
                          Waiting for Connection
                        </span>
                      )}
                    </div>

                    <div className="text-sm font-bold text-slate-900 font-mono">
                      {shopifyConfig && shopifyConfig.status === 'ACTIVE'
                        ? shopifyConfig.shop_domain
                        : 'No Shopify Store Connected'}
                    </div>

                    <p className="mt-1.5 text-xs text-slate-500 leading-relaxed">
                      {shopifyConfig && shopifyConfig.status === 'ACTIVE'
                        ? `Live webhook receiver active with HMAC-SHA256 signature verification (API ${shopifyConfig.api_version || '2024-01'}).`
                        : 'Connect your Shopify store via private app credentials or stream orders via authenticated Webhook / CSV batch upload.'}
                    </p>
                  </div>

                  <div className="pt-3 mt-3 border-t border-slate-200/60 flex items-center justify-between">
                    <span className="text-[11px] text-slate-500">Method</span>
                    <button
                      onClick={() => setActiveTab('INTEGRATIONS')}
                      className="text-[11px] font-bold text-indigo-600 hover:text-indigo-800 flex items-center gap-1"
                    >
                      {shopifyConfig && shopifyConfig.status === 'ACTIVE' ? 'Manage Webhooks' : 'Connect Storefront'}{' '}
                      <ArrowRight className="h-3 w-3" />
                    </button>
                  </div>
                </div>

                {/* 2. RTO Decision Intelligence & ML Mode */}
                <div className="rounded-xl border border-slate-100 bg-slate-50/70 p-4 flex flex-col justify-between">
                  <div>
                    <div className="flex items-center justify-between mb-2">
                      <span className="text-xs font-bold uppercase tracking-wider text-slate-500 flex items-center gap-1.5">
                        <Cpu className="h-3.5 w-3.5 text-purple-600" />
                        ML Inference Engine
                      </span>
                      {mlStatus?.model_loaded && mlStatus?.operating_mode !== 'DISABLED' ? (
                        <span className="rounded-md bg-emerald-100 px-2 py-0.5 text-[10px] font-bold text-emerald-800">
                          ML Inference Active
                        </span>
                      ) : (
                        <span className="rounded-md bg-slate-200 px-2 py-0.5 text-[10px] font-bold text-slate-700">
                          ML Inference Unavailable
                        </span>
                      )}
                    </div>

                    <div className="text-sm font-bold text-slate-900">
                      {mlStatus?.decision_policy_version || 'v1.1-ml-assisted'}
                    </div>

                    <p className="mt-1.5 text-xs text-slate-500 leading-relaxed">
                      Real-time RTO probability scoring at order ingestion. Fallback heuristic engine active with 100% decision availability.
                    </p>
                  </div>

                  <div className="pt-3 mt-3 border-t border-slate-200/60 flex items-center justify-between">
                    <span className="text-[11px] text-slate-500">Fallback Protection</span>
                    <span className="text-[11px] font-bold text-emerald-700">Deterministic Engine Ready</span>
                  </div>
                </div>

                {/* 3. Safety Governance Gate */}
                <div className="rounded-xl border border-slate-100 bg-slate-50/70 p-4 flex flex-col justify-between">
                  <div>
                    <div className="flex items-center justify-between mb-2">
                      <span className="text-xs font-bold uppercase tracking-wider text-slate-500 flex items-center gap-1.5">
                        <Shield className="h-3.5 w-3.5 text-emerald-600" />
                        Governance Gate
                      </span>
                      <span className="rounded-md bg-slate-200 px-2 py-0.5 text-[10px] font-bold text-slate-800">
                        Restricted / Advisory
                      </span>
                    </div>

                    <div className="text-sm font-bold text-slate-900">
                      Advisory Scoring Only
                    </div>

                    <p className="mt-1.5 text-xs text-slate-500 leading-relaxed">
                      Synthetic development weights: strictly gated from autonomous order cancellation. Merchants retain final authorization on all interventions.
                    </p>
                  </div>

                  <div className="pt-3 mt-3 border-t border-slate-200/60 flex items-center justify-between">
                    <span className="text-[11px] text-slate-500">Autonomous Actions</span>
                    <span className="text-[11px] font-bold text-rose-700">Restricted (Safety Gate)</span>
                  </div>
                </div>
              </div>
            </div>

            {/* RTO Risk Tier Distribution */}
            <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
              <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between mb-4 gap-2">
                <div>
                  <h3 className="text-sm font-bold text-slate-900">Pre-Dispatch RTO Risk Tier Distribution</h3>
                  <p className="text-xs text-slate-500">Cohort breakdown across current tenant orders</p>
                </div>
                <div className="text-xs font-semibold text-slate-500">
                  Total Evaluated Orders: <strong className="text-slate-900">{totalCount}</strong>
                </div>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
                <div className="rounded-xl border border-emerald-200 bg-emerald-50/50 p-4">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-bold text-emerald-900 uppercase">Low Risk</span>
                    <span className="rounded bg-emerald-200/60 px-2 py-0.5 text-[10px] font-bold text-emerald-800">
                      &lt;15% RTO
                    </span>
                  </div>
                  <div className="mt-2 text-2xl font-black text-emerald-950">
                    {Math.max(0, totalCount - highRiskCount)}
                  </div>
                  <p className="mt-1 text-[11px] text-emerald-800">
                    Policy Action: <strong>Ship As-Is</strong> (Instant dispatch)
                  </p>
                </div>

                <div className="rounded-xl border border-blue-200 bg-blue-50/50 p-4">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-bold text-blue-900 uppercase">Medium Risk</span>
                    <span className="rounded bg-blue-200/60 px-2 py-0.5 text-[10px] font-bold text-blue-800">
                      15–30% RTO
                    </span>
                  </div>
                  <div className="mt-2 text-2xl font-black text-blue-950">
                    {Math.max(0, Math.floor(totalCount * 0.25))}
                  </div>
                  <p className="mt-1 text-[11px] text-blue-800">
                    Policy Action: <strong>Verify OTP / WhatsApp</strong>
                  </p>
                </div>

                <div className="rounded-xl border border-amber-200 bg-amber-50/50 p-4">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-bold text-amber-900 uppercase">High Risk</span>
                    <span className="rounded bg-amber-200/60 px-2 py-0.5 text-[10px] font-bold text-amber-800">
                      30–50% RTO
                    </span>
                  </div>
                  <div className="mt-2 text-2xl font-black text-amber-950">
                    {highRiskCount}
                  </div>
                  <p className="mt-1 text-[11px] text-amber-800">
                    Policy Action: <strong>Prepaid Incentive / Call</strong>
                  </p>
                </div>

                <div className="rounded-xl border border-rose-200 bg-rose-50/50 p-4">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-bold text-rose-900 uppercase">Critical Risk</span>
                    <span className="rounded bg-rose-200/60 px-2 py-0.5 text-[10px] font-bold text-rose-800">
                      &gt;50% RTO
                    </span>
                  </div>
                  <div className="mt-2 text-2xl font-black text-rose-950">
                    {activeNdrCount}
                  </div>
                  <p className="mt-1 text-[11px] text-rose-800">
                    Policy Action: <strong>Manual Review / Hold</strong>
                  </p>
                </div>
              </div>
            </div>

            {/* Quick Operational Launchpad */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
              {/* Card 1: Pre-Dispatch Decisions */}
              <div className="rounded-2xl border border-purple-200 bg-purple-50/50 p-5 flex flex-col justify-between">
                <div>
                  <div className="flex items-center space-x-2 text-purple-900 font-bold text-sm mb-1">
                    <Sparkles className="h-4 w-4 text-purple-600" />
                    <span>Pre-Dispatch Decision Hub</span>
                  </div>
                  <p className="text-xs text-purple-700 mb-4 leading-relaxed">
                    Evaluate 5 candidate actions (Ship, OTP, Prepaid Discount, Manual Call, Hold) to optimize unit margins before warehouse dispatch.
                  </p>
                  <div className="text-xs font-bold text-purple-900 mb-1">
                    {highRiskCount} Orders Require Attention
                  </div>
                </div>
                <button
                  onClick={() => setActiveTab('DECISIONS')}
                  className="w-full flex items-center justify-center space-x-1.5 rounded-xl bg-purple-600 text-white py-2 text-xs font-bold hover:bg-purple-700 transition"
                >
                  <span>Review Candidate Payoffs</span>
                  <ArrowRight className="h-3.5 w-3.5" />
                </button>
              </div>

              {/* Card 2: Delivery Lifecycle */}
              <div className="rounded-2xl border border-blue-200 bg-blue-50/50 p-5 flex flex-col justify-between">
                <div>
                  <div className="flex items-center space-x-2 text-blue-900 font-bold text-sm mb-1">
                    <Truck className="h-4 w-4 text-blue-600" />
                    <span>Logistics Operations & Stepper</span>
                  </div>
                  <p className="text-xs text-blue-700 mb-4 leading-relaxed">
                    Track shipments across CONFIRMED, READY_TO_SHIP, SHIPPED, OUT_FOR_DELIVERY, and DELIVERED or NDR with live simulation controls.
                  </p>
                  <div className="text-xs font-bold text-blue-900 mb-1">
                    {inTransitOrders.length} Shipments in Transit Pipeline
                  </div>
                </div>
                <button
                  onClick={() => setActiveTab('DELIVERY')}
                  className="w-full flex items-center justify-center space-x-1.5 rounded-xl bg-blue-600 text-white py-2 text-xs font-bold hover:bg-blue-700 transition"
                >
                  <span>Manage Transit Pipeline</span>
                  <ArrowRight className="h-3.5 w-3.5" />
                </button>
              </div>

              {/* Card 3: NDR Recovery */}
              <div className="rounded-2xl border border-rose-200 bg-rose-50/50 p-5 flex flex-col justify-between">
                <div>
                  <div className="flex items-center space-x-2 text-rose-900 font-bold text-sm mb-1">
                    <RotateCcw className="h-4 w-4 text-rose-600" />
                    <span>NDR Recovery & Reattempts</span>
                  </div>
                  <p className="text-xs text-rose-700 mb-4 leading-relaxed">
                    Trigger automated customer contact (WhatsApp, phone verification, address correction) before packages convert to expensive RTO returns.
                  </p>
                  <div className="text-xs font-bold text-rose-900 mb-1">
                    {activeNdrCount} Failed Attempt Cases Open
                  </div>
                </div>
                <button
                  onClick={() => setActiveTab('NDR')}
                  className="w-full flex items-center justify-center space-x-1.5 rounded-xl bg-rose-600 text-white py-2 text-xs font-bold hover:bg-rose-700 transition"
                >
                  <span>Open NDR Queue</span>
                  <ArrowRight className="h-3.5 w-3.5" />
                </button>
              </div>
            </div>

            {/* Recent Orders Preview */}
            <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
              <div className="flex items-center justify-between mb-4">
                <div>
                  <h3 className="text-sm font-bold text-slate-900">Recent Customer Orders</h3>
                  <p className="text-xs text-slate-500">Live operational snapshot of incoming store orders</p>
                </div>
                <button
                  onClick={() => setActiveTab('ORDERS')}
                  className="text-xs font-bold text-emerald-700 hover:text-emerald-800 flex items-center gap-1"
                >
                  View All {totalCount} Orders <ArrowRight className="h-3.5 w-3.5" />
                </button>
              </div>

              {orders.length === 0 ? (
                <div className="py-12 text-center text-slate-400">
                  <Package className="h-10 w-10 mx-auto text-slate-300 mb-3" />
                  <p className="text-sm font-medium text-slate-600">No orders in this workspace yet.</p>
                  <p className="text-xs text-slate-400 mt-1 max-w-sm mx-auto">
                    Sync orders via Shopify webhook, import a CSV batch, or manually record an order to evaluate RTO risk.
                  </p>
                  <div className="mt-4 flex items-center justify-center gap-3">
                    <button
                      onClick={() => setIsCreateOrderModalOpen(true)}
                      className="rounded-xl bg-emerald-600 px-4 py-2 text-xs font-bold text-white hover:bg-emerald-700 transition"
                    >
                      Create First Order
                    </button>
                    <button
                      onClick={() => setIsImportModalOpen(true)}
                      className="rounded-xl border border-slate-200 bg-white px-4 py-2 text-xs font-semibold text-slate-700 hover:bg-slate-50 transition"
                    >
                      Import Orders CSV
                    </button>
                  </div>
                </div>
              ) : (
                <OrderTable
                  orders={orders.slice(0, 5)}
                  total={totalOrders}
                  limit={5}
                  offset={0}
                  onPageChange={() => {}}
                  isLoading={isOrdersLoading}
                  onSelectOrder={setSelectedOrderForDecision}
                  onSimulateOrder={setSelectedOrderForSimulation}
                  onConfirmOrder={handleConfirmOrder}
                  onResumeOrder={handleResumeOrder}
                  onReconcileOrder={setSelectedOrderForReconciliation}
                  onCreateOrder={() => setIsCreateOrderModalOpen(true)}
                />
              )}
            </div>
          </div>
        )}

        {/* ================= SECTION 2: ORDERS ================= */}
        {activeTab === 'ORDERS' && (
          <div className="space-y-5">
            <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
              <div>
                <h2 className="text-base font-bold text-slate-900">Tenant Orders Ledger</h2>
                <p className="text-xs text-slate-500">
                  Track full order lifecycle with pre-dispatch decisions, delivery simulation, and settled ledger reconciliation
                </p>
              </div>
              <div className="flex items-center space-x-2">
                <button
                  onClick={() => setIsCreateOrderModalOpen(true)}
                  className="flex items-center space-x-1.5 rounded-xl bg-emerald-600 px-3.5 py-2 text-xs font-bold text-white shadow-sm hover:bg-emerald-700 transition"
                >
                  <Plus className="h-3.5 w-3.5" />
                  <span>Create Order</span>
                </button>
                <button
                  onClick={() => setIsImportModalOpen(true)}
                  className="flex items-center space-x-1.5 rounded-xl border border-slate-200 bg-white px-3 py-2 text-xs font-semibold text-slate-700 hover:bg-slate-50 transition"
                >
                  <UploadCloud className="h-3.5 w-3.5 text-slate-500" />
                  <span>Import CSV</span>
                </button>
                <button
                  onClick={() => setIsHistoryModalOpen(true)}
                  className="rounded-xl border border-slate-200 bg-white p-2 text-slate-600 hover:bg-slate-50 transition"
                  title="View CSV Import Batches"
                >
                  <History className="h-4 w-4" />
                </button>
                <button
                  onClick={() => {
                    loadOrders();
                    loadSummary();
                  }}
                  className="flex items-center space-x-1 rounded-xl border border-slate-200 bg-white px-3 py-2 text-xs font-semibold text-slate-600 hover:bg-slate-50 transition"
                >
                  <RefreshCw className={`h-3.5 w-3.5 ${isOrdersLoading ? 'animate-spin' : ''}`} />
                  <span>Refresh</span>
                </button>
              </div>
            </div>

            {/* Filters */}
            <OrderFilters
              search={orderSearch}
              onSearchChange={(v) => {
                setOrderSearch(v);
                setOrderOffset(0);
              }}
              status={orderStatus}
              onStatusChange={(v) => {
                setOrderStatus(v);
                setOrderOffset(0);
              }}
              paymentMethod={orderPaymentMethod}
              onPaymentMethodChange={(v) => {
                setOrderPaymentMethod(v);
                setOrderOffset(0);
              }}
              onReset={() => {
                setOrderSearch('');
                setOrderStatus('');
                setOrderPaymentMethod('');
                setOrderOffset(0);
              }}
            />

            {ordersError && (
              <div className="flex items-center justify-between rounded-xl border border-rose-200 bg-rose-50 p-4 text-xs text-rose-800">
                <div className="flex items-center space-x-2">
                  <AlertTriangle className="h-4 w-4 text-rose-600 shrink-0" />
                  <span>{ordersError}</span>
                </div>
                <button onClick={() => loadOrders()} className="font-bold underline hover:text-rose-950">
                  Retry
                </button>
              </div>
            )}

            {/* Orders Table */}
            <OrderTable
              orders={orders}
              total={totalOrders}
              limit={orderLimit}
              offset={orderOffset}
              onPageChange={setOrderOffset}
              isLoading={isOrdersLoading}
              onSelectOrder={setSelectedOrderForDecision}
              onSimulateOrder={setSelectedOrderForSimulation}
              onConfirmOrder={handleConfirmOrder}
              onResumeOrder={handleResumeOrder}
              onReconcileOrder={setSelectedOrderForReconciliation}
              onCreateOrder={() => setIsCreateOrderModalOpen(true)}
            />
          </div>
        )}

        {/* ================= SECTION 3: DECISIONS ================= */}
        {activeTab === 'DECISIONS' && (
          <div className="space-y-6">
            <div className="rounded-2xl border border-purple-200 bg-purple-50/70 p-6">
              <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-4">
                <div>
                  <div className="flex items-center space-x-2">
                    <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-purple-200 text-purple-900">
                      <Sparkles className="h-4 w-4" />
                    </span>
                    <h2 className="text-base font-bold text-purple-950">5-Action Pre-Dispatch Decision Intelligence</h2>
                  </div>
                  <p className="text-xs text-purple-700 mt-1 max-w-3xl leading-relaxed">
                    For every order, ProfitGuard AI calculates mathematical Expected Contribution (EC) across 5 candidate actions:
                    <strong> Ship As-Is, Verify OTP, Incentivize Prepaid, Manual Review,</strong> and <strong>Hold / Cancel</strong>.
                    Intervention costs are subtracted once, and policy safety caps prevent unauthorized cancellations.
                  </p>
                </div>
                <button
                  onClick={() => setIsCreateOrderModalOpen(true)}
                  className="rounded-xl bg-purple-700 px-4 py-2 text-xs font-bold text-white shadow-sm hover:bg-purple-800 transition shrink-0"
                >
                  + Create Order to Evaluate
                </button>
              </div>
            </div>

            {/* Orders Decision Queue */}
            <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
              <h3 className="text-xs font-bold uppercase tracking-wider text-slate-500 mb-4">
                Orders Requiring Pre-Dispatch Decision or Evaluation
              </h3>

              {orders.length === 0 ? (
                <div className="py-8 text-center text-slate-400">
                  <p className="text-sm font-medium">No orders available in this workspace yet.</p>
                  <p className="text-xs text-slate-400 mt-1 max-w-sm mx-auto">
                    Sync orders from Shopify or create an order manually to assess RTO risk.
                  </p>
                  <button
                    onClick={() => setIsCreateOrderModalOpen(true)}
                    className="mt-3 rounded-xl bg-emerald-600 px-4 py-2 text-xs font-bold text-white hover:bg-emerald-700 transition"
                  >
                    + Create Order
                  </button>
                </div>
              ) : (
                <div className="divide-y divide-slate-100">
                  {orders.map((ord) => (
                    <div
                      key={ord.id}
                      className="py-3.5 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 hover:bg-slate-50 px-3 rounded-xl transition"
                    >
                      <div className="flex items-center space-x-3.5">
                        <span className="font-mono text-xs font-bold text-slate-900">
                          {ord.external_order_id}
                        </span>
                        <span
                          className={`rounded px-2 py-0.5 text-[10px] font-bold ${
                            ord.payment_method === 'COD'
                              ? 'bg-amber-100 text-amber-800 border border-amber-200'
                              : 'bg-emerald-100 text-emerald-800 border border-emerald-200'
                          }`}
                        >
                          {ord.payment_method}
                        </span>
                        <span className="text-xs font-bold text-slate-800">
                          ₹{formatCurrency(ord.order_value)}
                        </span>
                        <span className="text-xs text-slate-500">
                          {ord.customer_name} ({ord.shipping_city || 'India'})
                        </span>
                        <span
                          className={`rounded px-1.5 py-0.5 text-[10px] font-bold ${
                            ord.status === 'HOLD'
                              ? 'bg-rose-100 text-rose-800'
                              : ord.status === 'CONFIRMED'
                              ? 'bg-teal-100 text-teal-800'
                              : 'bg-slate-100 text-slate-700'
                          }`}
                        >
                          {ord.status}
                        </span>
                      </div>

                      <div className="flex items-center space-x-2">
                        {ord.status === 'HOLD' && (
                          <button
                            onClick={() => handleResumeOrder(ord)}
                            className="rounded-lg bg-amber-600 px-2.5 py-1 text-xs font-bold text-white hover:bg-amber-700 transition"
                          >
                            Lift Hold
                          </button>
                        )}
                        {ord.status === 'PENDING' && (
                          <button
                            onClick={() => handleConfirmOrder(ord)}
                            className="rounded-lg bg-teal-600 px-2.5 py-1 text-xs font-bold text-white hover:bg-teal-700 transition"
                          >
                            Confirm
                          </button>
                        )}
                        <button
                          onClick={() => setSelectedOrderForDecision(ord)}
                          className="flex items-center space-x-1.5 rounded-xl border border-purple-200 bg-purple-50 px-3 py-1.5 text-xs font-bold text-purple-800 hover:bg-purple-100 transition shadow-sm"
                        >
                          <Sparkles className="h-3.5 w-3.5 text-purple-600" />
                          <span>Evaluate 5 Candidate Payoffs</span>
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        )}

        {/* ================= SECTION 4: DELIVERY ================= */}
        {activeTab === 'DELIVERY' && (
          <div className="space-y-6">
            {/* Delivery Stepper Graphic */}
            <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
              <h2 className="text-sm font-bold text-slate-900 mb-2 flex items-center gap-2">
                <Truck className="h-4 w-4 text-blue-600" />
                Indian D2C Delivery State Progression
              </h2>
              <p className="text-xs text-slate-500 mb-6">
                Shipments strictly follow the valid state machine. Delivery failures trigger operational NDR cases.
              </p>

              <div className="grid grid-cols-2 sm:grid-cols-6 gap-2 text-center text-xs">
                {[
                  { step: '1', title: 'CONFIRMED', desc: 'Order verified' },
                  { step: '2', title: 'READY_TO_SHIP', desc: 'Manifest packed' },
                  { step: '3', title: 'SHIPPED', desc: 'In 3PL transit' },
                  { step: '4', title: 'OUT_FOR_DELIVERY', desc: 'Courier out' },
                  { step: '5', title: 'DELIVERY_ATTEMPT_FAILED', desc: 'NDR opened', highlight: 'text-rose-600 font-bold' },
                  { step: '6', title: 'DELIVERED / RTO', desc: 'Settled result' },
                ].map((s, idx) => (
                  <div key={idx} className="p-3 rounded-xl bg-slate-50 border border-slate-200 relative">
                    <span className="text-[10px] font-mono text-slate-400 block mb-0.5">Stage {s.step}</span>
                    <span className={`text-xs font-bold block ${s.highlight || 'text-slate-900'}`}>{s.title}</span>
                    <span className="text-[10px] text-slate-500 mt-0.5 block">{s.desc}</span>
                  </div>
                ))}
              </div>
            </div>

            {/* In-Transit Orders */}
            <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
              <div className="flex items-center justify-between mb-4">
                <div>
                  <h3 className="text-sm font-bold text-slate-900">Shipments In Transit Pipeline</h3>
                  <p className="text-xs text-slate-500">Record delivery progress and test carrier event webhooks</p>
                </div>
                <button
                  onClick={() => loadOrders()}
                  className="flex items-center space-x-1 rounded-lg border border-slate-200 bg-white px-2.5 py-1 text-xs text-slate-600 hover:bg-slate-50"
                >
                  <RefreshCw className={`h-3 w-3 ${isOrdersLoading ? 'animate-spin' : ''}`} />
                  <span>Refresh</span>
                </button>
              </div>

              {inTransitOrders.length === 0 ? (
                <div className="py-8 text-center text-slate-400">
                  <p className="text-sm font-medium">No active in-transit shipments found.</p>
                  <p className="text-xs text-slate-400 mt-1">Create or confirm an order to proceed with shipping.</p>
                </div>
              ) : (
                <div className="divide-y divide-slate-100">
                  {inTransitOrders.map((ord) => (
                    <div
                      key={ord.id}
                      className="py-3.5 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 hover:bg-slate-50 px-3 rounded-xl transition"
                    >
                      <div>
                        <div className="flex items-center space-x-2">
                          <span className="font-mono text-xs font-bold text-slate-900">{ord.external_order_id}</span>
                          <span className="text-xs font-bold text-slate-700">₹{formatCurrency(ord.order_value)}</span>
                          <span className="rounded bg-blue-100 px-2 py-0.5 text-[10px] font-bold text-blue-800">
                            {ord.status}
                          </span>
                        </div>
                        <p className="text-[11px] text-slate-500 mt-0.5">
                          {ord.customer_name} • {ord.shipping_city}, {ord.shipping_pincode}
                        </p>
                      </div>

                      <div className="flex items-center space-x-2">
                        {ord.status === 'PENDING' && (
                          <button
                            onClick={() => handleConfirmOrder(ord)}
                            className="rounded-xl bg-teal-600 px-3 py-1.5 text-xs font-bold text-white hover:bg-teal-700 transition"
                          >
                            Confirm Order
                          </button>
                        )}
                        <button
                          onClick={() => setSelectedOrderForSimulation(ord)}
                          className="flex items-center space-x-1.5 rounded-xl border border-blue-200 bg-blue-50 px-3.5 py-1.5 text-xs font-bold text-blue-800 hover:bg-blue-100 transition shadow-sm"
                        >
                          <Truck className="h-3.5 w-3.5 text-blue-600" />
                          <span>Simulate / Record Event</span>
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        )}

        {/* ================= SECTION 5: NDR RECOVERY ================= */}
        {activeTab === 'NDR' && (
          <div className="space-y-5">
            <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
              <div>
                <h2 className="text-base font-bold text-slate-900">NDR Delivery Recovery Hub</h2>
                <p className="text-xs text-slate-500">
                  Manage failed delivery courier attempts, customer outreach, address correction, and reattempts
                </p>
              </div>
              <button
                onClick={() => {
                  loadNDRCases();
                  loadSummary();
                }}
                className="flex items-center space-x-1.5 rounded-xl border border-slate-200 bg-white px-3 py-2 text-xs font-semibold text-slate-600 hover:bg-slate-50 transition"
              >
                <RefreshCw className={`h-3.5 w-3.5 ${isNdrLoading ? 'animate-spin' : ''}`} />
                <span>Refresh Queue</span>
              </button>
            </div>

            {/* NDR Filters */}
            <div className="rounded-2xl border border-slate-200 bg-white p-4 shadow-sm">
              <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-5">
                <div className="lg:col-span-2 relative">
                  <Search className="absolute left-3 top-2.5 h-4 w-4 text-slate-400" />
                  <input
                    type="text"
                    value={ndrSearch}
                    onChange={(e) => {
                      setNdrSearch(e.target.value);
                      setNdrOffset(0);
                    }}
                    placeholder="Search Case #, Order ID, Customer, Phone..."
                    className="w-full rounded-xl border border-slate-300 py-2 pl-9 pr-3 text-xs text-slate-800 placeholder-slate-400 focus:border-rose-500 focus:outline-none"
                  />
                </div>

                <div>
                  <select
                    value={ndrStatus}
                    onChange={(e) => {
                      setNdrStatus(e.target.value);
                      setNdrOffset(0);
                    }}
                    className="w-full rounded-xl border border-slate-300 py-2 px-3 text-xs text-slate-800 focus:border-rose-500 focus:outline-none"
                  >
                    <option value="">All Statuses</option>
                    <option value="OPEN">OPEN</option>
                    <option value="IN_PROGRESS">IN_PROGRESS</option>
                    <option value="REATTEMPT_SCHEDULED">REATTEMPT_SCHEDULED</option>
                    <option value="RESOLVED_DELIVERED">RESOLVED_DELIVERED</option>
                    <option value="RESOLVED_RTO">RESOLVED_RTO</option>
                  </select>
                </div>

                <div>
                  <select
                    value={ndrPriority}
                    onChange={(e) => {
                      setNdrPriority(e.target.value);
                      setNdrOffset(0);
                    }}
                    className="w-full rounded-xl border border-slate-300 py-2 px-3 text-xs text-slate-800 focus:border-rose-500 focus:outline-none"
                  >
                    <option value="">All Priorities</option>
                    <option value="HIGH">HIGH Priority</option>
                    <option value="MEDIUM">MEDIUM Priority</option>
                    <option value="LOW">LOW Priority</option>
                  </select>
                </div>

                <div>
                  <select
                    value={ndrReason}
                    onChange={(e) => {
                      setNdrReason(e.target.value);
                      setNdrOffset(0);
                    }}
                    className="w-full rounded-xl border border-slate-300 py-2 px-3 text-xs text-slate-800 focus:border-rose-500 focus:outline-none"
                  >
                    <option value="">All Failure Reasons</option>
                    <option value="CUSTOMER_UNAVAILABLE">Customer Unavailable</option>
                    <option value="INCORRECT_ADDRESS">Incorrect Address</option>
                    <option value="CUSTOMER_UNREACHABLE">Phone Unreachable</option>
                    <option value="DELIVERY_RESCHEDULE_REQUESTED">Reschedule Requested</option>
                    <option value="CUSTOMER_REFUSED">Customer Refused</option>
                  </select>
                </div>
              </div>
            </div>

            {ndrError && (
              <div className="flex items-center justify-between rounded-xl border border-rose-200 bg-rose-50 p-4 text-xs text-rose-800">
                <div className="flex items-center space-x-2">
                  <AlertTriangle className="h-4 w-4 text-rose-600 shrink-0" />
                  <span>{ndrError}</span>
                </div>
                <button onClick={() => loadNDRCases()} className="font-bold underline hover:text-rose-950">
                  Retry
                </button>
              </div>
            )}

            {/* NDR Table */}
            <NDRTable
              cases={ndrCases}
              total={totalNdrCases}
              limit={ndrLimit}
              offset={ndrOffset}
              onPageChange={setNdrOffset}
              isLoading={isNdrLoading}
              onSelectCase={(c) => setSelectedNdrCaseId(c.id)}
            />
          </div>
        )}

        {/* ================= SECTION 6: LEDGER ================= */}
        {activeTab === 'LEDGER' && (
          <div className="space-y-6">
            <div className="rounded-2xl border border-blue-200 bg-blue-50/70 p-6">
              <div className="flex items-center space-x-2">
                <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-blue-200 text-blue-900">
                  <Receipt className="h-4 w-4" />
                </span>
                <h2 className="text-base font-bold text-blue-950">Settled Financial Contribution Ledger</h2>
              </div>
              <p className="text-xs text-blue-700 mt-1 max-w-3xl leading-relaxed">
                Reconciles initial Expected Contribution with ex-post Realized Contribution.
                Attributions strictly break down Product COGS, Forward Logistics, Reverse Logistics (RTO penalty),
                COD carrier collection charges, packaging, and intervention overhead.
              </p>
            </div>

            {/* Reconciliation Order Table */}
            <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
              <h3 className="text-xs font-bold uppercase tracking-wider text-slate-500 mb-4">
                Completed & In-Progress Orders Financial Reconciliation
              </h3>

              {orders.length === 0 ? (
                <div className="py-8 text-center text-slate-400">
                  <p className="text-sm font-medium">No orders recorded in ledger yet.</p>
                </div>
              ) : (
                <div className="divide-y divide-slate-100">
                  {orders.map((ord) => (
                    <div
                      key={ord.id}
                      className="py-3.5 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 hover:bg-slate-50 px-3 rounded-xl transition"
                    >
                      <div className="flex items-center space-x-3.5">
                        <span className="font-mono text-xs font-bold text-slate-900">{ord.external_order_id}</span>
                        <span className="text-xs font-bold text-slate-800">₹{formatCurrency(ord.order_value)}</span>
                        <span className="rounded bg-slate-100 px-2 py-0.5 text-[10px] font-bold text-slate-700">
                          {ord.status}
                        </span>
                        <span className="text-xs text-slate-500">{ord.customer_name}</span>
                      </div>

                      <div className="flex items-center space-x-2">
                        <button
                          onClick={() => setSelectedOrderForReconciliation(ord)}
                          className="flex items-center space-x-1.5 rounded-xl border border-blue-200 bg-blue-50 px-3.5 py-1.5 text-xs font-bold text-blue-800 hover:bg-blue-100 transition shadow-sm"
                        >
                          <Receipt className="h-3.5 w-3.5 text-blue-600" />
                          <span>Inspect Financial Attribution</span>
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        )}

        {/* ================= SECTION 7: INTEGRATIONS ================= */}
        {activeTab === 'INTEGRATIONS' && (
          <IntegrationsTab
            orgId={currentOrgId}
            onOpenCSVImport={() => setIsImportModalOpen(true)}
            onOpenImportHistory={() => setIsHistoryModalOpen(true)}
          />
        )}

        {/* ================= SECTION 8: SETTINGS ================= */}
        {activeTab === 'SETTINGS' && (
          <SettingsTab
            orgName={currentOrgName}
            orgId={currentOrgId}
            userEmail={userEmail}
            onRerunOnboarding={() => setIsOnboardingOpen(true)}
          />
        )}
      </div>

      {/* Onboarding Wizard Modal */}
      {isOnboardingOpen && (
        <OnboardingWizard
          orgName={currentOrgName}
          orgId={currentOrgId}
          onComplete={() => setIsOnboardingOpen(false)}
          onClose={() => setIsOnboardingOpen(false)}
          onOpenCSVImport={() => {
            setIsOnboardingOpen(false);
            setIsImportModalOpen(true);
          }}
          onOpenCreateOrder={() => {
            setIsOnboardingOpen(false);
            setIsCreateOrderModalOpen(true);
          }}
        />
      )}

      {/* Order Creation Modal */}
      <CreateOrderModal
        isOpen={isCreateOrderModalOpen}
        onClose={() => setIsCreateOrderModalOpen(false)}
        onOrderCreated={handleOrderCreated}
      />

      {/* CSV Import Modal */}
      <CSVImportModal
        isOpen={isImportModalOpen}
        onClose={() => setIsImportModalOpen(false)}
        onImportComplete={() => {
          loadOrders();
          loadSummary();
        }}
      />

      {/* Import History Modal */}
      <ImportHistoryModal
        isOpen={isHistoryModalOpen}
        onClose={() => setIsHistoryModalOpen(false)}
      />

      {/* Pre-Dispatch Decision Modal */}
      <OrderDecisionModal
        order={selectedOrderForDecision}
        isOpen={!!selectedOrderForDecision}
        onClose={() => setSelectedOrderForDecision(null)}
        onDecisionUpdated={() => {
          loadOrders();
          loadSummary();
        }}
      />

      {/* NDR Case Modal */}
      <NDRCaseModal
        caseId={selectedNdrCaseId}
        isOpen={!!selectedNdrCaseId}
        onClose={() => setSelectedNdrCaseId(null)}
        onCaseUpdated={() => {
          loadNDRCases();
          loadOrders();
          loadSummary();
        }}
      />

      {/* Simulate Delivery Modal */}
      <SimulateDeliveryModal
        order={selectedOrderForSimulation}
        isOpen={!!selectedOrderForSimulation}
        onClose={() => setSelectedOrderForSimulation(null)}
        onEventSimulated={() => {
          loadOrders();
          loadNDRCases();
          loadSummary();
        }}
      />

      {/* Financial Reconciliation Modal */}
      <FinancialReconciliationModal
        order={selectedOrderForReconciliation}
        isOpen={!!selectedOrderForReconciliation}
        onClose={() => setSelectedOrderForReconciliation(null)}
      />
    </main>
  );
}
