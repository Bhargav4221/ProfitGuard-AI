export interface OrderItem {
  id: string;
  order_id: string;
  sku?: string;
  external_product_id?: string;
  product_name: string;
  quantity: number;
  unit_price: string;
  unit_cost?: string;
  total_price: string;
  created_at: string;
}

export interface Order {
  id: string;
  org_id: string;
  external_order_id: string;
  order_date: string;
  currency: string;
  order_value: string;
  payment_method: 'COD' | 'PREPAID';
  status:
    | 'PENDING'
    | 'CONFIRMED'
    | 'READY_TO_SHIP'
    | 'SHIPPED'
    | 'OUT_FOR_DELIVERY'
    | 'NDR'
    | 'DELIVERED'
    | 'RTO'
    | 'CANCELLED'
    | 'HOLD';
  fulfillment_status: 'UNFULFILLED' | 'FULFILLED' | 'PARTIAL' | 'HOLD';
  customer_name?: string;
  customer_phone?: string;
  customer_email?: string;
  shipping_address1?: string;
  shipping_address2?: string;
  shipping_city?: string;
  shipping_state?: string;
  shipping_pincode?: string;
  shipping_country: string;
  courier_name?: string;
  tracking_number?: string;
  source_channel: string;
  import_job_id?: string;
  created_at: string;
  updated_at: string;
  items?: OrderItem[];
}

export interface OrderListResponse {
  orders: Order[];
  total: number;
  limit: number;
  offset: number;
}

export interface CSVRowError {
  row_index: number;
  external_order_id?: string;
  column_name?: string;
  error_message: string;
}

export interface CSVPreviewResponse {
  preview_id: string;
  filename: string;
  total_rows: number;
  valid_rows: number;
  invalid_rows: number;
  duplicate_rows: number;
  sample_valid_rows: Record<string, any>[];
  errors: CSVRowError[];
}

export interface CSVCommitResponse {
  import_id: string;
  filename: string;
  status: string;
  inserted_count: number;
  skipped_count: number;
  total_rows: number;
}

export interface ImportJobError {
  id: string;
  row_index: number;
  external_order_id?: string;
  column_name?: string;
  error_message: string;
  created_at: string;
}

export interface ImportJob {
  id: string;
  org_id: string;
  filename: string;
  status: 'PREVIEW' | 'COMMITTED' | 'CANCELLED';
  total_rows: number;
  valid_rows: number;
  invalid_rows: number;
  duplicate_rows: number;
  created_at: string;
  committed_at?: string;
  errors?: ImportJobError[];
}

export interface ImportJobListResponse {
  jobs: ImportJob[];
  total: number;
  limit: number;
  offset: number;
}


export interface ActionEvaluation {
  action: 'SHIP_AS_IS' | 'VERIFY_OTP' | 'INCENTIVIZE_PREPAID' | 'MANUAL_REVIEW' | 'HOLD_CANCEL';
  expected_contribution: string;
  lift_vs_ship_as_is: string;
  intervention_cost: string;
  probabilities: Record<string, string>;
  terminal_payoffs: Record<string, string>;
  is_recommended: boolean;
  is_policy_eligible: boolean;
  disqualification_reason?: string;
}

export interface TriggeredRule {
  rule_name: string;
  factor: string;
  risk_delta: string;
  description: string;
}

export interface PolicyGuard {
  guard_name: string;
  passed: boolean;
  detail: string;
}

export interface DecisionExplanation {
  primary_reason: string;
  triggered_rules: TriggeredRule[];
  policy_guards: PolicyGuard[];
  uncertainty_disclosure: Record<string, any>;
  financial_assumptions: Record<string, string>;
  operational_probability_assumptions?: Record<string, string>;
}

export interface OrderEvaluation {
  id: string;
  org_id: string;
  order_id: string;
  evaluated_at: string;
  recommended_action: 'SHIP_AS_IS' | 'VERIFY_OTP' | 'INCENTIVIZE_PREPAID' | 'MANUAL_REVIEW' | 'HOLD_CANCEL';
  recommended_lift: string;
  ship_as_is_ec: string;
  best_ec: string;
  profit_at_risk: string;
  baseline_p_rto: string;
  uncertainty_score: string;
  risk_tier: 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL';
  comparison_data: ActionEvaluation[];
  explanation_data: DecisionExplanation;
  decision_status: 'EVALUATED' | 'ACCEPTED' | 'OVERRIDDEN' | 'EXECUTED' | 'CANCELLED';
  selected_action?: string;
  override_reason?: string;
  decided_at?: string;
  intervention_status: 'NONE' | 'PENDING' | 'OTP_VERIFIED' | 'OTP_FAILED' | 'PREPAID_CONVERTED' | 'PREPAID_DECLINED' | 'MANUAL_APPROVED' | 'MANUAL_REJECTED';
  intervention_notes?: string;
  intervention_resolved_at?: string;
  recommended_action_deterministic?: 'SHIP_AS_IS' | 'VERIFY_OTP' | 'INCENTIVIZE_PREPAID' | 'MANUAL_REVIEW' | 'HOLD_CANCEL';
  recommended_action_ml_assisted?: 'SHIP_AS_IS' | 'VERIFY_OTP' | 'INCENTIVIZE_PREPAID' | 'MANUAL_REVIEW' | 'HOLD_CANCEL';
  ml_operating_mode?: 'SHADOW' | 'LIVE_ASSISTED' | 'DISABLED';
  decision_policy_version?: string;
}

