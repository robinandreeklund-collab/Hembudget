/**
 * V2 API-klient · parallell migration.
 *
 * Wrappar /v2/*-endpoints. Använder samma token från `@/api/client`
 * så ingen separat auth behövs.
 */
import { api } from "@/api/client";

export type SpendProfile = "sparsam" | "balanserad" | "slosa";
export type FairnessChoice = "50_50" | "proportionellt" | "pool";
export type PartnerModel = "solo" | "ai" | "klasskompis";

export type V2Status = {
  role: "student" | "teacher" | "demo";
  v2_eligible: boolean;
  v2_onboarding_completed: boolean;
  v2_level: number;
  v2_spend_profile: SpendProfile;
  v2_fairness_choice: FairnessChoice | null;
  v2_partner_model: PartnerModel;
  is_super_admin: boolean;
};

export type OnboardingComplete = {
  student_id: number;
  completed_at: string;
  v2_level: number;
  redirect_to: string;
};

export type HubCharacter = {
  /** Karaktärens fulla namn (förnamn + efternamn) eller fallback till
   * student.display_name om karaktärsnamnet saknas i DB:n. */
  display_name: string;
  first_name: string | null;
  last_name: string | null;
  profession: string | null;
  employer: string | null;
  age: number | null;
  city: string | null;
  family_status: string | null;
  housing_type: string | null;
  housing_monthly: number | null;
  gross_salary_monthly: number | null;
  net_salary_monthly: number | null;
  personality: string | null;
};

export type HubPentagon = {
  total_score: number;
  ekonomi: number;
  karriar: number;
  halsa: number;
  relation: number;
  fritid: number;
  year_month: string;
};

export type HubMonthSummary = {
  income: number;
  expenses: number;
  saved: number;
  save_rate_pct: number;
  transactions_count: number;
};

export type HubData = {
  student_id: number;
  character: HubCharacter;
  v2_level: number;
  v2_spend_profile: SpendProfile;
  v2_fairness_choice: FairnessChoice | null;
  v2_partner_model: PartnerModel;
  pentagon: HubPentagon | null;
  month_summary: HubMonthSummary;
  total_balance: number;
  accounts_count: number;
};

export type BankAccount = {
  id: number;
  name: string;
  bank: string;
  type: string;
  account_number: string | null;
  current_balance: number;
  fund_value: number;
  total_value: number;
  incognito: boolean;
};

export type BankTransaction = {
  id: number;
  account_id: number;
  account_name: string;
  date: string;
  amount: number;
  description: string;
  merchant: string | null;
  category_id: number | null;
  is_transfer: boolean;
};

export type BankUpcoming = {
  id: number;
  name: string;
  kind: "bill" | "income";
  amount: number;
  expected_date: string;
  debit_account_id: number | null;
  bankgiro: string | null;
  plusgiro: string | null;
  autogiro: boolean;
  is_paid: boolean;
};

export type BankSummary = {
  total_balance: number;
  accounts_count: number;
  upcoming_open_total: number;
  upcoming_open_count: number;
  income_this_month: number;
  expenses_this_month: number;
  transactions_count: number;
};

export type BankData = {
  student_id: number;
  year_month: string;
  summary: BankSummary;
  accounts: BankAccount[];
  recent_transactions: BankTransaction[];
  upcoming_bills: BankUpcoming[];
};

export type V2BudgetCategoryRow = {
  category_id: number;
  category_name: string;
  group_name: string | null;
  icon: string;
  planned: number;
  actual: number;
  consumer_reference: number | null;
  progress_pct: number;
  status: "under" | "near" | "over" | "fixed" | "savings" | "income";
  is_fixed: boolean;
  is_income: boolean;
};

export type V2BudgetSummary = {
  income_total: number;
  expenses_total: number;
  planned_expenses_total: number;
  saved: number;
  save_rate_pct: number;
  days_into_month: number;
  days_in_month: number;
  progress_pct: number;
  over_budget_total: number;
  categories_count: number;
};

export type BudgetData = {
  student_id: number;
  month: string;
  summary: V2BudgetSummary;
  categories: V2BudgetCategoryRow[];
};

