import {
  CSVCommitResponse,
  CSVPreviewResponse,
  ImportJob,
  ImportJobListResponse,
  Order,
  OrderItem,
  OrderListResponse,
  OrderEvaluation,
  FinancialReconciliation,
  DemoJourneyResponse,
  AuthUser,
  TokenResponse,
  OrganizationMembership,
  DeliveryEvent,
  NDRCase,
  NDRListResponse,
  NDRRecommendation,
  DashboardSummary,
  MerchantEconomics,
  CreateOrderInput,
  MLStatusResponse,
  ShopifyStoreConfig,
  ShopifyWebhookDelivery,
  ShopifyWebhookDeliveryList,
  WhatsAppConfig,
  WhatsAppMessage,
  WhatsAppMessageList,
  WhatsAppOptOut,
  WhatsAppTestResult,
} from '@/types';

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api/v1';
const HEALTH_URL = API_BASE_URL.replace(/\/api\/v1\/?$/, '/healthz');

/**
 * Validates whether a JWT token is well-formed and unexpired.
 */
export function isTokenValid(token: string | null): boolean {
  if (!token) return false;
  try {
    const parts = token.split('.');
    if (parts.length !== 3) return false;
    const base64 = parts[1].replace(/-/g, '+').replace(/_/g, '/');
    const jsonPayload = decodeURIComponent(
      atob(base64)
        .split('')
        .map((c) => '%' + ('00' + c.charCodeAt(0).toString(16)).slice(-2))
        .join('')
    );
    const parsed = JSON.parse(jsonPayload);
    const now = Math.floor(Date.now() / 1000);
    return typeof parsed.exp === 'number' && parsed.exp > now + 15;
  } catch {
    return false;
  }
}

export function hasValidSession(): boolean {
  if (typeof window === 'undefined') return false;
  const token = localStorage.getItem('profitguard_token');
  const orgId = localStorage.getItem('profitguard_org_id');
  return !!(token && orgId && isTokenValid(token));
}

export function getStoredOrgId(): string | null {
  if (typeof window === 'undefined') return null;
  return localStorage.getItem('profitguard_org_id');
}

export function getStoredUserEmail(): string | null {
  if (typeof window === 'undefined') return null;
  return localStorage.getItem('profitguard_user_email');
}

export function getStoredOrgName(): string | null {
  if (typeof window === 'undefined') return null;
  return localStorage.getItem('profitguard_org_name');
}

/**
 * Checks connectivity to the backend health endpoint.
 */
export async function checkBackendHealth(): Promise<{ status: string; database: string; error?: string }> {
  try {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 4000);
    const res = await fetch(HEALTH_URL, {
      signal: controller.signal,
      cache: 'no-store',
    });
    clearTimeout(timeoutId);
    if (!res.ok) {
      return { status: 'unhealthy', database: 'error', error: `HTTP ${res.status}` };
    }
    return await res.json();
  } catch (err: any) {
    return {
      status: 'unreachable',
      database: 'disconnected',
      error: err.name === 'AbortError' ? 'Timeout connecting to backend' : err.message || 'Connection refused',
    };
  }
}