export interface DeliveryEvent {
  id: string;
  org_id: string;
  order_id: string;
  event_id: string;
  event_type: string;
  previous_status?: string;
  new_status: string;
  event_source: string;
  is_simulated: boolean;
  carrier_name?: string;
  tracking_number?: string;
  carrier_status_code?: string;
  reason_code?: string;
  reason_description?: string;
  location?: string;
  occurred_at: string;
  created_at: string;
}

export interface NDRActionLog {
  id: string;
  ndr_case_id: string;
  order_id: string;
  actor_user_id?: string;
  action_type: string;
  action_details: Record<string, any>;
  intervention_cost: string;
  notes?: string;
  created_at: string;
}

export interface NDRCase {
  id: string;
  org_id: string;
  order_id: string;
  case_number: string;
  status: 'OPEN' | 'IN_PROGRESS' | 'REATTEMPT_SCHEDULED' | 'RESOLVED_DELIVERED' | 'RESOLVED_RTO' | 'RESOLVED_CANCELLED' | 'CLOSED';
  priority: 'HIGH' | 'MEDIUM' | 'LOW';
  attempt_count: number;
  last_attempt_date: string;
  reason_code: string;
  carrier_reason_raw?: string;
  assigned_operator_id?: string;
  assigned_operator_name?: string;
  customer_contacted: boolean;
  contact_method?: string;
  customer_response?: string;
  updated_address1?: string;
  updated_address2?: string;
  updated_city?: string;
  updated_state?: string;
  updated_pincode?: string;
  updated_phone?: string;
  reattempt_date?: string;
  next_action?: string;
  next_action_due?: string;
  is_simulated: boolean;
  expected_recovery_lift?: string;
  estimated_recovery_ec?: string;
  recommended_recovery_action?: string;
  recommendation_rationale?: string;
  closed_at?: string;
  closure_reason?: string;
  created_at: string;
  updated_at: string;
  order_external_id?: string;
  order_value?: string;
  customer_name?: string;
  customer_phone?: string;
  shipping_city?: string;
  shipping_pincode?: string;
  payment_method?: string;
  actions: NDRActionLog[];
}

export interface NDRListResponse {
  cases: NDRCase[];
  total: number;
  limit: number;
  offset: number;
}

export interface NDRRecommendation {
  ndr_case_id: string;
  order_id: string;
  recommended_action: string;
  expected_recovery_lift: string;
  estimated_recovery_ec: string;
  baseline_rto_loss: string;
  profit_at_risk: string;
  estimated_rescue_prob: string;
  intervention_cost: string;
  rationale: string;
  data_sufficiency: string;
  accounting_notes: string;
}

export interface FinancialReconciliation {
  id: string;
  org_id: string;
  order_id: string;
  external_order_id: string;
  reconciliation_status: 'SETTLED' | 'PENDING' | 'DISPUTED';
  reconciled_at: string;
  order_value: string;
  collected_revenue: string;
  cogs: string;
  forward_shipping_cost: string;
  reverse_shipping_cost: string;
  payment_fee: string;
  packaging_cost: string;
  inventory_damage_cost: string;
  pre_dispatch_intervention_cost: string;
  ndr_recovery_intervention_cost: string;
  total_expenses: string;
  realized_contribution: string;
  expected_contribution_initial?: string;
  contribution_variance?: string;
  is_simulated: boolean;
  notes?: string;
  accounting_convention: string;
}

export interface DemoJourneyStep {
  step: number;
  title: string;
  details: string;
  [key: string]: any;
}

export interface DemoJourneyResponse {
  status: string;
  message: string;
  steps_completed: number;
  transcript: DemoJourneyStep[];
  final_reconciliation: {
    status: string;
    order_value: string;
    collected_revenue: string;
    realized_contribution: string;
    reconciled_at: string;
  };
}

export interface AuthUser {
  id: string;
  email: string;
  full_name?: string;
  is_active: boolean;
  created_at: string;
}

export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
}