export type V2GoalRow = {
  id: number;
  name: string;
  icon: string;
  target_amount: number;
  current_amount: number;
  target_date: string | null;
  progress_pct: number;
  months_remaining: number | null;
  monthly_pace_target: number | null;
  expected_progress_pct: number | null;
  account_name: string | null;
  status: "new" | "ahead" | "on_track" | "behind" | "complete";
  color: string;
};

export type V2GoalsSummary = {
  total_saved: number;
  total_target: number;
  overall_progress_pct: number;
  monthly_pace_total: number;
  goals_count: number;
  on_track_count: number;
  behind_count: number;
};

export type GoalsData = {
  student_id: number;
  summary: V2GoalsSummary;
  goals: V2GoalRow[];
};

// === Postlådan ===
export type V2MailType = "invoice" | "salary_slip" | "authority" | "reminder" | "info";
export type V2MailStatus = "unhandled" | "viewed" | "exported" | "paid" | "expired";
export type V2MailSenderKind =
  | "bank"
  | "cred"
  | "skv"
  | "ins"
  | "land"
  | "util"
  | "work"
  | "pen"
  | "other";

export type V2MailItem = {
  id: number;
  sender: string;
  sender_short: string | null;
  sender_kind: V2MailSenderKind;
  sender_meta: string | null;
  mail_type: V2MailType;
  subject: string;
  body_meta: string | null;
  amount: number | null;
  due_date: string | null;
  received_at: string;
  status: V2MailStatus;
  upcoming_id: number | null;
  transaction_id: number | null;
  is_recurring: boolean;
  ocr_reference: string | null;
  bankgiro: string | null;
};

export type V2MailSummary = {
  total_count: number;
  unhandled_count: number;
  invoice_count: number;
  salary_slip_count: number;
  authority_count: number;
  info_count: number;
  other_count: number;
  to_pay_amount: number;
  incoming_amount: number;
  overdue_count: number;
  spend_profile: string;
  last_received_at: string | null;
  next_due_date: string | null;
};

export type MailData = {
  student_id: number;
  summary: V2MailSummary;
  items: V2MailItem[];
};

export type V2MailSeedItem = {
  sender: string;
  sender_short?: string;
  sender_kind?: V2MailSenderKind;
  sender_meta?: string;
  mail_type: V2MailType;
  subject: string;
  body_meta?: string;
  body?: string;
  amount?: number;
  due_date?: string;
  is_recurring?: boolean;
  ocr_reference?: string;
  bankgiro?: string;
};

// === Fas 2C · Arbetsgivaren · master-modeller ===

export type V2CollectiveAgreementOut = {
  id: number;
  code: string;
  name: string;
  union: string;
  employer_org: string;
};

export type V2AgreementBenefitOut = {
  id: number;
  agreement_id: number;
  kind: string;
  name: string;
  detail: string | null;
  value: string;
  sort_order: number;
};

export type V2MarketSalaryRangeOut = {
  id: number;
  profession: string;
  city: string;
  year: number;
  experience_band: string;
  low: number;
  high: number;
  median: number | null;
  source: string | null;
};

export type V2TeacherEmployerOverview = {
  student_id: number;
  student_name: string;
  profession: string;
  employer: string;
  agreement_name: string | null;
  agreement_id: number | null;
  pension_pct: number | null;
  gross_salary_monthly: number;
  market_low: number | null;
  market_high: number | null;
  benefits: V2EmployerAgreementBenefit[];
  satisfaction_score: number;
  satisfaction_trend: string;
  satisfaction_delta_4w: number;
  salary_negotiations: V2EmployerNegotiation[];
  questions_answered_count: number;
  questions_pending_count: number;
};

// === /v2/arbetsgivaren ===

export type V2EmployerSalarySlip = {
  id: number;
  month: string;
  date: string;
  net_amount: number;
  gross_amount: number | null;
  tax_amount: number | null;
  pension_amount: number | null;
  description: string;
};

export type V2EmployerAgreementBenefit = {
  name: string;
  detail: string;
  value: string;
};

export type V2EmployerNegotiation = {
  id: number;
  status: "active" | "completed" | "abandoned";
  round_no: number;
  max_rounds: number;
  starting_salary: number;
  requested_salary: number | null;
  proposed_pct: number | null;
  avtal_norm_pct: number | null;
  final_salary: number | null;
  final_pct: number | null;
  started_at: string;
  completed_at: string | null;
};

