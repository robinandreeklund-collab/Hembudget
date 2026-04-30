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
