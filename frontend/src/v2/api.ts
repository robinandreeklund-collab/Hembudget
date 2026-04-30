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
  display_name: string;
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