export type V2EmployerQuestionRow = {
  id: number;
  question_id: number;
  question_text: string;
  difficulty: "easy" | "medium" | "hard";
  answered_at: string | null;
  student_answer: string | null;
  delta: number | null;
  is_open: boolean;
};

export type V2EmployerSatisfaction = {
  score: number;
  trend: "rising" | "falling" | "stable";
  delta_4w: number;
};

export type EmployerData = {
  student_id: number;
  profession: string;
  employer: string;
  agreement_name: string | null;
  agreement_union: string | null;
  gross_salary_monthly: number;
  net_salary_monthly: number;
  pension_pct: number | null;
  pension_monthly: number | null;
  employed_since: string | null;
  next_revision_date: string | null;
  market_low: number | null;
  market_high: number | null;
  satisfaction: V2EmployerSatisfaction;
  negotiation: V2EmployerNegotiation | null;
  salary_slips: V2EmployerSalarySlip[];
  agreement_benefits: V2EmployerAgreementBenefit[];
  questions: V2EmployerQuestionRow[];
  open_question_id: number | null;
};

// === /v2/lan ===

export type V2LoanCard = {
  id: number | null;
  eyebrow: string;
  name: string;
  detail: string;
  balance: number | null;
  monthly_text: string | null;
  is_active: boolean;
  is_warning: boolean;
};

export type V2LoanScheduleRow = {
  month: string;
  label: string;
  description: string;
  monthly_amount: number;
  capital_part: number | null;
  interest_part: number | null;
  status: string;
};

export type V2CreditFactor = {
  factor: string;
  detail: string;
  value: string;
  assessment: string;
  severity: "good" | "warn" | "bad" | "neutral";
};

export type LoanData = {
  student_id: number;
  total_debt: number;
  debt_ratio: number;
  annual_income: number;
  credit_class: string;
  cards: V2LoanCard[];
  schedule: V2LoanScheduleRow[];
  credit_factors: V2CreditFactor[];
};

// === Fas 2A · Lånegivaren ===

export type V2KALPResponse = {
  id: number;
  computed_at: string;
  monthly_income_net: number;
  monthly_housing: number;
  monthly_consumer_schablon: number;
  monthly_existing_debt_payments: number;
  stress_test_rate: number;
  loan_amount: number;
  loan_term_months: number;
  monthly_loan_payment_at_stress: number;
  monthly_left_after_all: number;
  passed: boolean;
};

export type V2PaymentMark = {
  id: number;
  occurred_on: string;
  creditor: string;
  amount: number;
  kind: "obetald-faktura" | "kronofogden" | "betalningsforelaggande";
  notes: string | null;
  expires_at: string | null;
  created_at: string;
};

export type V2CreditCheckOut = {
  id: number;
  computed_at: string;
  annual_income: number;
  total_debt: number;
  debt_ratio: number;
  payment_marks_count: number;
  running_applications: number;
  uc_score_class: string;
  uc_score_value: number;
};

export type V2TeacherCreditOverview = {
  student_id: number;
  student_name: string;
  annual_income: number;
  total_debt: number;
  debt_ratio: number;
  active_loans_count: number;
  payment_marks: V2PaymentMark[];
  latest_credit_check: V2CreditCheckOut | null;
  kalp_history: V2KALPResponse[];
  loan_products_count: number;
  available_products_count: number;
};

// === Fas 2D · Försäkringar ===

export type V2InsurancePolicyKind =
  | "hem"
  | "olycksfall"
  | "liv"
  | "barnforsakring"
  | "bostadsrattsforsakring"
  | "bilforsakring"
  | "djur"
  | "ovrig";

export type V2InsuranceClaimKind =
  | "stold"
  | "olycka"
  | "skada"
  | "vattenskada"
  | "brand"
  | "info"
  | "premiehojning"
  | "bytte_bolag";

export type V2InsuranceStatus = "active" | "considered" | "cancelled";
export type V2ClaimStatus =
  | "submitted"
  | "approved"
  | "partial"
  | "denied"
  | "paid"
  | "info";

export type V2InsurancePolicyOut = {
  id: number;
  provider: string;
  name: string;
  kind: V2InsurancePolicyKind;
  premium_monthly: number;
  coverage_amount: number | null;
  deductible: number | null;
  autogiro: boolean;
  status: V2InsuranceStatus;
  started_on: string | null;
  ended_on: string | null;
  notes: string | null;
};