export interface OrganizationMembership {
  id: string;
  org_id: string;
  user_id: string;
  role: 'OWNER' | 'ADMIN' | 'OPERATOR' | 'AUDITOR';
  created_at: string;
  organization?: {
    id: string;
    name: string;
    slug: string;
  };
}

export interface DashboardSummary {
  total_orders: number;
  total_gmv: string;
  expected_contribution: string;
  realized_contribution: string;
  high_risk_count: number;
  active_ndr_count: number;
  status_breakdown: Record<string, number>;
  payment_method_breakdown: Record<string, number>;
}

export interface MerchantEconomics {
  id: string;
  org_id: string;
  default_cogs_percent: string;
  forward_shipping_cost: string;
  reverse_shipping_cost: string;
  packaging_cost: string;
  cod_carrier_fee: string;
  cod_fee_incurred_on: string;
  payment_gateway_percent: string;
  payment_gateway_flat: string;
  inventory_damage_rate: string;
  otp_verification_cost: string;
  manual_review_cost: string;
  prepaid_incentive_discount: string;
  prepaid_comms_cost: string;
  tax_accounting_mode: string;
  allow_auto_cancel: boolean;
  enable_holdout_experiment: boolean;
  holdout_percentage: string;
  safety_value_cap: string;
}

export interface CreateOrderInput {
  external_order_id: string;
  order_value: string;
  payment_method: 'COD' | 'PREPAID';
  customer_name?: string;
  customer_phone?: string;
  customer_email?: string;
  shipping_address1?: string;
  shipping_address2?: string;
  shipping_city?: string;
  shipping_state?: string;
  shipping_pincode?: string;
  items?: {
    product_name: string;
    sku?: string;
    quantity: number;
    unit_price: string;
    unit_cost?: string;
  }[];
}

export interface MLStatusResponse {
  operating_mode: 'SHADOW' | 'LIVE_ASSISTED' | 'DISABLED';
  is_approved_for_consequential_actions: boolean;
  decision_policy_version: string;
  model_loaded: boolean;
  model_metadata: {
    model_version?: string;
    model_type?: string;
    operating_threshold?: number;
    training_data_source?: string;
    training_date?: string;
    feature_count?: number;
    expected_feature_order?: string[];
    [key: string]: any;
  };
  governance_notice: string;
}

export interface ShopifyStoreConfig {
  id: string;
  org_id: string;
  shop_domain: string;
  status: 'ACTIVE' | 'DISCONNECTED' | 'REVOKED';
  has_access_token: boolean;
  has_webhook_secret: boolean;
  scopes?: string;
  api_version?: string;
  installed_at: string;
  uninstalled_at?: string;
  created_at: string;
  updated_at: string;
}

export interface ShopifyWebhookDelivery {
  id: string;
  org_id?: string;
  shopify_delivery_id: string;
  topic: string;
  shop_domain: string;
  shopify_order_id?: string;
  order_id?: string;
  status: string;
  error_message?: string;
  payload_summary?: Record<string, any>;
  processed_at?: string;
  created_at: string;
}

export interface ShopifyWebhookDeliveryList {
  items: ShopifyWebhookDelivery[];
  total: number;
  page: number;
  page_size: number;
}

export interface WhatsAppConfig {
  id: string;
  org_id: string;
  phone_number_id?: string;
  business_account_id?: string;
  has_access_token: boolean;
  has_app_secret: boolean;
  webhook_verify_token?: string;
  operating_mode: 'MOCK' | 'META_TEST' | 'LIVE';
  status: 'NOT_CONFIGURED' | 'ACTIVE' | 'DISCONNECTED' | 'ERROR';
  verified_name?: string;
  quality_rating?: string;
  api_version: string;
  webhook_url?: string;
  last_webhook_received_at?: string;
  last_error?: string;
  created_at: string;
  updated_at: string;
}

export interface WhatsAppMessage {
  id: string;
  org_id: string;
  order_id?: string;
  ndr_case_id?: string;
  wamid?: string;
  direction: 'OUTBOUND' | 'INBOUND';
  recipient_phone: string;
  sender_phone?: string;
  message_type: string;
  template_name?: string;
  body_preview?: string;
  status: 'QUEUED' | 'SENT' | 'DELIVERED' | 'READ' | 'FAILED';
  error_code?: string;
  error_message?: string;
  intervention_cost: string;
  sent_at?: string;
  delivered_at?: string;
  read_at?: string;
  created_at: string;
}

export interface WhatsAppMessageList {
  items: WhatsAppMessage[];
  total: number;
  page: number;
  page_size: number;
}

export interface WhatsAppTestResult {
  connected: boolean;
  operating_mode: string;
  phone_number_id?: string;
  display_phone_number?: string;
  verified_name?: string;
  quality_rating?: string;
  message: string;
}

export interface WhatsAppOptOut {
  id: string;
  phone_number: string;
  opted_out_at: string;
  reason: string;
}