export async function loginUser(email: string, password: string): Promise<TokenResponse> {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), 8000);
  try {
    const res = await fetch(`${API_BASE_URL}/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
      body: JSON.stringify({ email, password }),
      signal: controller.signal,
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: 'Incorrect email or password' }));
      throw new Error(err.detail || 'Login failed');
    }
    const tokenData: TokenResponse = await res.json();
    if (typeof window !== 'undefined') {
      localStorage.setItem('profitguard_token', tokenData.access_token);
      localStorage.setItem('profitguard_user_email', email);
    }

    // Fetch user organizations and store active org ID and name
    try {
      const orgs = await fetchUserOrganizations(tokenData.access_token);
      if (orgs.length > 0) {
        localStorage.setItem('profitguard_org_id', orgs[0].org_id);
        if (orgs[0].organization?.name) {
          localStorage.setItem('profitguard_org_name', orgs[0].organization.name);
        }
      }
    } catch (orgErr) {
      console.warn('Failed to resolve organization during login:', orgErr);
    }

    return tokenData;
  } finally {
    clearTimeout(timeoutId);
  }
}

export async function registerUser(
  email: string,
  password: string,
  fullName: string,
  organizationName: string
): Promise<TokenResponse> {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), 8000);
  try {
    const res = await fetch(`${API_BASE_URL}/auth/register`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
      body: JSON.stringify({
        email,
        password,
        full_name: fullName,
        organization_name: organizationName,
      }),
      signal: controller.signal,
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: 'Registration failed' }));
      throw new Error(err.detail || 'Registration failed');
    }
    const tokenData: TokenResponse = await res.json();
    if (typeof window !== 'undefined') {
      localStorage.setItem('profitguard_token', tokenData.access_token);
      localStorage.setItem('profitguard_user_email', email);
      localStorage.setItem('profitguard_org_name', organizationName);
    }

    // Fetch organizations to acquire created org_id
    try {
      const orgs = await fetchUserOrganizations(tokenData.access_token);
      if (orgs.length > 0) {
        localStorage.setItem('profitguard_org_id', orgs[0].org_id);
      }
    } catch (orgErr) {
      console.warn('Failed to resolve organization after registration:', orgErr);
    }

    return tokenData;
  } finally {
    clearTimeout(timeoutId);
  }
}

export async function fetchUserOrganizations(token?: string): Promise<OrganizationMembership[]> {
  const authToken = token || (typeof window !== 'undefined' ? localStorage.getItem('profitguard_token') : null);
  const headers: HeadersInit = {
    Accept: 'application/json',
  };
  if (authToken) {
    headers['Authorization'] = `Bearer ${authToken}`;
  }

  const res = await fetch(`${API_BASE_URL}/orgs`, { headers });
  if (!res.ok) {
    throw new Error('Failed to fetch user organizations');
  }
  return res.json();
}

export async function fetchCurrentUser(): Promise<AuthUser> {
  return apiFetch<AuthUser>('/auth/me');
}

/**
 * Validates active session. Throws error if not authenticated so callers know to request login.
 */
export async function ensureAuthenticatedSession(): Promise<{ token: string; orgId: string }> {
  if (typeof window === 'undefined') {
    return { token: '', orgId: '' };
  }

  const token = localStorage.getItem('profitguard_token');
  const orgId = localStorage.getItem('profitguard_org_id');

  if (token && orgId && isTokenValid(token)) {
    return { token, orgId };
  }

  // Not authenticated
  throw new Error('AUTHENTICATION_REQUIRED');
}

export async function logoutSession(): Promise<void> {
  if (typeof window !== 'undefined') {
    const token = localStorage.getItem('profitguard_token');
    if (token) {
      try {
        await fetch(`${API_BASE_URL}/auth/logout`, {
          method: 'POST',
          headers: { Authorization: `Bearer ${token}` },
        });
      } catch {
        // Silently tolerate network logout errors
      }
    }
    localStorage.removeItem('profitguard_token');
    localStorage.removeItem('profitguard_org_id');
    localStorage.removeItem('profitguard_user_email');
    localStorage.removeItem('profitguard_org_name');
  }
}

/**
 * Centralized HTTP client wrapper with automatic token management,
 * 12s timeout, and unified error handling.
 */
async function apiFetch<T>(path: string, options: RequestInit = {}): Promise<T> {
  const session = await ensureAuthenticatedSession();
  const headers: Record<string, string> = {
    Accept: 'application/json',
    ...(options.headers as Record<string, string>),
  };

  if (session.token) {
    headers['Authorization'] = `Bearer ${session.token}`;
  }
  if (session.orgId) {
    headers['X-Org-Id'] = session.orgId;
  }

  // Set Content-Type only if not sending FormData
  if (!(options.body instanceof FormData) && !headers['Content-Type']) {
    headers['Content-Type'] = 'application/json';
  }

  const controller = new AbortController();
  const timeoutMs = 12000;
  const timeoutId = setTimeout(() => controller.abort(), timeoutMs);

  let res: Response;
  try {
    res = await fetch(`${API_BASE_URL}${path}`, {
      ...options,
      headers,
      signal: options.signal || controller.signal,
    });
  } catch (netErr: any) {
    clearTimeout(timeoutId);
    if (netErr.name === 'AbortError') {
      throw new Error(`Request timed out after ${timeoutMs / 1000}s while accessing ${path}`);
    }
    throw new Error(
      `Cannot connect to ProfitGuard backend at ${API_BASE_URL}. Ensure uvicorn is running on port 8000.`
    );
  } finally {
    clearTimeout(timeoutId);
  }

  if (res.status === 401) {
    if (typeof window !== 'undefined') {
      localStorage.removeItem('profitguard_token');
    }
    throw new Error('AUTHENTICATION_REQUIRED');
  }

  if (res.status === 503) {
    throw new Error('ProfitGuard backend or database is temporarily unavailable (503). Check database connectivity.');
  }

  if (!res.ok) {
    const errorBody = await res.json().catch(() => ({ detail: `HTTP ${res.status}: ${res.statusText}` }));
    throw new Error(errorBody.detail || errorBody.message || `Request failed with HTTP ${res.status}`);
  }

  return (await res.json()) as T;
}

// -----------------------------------------------------------------------------
// Dashboard & Summary Metrics
// -----------------------------------------------------------------------------

export async function fetchDashboardSummary(): Promise<DashboardSummary> {
  return apiFetch<DashboardSummary>('/orders/summary');
}

export async function fetchMerchantEconomics(): Promise<MerchantEconomics> {
  return apiFetch<MerchantEconomics>('/economics');
}

// -----------------------------------------------------------------------------
// Orders API Methods
// -----------------------------------------------------------------------------

export async function fetchOrders(params: {
  status?: string;
  payment_method?: string;
  search?: string;
  date_from?: string;
  date_to?: string;
  limit?: number;
  offset?: number;
}): Promise<OrderListResponse> {
  const query = new URLSearchParams();
  if (params.status) query.set('status', params.status);
  if (params.payment_method) query.set('payment_method', params.payment_method);
  if (params.search) query.set('search', params.search);
  if (params.date_from) query.set('date_from', params.date_from);
  if (params.date_to) query.set('date_to', params.date_to);
  if (params.limit) query.set('limit', params.limit.toString());
  if (params.offset) query.set('offset', params.offset.toString());

  return apiFetch<OrderListResponse>(`/orders?${query.toString()}`);
}

export async function fetchOrderDetails(orderId: string): Promise<Order> {
  return apiFetch<Order>(`/orders/${orderId}`);
}

export async function confirmOrder(orderId: string): Promise<Order> {
  return apiFetch<Order>(`/orders/${orderId}/confirm`, {
    method: 'POST',
  });
}

export async function resumeOrder(orderId: string): Promise<Order> {
  return apiFetch<Order>(`/orders/${orderId}/resume`, {
    method: 'POST',
  });
}

export async function fetchOrderItems(orderId: string): Promise<OrderItem[]> {
  return apiFetch<OrderItem[]>(`/orders/${orderId}/items`);
}

export async function createManualOrder(orderData: CreateOrderInput): Promise<Order> {
  return apiFetch<Order>('/orders', {
    method: 'POST',
    body: JSON.stringify(orderData),
  });
}

/**
 * Creates a realistic sample order with authentic Indian customer details,
 * clearly labeled as [SAMPLE], using normal tenant APIs.
 */
export async function createSampleOrder(): Promise<Order> {
  const randomSuffix = Math.floor(1000 + Math.random() * 9000);
  const sampleOrder: CreateOrderInput = {
    external_order_id: `SAMPLE-ORD-${randomSuffix}`,
    order_value: '1899.00',
    payment_method: 'COD',
    customer_name: 'Aditya Verma [SAMPLE]',
    customer_phone: '9876543210',
    customer_email: `sample.customer.${randomSuffix}@example.com`,
    shipping_address1: '42, Brigade Millennium, JP Nagar 7th Phase',
    shipping_city: 'Bengaluru',
    shipping_state: 'Karnataka',
    shipping_pincode: '560078',
    items: [
      {
        product_name: 'Artisan Cotton Kurta [SAMPLE]',
        sku: 'KURTA-COTTON-NVY',
        quantity: 1,
        unit_price: '1899.00',
        unit_cost: '570.00',
      },
    ],
  };
  return createManualOrder(sampleOrder);
}

export async function downloadCSVTemplate(): Promise<Blob> {
  const session = await ensureAuthenticatedSession();
  const res = await fetch(`${API_BASE_URL}/csv-import/template`, {
    headers: {
      Authorization: `Bearer ${session.token}`,
      'X-Org-Id': session.orgId,
    },
  });
  if (!res.ok) {
    throw new Error('Failed to download CSV template');
  }
  return res.blob();
}

export async function uploadCSVPreview(file: File): Promise<CSVPreviewResponse> {
  const formData = new FormData();
  formData.append('file', file);
  return apiFetch<CSVPreviewResponse>('/csv-import/preview', {
    method: 'POST',
    body: formData,
  });
}

export async function commitCSVImport(previewId: string): Promise<CSVCommitResponse> {
  return apiFetch<CSVCommitResponse>('/csv-import/commit', {
    method: 'POST',
    body: JSON.stringify({ preview_id: previewId }),
  });
}

export async function fetchImportHistory(limit = 20, offset = 0): Promise<ImportJobListResponse> {
  return apiFetch<ImportJobListResponse>(`/csv-import/history?limit=${limit}&offset=${offset}`);
}

export async function fetchImportJobDetails(importId: string): Promise<ImportJob> {
  return apiFetch<ImportJob>(`/csv-import/history/${importId}`);
}

// -----------------------------------------------------------------------------
// Decision Engine API Methods
// -----------------------------------------------------------------------------

export async function evaluateOrder(orderId: string): Promise<OrderEvaluation> {
  return apiFetch<OrderEvaluation>(`/orders/${orderId}/evaluate`, {
    method: 'POST',
  });
}

export async function fetchOrderDecision(orderId: string): Promise<OrderEvaluation> {
  return apiFetch<OrderEvaluation>(`/orders/${orderId}/decision`);
}

export async function recordOrderDecision(
  orderId: string,
  action: string,
  overrideReason?: string
): Promise<OrderEvaluation> {
  return apiFetch<OrderEvaluation>(`/orders/${orderId}/decision`, {
    method: 'POST',
    body: JSON.stringify({
      action,
      override_reason: overrideReason || null,
    }),
  });
}

export async function recordInterventionOutcome(
  orderId: string,
  outcome: string,
  notes?: string
): Promise<OrderEvaluation> {
  return apiFetch<OrderEvaluation>(`/orders/${orderId}/intervention-outcome`, {
    method: 'POST',
    body: JSON.stringify({
      outcome,
      notes: notes || null,
    }),
  });
}

// -----------------------------------------------------------------------------
// Delivery Lifecycle & NDR Hub API Methods
// -----------------------------------------------------------------------------

export async function fetchOrderDeliveryEvents(orderId: string): Promise<DeliveryEvent[]> {
  return apiFetch<DeliveryEvent[]>(`/delivery/events/${orderId}`);
}

export async function simulateDeliveryEvent(payload: {
  order_id: string;
  event_id?: string;
  event_type: string;
  reason_code?: string;
  carrier_name?: string;
  location?: string;
  notes?: string;
}): Promise<DeliveryEvent> {
  return apiFetch<DeliveryEvent>('/delivery/simulate', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export async function fetchNDRCases(params?: {
  status?: string;
  reason?: string;
  priority?: string;
  search?: string;
  limit?: number;
  offset?: number;
}): Promise<NDRListResponse> {
  const query = new URLSearchParams();
  if (params?.status) query.append('status', params.status);
  if (params?.reason) query.append('reason', params.reason);
  if (params?.priority) query.append('priority', params.priority);
  if (params?.search) query.append('search', params.search);
  if (params?.limit) query.append('limit', params.limit.toString());
  if (params?.offset) query.append('offset', params.offset.toString());

  return apiFetch<NDRListResponse>(`/delivery/ndr?${query.toString()}`);
}

export async function fetchNDRCase(caseId: string): Promise<NDRCase> {
  return apiFetch<NDRCase>(`/delivery/ndr/${caseId}`);
}

export async function recordNDRAction(
  caseId: string,
  action: {
    action_type: string;
    contact_method?: string;
    customer_response?: string;
    updated_address1?: string;
    updated_city?: string;
    updated_pincode?: string;
    updated_phone?: string;
    reattempt_date?: string;
    closure_reason?: string;
    notes?: string;
  }
): Promise<NDRCase> {
  return apiFetch<NDRCase>(`/delivery/ndr/${caseId}/actions`, {
    method: 'POST',
    body: JSON.stringify(action),
  });
}

export async function fetchNDRRecommendation(caseId: string): Promise<NDRRecommendation> {
  return apiFetch<NDRRecommendation>(`/delivery/ndr/${caseId}/recommendation`);
}

export async function fetchOrderReconciliation(orderId: string): Promise<FinancialReconciliation> {
  return apiFetch<FinancialReconciliation>(`/orders/${orderId}/reconciliation`);
}

export async function reconcileOrder(orderId: string, notes?: string): Promise<FinancialReconciliation> {
  return apiFetch<FinancialReconciliation>(`/orders/${orderId}/reconcile`, {
    method: 'POST',
    body: JSON.stringify({ notes }),
  });
}

export async function runDemoJourney(): Promise<DemoJourneyResponse> {
  return apiFetch<DemoJourneyResponse>('/demo/run-journey', {
    method: 'POST',
  });
}

export async function seedDemoData(): Promise<{ status: string; message: string; seeded_orders: string[] }> {
  return apiFetch<{ status: string; message: string; seeded_orders: string[] }>('/demo/seed', {
    method: 'POST',
  });
}

export async function resetDemoData(): Promise<{ status: string; message: string; deleted_count: number }> {
  return apiFetch<{ status: string; message: string; deleted_count: number }>('/demo/reset', {
    method: 'POST',
  });
}

export async function fetchEconomics(): Promise<MerchantEconomics> {
  return apiFetch<MerchantEconomics>('/economics');
}

export async function updateEconomics(payload: Partial<MerchantEconomics>): Promise<MerchantEconomics> {
  return apiFetch<MerchantEconomics>('/economics', {
    method: 'PUT',
    body: JSON.stringify(payload),
  });
}

export async function fetchMLStatus(): Promise<MLStatusResponse> {
  return apiFetch<MLStatusResponse>('/monitoring/ml-status');
}

export async function fetchShopifyStoreConfig(): Promise<ShopifyStoreConfig | null> {
  return apiFetch<ShopifyStoreConfig | null>('/integrations/shopify');
}

export async function configureShopifyStore(data: {
  shop_domain: string;
  access_token?: string;
  webhook_secret?: string;
  scopes?: string;
}): Promise<ShopifyStoreConfig> {
  return apiFetch<ShopifyStoreConfig>('/integrations/shopify/configure', {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

export async function disconnectShopifyStore(): Promise<{ status: string; message: string }> {
  return apiFetch<{ status: string; message: string }>('/integrations/shopify/disconnect', {
    method: 'POST',
  });
}

export async function fetchShopifyWebhooks(page: number = 1, pageSize: number = 20): Promise<ShopifyWebhookDeliveryList> {
  return apiFetch<ShopifyWebhookDeliveryList>(`/integrations/shopify/webhooks?page=${page}&page_size=${pageSize}`);
}

// ============================================================================
// Meta WhatsApp Business Cloud API Functions
// ============================================================================

export async function fetchWhatsAppConfig(): Promise<WhatsAppConfig | null> {
  return apiFetch<WhatsAppConfig | null>('/integrations/whatsapp');
}

export async function configureWhatsApp(data: {
  phone_number_id: string;
  business_account_id?: string;
  access_token?: string;
  app_secret?: string;
  webhook_verify_token?: string;
  operating_mode: 'MOCK' | 'META_TEST' | 'LIVE';
  api_version?: string;
}): Promise<WhatsAppConfig> {
  return apiFetch<WhatsAppConfig>('/integrations/whatsapp/configure', {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

export async function disconnectWhatsApp(): Promise<{ status: string; message: string }> {
  return apiFetch<{ status: string; message: string }>('/integrations/whatsapp/disconnect', {
    method: 'POST',
  });
}

export async function testWhatsAppConnection(): Promise<WhatsAppTestResult> {
  return apiFetch<WhatsAppTestResult>('/integrations/whatsapp/test-connection', {
    method: 'POST',
  });
}

export async function sendWhatsAppTestMessage(recipientPhone: string, messageText?: string): Promise<WhatsAppMessage> {
  return apiFetch<WhatsAppMessage>('/integrations/whatsapp/send-test', {
    method: 'POST',
    body: JSON.stringify({ recipient_phone: recipientPhone, message_text: messageText }),
  });
}

export async function sendWhatsAppOrderOtp(orderId: string, recipientPhone?: string): Promise<WhatsAppMessage> {
  return apiFetch<WhatsAppMessage>('/integrations/whatsapp/send-otp', {
    method: 'POST',
    body: JSON.stringify({ order_id: orderId, recipient_phone: recipientPhone }),
  });
}

export async function sendWhatsAppNdrRecovery(
  ndrCaseId: string,
  recipientPhone?: string,
  notes?: string
): Promise<WhatsAppMessage> {
  return apiFetch<WhatsAppMessage>('/integrations/whatsapp/send-ndr-recovery', {
    method: 'POST',
    body: JSON.stringify({ ndr_case_id: ndrCaseId, recipient_phone: recipientPhone, notes }),
  });
}

export async function fetchWhatsAppMessages(params?: {
  page?: number;
  pageSize?: number;
  orderId?: string;
  ndrCaseId?: string;
  status?: string;
}): Promise<WhatsAppMessageList> {
  const query = new URLSearchParams();
  if (params?.page) query.append('page', params.page.toString());
  if (params?.pageSize) query.append('page_size', params.pageSize.toString());
  if (params?.orderId) query.append('order_id', params.orderId);
  if (params?.ndrCaseId) query.append('ndr_case_id', params.ndrCaseId);
  if (params?.status) query.append('status', params.status);

  const qs = query.toString() ? `?${query.toString()}` : '';
  return apiFetch<WhatsAppMessageList>(`/integrations/whatsapp/messages${qs}`);
}

export async function fetchWhatsAppOptOuts(): Promise<WhatsAppOptOut[]> {
  return apiFetch<WhatsAppOptOut[]>('/integrations/whatsapp/opt-outs');
}