export type V2InsuranceClaimOut = {
  id: number;
  occurred_on: string;
  policy_id: number | null;
  policy_name: string | null;
  kind: V2InsuranceClaimKind;
  title: string;
  description: string | null;
  amount_claimed: number | null;
  amount_paid: number | null;
  status: V2ClaimStatus;
  paid_at: string | null;
  no_policy: boolean;
  notes: string | null;
  created_at: string;
};

export type V2InsuranceSummary = {
  active_count: number;
  considered_count: number;
  cancelled_count: number;
  total_premium_monthly: number;
  total_coverage: number;
  claims_paid_12m: number;
  claims_paid_amount_12m: number;
  claims_unprotected_12m: number;
  coverage_gaps: string[];
};

export type V2InsuranceData = {
  student_id: number;
  summary: V2InsuranceSummary;
  policies: V2InsurancePolicyOut[];
  claims: V2InsuranceClaimOut[];
};

export type V2TeacherInsuranceOverview = {
  student_id: number;
  student_name: string;
  summary: V2InsuranceSummary;
  policies: V2InsurancePolicyOut[];
  claims: V2InsuranceClaimOut[];
};

// === /v2/forbrukning (Fas 2E) ===

export type V2UtilityCategory =
  | "electricity"
  | "broadband"
  | "mobile"
  | "streaming"
  | "transport"
  | "water"
  | "heating"
  | "ovrig";

export type V2UtilitySubStatus = "active" | "cancelled" | "considered";

export type V2UtilitySubscriptionOut = {
  id: number;
  supplier: string;
  name: string;
  category: V2UtilityCategory;
  monthly_cost: number;
  grid_fee_monthly: number | null;
  spot_pricing: boolean;
  binding_end: string | null;
  notice_days: number;
  invoice_day: number | null;
  status: V2UtilitySubStatus;
  included_in_rent: boolean;
  started_on: string | null;
  ended_on: string | null;
  notes: string | null;
};

export type V2UtilityReadingOut = {
  id: number;
  supplier: string;
  meter_type: string;
  meter_role: string;
  period_start: string;
  period_end: string;
  consumption: number | null;
  consumption_unit: string | null;
  cost_kr: number;
  source: string;
  notes: string | null;
};

export type V2UtilitySummary = {
  active_count: number;
  total_monthly_cost: number;
  total_grid_fee: number;
  has_spot_pricing: boolean;
  binding_expiring_soon: number;
  last_month_cost: number;
  last_month_kwh: number;
  suggested_savings_monthly: number;
};

export type V2UtilityData = {
  student_id: number;
  summary: V2UtilitySummary;
  subscriptions: V2UtilitySubscriptionOut[];
  readings: V2UtilityReadingOut[];
};

export type V2TeacherUtilityOverview = {
  student_id: number;
  student_name: string;
  summary: V2UtilitySummary;
  subscriptions: V2UtilitySubscriptionOut[];
  readings: V2UtilityReadingOut[];
};

// === /v2/skatten ===

export type V2TaxLineItem = {
  category: "income" | "deduction" | "capital" | "tax" | "diff";
  label: string;
  name: string;
  detail: string;
  amount: number;
  is_proposal: boolean;
  proposal_id: string | null;
};

export type V2TaxDeductionRow = {
  id: number;
  year: number;
  kind: string;
  name: string;
  description: string | null;
  amount: number;
  source: string;
  created_at: string;
};

export type V2TaxProposalRow = {
  id: number;
  year: number;
  kind: string;
  name: string;
  description: string | null;
  suggested_amount: number;
  status: "pending" | "approved" | "rejected";
  decided_at: string | null;
  deduction_id: number | null;
  source: string;
  created_at: string;
};

export type V2TaxYearReturnOut = {
  id: number;
  year: number;
  submitted_at: string;
  locked: boolean;
  gross_income: number;
  prelim_tax_paid: number;
  deductions_total: number;
  final_tax: number;
  diff: number;
};

export type TaxData = {
  student_id: number;
  year: number;
  deadline: string | null;
  gross_income: number;
  prelim_tax_paid: number;
  final_tax: number;
  diff: number;
  pending_proposal_count: number;
  items: V2TaxLineItem[];
  deductions: V2TaxDeductionRow[];
  proposals: V2TaxProposalRow[];
  submitted: V2TaxYearReturnOut | null;
  can_submit: boolean;
};

