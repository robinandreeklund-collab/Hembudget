/**
 * API-klient för /v2/foretag/*-endpoints (Företagsläget · Bug #7-utbyggnad).
 *
 * Token läses via centrala getToken() från @/api/client — tidigare
 * läste vi sessionStorage direkt här, vilket gick sönder när auth
 * migrerades till localStorage (alla bizApi-anrop fick "Missing
 * bearer token" → läraren såg fel state, eleven kunde inte lasta
 * data).
 */
import { getToken } from "@/api/client";

const TOKEN = () => getToken() || "";

async function call<T>(path: string, opts: RequestInit = {}): Promise<T> {
  const r = await fetch(path, {
    ...opts,
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${TOKEN()}`,
      ...(opts.headers || {}),
    },
  });
  if (!r.ok) {
    throw new Error(`HTTP ${r.status}: ${await r.text()}`);
  }
  if (r.status === 204) return undefined as T;
  const ct = r.headers.get("content-type") || "";
  if (!ct.includes("application/json")) return undefined as T;
  return r.json();
}


export type CompanyForm = "enskild_firma" | "ab" | "handelsbolag";

export type Company = {
  id: number;
  name: string;
  org_number: string | null;
  form: CompanyForm;
  started_on: string;
  share_capital: number | null;
  vat_registered: boolean;
  vat_period: string;
  sni_code: string | null;
  industry_label: string | null;
  industry_key: string | null;
  city_key: string | null;
  city_display: string | null;
  active: boolean;
};

export type Industry = {
  key: string;
  label: string;
  short_description: string;
  sni_code: string;
  hourly_rate_min: number;
  hourly_rate_max: number;
  margin_baseline_pct: number;
  requires_lokal: boolean;
  monthly_lokal_cost_baseline: number;
  equipment_cost_init: number;
  pipeline_per_week_baseline: number;
  learning_focus: string;
  available_in_my_city: boolean;
};

export type CompanyTransaction = {
  id: number;
  occurred_on: string;
  kind: "income" | "expense" | "salary" | "vat_payment" | "tax_payment";
  category: string;
  description: string;
  amount_excl_vat: number;
  vat_rate: number;
  vat_amount: number;
  total_incl_vat: number;
  notes: string | null;
};

export type CompanyCustomer = {
  id: number;
  name: string;
  org_number: string | null;
  email: string | null;
  address: string | null;
  is_private: boolean;
};

export type CompanyInvoice = {
  id: number;
  invoice_number: string;
  customer_name: string;
  issued_on: string;
  due_on: string;
  description: string;
  amount_excl_vat: number;
  vat_amount: number;
  total_incl_vat: number;
  status: "draft" | "sent" | "paid" | "overdue" | "cancelled";
  paid_on: string | null;
  rot_rut_kind: "rot" | "rut" | null;
  rot_rut_amount: number | null;
};

export type CompanyOwnerSalary = {
  id: number;
  paid_on: string;
  gross_salary: number;
  employer_fee_amount: number;
  prel_tax_amount: number;
  net_to_owner: number;
  total_cost_to_company: number;
};

export type VatPeriod = {
  id: number;
  period_label: string;
  start_date: string;
  end_date: string;
  due_date: string;
  output_vat: number;
  input_vat: number;
  net_vat: number;
  status: "open" | "filed" | "paid";
  filed_on: string | null;
};

export type CorporateTax = {
  year: number;
  income_total: number;
  expense_total: number;
  profit_before_tax: number;
  corporate_tax_rate: number;
  estimated_tax: number;
  profit_after_tax: number;
  n_transactions: number;
};


export type BizPentagon = {
  axes: {
    omsattning: number;
    kundbas: number;
    likviditet: number;
    tidsatgang: number;
    vinst: number;
  };
  axes_prev?: {
    omsattning: number;
    kundbas: number;
    likviditet: number;
    tidsatgang: number;
    vinst: number;
  } | null;
  total_score: number;
  metrics: {
    income_4w: number;
    expense_4w: number;
    profit_4w: number;
    margin_4w_pct: number;
    kassa: number;
    n_invoices_active: number;
  };
};

export type ModeStatus = {
  enabled: boolean;
  has_active_company: boolean;
};

// === BizBank-overview · matchar prototyp p-biz-bank ===
export type BizBankAccount = {
  eye: string;
  name: string;
  number: string;
  balance: number;
  balance_meta: string;
  is_primary: boolean;
};

export type BizBankTx = {
  occurred_on: string;
  name: string;
  name_sub: string | null;
  category: string;
  amount_signed: number;
  is_income: boolean;
  is_owner_salary: boolean;
};

// === Pentagon axis-detail (för flip-kortet) ===
export type BizAxis = "omsattning" | "kundbas" | "likviditet" | "tidsatgang" | "vinst";

export type BizAxisFactor = {
  explanation: string;
  points: number;
  delta_label: string;
};

export type BizAxisEvent = {
  occurred_at: string | null;
  date_label: string;
  title: string;
  detail: string | null;
  delta: number | null;
  delta_label: string;
};

export type BizAxisDetail = {
  axis: BizAxis;
  axis_label: string;
  axis_number: string;
  score: number;
  factors: BizAxisFactor[];
  events: BizAxisEvent[];
  summary_text: string;
};

export type BizBankOverview = {
  accounts: BizBankAccount[];
  transactions: BizBankTx[];
  f_skatt_due: string | null;
  f_skatt_amount: number;
  own_salary_this_month: number;
  next_vat_due: string | null;
  next_vat_amount: number;
};


export const bizApi = {
  getCompany: () => call<Company | null>("/v2/foretag"),
  createCompany: (b: {
    name: string;
    form: CompanyForm;
    industry_key: string;
    vat_registered?: boolean;
    vat_period?: string;
    share_capital?: number | null;
    org_number?: string | null;
    funding_method?: "cash" | "private_loan" | "business_loan_pg";
  }) =>
    call<Company>("/v2/foretag", { method: "POST", body: JSON.stringify(b) }),

  // Lista de 10 fasta branscherna (med 'available_in_my_city'-flagga)
  listIndustries: () => call<Industry[]>("/v2/foretag/industries"),

  // Sammanfattning för privat-hub · visar bara om eleven har företag
  privateSummary: () =>
    call<{
      has_company: boolean;
      company_name: string | null;
      industry_label: string | null;
      city_display: string | null;
      week_no: number;
      income_4w: number;
      profit_4w: number;
      margin_pct: number;
      kassa: number;
      n_invoices_open: number;
      n_invoices_overdue: number;
      pentagon_score: number;
      summary_text: string;
      n_new_opportunities: number;
      n_quotes_pending: number;
      n_quotes_won_recent: number;
      n_quotes_lost_recent: number;
    }>("/v2/foretag/private-summary"),
  patchCompany: (id: number, b: Partial<Company> & { name: string; form: string }) =>
    call<Company>(`/v2/foretag/${id}`, { method: "PATCH", body: JSON.stringify(b) }),
  closeCompany: (id: number) =>
    call<void>(`/v2/foretag/${id}`, { method: "DELETE" }),

  // Transactions
  listTransactions: (limit = 100) =>
    call<CompanyTransaction[]>(`/v2/foretag/transactions?limit=${limit}`),
  addTransaction: (b: {
    occurred_on: string; kind: string; category: string;
    description: string; amount_excl_vat: number; vat_rate?: number;
    notes?: string;
  }) =>
    call<CompanyTransaction>("/v2/foretag/transactions", {
      method: "POST",
      body: JSON.stringify(b),
    }),
  deleteTransaction: (id: number) =>
    call<void>(`/v2/foretag/transactions/${id}`, { method: "DELETE" }),

  // Customers
  listCustomers: () => call<CompanyCustomer[]>("/v2/foretag/customers"),
  addCustomer: (b: { name: string; org_number?: string; email?: string; address?: string; is_private?: boolean }) =>
    call<CompanyCustomer>("/v2/foretag/customers", {
      method: "POST",
      body: JSON.stringify(b),
    }),

  // Invoices
  listInvoices: () => call<CompanyInvoice[]>("/v2/foretag/invoices"),
  addInvoice: (b: {
    customer_id: number; issued_on: string; due_on: string;
    description: string; amount_excl_vat: number; vat_rate?: number;
    rot_rut_kind?: string; rot_rut_amount?: number;
  }) =>
    call<CompanyInvoice>("/v2/foretag/invoices", {
      method: "POST",
      body: JSON.stringify(b),
    }),
  markInvoicePaid: (id: number) =>
    call<CompanyInvoice>(`/v2/foretag/invoices/${id}/mark-paid`, {
      method: "POST",
    }),

  // Owner salary
  listOwnerSalaries: () => call<CompanyOwnerSalary[]>("/v2/foretag/owner-salaries"),
  payOwnerSalary: (b: { paid_on: string; gross_salary: number; is_young?: boolean; notes?: string }) =>
    call<CompanyOwnerSalary>("/v2/foretag/owner-salary", {
      method: "POST",
      body: JSON.stringify(b),
    }),
  previewOwnerSalary: (gross: number, isYoung = false) =>
    call<{
      gross_salary: number;
      employer_fee_rate: number;
      employer_fee_amount: number;
      prel_tax_rate: number;
      prel_tax_amount: number;
      net_to_owner: number;
      total_cost_to_company: number;
    }>(`/v2/foretag/owner-salary/preview?gross_salary=${gross}&is_young=${isYoung}`),

  // BizBank overview (prototyp p-biz-bank)
  bankOverview: () => call<BizBankOverview>("/v2/foretag/bank-overview"),

  // Pentagon axis-detail (flip-kortets baksida)
  pentagonAxisDetail: (axis: BizAxis) =>
    call<BizAxisDetail>(`/v2/foretag/pentagon/axis/${axis}`),

  // VAT
  listVatPeriods: () => call<VatPeriod[]>("/v2/foretag/vat/periods"),
  previewVat: (start: string, end: string) =>
    call<{
      output_vat: number;
      input_vat: number;
      net_vat: number;
      n_transactions: number;
    }>(`/v2/foretag/vat/preview?start=${start}&end=${end}`),
  fileVat: (b: { period_label: string; start_date: string; end_date: string; due_date: string }) =>
    call<VatPeriod>("/v2/foretag/vat/file", {
      method: "POST",
      body: JSON.stringify(b),
    }),

  // Corporate tax
  corporateTax: (year: number) =>
    call<CorporateTax>(`/v2/foretag/corporate-tax/${year}`),

  // Bug #7-utbyggnad · företagets pentagon + status
  pentagon: () => call<BizPentagon>("/v2/foretag/pentagon"),
  modeStatus: () => call<ModeStatus>("/v2/foretag/mode-status"),

  // Eget uttag (enskild firma)
  withdraw: (b: { paid_on: string; amount: number; notes?: string }) =>
    call<{ id: number; paid_on: string; amount: number }>(
      "/v2/foretag/owner-withdrawal",
      { method: "POST", body: JSON.stringify(b) },
    ),

  // Spelmotor · manuell stega-vecka (proxy till bizEngineApi.tick)
  tick: () =>
    call<{
      week_no: number;
      new_opportunities: number;
      quotes_decided: number;
      quotes_accepted: number;
      quotes_rejected: number;
      invoices_paid_now: number;
      events_triggered: number;
      reputation_after: number;
      notes: string[];
    }>("/v2/foretag/tick", { method: "POST" }),
};


// === Lärar-endpoints ===

export type TeacherForetagOverview = {
  student_id: number;
  student_name: string;
  business_mode_enabled: boolean;
  company: Company | null;
  pentagon: BizPentagon | null;
  n_transactions_total: number;
  n_invoices_total: number;
  n_invoices_unpaid: number;
  n_owner_salaries: number;
  last_owner_salary_date: string | null;
  next_vat_due: string | null;
  summary_md: string;
};

export type TeacherClassRow = {
  student_id: number;
  student_name: string;
  has_company: boolean;
  company_name: string | null;
  company_form: string | null;
  reputation: number | null;
  week_no: number | null;
  revenue_4w: number | null;
  profit_4w: number | null;
  n_invoices_unpaid: number | null;
  n_open_opportunities: number | null;
  biz_mode_enabled: boolean;
};

export type TeacherClassOverview = {
  teacher_id: number;
  n_students: number;
  n_with_active_company: number;
  avg_reputation: number | null;
  avg_revenue_4w: number | null;
  rows: TeacherClassRow[];
};

export const teacherBizApi = {
  overview: (studentId: number) =>
    call<TeacherForetagOverview>(
      `/v2/teacher/foretag/overview/${studentId}`,
    ),
  toggle: (studentId: number, enabled: boolean) =>
    call<{ enabled: boolean; has_active_company: boolean }>(
      `/v2/teacher/foretag/toggle/${studentId}`,
      { method: "POST", body: JSON.stringify({ enabled }) },
    ),
  classOverview: () =>
    call<TeacherClassOverview>("/v2/teacher/foretag/class-overview"),
  sendSupplierInvoice: (b: {
    target_student_ids: number[];
    sender_name: string;
    description: string;
    amount_excl_vat: number;
    vat_rate?: number;
    due_in_days?: number;
    notes?: string;
  }) =>
    call<{
      n_created: number;
      n_skipped_no_company: number;
      n_skipped_not_my_student: number;
    }>("/v2/teacher/foretag/supplier-invoices", {
      method: "POST",
      body: JSON.stringify(b),
    }),
  reviewInvoice: (
    studentId: number, invoiceId: number,
    body: { decision: "approved" | "rejected"; comment?: string },
  ) =>
    call<{
      invoice_id: number;
      new_status: string;
      teacher_comment: string | null;
    }>(
      `/v2/teacher/foretag/invoices/${studentId}/${invoiceId}/review`,
      { method: "PATCH", body: JSON.stringify(body) },
    ),
};


// === Spelmotor-typer + API ===

export type Opportunity = {
  id: number;
  title: string;
  description: string;
  customer_name: string;
  customer_segment: string;
  industry_tag: string | null;
  requires_car?: boolean;
  market_price: number;
  expected_delivery_days: number;
  deadline_on: string;
  received_on: string;
  status: string;
  week_no: number;
  has_quote: boolean;
  quote_offered_price: number | null;
  quote_offered_delivery_days: number | null;
  quote_pitch_text: string | null;
  quote_pitch_quality: number | null;
  quote_accept_probability: number | null;
  quote_accepted: boolean | null;
  quote_decision_explanation: string | null;
};

export type Quote = {
  id: number;
  opportunity_id: number;
  offered_price: number;
  offered_delivery_days: number;
  pitch_text: string | null;
  pitch_quality: number | null;
  accept_probability: number | null;
  accepted: boolean | null;
  decision_explanation: string | null;
  submitted_on: string;
  decided_on: string | null;
};

export type Job = {
  id: number;
  title: string;
  customer_name: string;
  agreed_price: number;
  started_on: string;
  expected_complete_on: string;
  delivered_on: string | null;
  status: string;
  quality_score: number | null;
  invoice_id: number | null;
  estimated_hours: number;
  hours_per_week: number;
  days_remaining: number;
  days_total: number;
  progress_pct: number;
  is_overdue: boolean;
  is_klass_pool: boolean;
};

export type MarketingCampaign = {
  id: number;
  kind: string;
  title: string;
  copy_text: string | null;
  cost: number;
  duration_weeks: number;
  ai_quality_factor: number | null;
  ai_feedback: string | null;
  started_on: string;
  ends_on: string;
  active: boolean;
};

export type Decision = {
  id: number;
  kind: string;
  title: string;
  monthly_cost: number;
  one_time_cost: number;
  capacity_delta: number;
  reputation_delta: number;
  insurance_kind: string | null;
  started_on: string;
  ends_on: string | null;
  active: boolean;
};

export type SupplierInvoice = {
  id: number;
  sender_name: string;
  invoice_number: string;
  issued_on: string;
  due_on: string;
  description: string;
  amount_excl_vat: number;
  vat_rate: number;
  source: string;
  status: string;
  paid_on: string | null;
  notes: string | null;
};

export type TickResult = {
  week_no: number;
  new_opportunities: number;
  quotes_decided: number;
  quotes_accepted: number;
  quotes_rejected: number;
  invoices_paid_now: number;
  events_triggered: number;
  reputation_after: number;
  notes: string[];
};

export type TickStatus = {
  last_auto_tick_at: string | null;
  next_tick_at: string;
  interval_hours: number;
  seconds_until_next_tick: number;
  week_no: number;
  open_quotes_count: number;
};

export const bizEngineApi = {
  tickStatus: () => call<TickStatus>("/v2/foretag/tick-status"),
  listOpportunities: (status?: string) =>
    call<Opportunity[]>(
      `/v2/foretag/opportunities${status ? `?status_filter=${status}` : ""}`,
    ),
  submitQuote: (oppId: number, b: {
    offered_price: number;
    offered_delivery_days: number;
    pitch_text?: string;
  }) =>
    call<Quote>(`/v2/foretag/opportunities/${oppId}/quote`, {
      method: "POST",
      body: JSON.stringify(b),
    }),
  getQuote: (oppId: number) =>
    call<Quote | null>(`/v2/foretag/opportunities/${oppId}/quote`),

  listJobs: (status?: string) =>
    call<Job[]>(
      `/v2/foretag/jobs${status ? `?status_filter=${status}` : ""}`,
    ),
  deliverJob: (jobId: number, b: {
    quality_score: number;
    create_invoice?: boolean;
  }) =>
    call<{
      job: Job;
      invoice_id: number | null;
      invoice_number: string | null;
    }>(`/v2/foretag/jobs/${jobId}/deliver`, {
      method: "POST",
      body: JSON.stringify(b),
    }),

  listMarketing: (onlyActive = false) =>
    call<MarketingCampaign[]>(
      `/v2/foretag/marketing${onlyActive ? "?only_active=true" : ""}`,
    ),
  createMarketing: (b: {
    kind: string;
    title: string;
    copy_text?: string;
    cost: number;
    duration_weeks?: number;
  }) =>
    call<MarketingCampaign>("/v2/foretag/marketing", {
      method: "POST",
      body: JSON.stringify(b),
    }),

  listDecisions: (onlyActive = false) =>
    call<Decision[]>(
      `/v2/foretag/decisions${onlyActive ? "?only_active=true" : ""}`,
    ),
  createDecision: (b: {
    kind: string;
    title: string;
    monthly_cost?: number;
    one_time_cost?: number;
    capacity_delta?: number;
    reputation_delta?: number;
    insurance_kind?: string;
    notes?: string;
  }) =>
    call<Decision>("/v2/foretag/decisions", {
      method: "POST",
      body: JSON.stringify(b),
    }),
  endDecision: (id: number) =>
    call<void>(`/v2/foretag/decisions/${id}`, { method: "DELETE" }),

  listSupplierInvoices: (status?: string) =>
    call<SupplierInvoice[]>(
      `/v2/foretag/supplier-invoices${status ? `?status_filter=${status}` : ""}`,
    ),
  paySupplierInvoice: (id: number) =>
    call<SupplierInvoice>(`/v2/foretag/supplier-invoices/${id}/pay`, {
      method: "POST",
    }),

  tick: () =>
    call<TickResult>("/v2/foretag/tick", { method: "POST" }),
};