export type V2TeacherTaxOverview = {
  student_id: number;
  student_name: string;
  year: number;
  gross_income: number;
  prelim_tax_paid: number;
  deductions_total: number;
  final_tax: number;
  diff: number;
  deductions: V2TaxDeductionRow[];
  proposals: V2TaxProposalRow[];
  submitted: V2TaxYearReturnOut | null;
};

export type TaxDeductionKind =
  | "rese"
  | "bolane-ranta"
  | "csn-ranta"
  | "dubbel-bosattning"
  | "rot"
  | "rut"
  | "fackavgift"
  | "ovrig";

export type V2RosterRow = {
  student_id: number;
  display_name: string;
  class_label: string | null;
  v2_enabled: boolean;
  v2_onboarding_completed: boolean;
  v2_level: number;
};

export type OnboardingEventType =
  | "viewed"
  | "back"
  | "next"
  | "completed"
  | "abandoned";

export const v2Api = {
  status: () => api<V2Status>("/v2/status"),
  hub: () => api<HubData>("/v2/hub"),
  bank: (limitTransactions: number = 30) =>
    api<BankData>(`/v2/bank?limit_transactions=${limitTransactions}`),
  budget: (month?: string) =>
    api<BudgetData>(`/v2/budget${month ? `?month=${month}` : ""}`),
  /** Uppdatera planerad budget för en kategori. */
  updateBudgetCategory: (
    categoryId: number,
    body: { planned_amount: number; month?: string; is_income?: boolean },
  ) =>
    api<V2BudgetCategoryRow>(`/v2/budget/${categoryId}`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  /** Skapa ny kategori + sätt initial budget. */
  createBudgetCategory: (body: {
    category_name: string;
    planned_amount: number;
    month?: string;
    is_income?: boolean;
  }) =>
    api<V2BudgetCategoryRow>("/v2/budget/category", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  /** Radera budget-raden för en kategori i en månad. */
  deleteBudgetRow: (categoryId: number, month?: string) =>
    api<void>(
      `/v2/budget/${categoryId}${month ? `?month=${month}` : ""}`,
      { method: "DELETE" },
    ),
  goals: () => api<GoalsData>("/v2/mal"),
  arbetsgivaren: () => api<EmployerData>("/v2/arbetsgivaren"),

  // === Fas 2D · Försäkringar ===
  forsakringar: () => api<V2InsuranceData>("/v2/forsakringar"),
  insuranceCreatePolicy: (body: {
    provider: string;
    name: string;
    kind: V2InsurancePolicyKind;
    premium_monthly: number;
    coverage_amount?: number;
    deductible?: number;
    autogiro?: boolean;
    status?: V2InsuranceStatus;
    started_on?: string;
    notes?: string;
  }) =>
    api<V2InsurancePolicyOut>("/v2/forsakringar/policies", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  insuranceUpdateStatus: (policyId: number, status: V2InsuranceStatus) =>
    api<V2InsurancePolicyOut>(
      `/v2/forsakringar/policies/${policyId}/status`,
      { method: "PATCH", body: JSON.stringify({ status }) },
    ),
  insuranceDeletePolicy: (policyId: number) =>
    api<void>(`/v2/forsakringar/policies/${policyId}`, {
      method: "DELETE",
    }),
  /** Lärar-API · seedа default-katalog. */
  teacherSeedDefaultInsurance: (studentId: number) =>
    api<{ student_id: number; policies_created: number }>(
      `/v2/teacher/students/${studentId}/insurance/seed-default`,
      { method: "POST", body: "{}" },
    ),
  /** Lärar-API · skapa skadehändelse. */
  teacherCreateInsuranceClaim: (
    studentId: number,
    body: {
      occurred_on: string;
      policy_id?: number;
      kind: V2InsuranceClaimKind;
      title: string;
      description?: string;
      amount_claimed?: number;
      amount_paid?: number;
      status?: V2ClaimStatus;
      paid_at?: string;
      no_policy?: boolean;
      notes?: string;
    },
  ) =>
    api<V2InsuranceClaimOut>(
      `/v2/teacher/students/${studentId}/insurance/claims`,
      { method: "POST", body: JSON.stringify(body) },
    ),
  teacherDeleteInsuranceClaim: (studentId: number, claimId: number) =>
    api<void>(
      `/v2/teacher/students/${studentId}/insurance/claims/${claimId}`,
      { method: "DELETE" },
    ),
  teacherInsuranceOverview: (studentId: number) =>
    api<V2TeacherInsuranceOverview>(
      `/v2/teacher/students/${studentId}/insurance-overview`,
    ),
  // === /v2/forbrukning (Fas 2E) ===
  forbrukning: () => api<V2UtilityData>("/v2/forbrukning"),
  utilityCreateSubscription: (body: {
    supplier: string;
    name: string;
    category: V2UtilityCategory;
    monthly_cost: number;
    grid_fee_monthly?: number;
    spot_pricing?: boolean;
    binding_end?: string;
    notice_days?: number;
    invoice_day?: number;
    status?: V2UtilitySubStatus;
    included_in_rent?: boolean;
    started_on?: string;
    notes?: string;
  }) =>
    api<V2UtilitySubscriptionOut>("/v2/forbrukning/subscriptions", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  utilityPatchSubscription: (
    subId: number,
    body: {
      monthly_cost?: number;
      status?: V2UtilitySubStatus;
      binding_end?: string;
      notes?: string;
    },
  ) =>
    api<V2UtilitySubscriptionOut>(
      `/v2/forbrukning/subscriptions/${subId}`,
      { method: "PATCH", body: JSON.stringify(body) },
    ),
  utilityDeleteSubscription: (subId: number) =>
    api<void>(`/v2/forbrukning/subscriptions/${subId}`, {
      method: "DELETE",
    }),
  /** Lärar-API · seedа default-katalog (6 svenska abonnemang). */
  teacherSeedDefaultUtility: (studentId: number) =>
    api<{ student_id: number; subscriptions_created: number }>(
      `/v2/teacher/students/${studentId}/utility/seed-default`,
      { method: "POST", body: "{}" },
    ),
  /** Lärar-API · skapa månadsfaktura (UtilityReading). */
  teacherCreateUtilityReading: (
    studentId: number,
    body: {
      supplier: string;
      meter_type:
        | "electricity"
        | "broadband"
        | "water"
        | "heating"
        | "district_heating";
      meter_role?: "grid" | "energy" | "total";
      period_start: string;
      period_end: string;
      consumption?: number;
      consumption_unit?: string;
      cost_kr: number;
      notes?: string;
    },
  ) =>
    api<V2UtilityReadingOut>(
      `/v2/teacher/students/${studentId}/utility/readings`,
      { method: "POST", body: JSON.stringify(body) },
    ),
  teacherDeleteUtilityReading: (studentId: number, readingId: number) =>
    api<void>(
      `/v2/teacher/students/${studentId}/utility/readings/${readingId}`,
      { method: "DELETE" },
    ),
  teacherUtilityOverview: (studentId: number) =>
    api<V2TeacherUtilityOverview>(
      `/v2/teacher/students/${studentId}/utility-overview`,
    ),
  /** Lärar-API · lista alla CollectiveAgreement. */
  teacherListAgreements: () =>
    api<V2CollectiveAgreementOut[]>("/v2/teacher/agreements"),
  /** Lärar-API · lista benefits för ett avtal. */
  teacherListAgreementBenefits: (agreementId: number) =>
    api<V2AgreementBenefitOut[]>(
      `/v2/teacher/agreements/${agreementId}/benefits`,
    ),
  /** Lärar-API · skapa benefit. */
  teacherCreateAgreementBenefit: (body: {
    agreement_id: number;
    kind: string;
    name: string;
    detail?: string;
    value: string;
    sort_order?: number;
  }) =>
    api<V2AgreementBenefitOut>("/v2/teacher/agreement-benefits", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  /** Lärar-API · ta bort benefit. */
  teacherDeleteAgreementBenefit: (benefitId: number) =>
    api<void>(`/v2/teacher/agreement-benefits/${benefitId}`, {
      method: "DELETE",
    }),
  /** Lärar-API · seedа default-katalog för avtal. */
  teacherSeedDefaultAgreementBenefits: () =>
    api<{ created: number }>(
      "/v2/teacher/agreement-benefits/seed-default",
      { method: "POST", body: "{}" },
    ),
  /** Lärar-API · lista marknadsspann (filtrera på yrke). */
  teacherListMarketRanges: (profession?: string) =>
    api<V2MarketSalaryRangeOut[]>(
      `/v2/teacher/market-salary-ranges${
        profession ? `?profession=${encodeURIComponent(profession)}` : ""
      }`,
    ),
  /** Lärar-API · skapa/uppdatera marknadsspann. */
  teacherCreateMarketRange: (body: {
    profession: string;
    city: string;
    year: number;
    experience_band?: string;
    low: number;
    high: number;
    median?: number;
    source?: string;
    notes?: string;
  }) =>
    api<V2MarketSalaryRangeOut>("/v2/teacher/market-salary-ranges", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  /** Lärar-API · ta bort marknadsspann. */
  teacherDeleteMarketRange: (rangeId: number) =>
    api<void>(`/v2/teacher/market-salary-ranges/${rangeId}`, {
      method: "DELETE",
    }),
  /** Lärar-API · seedа SCB-katalog (svenska 2026). */
  teacherSeedDefaultMarketRanges: () =>
    api<{ created: number }>(
      "/v2/teacher/market-salary-ranges/seed-default",
      { method: "POST", body: "{}" },
    ),
  /** Lärar-API · full insyn i elevens arbetsgivar-aktör. */
  teacherEmployerOverview: (studentId: number) =>
    api<V2TeacherEmployerOverview>(
      `/v2/teacher/students/${studentId}/employer-overview`,
    ),
  skatten: (year?: number) =>
    api<TaxData>(`/v2/skatten${year ? `?year=${year}` : ""}`),
  /** Eleven registrerar manuellt avdrag. */
  taxAddDeduction: (body: {
    year: number;
    kind: TaxDeductionKind;
    name: string;
    description?: string;
    amount: number;
  }) =>
    api<V2TaxDeductionRow>("/v2/skatten/deductions", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  /** Eleven tar bort sitt avdrag. */
  taxDeleteDeduction: (deductionId: number) =>
    api<void>(`/v2/skatten/deductions/${deductionId}`, {
      method: "DELETE",
    }),
  /** Eleven godkänner/avvisar förslag. */
  taxProposalDecision: (
    proposalId: number,
    decision: "approve" | "reject",
  ) =>
    api<V2TaxProposalRow>(
      `/v2/skatten/proposals/${proposalId}/decision`,
      { method: "POST", body: JSON.stringify({ decision }) },
    ),
  /** Eleven lämnar in deklarationen. */
  taxSubmitYear: (year: number) =>
    api<{
      return_id: number;
      year: number;
      submitted_at: string;
      locked: boolean;
      final_tax: number;
      diff: number;
    }>(`/v2/skatten/${year}/submit`, { method: "POST", body: "{}" }),
  /** Lärar-API · skapa förslag manuellt. */
  teacherCreateTaxProposal: (
    studentId: number,
    body: {
      year: number;
      kind: TaxDeductionKind;
      name: string;
      description?: string;
      suggested_amount: number;
    },
  ) =>
    api<V2TaxProposalRow>(
      `/v2/teacher/students/${studentId}/tax-proposals`,
      { method: "POST", body: JSON.stringify(body) },
    ),
  /** Lärar-API · auto-generera förslag från Loan-räntor. */
  teacherAutoGenerateTaxProposals: (studentId: number, year?: number) =>
    api<{ student_id: number; year: number; created: number }>(
      `/v2/teacher/students/${studentId}/tax-proposals/auto-generate${
        year ? `?year=${year}` : ""
      }`,
      { method: "POST", body: "{}" },
    ),
  /** Lärar-API · ta bort förslag. */
  teacherDeleteTaxProposal: (studentId: number, proposalId: number) =>
    api<void>(
      `/v2/teacher/students/${studentId}/tax-proposals/${proposalId}`,
      { method: "DELETE" },
    ),
  /** Lärar-API · full insyn i deklarationen. */
  teacherTaxOverview: (studentId: number, year?: number) =>
    api<V2TeacherTaxOverview>(
      `/v2/teacher/students/${studentId}/tax-overview${
        year ? `?year=${year}` : ""
      }`,
    ),
  lan: () => api<LoanData>("/v2/lan"),
  /** Räkna KALP för ett tänkt lånebelopp (sparas i scope-DB). */
  kalp: (loanAmount: number, loanTermMonths: number = 300) =>
    api<V2KALPResponse>("/v2/lan/kalp", {
      method: "POST",
      body: JSON.stringify({
        loan_amount: loanAmount,
        loan_term_months: loanTermMonths,
      }),
    }),
  /** Lärar-API · seedа default-katalog (5 produkter). */
  teacherSeedDefaultLoanProducts: (studentId: number) =>
    api<{ student_id: number; products_created: number }>(
      `/v2/teacher/students/${studentId}/loan-products/seed-default`,
      { method: "POST", body: "{}" },
    ),
  /** Lärar-API · skapa enskild låneprodukt. */
  teacherCreateLoanProduct: (
    studentId: number,
    body: {
      lender: string;
      name: string;
      kind: "csn" | "bolan" | "privatlan" | "billan" | "smslan";
      interest_rate_min: number;
      interest_rate_max: number;
      max_amount?: number;
      binding_required?: boolean;
      description?: string;
      risk_class?: "billig" | "medel" | "dyr";
      available?: boolean;
    },
  ) =>
    api<{
      id: number;
      lender: string;
      name: string;
      kind: string;
    }>(`/v2/teacher/students/${studentId}/loan-products`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  /** Lärar-API · lägg till betalningsanmärkning. */
  teacherCreatePaymentMark: (
    studentId: number,
    body: {
      occurred_on: string;
      creditor: string;
      amount: number;
      kind: "obetald-faktura" | "kronofogden" | "betalningsforelaggande";
      notes?: string;
      expires_at?: string;
    },
  ) =>
    api<V2PaymentMark>(
      `/v2/teacher/students/${studentId}/payment-marks`,
      { method: "POST", body: JSON.stringify(body) },
    ),
  /** Lärar-API · ta bort anmärkning. */
  teacherDeletePaymentMark: (studentId: number, markId: number) =>
    api<void>(
      `/v2/teacher/students/${studentId}/payment-marks/${markId}`,
      { method: "DELETE" },
    ),
  /** Lärar-API · full insyn i elevens kreditprofil. */
  teacherCreditOverview: (studentId: number) =>
    api<V2TeacherCreditOverview>(
      `/v2/teacher/students/${studentId}/credit-overview`,
    ),
  postladan: (filter?: V2MailType | "unhandled" | "other") =>
    api<MailData>(`/v2/postladan${filter ? `?filter=${filter}` : ""}`),
  updateMailStatus: (mailId: number, status: V2MailStatus) =>
    api<V2MailItem>(`/v2/postladan/${mailId}/status`, {
      method: "PATCH",
      body: JSON.stringify({ status }),
    }),
  seedMailForStudent: (
    studentId: number,
    items: V2MailSeedItem[],
    replaceExisting: boolean = false,
  ) =>
    api<{ student_id: number; created: number; deleted: number }>(
      `/v2/teacher/students/${studentId}/mail-seed`,
      {
        method: "POST",
        body: JSON.stringify({
          items,
          replace_existing: replaceExisting,
        }),
      },
    ),
  completeOnboarding: (body: {
    spend_profile: SpendProfile;
    fairness_choice: FairnessChoice | null;
    partner_model: PartnerModel;
  }) =>
    api<OnboardingComplete>("/v2/onboarding/complete", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  logOnboardingEvent: (body: {
    step: number;
    event_type: OnboardingEventType;
    duration_ms?: number;
    payload?: string;
  }) =>
    api<{ event_id: number; student_id: number }>(
      "/v2/onboarding/event",
      { method: "POST", body: JSON.stringify(body) },
    ),
  // Lärar-API:er för att toggla v2 per elev
  toggleStudent: (studentId: number, enabled: boolean) =>
    api<{ student_id: number; v2_enabled: boolean; display_name: string }>(
      `/v2/teacher/students/${studentId}/v2-toggle`,
      { method: "POST", body: JSON.stringify({ enabled }) },
    ),
  bulkToggle: (enabled: boolean, studentIds?: number[]) =>
    api<{ affected: number; enabled: boolean }>(
      "/v2/teacher/students/v2-bulk",
      {
        method: "POST",
        body: JSON.stringify({
          enabled,
          student_ids: studentIds ?? null,
        }),
      },
    ),
  roster: () =>
    api<V2RosterRow[]>("/v2/teacher/students/v2-roster"),
};
