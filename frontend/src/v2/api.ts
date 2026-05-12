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

export type SeedStatus = "pending" | "complete" | "failed";

export type V2Status = {
  role: "student" | "teacher" | "demo";
  v2_eligible: boolean;
  v2_onboarding_completed: boolean;
  v2_level: number;
  v2_spend_profile: SpendProfile;
  v2_fairness_choice: FairnessChoice | null;
  v2_partner_model: PartnerModel;
  is_super_admin: boolean;
  /** "pending" tills BackgroundTask seedat all initial-data
   * (lön, postlådan, försäkringar, pension, rental, events). Frontend
   * visar overlay tills "complete" så eleven inte ser tomma vyer. */
  seed_status?: SeedStatus;
  /** Eleven-id · används för att cacha seed-complete per id i
   * sessionStorage så overlayn inte flashar vid efterföljande
   * navigation. NULL för lärare/demo. */
  student_id?: number | null;
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
  /** 'employed' (default) | 'self_employed' | 'unemployed' · styr
   * HubV2-rendering: 'Anställd · X' / 'Egenföretagare · {company}'
   * / 'Söker jobb'. */
  employment_status?: "employed" | "self_employed" | "unemployed";
  /** Datum då pågående anställning upphör (LAS uppsägningstid).
   * Lön genereras tills detta datum, sedan stoppas salary_phase. */
  employment_end_on?: string | null;
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
  save_rate_pct: number | null;
  transactions_count: number;
  start_of_month_balance: number;
};

export type HubEventItem = {
  id: number;
  kind: "event" | "invite";
  title: string;
  category: string;
  cost: number;
  deadline: string;
  source: string;
  from_name: string | null;
  days_until_deadline: number;
  declinable: boolean;
};

export type HubGameTime = {
  iso_date: string;
  weekday_label: string;
  full_label: string;
  short_label: string;
  year_month: string;
  real_anchor_at: string;
  seconds_per_game_day: number;
  seconds_into_current_day: number;
  seconds_until_next_day: number;
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
  pending_events: HubEventItem[];
  game_time: HubGameTime | null;
};

// === Events / sociala händelser (V2) ===

export type V2EventItem = {
  id: number;
  event_code: string;
  title: string;
  description: string;
  category: string;
  cost: number;
  proposed_date: string | null;
  deadline: string;
  source: string;
  status: string;
  social_invite_allowed: boolean;
  declinable: boolean;
  created_at: string;
};

export type V2InviteItem = {
  id: number;
  from_student_id: number;
  from_name: string;
  event_code: string;
  event_title: string;
  proposed_date: string | null;
  deadline: string;
  cost: number;
  cost_split_model: string;
  swish_amount: number | null;
  message: string | null;
  status: string;
  created_at: string;
};

export type V2ClassmateItem = {
  student_id: number;
  display_name: string;
  class_label: string | null;
};

export type V2EventAcceptResponse = {
  event_id: number;
  status: string;
  transaction_id: number | null;
  cost_applied: number;
  income_applied: number;
  impact_applied: Record<string, number>;
  pedagogical_note: string;
};

export type V2EventDeclineResponse = {
  event_id: number;
  status: string;
  impact_applied: Record<string, number>;
  pedagogical_note: string;
  current_decline_streak: number;
  show_streak_nudge: boolean;
};

export type BankAccount = {
  id: number;
  name: string;
  bank: string;
  type: string;
  account_number: string | null;
  current_balance: number;
  fund_value: number;
  /** Aktievärde · quantity × senaste kurs. 0 om kontot inte har aktier. */
  stock_value?: number;
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
  mail_id: number | null;
  is_signed: boolean;
  // Spel-dagar tills förfall · negativa = förfluten. Räknas backend-
  // side mot current_game_date() så frontend slipper jämföra mot
  // real-tid (= maj 2026 medan spel-tid är jan).
  days_until_expected: number;
};

export type BankSummary = {
  total_balance: number;
  accounts_count: number;
  upcoming_open_total: number;
  upcoming_open_count: number;
  income_this_month: number;
  expenses_this_month: number;
  transactions_count: number;
  next_release_at: string | null;
  pending_count: number;
  // Spel-tid · ISO. Frontend använder detta som "today" för
  // datum-jämförelser (DAYS_UNTIL etc.) istället för new Date().
  today_game: string | null;
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
  save_rate_pct: number | null;
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
export type V2MailStatus =
  | "unhandled"
  | "viewed"
  | "exported"
  | "paid"
  | "expired"
  | "handled"
  | "failed";
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
  body: string | null;
  amount: number | null;
  due_date: string | null;
  received_at: string;
  status: V2MailStatus;
  upcoming_id: number | null;
  transaction_id: number | null;
  is_recurring: boolean;
  ocr_reference: string | null;
  bankgiro: string | null;
  notes: string | null;
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
  // Realtid-projektion · när nästa pending mail "släpps" till postlådan.
  next_release_at: string | null;
  pending_count: number;
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

// === Huvudbok / Ledger (V2) =============================================
// Rapporterar balansrapport per konto + resultaträkning per kategori +
// avstämningskontroller. Svarar på GET /v2/ledger/?month=YYYY-MM eller ?year=YYYY.

export type LedgerAccount = {
  id: number;
  name: string;
  type: string;
  opening: number;
  income: number;
  expense: number;
  transfer_in: number;
  transfer_out: number;
  closing: number;
  fund_value?: number | null;
  total_value?: number | null;
  tx_count: number;
};

export type LedgerCategoryRow = {
  id: number | null;
  name: string;
  income: number;
  expense: number;
  net: number;
  tx_count: number;
};

export type LedgerCheck = {
  type: string;
  label: string;
  status: "ok" | "warn" | "fail";
  message: string;
  detail_count?: number;
};

export type LedgerData = {
  period: {
    label: string;
    start: string;
    end: string;
  };
  locked_months: string[];
  accounts: LedgerAccount[];
  categories: LedgerCategoryRow[];
  loans?: Array<{
    name: string;
    expected_balance: number;
    matched_balance: number;
    delta: number;
  }>;
  upcoming_summary?: Record<string, unknown>;
  totals: {
    income: number;
    expenses: number;
    net_result: number;
    assets: number;
    liabilities: number;
    net_worth: number;
    uncategorized_count: number;
  };
  checks: LedgerCheck[];
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

export type V2LoanKind = "privatlan" | "billan" | "bolan" | "smslan";

export type V2LoanApplyRequest = {
  loan_kind: V2LoanKind;
  amount: number;
  term_months: number;
  purpose?: string;
  debit_account_id?: number;
  accept_offer?: boolean;
};

export type V2WellbeingImpact = {
  axis: string;
  delta: number;
  explanation: string;
};

export type V2LoanApplyResponse = {
  application_id: number;
  approved: boolean;
  decline_reason?: string | null;
  loan_kind: string;
  score: number;
  grade: string;
  score_components: Record<string, number>;
  kalp_passed: boolean;
  kalp_left_after_all: number;
  offered_rate?: number | null;
  offered_monthly_payment?: number | null;
  offered_total_repay?: number | null;
  lender?: string | null;
  loan_id?: number | null;
  wellbeing_impact: V2WellbeingImpact[];
  warnings: string[];
};

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
  | "frisktandvard"
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

// === /v2/arbetsformedlingen (Sprint 6 · A1-A5) ===

export type V2ArbetsformedlingenJob = {
  listing_id: string;
  yrke_key: string;
  yrke_display: string;
  yrke_ssyk: string;
  employer_name: string;
  city_key: string;
  city_display: string;
  monthly_gross_min: number;
  monthly_gross_median: number;
  monthly_gross_max: number;
  education_level: string;
  match_score: number;
  description: string;
  // Sprint 7 · utökad annons-data
  company_blurb: string;
  job_description: string[];
  requirements: string[];
  meriter: string[];
  benefits: string[];
  employment_type: string;
  application_deadline: string;
  work_hours: string;
  start_date: string;
};

export type V2CoverLetterPreviewIn = {
  text: string;
  yrke_display: string;
  employer_name: string;
  job_description?: string;
  requirements?: string[];
};

export type V2CoverLetterPreviewOut = {
  score: number;
  feedback_md: string;
  highlights: string[];
};

export type V2ArbetsformedlingenJobsResponse = {
  mats_message: string;
  year_month: string;
  jobs: V2ArbetsformedlingenJob[];
};

export type V2ArbetsformedlingenApplication = {
  id: number;
  yrke_key: string;
  yrke_display: string;
  employer_name: string;
  city_key: string;
  city_display: string;
  status:
    | "round_1" | "round_2" | "round_3" | "round_4" | "round_5"
    | "offer_pending" | "accepted" | "rejected" | "declined" | "abandoned";
  current_round: number;
  match_score: number;
  monthly_gross_offered: number | null;
  final_score: number | null;
  feedback_md: string | null;
  rounds_data: Record<string, unknown> | null;
  started_on: string;
  completed_on: string | null;
  // Sprint 7 · läses av elev + lärar-vy
  cover_letter_text: string | null;
  case_answer_text: string | null;
  ai_feedback_md: string | null;
  job_ad_data: Record<string, unknown> | null;
};

export type V2ArbetsformedlingenRoundOut = {
  round_n: number;
  score_delta: number;
  feedback_md: string;
  pentagon_delta: Record<string, number>;
  advanced_to: number;
  final_status: string | null;
  application: V2ArbetsformedlingenApplication;
};

export type V2TeacherAFOverview = {
  student_id: number;
  student_name: string;
  n_applications_total: number;
  n_active: number;
  n_completed: number;
  n_declined: number;
  n_abandoned: number;
  avg_match_score: number | null;
  avg_final_score: number | null;
  last_application_date: string | null;
  summary_md: string;
};


// === /v2/boendemarknad (Sprint 5 · B1-B5) ===

export type V2BoendemarknadListing = {
  listing_id: string;
  city_key: string;
  city_display: string;
  type: "bostadsratt" | "villa" | "radhus";
  address: string;
  size_kvm: number;
  rooms: number;
  asking_price: number;
  monthly_avgift: number;
  description: string;
  quality_score: number;
};

export type V2BoendemarknadListings = {
  city_key: string;
  city_display: string;
  year_month: string;
  market_price_per_kvm: number;
  listings: V2BoendemarknadListing[];
};

export type V2BoendemarknadValuation = {
  has_owned_home: boolean;
  purchase_price: number | null;
  current_value: number | null;
  unrealized_gain: number | null;
  loan_balance: number | null;
  equity: number | null;
  city_key: string | null;
  note: string | null;
};

export type V2BoendemarknadBuyResult = {
  listing_id: string;
  accepted: boolean;
  loan_id: number | null;
  monthly_cost: number;
  cash_required: number;
  pentagon_delta: Record<string, number>;
  error: string | null;
};

export type V2BoendemarknadSellResult = {
  estimated_value: number;
  estimated_proceeds_after_costs: number;
  sell_horizon_months: number;
  capital_gain_estimate: number;
  pentagon_delta: Record<string, number>;
};

export type V2BoendemarknadCityPrice = {
  city_key: string;
  city_display: string;
  year_month: string;
  price_per_kvm: number;
};

export type V2BoendemarknadActiveHome = {
  id: number;
  home_type: "hyresratt" | "bostadsratt" | "villa" | "radhus";
  status: "active" | "notice_given" | "selling" | "terminated";
  city_key: string;
  address: string | null;
  size_kvm: number;
  rooms: number;
  monthly_cost: number;
  purchase_price: number | null;
  loan_id: number | null;
  listing_id: string | null;
  entered_on: string;
  termination_date: string | null;
  estimated_sale_date: string | null;
  household_size_when_chosen: number;
};

export type V2BoendemarknadTerminateResult = {
  home_id: number;
  status: string;
  termination_date: string;
  months_until_termination: number;
};


// === /v2/hyresvarden (Fas 2F) ===

export type V2RentalContractType =
  | "forsta_hand"
  | "andra_hand"
  | "inneboende"
  | "bostadsratt";

export type V2RentalDurationType = "tillsvidare" | "tidsbegransad";

export type V2RentalContractStatus =
  | "active"
  | "terminated"
  | "considered";

export type V2RentalNoticeType =
  | "hyresavi"
  | "underhall"
  | "hyreshojning"
  | "trapphusrenovering"
  | "forhandling"
  | "brand"
  | "andrahand_ansokan"
  | "ovrig";

export type V2RentalNoticeStatus =
  | "info"
  | "action_required"
  | "paid"
  | "acknowledged"
  | "denied";

export type V2RentalContractOut = {
  id: number;
  landlord: string;
  address: string;
  rooms_label: string;
  area_sqm: number;
  city: string | null;
  district: string | null;
  contract_type: V2RentalContractType;
  duration_type: V2RentalDurationType;
  monthly_rent: number;
  deposit: number | null;
  ocr_reference: string | null;
  autogiro: boolean;
  notice_period_months: number;
  started_on: string | null;
  ended_on: string | null;
  queue_years: number | null;
  queue_priority: string | null;
  market_price_per_sqm: number | null;
  status: V2RentalContractStatus;
  notes: string | null;
};

export type V2RentalNoticeOut = {
  id: number;
  contract_id: number | null;
  occurred_on: string;
  notice_type: V2RentalNoticeType;
  title: string;
  description: string | null;
  amount: number | null;
  change_pct: number | null;
  status: V2RentalNoticeStatus;
  notes: string | null;
  created_at: string;
};

export type V2RentalSummary = {
  has_active_contract: boolean;
  monthly_rent: number;
  rent_per_sqm_yearly: number;
  rent_share_of_net_pct: number | null;
  notices_open: number;
  notices_paid_12m: number;
  biggest_hike_pct_12m: number | null;
  market_diff_pct: number | null;
  market_buy_estimate: number | null;
};

export type V2RentalData = {
  student_id: number;
  summary: V2RentalSummary;
  contract: V2RentalContractOut | null;
  notices: V2RentalNoticeOut[];
};

export type V2TeacherRentalOverview = {
  student_id: number;
  student_name: string;
  summary: V2RentalSummary;
  contract: V2RentalContractOut | null;
  notices: V2RentalNoticeOut[];
};

// === /v2/pension (Fas 2G) ===

export type V2PensionPillarSource = "auto" | "agreement" | "isk" | "missing";

export type V2PensionPillar = {
  label: string;
  name: string;
  detail: string;
  monthly_at_retire: number;
  source: V2PensionPillarSource;
};

export type V2PensionScenarios = {
  age_65_early: number;
  age_67_target: number;
  age_70_late: number;
};

export type V2PensionAssumptions = {
  retire_age: number;
  real_return_pct: number;
  ibb_yearly: number;
  delningstal: number;
  custom_isk_monthly: number;
  itp1_low_pct: number;
  itp1_high_pct: number;
  notes: string | null;
};

export type V2PensionData = {
  student_id: number;
  assumptions: V2PensionAssumptions;
  years_to_retire: number;
  pillars: V2PensionPillar[];
  total_monthly_at_retire: number;
  scenarios: V2PensionScenarios;
  isk_current_value: number;
  has_collective_agreement: boolean;
  age: number | null;
  gross_salary_monthly: number | null;
};

export type V2TeacherPensionOverview = {
  student_id: number;
  student_name: string;
  forecast: V2PensionData;
};

// === /v2/avanza (Fas 2G — Aktör 05) ===

export type V2AvanzaFundOut = {
  id: number;
  fund_name: string;
  units: number | null;
  market_value: number;
  last_price: number | null;
  change_pct: number | null;
  day_change_pct: number | null;
  last_update_date: string;
};

export type V2AvanzaStockOut = {
  id: number;
  ticker: string;
  quantity: number;
  avg_cost: number;
  last_price: number | null;
  market_value: number;
  unrealized_pnl: number;
  unrealized_pnl_pct: number | null;
};

export type V2AvanzaTradeRow = {
  id: number;
  ticker: string;
  side: string;
  quantity: number;
  price: number;
  courtage: number;
  total_amount: number;
  realized_pnl: number | null;
  student_rationale: string | null;
  executed_at: string;
};

export type V2AvanzaSummary = {
  isk_account_id: number | null;
  isk_account_name: string | null;
  cash_balance: number;
  funds_value: number;
  stocks_value: number;
  total_value: number;
  schablonskatt_estimate: number;
  fund_count: number;
  stock_count: number;
  monthly_savings: number;
};

export type V2AvanzaData = {
  student_id: number;
  summary: V2AvanzaSummary;
  funds: V2AvanzaFundOut[];
  stocks: V2AvanzaStockOut[];
  recent_trades: V2AvanzaTradeRow[];
};

export type V2TeacherAvanzaOverview = {
  student_id: number;
  student_name: string;
  avanza: V2AvanzaData;
};

// === /v2/bokforing (Fas 2H — Verktyg 02) ===

export type V2BookkeepingTxRow = {
  id: number;
  date: string;
  account_id: number;
  account_name: string;
  amount: number;
  raw_description: string;
  normalized_merchant: string | null;
  category_id: number | null;
  category_name: string | null;
  ai_confidence: number | null;
  user_verified: boolean;
  is_transfer: boolean;
  notes: string | null;
};

export type V2BookkeepingCategoryRef = {
  id: number;
  name: string;
  parent_id: number | null;
  color: string | null;
};

export type V2BookkeepingSummary = {
  period_label: string;
  period_start: string;
  period_end: string;
  total_transactions: number;
  auto_classified: number;
  manual_classified: number;
  unclassified: number;
  classification_rate_pct: number;
  income_total: number;
  expense_total: number;
  saved_total: number;
  saved_pct: number;
  last_classified_at: string | null;
};

export type V2BookkeepingData = {
  student_id: number;
  summary: V2BookkeepingSummary;
  unclassified: V2BookkeepingTxRow[];
  classified: V2BookkeepingTxRow[];
  categories: V2BookkeepingCategoryRef[];
};

export type V2BulkClassifyResult = {
  processed: number;
  classified: number;
  via_rule: number;
  via_history: number;
  via_llm: number;
  still_unclassified: number;
};

export type V2TeacherBookkeepingOverview = {
  student_id: number;
  student_name: string;
  bokforing: V2BookkeepingData;
};

// === /v2/moduler (Fas 2I — Skola 09) ===

export type V2ModuleStepKind =
  | "read"
  | "watch"
  | "reflect"
  | "task"
  | "quiz";

export type V2ModuleProgressOut = {
  student_module_id: number;
  module_id: number;
  title: string;
  summary: string | null;
  is_template: boolean;
  teacher_owned: boolean;
  sort_order: number;
  started_at: string | null;
  completed_at: string | null;
  assigned_at: string;
  step_count: number;
  completed_step_count: number;
  progress_pct: number;
  current_step_no: number | null;
  estimated_minutes_left: number | null;
};

export type V2ModuleAvailableOut = {
  module_id: number;
  title: string;
  summary: string | null;
  is_template: boolean;
  teacher_owned: boolean;
  step_count: number;
  estimated_total_minutes: number;
};

export type V2ModulerSummary = {
  in_progress_count: number;
  completed_count: number;
  available_count: number;
  avg_progress_pct: number;
  last_activity_at: string | null;
};

export type V2ModulerData = {
  student_id: number;
  summary: V2ModulerSummary;
  in_progress: V2ModuleProgressOut[];
  completed: V2ModuleProgressOut[];
  available: V2ModuleAvailableOut[];
};

export type V2TeacherModulerOverview = {
  student_id: number;
  student_name: string;
  moduler: V2ModulerData;
};

// === /v2/simulator (Fas 2J — Verktyg 05 + 06) ===

export type V2InvestSimResult = {
  start_amount: number;
  monthly_save: number;
  return_pct: number;
  years: number;
  is_isk: boolean;
  schablonskatt_pct: number;
  total_invested: number;
  final_value: number;
  total_growth: number;
  total_taxes: number;
  yearly_balances: number[];
  saved_scenario_id: number | null;
  compare: (Record<string, unknown> & {
    final_value: number;
    total_invested: number;
    total_taxes: number;
    diff_final: number;
  }) | null;
};

export type V2SimulatorScheduleRow = {
  month: number;
  payment: number;
  interest: number;
  principal: number;
  balance: number;
};

export type V2LoanSimResult = {
  principal: number;
  interest_rate_pct: number;
  term_months: number;
  amortization_type: "annuity" | "straight";
  extra_amortization_monthly: number;
  monthly_payment_baseline: number;
  total_paid_baseline: number;
  total_interest_baseline: number;
  monthly_payment_with_extra: number;
  total_paid_with_extra: number;
  total_interest_with_extra: number;
  payoff_months_with_extra: number;
  interest_savings: number;
  months_saved: number;
  schedule_first_12: V2SimulatorScheduleRow[];
  saved_scenario_id: number | null;
};

export type V2SimulatorScenarioRow = {
  id: number;
  name: string;
  kind: "invest" | "loan";
  params: Record<string, unknown>;
  result: Record<string, unknown> | null;
  created_at: string;
};

export type V2TeacherSimulatorOverview = {
  student_id: number;
  student_name: string;
  invest_count: number;
  loan_count: number;
  longest_horizon_years: number;
  biggest_principal: number;
  scenarios: V2SimulatorScenarioRow[];
};

// === /v2/feedback (Fas 2K — Skola · Lärar-feedback) ===

export type V2FeedbackKind =
  | "message"
  | "module_step"
  | "module_step_quiz"
  | "module_step_done"
  | "assignment";

export type V2FeedbackItem = {
  kind: V2FeedbackKind;
  source_id: number;
  title: string;
  body: string;
  created_at: string;
  is_unread: boolean;
  teacher_name: string | null;
  context_type: string | null;
  context_id: number | null;
  context_label: string | null;
  link_target: string | null;
};

export type V2FeedbackSummary = {
  total_count: number;
  unread_count: number;
  message_count: number;
  module_step_count: number;
  assignment_count: number;
  last_received_at: string | null;
};

export type V2FeedbackData = {
  student_id: number;
  summary: V2FeedbackSummary;
  items: V2FeedbackItem[];
};

export type V2TeacherFeedbackOverview = {
  student_id: number;
  student_name: string;
  feedback: V2FeedbackData;
};

// === /v2/maria (Fas 2L · Maria-AI lönesamtal) ===

export type V2MariaRound = {
  round_no: number;
  student_message: string;
  employer_response: string;
  proposed_pct: number | null;
  created_at: string;
};

export type V2MariaNegotiation = {
  id: number;
  profession: string;
  employer: string;
  starting_salary: number;
  avtal_norm_pct: number | null;
  avtal_code: string | null;
  started_at: string;
  completed_at: string | null;
  status: "active" | "completed" | "abandoned";
  final_salary: number | null;
  final_pct: number | null;
  teacher_summary_md: string | null;
  rounds: V2MariaRound[];
  max_rounds: number;
  is_disabled: boolean;
};

export type V2MariaData = {
  student_id: number;
  has_active: boolean;
  active: V2MariaNegotiation | null;
  history: V2MariaNegotiation[];
};

export type V2TeacherMariaOverview = {
  student_id: number;
  student_name: string;
  maria: V2MariaData;
};

// === /v2/bankid (Fas 2L · BankID-simulator) ===

export type V2BankIDInvoiceRow = {
  upcoming_id: number;
  name: string;
  amount: number;
  due_date: string;
  is_recurring: boolean;
  is_anomaly: boolean;
};

export type V2BankIDSessionOut = {
  id: number;
  upcoming_ids: number[];
  total_amount: number;
  invoice_count: number;
  status: "pending" | "signed" | "cancelled";
  current_step: number;
  signed_at: string | null;
  cancelled_at: string | null;
  duration_seconds: number | null;
  invoices: V2BankIDInvoiceRow[];
  notes: string | null;
  created_at: string;
  confirm_token: string | null;
  student_id: number | null;
};

export type V2BankIDListData = {
  student_id: number;
  sessions: V2BankIDSessionOut[];
  pending_count: number;
  signed_count: number;
  cancelled_count: number;
  total_signed_amount: number;
};

export type V2TeacherBankIDOverview = {
  student_id: number;
  student_name: string;
  bankid: V2BankIDListData;
};

// === /v2/tx/{id} (Fas 2M · Transaktion-detalj) ===

export type V2TxRecurringRow = {
  id: number;
  date: string;
  amount: number;
  description: string;
  is_self: boolean;
};

export type V2TxDetailData = {
  id: number;
  date: string;
  amount: number;
  raw_description: string;
  normalized_merchant: string | null;
  account_id: number;
  account_name: string;
  category_id: number | null;
  category_name: string | null;
  subcategory_id: number | null;
  subcategory_name: string | null;
  ai_confidence: number | null;
  user_verified: boolean;
  is_transfer: boolean;
  notes: string | null;
  tags: string[] | null;
  recurring: V2TxRecurringRow[];
  recurring_total_30d: number;
  recurring_count_30d: number;
  categories: V2BookkeepingCategoryRef[];
  accounts: { id: number; name: string; type: string }[];
  existing_rule_id: number | null;
};

export type V2TxCreateRuleResult = {
  rule_id: number;
  pattern: string;
  category_id: number;
  applied_count: number;
  already_existed: boolean;
};

// === /v2/messages (Fas 2M · Lärar-chat) ===

export type V2MessageRow = {
  id: number;
  sender_role: "student" | "teacher";
  body: string;
  context_type: string | null;
  context_id: number | null;
  created_at: string;
  read_at: string | null;
  is_unread: boolean;
};

export type V2MessagesData = {
  student_id: number;
  teacher_name: string | null;
  teacher_id: number | null;
  messages: V2MessageRow[];
  unread_count: number;
  last_received_at: string | null;
};

export type V2TeacherMessagesOverview = {
  student_id: number;
  student_name: string;
  messages: V2MessagesData;
  student_unread_count: number;
  teacher_unread_count: number;
};

// === /v2/portfolio (Fas 2M · Kompetens-portfolio) ===

export type V2CompetencyEntry = {
  competency_id: number;
  key: string;
  name: string;
  description: string | null;
  is_system: boolean;
  mastery: number;
  completed_steps: number;
  last_event_at: string | null;
  level: "B" | "G" | "F";
  level_label: string;
};

export type V2PortfolioSummary = {
  total_competencies: number;
  basis_count: number;
  grund_count: number;
  fordjup_count: number;
  last_event_at: string | null;
};

export type V2PortfolioData = {
  student_id: number;
  summary: V2PortfolioSummary;
  competencies: V2CompetencyEntry[];
};

export type V2TeacherPortfolioOverview = {
  student_id: number;
  student_name: string;
  portfolio: V2PortfolioData;
};

// === /v2/postladan/{id}/detail (Fas 2N · CC + Lönespec drill-down) ===

export type V2CcTxRow = {
  id: number;
  date: string;
  amount: number;
  raw_description: string;
  normalized_merchant: string | null;
  category_id: number | null;
  category_name: string | null;
  is_classified: boolean;
  user_verified: boolean;
};

export type V2CcInvoiceData = {
  period_start: string;
  period_end: string;
  total_amount: number;
  tx_count: number;
  classified_count: number;
  unclassified_count: number;
  auto_classified_count: number;
  avg_amount: number;
  profile_label: string;
  consumer_avg: number;
  profile_avg: number;
  transactions: V2CcTxRow[];
  prev_month_amount: number | null;
  diff_pct_vs_prev: number | null;
};

export type V2SalarySlipBreakdownRow = {
  label: string;
  amount: number;
  is_total: boolean;
};

export type V2SalarySlipData = {
  period_label: string;
  gross_salary: number;
  tax: number;
  net_salary: number;
  ob_total: number;
  pension_adjustment: number;
  employer_social: number;
  employer_itp1: number;
  employer_friskvard: number;
  total_employer_cost: number;
  net_lines: V2SalarySlipBreakdownRow[];
  employer_lines: V2SalarySlipBreakdownRow[];
  prev_month_net: number | null;
  diff_vs_prev: number | null;
};

export type V2InvoiceRow = {
  label: string;
  qty: number | null;
  unit: string | null;
  unit_price: number | null;
  amount: number;
};

export type V2InvoiceData = {
  kind: string; // el|mobil|bredband|hyra|brf_avgift|bolan|drift_villa|forsakring|lokaltrafik|annan
  invoice_number: string;
  period_start: string | null;
  period_end: string | null;
  rows: V2InvoiceRow[];
  subtotal: number;
  moms: number;
  moms_rate: number;
  total: number;
  ocr: string | null;
  bankgiro: string | null;
  extra: Record<string, unknown>;
};

export type V2MailDetailData = {
  mail: V2MailItem;
  cc_invoice: V2CcInvoiceData | null;
  salary_slip: V2SalarySlipData | null;
  invoice: V2InvoiceData | null;
};

export type V2TeacherMailDetailOverview = {
  student_id: number;
  student_name: string;
  detail: V2MailDetailData;
};

// === /v2/uppdrag (Mina uppdrag · Fas 2P) ===

export type V2UppdragStatus = "not_started" | "in_progress" | "completed";

export type V2UppdragUrgency =
  | "overdue"
  | "today"
  | "tomorrow"
  | "this_week"
  | "later"
  | "none";

export type V2UppdragRow = {
  id: number;
  teacher_id: number;
  title: string;
  description: string;
  kind: string;
  target_year_month: string | null;
  params: Record<string, unknown> | null;
  due_date: string | null;
  created_at: string;
  status: V2UppdragStatus;
  progress: string;
  detail: Record<string, unknown> | null;
  teacher_feedback: string | null;
  teacher_feedback_at: string | null;
  manually_completed_at: string | null;
  days_until_due: number | null;
  urgency: V2UppdragUrgency;
};

export type V2UppdragSummary = {
  active_count: number;
  completed_count: number;
  overdue_count: number;
  nearest_due_date: string | null;
  nearest_due_label: string | null;
  completed_this_month: number;
};

export type V2UppdragData = {
  student_id: number;
  teacher_name: string | null;
  active: V2UppdragRow[];
  completed: V2UppdragRow[];
  summary: V2UppdragSummary;
};

export type V2TeacherUppdragOverview = {
  student_id: number;
  student_name: string;
  uppdrag: V2UppdragData;
};

// === /v2/kompetens (Kompetens-detalj · Fas 2Q) ===

export type V2KompetensLevel = "B" | "G" | "F";

export type V2KompetensTimelineEvent = {
  occurred_at: string;
  event_type:
    | "step_completed"
    | "level_reached"
    | "module_completed"
    | "assigned";
  title: string;
  detail: string | null;
  badge: string | null;
  module_id: number | null;
  step_id: number | null;
};

export type V2KompetensModuleStatus = {
  module_id: number;
  title: string;
  completed: boolean;
  completed_steps: number;
  total_steps: number;
  completed_at: string | null;
};

export type V2KompetensRequirement = {
  label: string;
  description: string | null;
  met: boolean;
  value_label: string;
};

export type V2KompetensDetail = {
  competency_id: number;
  key: string;
  name: string;
  description: string | null;
  is_system: boolean;
  mastery: number;
  level: V2KompetensLevel;
  level_label: string;
  next_level: "G" | "F" | null;
  next_level_label: string | null;
  progress_to_next: number;
  completed_steps: number;
  total_steps: number;
  earned_weight: number;
  total_weight: number;
  last_event_at: string | null;
  timeline: V2KompetensTimelineEvent[];
  connected_modules: V2KompetensModuleStatus[];
  requirements_for_next: V2KompetensRequirement[];
};

export type V2TeacherKompetensOverview = {
  student_id: number;
  student_name: string;
  detail: V2KompetensDetail;
};

// === /v2/teacher/klass-overview (Lärar-hub · Fas 2R) ===

export type V2KlassStat = {
  eye: string;
  num_value: string;
  sub: string;
  accent: boolean;
};

export type V2KlassPentagon = {
  total_score: number;
  economy: number;
  safety: number;
  health: number;
  social: number;
  leisure: number;
  delta_total: number;
};

export type V2KlassNeedsHelpItem = {
  student_id: number;
  student_name: string;
  pent_total: number;
  days_inactive: number | null;
  reason: string;
};

export type V2KlassNegotiationItem = {
  negotiation_id: number;
  student_id: number;
  student_name: string;
  round_no: number;
  max_rounds: number;
  profession: string;
  starting_salary: number;
  last_proposed_salary: number | null;
  status: string;
  started_at: string;
};

export type V2KlassMailboxItem = {
  student_id: number;
  student_name: string;
  unhandled_count: number;
  oldest_days: number | null;
  has_authority: boolean;
};

export type V2KlassReadyForLevel = {
  student_id: number;
  student_name: string;
  weeks_at_level: number;
  progress_pct: number;
  current_level: number;
  target_level: number;
};

export type V2KlassLevelDistribution = {
  level_1_count: number;
  level_2_count: number;
  level_3_count: number;
  ready_for_promotion: V2KlassReadyForLevel[];
};

export type V2KlassMiniPentagon = {
  student_id: number;
  student_name: string;
  pent_total: number;
  economy: number;
  safety: number;
  health: number;
  social: number;
  leisure: number;
  level: number;
  days_since_last_activity: number | null;
};

export type V2KlassOverview = {
  teacher_id: number;
  teacher_name: string;
  school_name: string | null;
  period_label: string;
  total_students: number;
  active_today: number;
  reflections_unread_count: number;
  klass_stats: V2KlassStat[];
  klass_pentagon: V2KlassPentagon;
  students_needing_help: V2KlassNeedsHelpItem[];
  pending_negotiations: V2KlassNegotiationItem[];
  mailbox_top: V2KlassMailboxItem[];
  mailbox_total_unhandled: number;
  level_distribution: V2KlassLevelDistribution;
  mini_pentagons: V2KlassMiniPentagon[];
};

// === /v2/teacher/students/{id}/student-detail (Fas 2S · p-elev) ===

export type V2StudentDetailPentagon = {
  total_score: number;
  economy: number;
  safety: number;
  health: number;
  social: number;
  leisure: number;
  delta_total: number;
  tipped_towards: string;
};

export type V2StudentDetailModule = {
  student_module_id: number;
  module_id: number;
  title: string;
  summary: string | null;
  completed_steps: number;
  total_steps: number;
  progress_pct: number;
  started_at: string | null;
  last_activity_at: string | null;
  next_step_title: string | null;
};

export type V2StudentDetailEvent = {
  occurred_at: string;
  kind: string;
  summary: string;
  badge: string | null;
  detail: string | null;
};

export type V2StudentDetailCompetency = {
  competency_id: number;
  key: string;
  name: string;
  level: "B" | "G" | "F";
  level_label: string;
  mastery: number;
};

export type V2StudentDetailLevelProgression = {
  current_level: number;
  target_level: number | null;
  weeks_at_level: number;
  progress_pct: number;
  requirements_met: number;
  requirements_total: number;
  ready_for_promotion: boolean;
  blockers: string[];
};

export type V2StudentDetailAssignmentSummary = {
  active_count: number;
  overdue_count: number;
  completed_this_month: number;
};

// === /v2/notifications (Fas 2AB · live-notiser) ===

export type V2NotifKind =
  | "teacher" | "uppdrag" | "echo" | "modul"
  | "bank" | "social" | "system";

export type V2Notification = {
  id: string;
  kind: V2NotifKind;
  icon: string;
  occurred_at: string;
  time_label: string;
  title: string;
  body: string;
  unread: boolean;
  target_route: string | null;
};

export type V2NotificationsSummary = {
  total_count: number;
  unread_count: number;
  new_today_count: number;
  by_kind: Record<string, number>;
};

export type V2NotificationsResponse = {
  summary: V2NotificationsSummary;
  items: V2Notification[];
};

// === /v2/pentagon/axis/{axis} (Fas 2Z · flip-card) ===

export type V2PentAxis = "economy" | "safety" | "health" | "social" | "leisure";

export type V2PentAxisFactor = {
  explanation: string;
  points: number;
  delta_label: string;
};

export type V2PentAxisEvent = {
  occurred_at: string | null;
  date_label: string;
  title: string;
  detail: string | null;
  delta: number | null;
  delta_label: string;
};

export type V2PentAxisDetail = {
  axis: V2PentAxis;
  axis_label: string;
  axis_number: string;
  score: number;
  year_month: string;
  factors: V2PentAxisFactor[];
  events: V2PentAxisEvent[];
  summary_text: string;
};

export type V2TeacherPentAxisDetail = {
  student_id: number;
  student_name: string;
  detail: V2PentAxisDetail;
};

export type V2KlassAxisStudentRow = {
  student_id: number;
  student_name: string;
  axis_value: number;
  pent_total: number;
  delta_from_avg: number;
};

export type V2KlassAxisDetail = {
  axis: V2PentAxis;
  axis_label: string;
  axis_number: string;
  klass_avg: number;
  klass_total_avg: number;
  student_count: number;
  distribution: Record<string, number>;
  top_contributors: V2KlassAxisStudentRow[];
  bottom_contributors: V2KlassAxisStudentRow[];
  summary_text: string;
};

// === Lärar-modulbibliotek (Fas 2AN/2AO) ===

export type V2TeacherModuleStepKind =
  | "read" | "watch" | "reflect" | "task" | "quiz";

export type V2TeacherModuleStepOut = {
  id: number;
  module_id: number;
  sort_order: number;
  kind: V2TeacherModuleStepKind;
  title: string;
  content: string | null;
  params: Record<string, unknown> | null;
};

export type V2TeacherModuleOut = {
  id: number;
  teacher_id: number | null;
  title: string;
  summary: string | null;
  is_template: boolean;
  sort_order: number;
  created_at: string;
  step_count: number;
};

export type V2TeacherModuleDetail = V2TeacherModuleOut & {
  steps: V2TeacherModuleStepOut[];
};

// === /v2/teacher/students/{id}/activity-log (Fas 2Y · p-historik) ===

export type V2HistoryEventKind =
  | "onboarding"
  | "module_step"
  | "module_completed"
  | "maria_round"
  | "bankid"
  | "assignment"
  | "transaction"
  | "budget"
  | "loan"
  | "transfer"
  | "import"
  | "competency_raised"
  | "system";

export type V2HistoryEvent = {
  occurred_at: string;
  kind: V2HistoryEventKind;
  title: string;
  detail: string | null;
  badge: string;
  color: string;
  source_id: number | null;
  payload: Record<string, unknown> | null;
};

export type V2HistoryStats = {
  total_events: number;
  onboarding_count: number;
  transactions_count: number;
  module_steps_count: number;
  reflections_count: number;
  bankid_count: number;
  maria_rounds_count: number;
  days_since_signup: number | null;
};

export type V2HistoryResponse = {
  student_id: number;
  student_name: string;
  signup_at: string | null;
  onboarding_completed_at: string | null;
  stats: V2HistoryStats;
  events: V2HistoryEvent[];
};

// === /v2/teacher/students/create (Fas 2X · p-skapa) ===

export type V2CharacterArchetype =
  | "random"
  | "vard_underskoterska"
  | "it_konsult_junior"
  | "butiksbitrade"
  | "kassorska"
  | "lar_vikarie"
  | "anstalld_kommun"
  | "studerande_gymnasium";

export type V2CreateStudentIn = {
  first_name: string;
  last_initial?: string;
  archetype?: V2CharacterArchetype;
  spend_profile?: "sparsam" | "balanserad" | "slosa";
  partner_model?: "solo" | "ai" | "klasskompis";
  starting_level?: number;
  guardian_email?: string;
  family_id?: number | null;
  class_label?: string;  // Bug #1 · klasskoppling
};

export type V2CreatedStudentRow = {
  student_id: number;
  student_name: string;
  login_code: string;
  archetype: V2CharacterArchetype;
  spend_profile: string | null;
  partner_model: string | null;
  starting_level: number;
  guardian_email: string | null;
  created_at: string;
  last_login_at: string | null;
  activated: boolean;
};

export type V2CreatedStudentsResponse = {
  total_count: number;
  pending_activation_count: number;
  rows: V2CreatedStudentRow[];
};

// === /v2/teacher/pedagogics (Fas 2W · p-peda) ===

export type V2PedaConceptBox = {
  key: string;
  kind: "actor" | "tool" | "module";
  title: string;
  concepts: string[];
  student_count: number;
  is_underexposed: boolean;
  is_critical: boolean;
  note: string | null;
};

export type V2PedaCompetencyDist = {
  competency_id: number;
  key: string;
  name: string;
  basis_count: number;
  grund_count: number;
  fordjup_count: number;
  is_concerning: boolean;
};

export type V2PedaSuggestion = {
  title: string;
  body: string;
  cta_label: string;
  cta_target: string | null;
};

export type V2PedagogicsSummary = {
  total_concepts: number;
  total_boxes: number;
  most_seen_count: number;
  rarely_seen_count: number;
  underexposed_boxes: number;
};

export type V2PedagogicsResponse = {
  summary: V2PedagogicsSummary;
  concept_boxes: V2PedaConceptBox[];
  competency_distribution: V2PedaCompetencyDist[];
  suggestions: V2PedaSuggestion[];
};

// === /v2/teacher/maria-list (Fas 2V · p-maria) ===

export type V2MariaRoundCompact = {
  round_no: number;
  student_message: string;
  employer_response: string;
  proposed_pct: number | null;
  proposed_salary: number | null;
  created_at: string;
};

export type V2MariaListItem = {
  negotiation_id: number;
  student_id: number;
  student_name: string;
  profession: string;
  employer: string;
  starting_salary: number;
  status: string;
  started_at: string;
  completed_at: string | null;
  final_salary: number | null;
  final_pct: number | null;
  current_round_no: number;
  max_rounds: number;
  rounds: V2MariaRoundCompact[];
  near_pain_threshold: boolean;
  avtal_norm_pct: number | null;
};

export type V2MariaListSummary = {
  total_count: number;
  active_count: number;
  completed_count: number;
  abandoned_count: number;
  avg_round_no: number;
  near_pain_count: number;
};

export type V2MariaListResponse = {
  summary: V2MariaListSummary;
  active: V2MariaListItem[];
  completed: V2MariaListItem[];
};

// === /v2/teacher/mailboxes (Fas 2U · p-mail) ===

export type V2MailboxStatus = "klar" | "i_fas" | "släper" | "risk";

export type V2MailboxRow = {
  student_id: number;
  student_name: string;
  spend_profile: string | null;
  total_count_period: number;
  unhandled_count: number;
  oldest_days: number | null;
  reminders_count: number;
  has_authority_unhandled: boolean;
  status: V2MailboxStatus;
};

export type V2MailboxClassSummary = {
  total_students: number;
  total_generated_period: number;
  handled_in_time: number;
  handled_pct: number;
  overdue_count: number;
  reminders_total: number;
  profile_distribution: Record<string, number>;
};

export type V2MailboxResponse = {
  summary: V2MailboxClassSummary;
  rows: V2MailboxRow[];
};

export type V2MailboxBulkInjectIn = {
  sender: string;
  sender_kind?: string;
  sender_short?: string;
  mail_type: "invoice" | "salary_slip" | "authority" | "reminder" | "info";
  subject: string;
  body?: string;
  amount?: number;
  due_date?: string; // YYYY-MM-DD
  target_student_ids?: number[] | null;
};

export type V2MailboxBulkInjectResult = {
  students_targeted: number;
  mails_created: number;
};

// === /v2/teacher/reflections (Fas 2T · p-refl) ===

export type V2ReflectionFilter = "all" | "unread" | "flagged";

export type V2ReflectionItem = {
  progress_id: number;
  student_id: number;
  student_name: string;
  module_id: number;
  module_title: string;
  step_id: number;
  step_title: string;
  step_question: string | null;
  body: string;
  word_count: number;
  completed_at: string | null;
  teacher_feedback: string | null;
  feedback_at: string | null;
  flagged_for_help: boolean;
  rubric_label: string | null;
};

export type V2ReflectionsSummary = {
  total_count: number;
  unread_count: number;
  flagged_count: number;
  avg_word_count: number;
  last_received_at: string | null;
};

export type V2ReflectionsResponse = {
  summary: V2ReflectionsSummary;
  items: V2ReflectionItem[];
};

export type V2TeacherStudentDetail = {
  student_id: number;
  student_name: string;
  login_code_suffix: string;
  last_login_at: string | null;
  days_since_last_login: number | null;
  onboarding_completed: boolean;
  v2_level: number;
  v2_level_label: string;
  spend_profile: string | null;
  fairness_choice: string | null;
  partner_model: string | null;
  business_mode_enabled?: boolean;
  pentagon: V2StudentDetailPentagon;
  pentagon_explanation: string;
  active_modules: V2StudentDetailModule[];
  completed_modules_count: number;
  recent_events: V2StudentDetailEvent[];
  competencies: V2StudentDetailCompetency[];
  level_progression: V2StudentDetailLevelProgression;
  pending_negotiation: V2KlassNegotiationItem | null;
  assignments: V2StudentDetailAssignmentSummary;
  mailbox_unhandled_count: number;
  mailbox_oldest_days: number | null;
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
  gameTime: () => api<HubGameTime>("/v2/game-time"),
  // === Events / sociala händelser ===
  eventsPending: () =>
    api<{ events: V2EventItem[]; count: number }>("/v2/events/pending"),
  eventsHistory: (limit: number = 30) =>
    api<{ events: V2EventItem[]; count: number }>(
      `/v2/events/history?limit=${limit}`,
    ),
  eventAccept: (id: number, accountId?: number, decisionReason?: string) =>
    api<V2EventAcceptResponse>(`/v2/events/${id}/accept`, {
      method: "POST",
      body: JSON.stringify({
        account_id: accountId,
        decision_reason: decisionReason,
      }),
    }),
  eventDecline: (id: number, decisionReason?: string) =>
    api<V2EventDeclineResponse>(`/v2/events/${id}/decline`, {
      method: "POST",
      body: JSON.stringify({ decision_reason: decisionReason }),
    }),
  eventClassmates: () =>
    api<{ classmates: V2ClassmateItem[]; invites_enabled: boolean }>(
      "/v2/events/classmates",
    ),
  eventInviteClassmates: (
    eventId: number,
    classmateIds: number[],
    message?: string,
  ) =>
    api<{ created: number; invite_ids: number[] }>(
      "/v2/events/invite-classmates",
      {
        method: "POST",
        body: JSON.stringify({
          event_id: eventId,
          classmate_ids: classmateIds,
          message,
        }),
      },
    ),
  eventInvitations: () =>
    api<{ invitations: V2InviteItem[]; count: number }>(
      "/v2/events/invitations",
    ),
  eventInviteRespond: (
    inviteId: number,
    accept: boolean,
    decisionReason?: string,
  ) =>
    api<{ status: string; resulting_event_id: number | null }>(
      "/v2/events/invitations/respond",
      {
        method: "POST",
        body: JSON.stringify({
          invite_id: inviteId,
          accept,
          decision_reason: decisionReason,
        }),
      },
    ),
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
  /** Sätt alla kategoriers planerade belopp till Konsumentverket. */
  resetBudgetToKonsumentverket: (month?: string) =>
    api<{
      month: string;
      rows_updated: number;
      rows_created: number;
      categories_with_reference: number;
    }>(
      `/v2/budget/reset-to-konsumentverket${month ? `?month=${month}` : ""}`,
      { method: "POST", body: "{}" },
    ),
  goals: () => api<GoalsData>("/v2/mal"),
  goalCreate: (body: {
    name: string;
    target_amount: number;
    target_date?: string;
    account_id?: number;
    initial_amount?: number;
  }) =>
    api<{
      id: number;
      name: string;
      target_amount: number;
      current_amount: number;
      target_date: string | null;
      account_id: number | null;
    }>("/v2/mal", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  goalUpdate: (
    goalId: number,
    body: {
      name?: string;
      target_amount?: number;
      target_date?: string;
      current_amount?: number;
      account_id?: number;
    },
  ) =>
    api<unknown>(`/v2/mal/${goalId}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),
  goalDelete: (goalId: number) =>
    api<void>(`/v2/mal/${goalId}`, { method: "DELETE" }),
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
  /** Hämta elevens personliga frisktandvård-offert (SKV-4). */
  frisktandvardOffer: () =>
    api<{
      tier: number;
      age_category: "atb" | "normal";
      premium_monthly: number;
      explanation: string;
      tier_prices_atb: Record<number, number>;
      tier_prices_normal: Record<number, number>;
      already_active: boolean;
    }>("/v2/forsakringar/frisktandvard-offert"),
  /** Retry-betalning för en failed-mail (SKV-5). */
  retryPayment: (mailId: number) =>
    api<{
      status: "paid" | "rescheduled" | "still_insufficient";
      message: string;
      new_expected_date?: string;
      shortfall_kr?: number;
    }>(`/v2/postladan/${mailId}/retry-payment`, {
      method: "POST",
      body: "{}",
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
  // === /v2/hyresvarden (Fas 2F) ===
  hyresvarden: () => api<V2RentalData>("/v2/hyresvarden"),
  rentalCreateContract: (body: {
    landlord: string;
    address: string;
    rooms_label: string;
    area_sqm: number;
    city?: string;
    district?: string;
    contract_type?: V2RentalContractType;
    duration_type?: V2RentalDurationType;
    monthly_rent: number;
    deposit?: number;
    ocr_reference?: string;
    autogiro?: boolean;
    notice_period_months?: number;
    started_on?: string;
    queue_years?: number;
    queue_priority?: string;
    market_price_per_sqm?: number;
    notes?: string;
  }) =>
    api<V2RentalContractOut>("/v2/hyresvarden/contracts", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  rentalPatchContract: (
    contractId: number,
    body: {
      monthly_rent?: number;
      autogiro?: boolean;
      status?: V2RentalContractStatus;
      ended_on?: string;
      notes?: string;
    },
  ) =>
    api<V2RentalContractOut>(
      `/v2/hyresvarden/contracts/${contractId}`,
      { method: "PATCH", body: JSON.stringify(body) },
    ),
  rentalDeleteContract: (contractId: number) =>
    api<void>(`/v2/hyresvarden/contracts/${contractId}`, {
      method: "DELETE",
    }),
  /** Lärar-API · seedа Stockholmshem-kontrakt + 4 notiser. */
  teacherSeedDefaultRental: (studentId: number) =>
    api<{
      student_id: number;
      contracts_created: number;
      notices_created: number;
    }>(`/v2/teacher/students/${studentId}/rental/seed-default`, {
      method: "POST",
      body: "{}",
    }),
  teacherCreateRentalNotice: (
    studentId: number,
    body: {
      contract_id?: number;
      occurred_on: string;
      notice_type: V2RentalNoticeType;
      title: string;
      description?: string;
      amount?: number;
      change_pct?: number;
      status?: V2RentalNoticeStatus;
      notes?: string;
    },
  ) =>
    api<V2RentalNoticeOut>(
      `/v2/teacher/students/${studentId}/rental/notices`,
      { method: "POST", body: JSON.stringify(body) },
    ),
  teacherDeleteRentalNotice: (studentId: number, noticeId: number) =>
    api<void>(
      `/v2/teacher/students/${studentId}/rental/notices/${noticeId}`,
      { method: "DELETE" },
    ),
  teacherRentalOverview: (studentId: number) =>
    api<V2TeacherRentalOverview>(
      `/v2/teacher/students/${studentId}/rental-overview`,
    ),
  // === /v2/pension (Fas 2G) ===
  pension: () => api<V2PensionData>("/v2/pension"),
  pensionPatchAssumptions: (body: {
    retire_age?: number;
    real_return_pct?: number;
    custom_isk_monthly?: number;
    itp1_low_pct?: number;
    itp1_high_pct?: number;
    notes?: string;
  }) =>
    api<V2PensionAssumptions>("/v2/pension/assumptions", {
      method: "PATCH",
      body: JSON.stringify(body),
    }),
  teacherSeedDefaultPension: (studentId: number) =>
    api<{ student_id: number; created: number }>(
      `/v2/teacher/students/${studentId}/pension/seed-default`,
      { method: "POST", body: "{}" },
    ),
  teacherPatchPensionAssumptions: (
    studentId: number,
    body: {
      retire_age?: number;
      real_return_pct?: number;
      custom_isk_monthly?: number;
      itp1_low_pct?: number;
      itp1_high_pct?: number;
      notes?: string;
    },
  ) =>
    api<V2PensionAssumptions>(
      `/v2/teacher/students/${studentId}/pension/assumptions`,
      { method: "PATCH", body: JSON.stringify(body) },
    ),
  teacherPensionOverview: (studentId: number) =>
    api<V2TeacherPensionOverview>(
      `/v2/teacher/students/${studentId}/pension-overview`,
    ),
  // === /v2/avanza (Fas 2G — Aktör 05) ===
  avanza: () => api<V2AvanzaData>("/v2/avanza"),
  teacherAvanzaOverview: (studentId: number) =>
    api<V2TeacherAvanzaOverview>(
      `/v2/teacher/students/${studentId}/avanza-overview`,
    ),
  // === /v2/boendemarknad (Sprint 5 · B1-B5 + Sprint 5b · ActiveHome) ===
  boendemarknadListings: (ym: string, n = 6, onlyHouseholdFit = true) =>
    api<V2BoendemarknadListings>(
      `/v2/boendemarknad/listings?ym=${encodeURIComponent(ym)}&n=${n}` +
        `&only_household_fit=${onlyHouseholdFit}`,
    ),
  boendemarknadValuation: (ym: string) =>
    api<V2BoendemarknadValuation>(
      `/v2/boendemarknad/my-home/valuation?ym=${encodeURIComponent(ym)}`,
    ),
  boendemarknadMyHome: (ym: string) =>
    api<V2BoendemarknadActiveHome | null>(
      `/v2/boendemarknad/my-home?ym=${encodeURIComponent(ym)}`,
    ),
  boendemarknadBuy: (
    listingId: string, body: { year_month: string; listing_id: string },
  ) =>
    api<V2BoendemarknadBuyResult>(
      `/v2/boendemarknad/buy/${encodeURIComponent(listingId)}`,
      { method: "POST", body: JSON.stringify(body) },
    ),
  boendemarknadSell: (body: { year_month: string }) =>
    api<V2BoendemarknadSellResult>(
      "/v2/boendemarknad/sell",
      { method: "POST", body: JSON.stringify(body) },
    ),
  boendemarknadListRentals: (
    ym: string,
    minTier?: number,
    maxTier?: number,
  ) =>
    api<{
      city_key: string;
      city_display: string;
      year_month: string;
      listings: Array<{
        listing_id: string;
        city_key: string;
        city_display: string;
        tier: number;
        tier_label: string;
        address: string;
        size_kvm: number;
        rooms: number;
        monthly_rent: number;
        deposit: number;
        first_hand: boolean;
        queue_months: number;
        quality_score: number;
        description: string;
      }>;
    }>(
      `/v2/boendemarknad/rentals?ym=${encodeURIComponent(ym)}`
      + (minTier ? `&min_tier=${minTier}` : "")
      + (maxTier ? `&max_tier=${maxTier}` : ""),
    ),
  boendemarknadRentalMoveIn: (listingId: string, ym: string) =>
    api<{
      home: {
        id: number;
        home_type: string;
        status: string;
        city_key: string;
        address: string | null;
        size_kvm: number;
        rooms: number;
        monthly_cost: number;
      };
      pentagon_deltas: Record<string, number>;
      deposit_charged: number;
      welcome_message: string;
    }>(
      `/v2/boendemarknad/rentals/${encodeURIComponent(listingId)}/move-in?ym=${encodeURIComponent(ym)}`,
      { method: "POST", body: "{}" },
    ),
  boendemarknadTerminate: (body: { year_month: string }) =>
    api<V2BoendemarknadTerminateResult>(
      "/v2/boendemarknad/terminate-rental",
      { method: "POST", body: JSON.stringify(body) },
    ),
  boendemarknadMoveRental: (body: {
    year_month: string;
    listing_id: string;
    listing_size_kvm: number;
    listing_address: string;
    listing_monthly_cost: number;
  }) =>
    api<V2BoendemarknadActiveHome>(
      "/v2/boendemarknad/move-rental",
      { method: "POST", body: JSON.stringify(body) },
    ),
  teacherBoendemarknadListings: (city: string, ym: string, n = 6) =>
    api<V2BoendemarknadListings>(
      `/v2/teacher/boendemarknad/listings?city=${encodeURIComponent(city)}&ym=${encodeURIComponent(ym)}&n=${n}`,
    ),
  teacherBoendemarknadPrices: (ym: string) =>
    api<V2BoendemarknadCityPrice[]>(
      `/v2/teacher/boendemarknad/market-prices?ym=${encodeURIComponent(ym)}`,
    ),

  // === /v2/arbetsformedlingen (Sprint 6 · A1-A5) ===
  arbetsformedlingenJobs: (ym: string, n = 6) =>
    api<V2ArbetsformedlingenJobsResponse>(
      // Tom ym → backend default = innevarande spel-månad
      ym
        ? `/v2/arbetsformedlingen/jobs?ym=${encodeURIComponent(ym)}&n=${n}`
        : `/v2/arbetsformedlingen/jobs?n=${n}`,
    ),
  arbetsformedlingenApply: (opening: V2ArbetsformedlingenJob) =>
    api<V2ArbetsformedlingenApplication>(
      "/v2/arbetsformedlingen/apply",
      { method: "POST", body: JSON.stringify(opening) },
    ),
  arbetsformedlingenApplications: () =>
    api<V2ArbetsformedlingenApplication[]>("/v2/arbetsformedlingen/applications"),
  arbetsformedlingenSubmitRound: (appId: number, payload: Record<string, unknown>) =>
    api<V2ArbetsformedlingenRoundOut>(
      `/v2/arbetsformedlingen/applications/${appId}/round`,
      { method: "POST", body: JSON.stringify({ payload }) },
    ),
  arbetsformedlingenAccept: (appId: number) =>
    api<V2ArbetsformedlingenApplication>(
      `/v2/arbetsformedlingen/applications/${appId}/accept`,
      { method: "POST" },
    ),
  arbetsformedlingenDecline: (appId: number) =>
    api<V2ArbetsformedlingenApplication>(
      `/v2/arbetsformedlingen/applications/${appId}/decline`,
      { method: "POST" },
    ),
  arbetsformedlingenAbandon: (appId: number) =>
    api<V2ArbetsformedlingenApplication>(
      `/v2/arbetsformedlingen/applications/${appId}/abandon`,
      { method: "POST" },
    ),
  /** AI-feedback på personligt brev INNAN submit. Hjälper eleven
   *  iterera utan att förbruka rond 1-tillfället. */
  arbetsformedlingenCoverLetterPreview: (
    body: V2CoverLetterPreviewIn,
  ) =>
    api<V2CoverLetterPreviewOut>(
      "/v2/arbetsformedlingen/cover-letter-preview",
      {
        method: "POST",
        body: JSON.stringify(body),
      },
    ),
  teacherAFApplications: (studentId: number) =>
    api<V2ArbetsformedlingenApplication[]>(
      `/v2/teacher/arbetsformedlingen/applications/${studentId}`,
    ),
  teacherAFOverview: (studentId: number) =>
    api<V2TeacherAFOverview>(
      `/v2/teacher/arbetsformedlingen/overview/${studentId}`,
    ),

  // === /v2/bokforing (Fas 2H — Verktyg 02) ===
  bokforing: (period?: string) =>
    api<V2BookkeepingData>(
      `/v2/bokforing${period ? `?period=${encodeURIComponent(period)}` : ""}`,
    ),
  bookkeepingClassify: (txId: number, body: {
    category_id?: number;
    notes?: string;
  }) =>
    api<V2BookkeepingTxRow>(`/v2/bokforing/transactions/${txId}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),
  bookkeepingBulkClassify: (body: {
    transaction_ids?: number[];
    period?: string;
  }) =>
    api<V2BulkClassifyResult>("/v2/bokforing/classify-bulk", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  teacherBookkeepingOverview: (studentId: number, period?: string) =>
    api<V2TeacherBookkeepingOverview>(
      `/v2/teacher/students/${studentId}/bokforing-overview${period ? `?period=${encodeURIComponent(period)}` : ""}`,
    ),
  // === /v2/moduler (Fas 2I — Skola 09) ===
  moduler: () => api<V2ModulerData>("/v2/moduler"),
  teacherModulerOverview: (studentId: number) =>
    api<V2TeacherModulerOverview>(
      `/v2/teacher/students/${studentId}/moduler-overview`,
    ),
  // === /v2/simulator (Fas 2J — Verktyg 05 + 06) ===
  simulateInvestment: (body: {
    start_amount: number;
    monthly_save: number;
    return_pct: number;
    years: number;
    schablonskatt_pct?: number;
    is_isk?: boolean;
    save_as_scenario?: boolean;
    scenario_name?: string;
    compare?: Record<string, unknown>;
  }) =>
    api<V2InvestSimResult>("/v2/simulator/investment", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  simulateLoan: (body: {
    principal: number;
    interest_rate_pct: number;
    term_months: number;
    extra_amortization_monthly?: number;
    amortization_type?: "annuity" | "straight";
    save_as_scenario?: boolean;
    scenario_name?: string;
  }) =>
    api<V2LoanSimResult>("/v2/simulator/loan", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  simulatorScenarios: (kind?: "invest" | "loan") =>
    api<V2SimulatorScenarioRow[]>(
      `/v2/simulator/scenarios${kind ? `?kind=${kind}` : ""}`,
    ),
  simulatorDeleteScenario: (id: number) =>
    api<void>(`/v2/simulator/scenarios/${id}`, {
      method: "DELETE",
    }),
  teacherSimulatorOverview: (studentId: number) =>
    api<V2TeacherSimulatorOverview>(
      `/v2/teacher/students/${studentId}/simulator-overview`,
    ),
  // === /v2/feedback (Fas 2K — Skola · Lärar-feedback) ===
  feedback: (period_days = 90) =>
    api<V2FeedbackData>(`/v2/feedback?period_days=${period_days}`),
  feedbackMarkRead: (
    items: { kind: V2FeedbackKind; source_id: number }[],
  ) =>
    api<{ marked: number; already_read: number }>(
      "/v2/feedback/mark-read",
      { method: "POST", body: JSON.stringify({ items }) },
    ),
  teacherFeedbackOverview: (studentId: number, period_days = 90) =>
    api<V2TeacherFeedbackOverview>(
      `/v2/teacher/students/${studentId}/feedback-overview?period_days=${period_days}`,
    ),
  // === Köp fond på Avanza/ISK ===
  fundBuy: (body: {
    account_id: number;
    fund_name: string;
    amount: number;
  }) =>
    api<{
      fund_holding_id: number;
      fund_name: string;
      new_market_value: number;
      cash_remaining: number;
    }>("/v2/avanza/fund-buy", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  // === Extra-amortering på lån ===
  loanExtraAmortering: (
    loanId: number,
    body: { amount: number; debit_account_id: number },
  ) =>
    api<{
      loan_id: number;
      transaction_id: number;
      payment_id: number;
      amount: number;
      new_principal_estimate: number;
    }>(`/v2/lan/${loanId}/extra-amortering`, {
      method: "POST",
      body: JSON.stringify(body),
    }),

  // === Arbetsplats-frågor (workplace questions från arbetsgivaren) ===
  employerNextQuestion: () =>
    api<{
      id: number;
      code: string;
      scenario_md: string;
      options: Array<{ index: number; text: string }>;
      difficulty: number;
      tags: string[] | null;
    } | null>("/employer/questions/next"),
  employerAnswerQuestion: (questionId: number, chosenIndex: number) =>
    api<{
      delta_applied: number;
      chosen_explanation: string;
      correct_path_md: string;
      new_score: number;
      new_trend: string;
    }>("/employer/questions/answer", {
      method: "POST",
      body: JSON.stringify({
        question_id: questionId,
        chosen_index: chosenIndex,
      }),
    }),

  // === /v2/maria (Maria-AI lönesamtal) ===
  maria: () => api<V2MariaData>("/v2/maria"),
  mariaStart: () =>
    api<{
      negotiation: {
        id: number;
        profession: string;
        employer: string;
        starting_salary: number;
        status: string;
        avtal_norm_pct: number | null;
        avtal_code: string | null;
        rounds: Array<{
          round_no: number;
          student_message: string;
          employer_response: string;
          proposed_pct: number | null;
          tone_score: number | null;
          tone_reason: string | null;
        }>;
        max_rounds: number;
        final_pct: number | null;
        final_salary: number | null;
        teacher_summary_md: string | null;
        completed_at: string | null;
      };
      briefing_md: string;
      opening_message: string | null;
    }>("/employer/negotiation/start", {
      method: "POST",
      body: "{}",
    }),
  mariaSendMessage: (negotiationId: number, message: string) =>
    api<{
      round_no: number;
      employer_response: string;
      proposed_pct: number | null;
      is_final_round: boolean;
      negotiation_status: string;
      tone_score: number | null;
      tone_reason: string | null;
    }>(`/employer/negotiation/${negotiationId}/message`, {
      method: "POST",
      body: JSON.stringify({ message }),
    }),
  mariaAcceptPreview: (negotiationId: number) =>
    api<{
      final_pct: number | null;
      avtal_norm_pct: number | null;
      starting_salary: number;
      new_salary_if_accepted: number | null;
      salary_delta_per_month: number | null;
      salary_delta_per_year: number | null;
      accept_ekonomi_delta: number;
      accept_social_delta: number;
      accept_safety_delta: number;
      abandon_social_delta: number;
      abandon_safety_delta: number;
      accept_employer_sat_delta: number;
      abandon_employer_sat_delta: number;
      tone_history_total: number;
      warning_md: string | null;
    }>(`/employer/negotiation/${negotiationId}/accept-preview`),
  mariaComplete: (negotiationId: number, accept_offer: boolean) =>
    api<{
      final_pct: number | null;
      final_salary: number | null;
      avtal_norm_pct: number | null;
      pending_effective_from: string | null;
      summary_md: string;
      grade: number;
      grade_label: string;
      grade_strengths: string[];
      grade_improvements: string[];
      pentagon_deltas: Record<string, number>;
      maria_memory_polarity: string;
      maria_memory_md: string | null;
      tone_total: number;
      salary_delta_per_month: number | null;
      salary_delta_per_year: number | null;
    }>(`/employer/negotiation/${negotiationId}/complete`, {
      method: "POST",
      body: JSON.stringify({ accept_offer }),
    }),
  teacherMariaOverview: (studentId: number) =>
    api<V2TeacherMariaOverview>(
      `/v2/teacher/students/${studentId}/maria-overview`,
    ),
  // === /v2/bankid (BankID-simulator) ===
  bankidList: () => api<V2BankIDListData>("/v2/bankid/sessions"),
  bankidGet: (id: number) =>
    api<V2BankIDSessionOut>(`/v2/bankid/sessions/${id}`),
  bankidStart: (upcoming_ids: number[]) =>
    api<V2BankIDSessionOut>("/v2/bankid/sessions", {
      method: "POST",
      body: JSON.stringify({ upcoming_ids }),
    }),
  bankidSign: (id: number, opts: { duration_seconds?: number; pin: string }) =>
    api<V2BankIDSessionOut>(`/v2/bankid/sessions/${id}/sign`, {
      method: "POST",
      body: JSON.stringify(opts),
    }),
  bankidPinStatus: () =>
    api<{ has_pin: boolean }>("/v2/bankid/pin-status"),
  bankidSetPin: (pin: string) =>
    api<{ ok: boolean }>("/v2/bankid/set-pin", {
      method: "POST",
      body: JSON.stringify({ pin }),
    }),
  // Mobil-confirm-flöde · token från QR (no auth)
  // sid är optional men gör att backend slipper loopa alla scopes —
  // utan den tar request:en flera sekunder på instanser med många elever.
  bankidConfirmInfo: (token: string, sid?: number) => {
    const q = sid != null ? `?sid=${sid}` : "";
    return api<{
      session_id: number;
      invoice_count: number;
      total_amount: number;
      status: "pending" | "signed" | "cancelled";
      invoices: Array<{
        upcoming_id: number;
        name: string;
        amount: number;
        due_date: string;
        is_recurring: boolean;
        is_anomaly: boolean;
      }>;
      has_pin: boolean;
    }>(`/v2/bankid/confirm-info/${encodeURIComponent(token)}${q}`);
  },
  bankidConfirmSign: (token: string, pin: string, sid?: number) => {
    const q = sid != null ? `?sid=${sid}` : "";
    return api<{
      session_id: number;
      status: "pending" | "signed" | "cancelled";
      invoice_count: number;
      total_amount: number;
      has_pin: boolean;
    }>(`/v2/bankid/confirm-info/${encodeURIComponent(token)}${q}`, {
      method: "POST",
      body: JSON.stringify({ pin }),
    });
  },
  bankidCancel: (id: number) =>
    api<V2BankIDSessionOut>(`/v2/bankid/sessions/${id}/cancel`, {
      method: "POST",
      body: "{}",
    }),
  // Eleven flyttar pengar mellan egna konton
  bankenTransfer: (body: {
    from_account_id: number;
    to_account_id: number;
    amount: number;
    description?: string;
    transfer_date?: string;
  }) =>
    api<{
      source_tx_id: number;
      destination_tx_id: number;
      amount: number;
      transfer_date: string;
    }>("/v2/banken/transfer", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  // Eleven exporterar en faktura från postlådan till banken
  postladanExport: (
    mailId: number,
    body: {
      debit_account_id?: number;
      expected_date?: string;
      autogiro?: boolean;
    },
  ) =>
    api<{
      mail_id: number;
      upcoming_id: number;
      expected_date: string;
      amount: number;
    }>(`/v2/postladan/${mailId}/export-to-bank`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  // Ändra förfallodatum på en kommande dragning
  upcomingUpdate: (
    upcomingId: number,
    body: { expected_date?: string; debit_account_id?: number },
  ) =>
    api<{
      id: number;
      expected_date: string;
      debit_account_id: number | null;
      autogiro: boolean;
      is_paid: boolean;
    }>(`/v2/upcoming/${upcomingId}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),
  teacherBankIDOverview: (studentId: number) =>
    api<V2TeacherBankIDOverview>(
      `/v2/teacher/students/${studentId}/bankid-overview`,
    ),
  // === /v2/tx (transaktion-detalj) ===
  txDetail: (txId: number) => api<V2TxDetailData>(`/v2/tx/${txId}`),
  txClassify: (txId: number, body: {
    category_id?: number;
    subcategory_id?: number;
    account_id?: number;
    notes?: string;
  }) =>
    api<V2TxDetailData>(`/v2/tx/${txId}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),
  txCreateRule: (txId: number, body: {
    category_id: number;
    pattern?: string;
    apply_to_existing?: boolean;
  }) =>
    api<V2TxCreateRuleResult>(`/v2/tx/${txId}/create-rule`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  // === /v2/messages (lärar-chat) ===
  messages: () => api<V2MessagesData>("/v2/messages"),
  messagesSend: (body: string, context_type?: string, context_id?: number) =>
    api<V2MessageRow>("/v2/messages", {
      method: "POST",
      body: JSON.stringify({ body, context_type, context_id }),
    }),
  messagesMarkRead: (messageId: number) =>
    api<void>(`/v2/messages/${messageId}/mark-read`, {
      method: "POST",
      body: "{}",
    }),
  teacherMessagesOverview: (studentId: number) =>
    api<V2TeacherMessagesOverview>(
      `/v2/teacher/students/${studentId}/messages-overview`,
    ),
  teacherSendMessage: (
    studentId: number,
    body: string,
    context_type?: string,
    context_id?: number,
  ) =>
    api<V2MessageRow>(
      `/v2/teacher/students/${studentId}/messages`,
      {
        method: "POST",
        body: JSON.stringify({ body, context_type, context_id }),
      },
    ),
  // === /v2/portfolio (kompetens) ===
  portfolio: () => api<V2PortfolioData>("/v2/portfolio"),
  teacherPortfolioOverview: (studentId: number) =>
    api<V2TeacherPortfolioOverview>(
      `/v2/teacher/students/${studentId}/portfolio-overview`,
    ),
  // === /v2/postladan/{id}/detail (Fas 2N · CC + Lönespec drill-down) ===
  mailDetail: (mailId: number) =>
    api<V2MailDetailData>(`/v2/postladan/${mailId}/detail`),
  /** Hämtar fakturan som PDF (riktig reportlab-rendering). */
  mailPdf: async (mailId: number): Promise<Blob> => {
    const { getToken, getAsStudent } = await import("@/api/client");
    const { default: clientMod } = await import("@/api/client") as any;
    void clientMod;
    // Använd raw fetch — api()-helpern returnerar JSON, vi behöver blob
    const headers: Record<string, string> = {};
    const token = getToken();
    if (token) headers["Authorization"] = `Bearer ${token}`;
    const asStudent = getAsStudent();
    if (asStudent) headers["X-As-Student"] = String(asStudent);
    // apiBase: samma logik som api-helpern · läs från env eller window
    let base = (import.meta.env.VITE_API_BASE as string | undefined) || "";
    if (base === "/" || base.toUpperCase?.() === "SAME_ORIGIN") base = "";
    if (base && !/^https?:\/\//i.test(base)) base = `https://${base}`;
    if (!base) {
      // Lokal-dev: använd current host + port 8765 om inte SAME_ORIGIN
      const port = localStorage.getItem("hembudget_port") || "8765";
      const host = window.location.hostname;
      base = window.location.protocol === "https:"
        ? `https://${host}`
        : `http://${host}:${port}`;
    }
    const res = await fetch(
      `${base}/v2/postladan/${mailId}/pdf`, { headers },
    );
    if (!res.ok) {
      throw new Error(`PDF-rendering misslyckades (${res.status})`);
    }
    return await res.blob();
  },
  teacherMailDetail: (studentId: number, mailId: number) =>
    api<V2TeacherMailDetailOverview>(
      `/v2/teacher/students/${studentId}/mail/${mailId}/detail`,
    ),
  // === /v2/uppdrag (Mina uppdrag · Fas 2P) ===
  uppdrag: () => api<V2UppdragData>("/v2/uppdrag"),
  uppdragSelfComplete: (assignmentId: number) =>
    api<{
      ok: boolean;
      assignment_id: number;
      manually_completed_at: string;
    }>(`/v2/uppdrag/${assignmentId}/self-complete`, {
      method: "POST",
      body: "{}",
    }),
  teacherUppdragOverview: (studentId: number) =>
    api<V2TeacherUppdragOverview>(
      `/v2/teacher/students/${studentId}/uppdrag-overview`,
    ),
  // === /v2/kompetens (Kompetens-detalj · Fas 2Q) ===
  kompetensDetail: (competencyId: number) =>
    api<V2KompetensDetail>(`/v2/kompetens/${competencyId}`),
  teacherKompetensOverview: (studentId: number, competencyId: number) =>
    api<V2TeacherKompetensOverview>(
      `/v2/teacher/students/${studentId}/kompetens/${competencyId}`,
    ),
  // === /v2/teacher/klass-overview (Lärar-hub · Fas 2R) ===
  teacherKlassOverview: (classLabel?: string) =>
    api<V2KlassOverview>(
      classLabel
        ? `/v2/teacher/klass-overview?class_label=${encodeURIComponent(classLabel)}`
        : "/v2/teacher/klass-overview",
    ),
  // === /v2/teacher/students/{id}/student-detail (Fas 2S) ===
  teacherStudentDetail: (studentId: number) =>
    api<V2TeacherStudentDetail>(
      `/v2/teacher/students/${studentId}/student-detail`,
    ),
  // === /v2/teacher/reflections (Fas 2T) ===
  teacherReflections: (filter: V2ReflectionFilter = "all") =>
    api<V2ReflectionsResponse>(
      `/v2/teacher/reflections?filter=${filter}`,
    ),
  teacherReflectionFeedback: (progressId: number, body: string) =>
    api<V2ReflectionItem>(
      `/v2/teacher/reflections/${progressId}/feedback`,
      { method: "POST", body: JSON.stringify({ body }) },
    ),
  // === /v2/teacher/mailboxes (Fas 2U) ===
  teacherMailboxes: () =>
    api<V2MailboxResponse>("/v2/teacher/mailboxes"),
  teacherMailboxBulkInject: (body: V2MailboxBulkInjectIn) =>
    api<V2MailboxBulkInjectResult>(
      "/v2/teacher/mailboxes/bulk-inject",
      { method: "POST", body: JSON.stringify(body) },
    ),
  // === /v2/teacher/maria-list (Fas 2V) ===
  teacherMariaList: () =>
    api<V2MariaListResponse>("/v2/teacher/maria-list"),
  // === /v2/teacher/pedagogics (Fas 2W) ===
  teacherPedagogics: () =>
    api<V2PedagogicsResponse>("/v2/teacher/pedagogics"),
  // === /v2/teacher/students/create (Fas 2X) ===
  teacherCreateStudent: (body: V2CreateStudentIn) =>
    api<V2CreatedStudentRow>("/v2/teacher/students/create", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  teacherListCreatedStudents: () =>
    api<V2CreatedStudentsResponse>("/v2/teacher/students/created"),
  teacherDeleteStudent: (studentId: number) =>
    api<void>(`/v2/teacher/students/${studentId}`, {
      method: "DELETE",
    }),
  /** Status för pågående/nyligen klara student-raderingar. UI pollar
   * denna under pågående delete för att visa 'Raderar…' / 'Klar' / 'Fel'. */
  teacherDeleteJobs: () =>
    api<{
      rows: Array<{
        student_id: number;
        student_name: string;
        status: "queued" | "running" | "done" | "failed";
        started_at: number;
        finished_at: number | null;
        error: string | null;
      }>;
      pending_count: number;
    }>(`/v2/teacher/delete-jobs`),
  /** Starta bakgrunds-radering av alla mina elever. Returnerar omedelbart. */
  teacherDeleteAllMyStudents: () =>
    api<{ status: string; teacher_id: number }>(
      `/v2/teacher/bulk-delete-all-my-students`,
      { method: "DELETE" },
    ),
  /** Polla status på pågående bulk-delete. */
  teacherBulkDeleteStatus: () =>
    api<{
      status: "idle" | "queued" | "running" | "done" | "failed";
      deleted_count?: number;
      failed_count?: number;
      failed_ids?: number[];
      error?: string;
    }>(`/v2/teacher/bulk-delete-status`),
  // === /v2/teacher/students/{id}/activity-log (Fas 2Y) ===
  teacherStudentHistory: (studentId: number, limit = 100) =>
    api<V2HistoryResponse>(
      `/v2/teacher/students/${studentId}/activity-log?limit=${limit}`,
    ),
  // === /v2/pentagon/axis/{axis} (Fas 2Z · flip-card) ===
  pentagonAxisDetail: (axis: V2PentAxis) =>
    api<V2PentAxisDetail>(`/v2/pentagon/axis/${axis}`),
  teacherPentagonAxisDetail: (studentId: number, axis: V2PentAxis) =>
    api<V2TeacherPentAxisDetail>(
      `/v2/teacher/students/${studentId}/pentagon/axis/${axis}`,
    ),
  // === /v2/notifications (Fas 2AB · live-notiser) ===
  notifications: () =>
    api<V2NotificationsResponse>("/v2/notifications"),
  // === Fas 2AF · skapa uppdrag från lärar-elev-detalj ===
  teacherCreateAssignment: (
    studentId: number,
    body: {
      title: string;
      description: string;
      kind?: string;
      target_year_month?: string | null;
      due_date?: string | null;
      params?: Record<string, unknown> | null;
    },
  ) =>
    api<{
      assignment_id: number;
      student_id: number;
      title: string;
      kind: string;
      due_date: string | null;
      created_at: string;
    }>(`/v2/teacher/students/${studentId}/uppdrag`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  // === Fas 2AG · nivå-promotion + kompetens-override ===
  teacherPromoteStudentLevel: (
    studentId: number,
    body: {
      target_level: number;
      new_spend_profile?: "sparsam" | "balanserad" | "slosa";
      motivation?: string;
    },
  ) =>
    api<{
      student_id: number;
      student_name: string;
      previous_level: number;
      new_level: number;
      new_spend_profile: string | null;
    }>(`/v2/teacher/students/${studentId}/level-promote`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  teacherOverrideCompetency: (
    studentId: number,
    competencyId: number,
    body: { level: "B" | "G" | "F"; motivation: string },
  ) =>
    api<{
      competency_id: number;
      competency_key: string;
      competency_name: string;
      level: "B" | "G" | "F";
      motivation: string;
      updated_at: string;
      teacher_id: number;
    }>(
      `/v2/teacher/students/${studentId}/kompetens/${competencyId}/override`,
      { method: "POST", body: JSON.stringify(body) },
    ),
  teacherDeleteCompetencyOverride: (studentId: number, competencyId: number) =>
    api<{ deleted: boolean }>(
      `/v2/teacher/students/${studentId}/kompetens/${competencyId}/override`,
      { method: "DELETE" },
    ),
  // === Fas 2AH · klass-pentagon axis-detail ===
  teacherKlassPentagonAxis: (axis: V2PentAxis) =>
    api<V2KlassAxisDetail>(`/v2/teacher/klass-pentagon/axis/${axis}`),
  // === Fas 2AJ · QR-kod för elev-login ===
  teacherStudentLoginQr: (studentId: number) =>
    api<{
      student_id: number;
      student_name: string;
      login_code: string;
      login_url: string;
      qr_svg: string;
    }>(`/v2/teacher/students/${studentId}/login-qr`),
  // === Fas 2AP · Bulk-QR för utskrift ===
  teacherLoginQrBulk: () =>
    api<{
      teacher_id: number;
      teacher_name: string;
      items: {
        student_id: number;
        student_name: string;
        login_code: string;
        login_url: string;
        qr_svg: string;
      }[];
    }>("/v2/teacher/students/login-qr-bulk"),
  // === Fas 2AN/2AO · Lärar-modulbibliotek (wrappar v1-endpoints) ===
  teacherListModules: () =>
    api<V2TeacherModuleOut[]>("/teacher/modules"),
  teacherGetModule: (moduleId: number) =>
    api<V2TeacherModuleDetail>(`/teacher/modules/${moduleId}`),
  teacherCreateModule: (body: {
    title: string;
    summary?: string;
    is_template?: boolean;
  }) =>
    api<V2TeacherModuleDetail>("/teacher/modules", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  teacherUpdateModule: (
    moduleId: number,
    body: {
      title: string;
      summary?: string;
      is_template?: boolean;
    },
  ) =>
    api<V2TeacherModuleOut>(`/teacher/modules/${moduleId}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),
  teacherDeleteModule: (moduleId: number) =>
    api<{ ok: boolean }>(`/teacher/modules/${moduleId}`, {
      method: "DELETE",
    }),
  teacherCloneModule: (moduleId: number) =>
    api<V2TeacherModuleOut>(`/teacher/modules/${moduleId}/clone`, {
      method: "POST",
      body: "{}",
    }),
  teacherAssignModule: (moduleId: number, studentIds: number[]) =>
    api<{ assigned: number; auto_assignments: number }>(
      `/teacher/modules/${moduleId}/assign`,
      {
        method: "POST",
        body: JSON.stringify({ student_ids: studentIds }),
      },
    ),
  teacherUnassignModule: (moduleId: number, studentIds: number[]) =>
    api<{ unassigned: number }>(
      `/teacher/modules/${moduleId}/unassign`,
      {
        method: "POST",
        body: JSON.stringify({ student_ids: studentIds }),
      },
    ),
  teacherCreateModuleStep: (
    moduleId: number,
    body: {
      kind: "read" | "watch" | "reflect" | "task" | "quiz";
      title: string;
      content?: string;
      params?: Record<string, unknown> | null;
      sort_order?: number;
    },
  ) =>
    api<V2TeacherModuleStepOut>(
      `/teacher/modules/${moduleId}/steps`,
      { method: "POST", body: JSON.stringify(body) },
    ),
  teacherUpdateModuleStep: (
    moduleId: number,
    stepId: number,
    body: {
      kind: "read" | "watch" | "reflect" | "task" | "quiz";
      title: string;
      content?: string;
      params?: Record<string, unknown> | null;
      sort_order?: number;
    },
  ) =>
    api<V2TeacherModuleStepOut>(
      `/teacher/modules/${moduleId}/steps/${stepId}`,
      { method: "PATCH", body: JSON.stringify(body) },
    ),
  teacherDeleteModuleStep: (moduleId: number, stepId: number) =>
    api<{ ok: boolean }>(
      `/teacher/modules/${moduleId}/steps/${stepId}`,
      { method: "DELETE" },
    ),
  /** AI-skiss · genererar modul-utkast (titel + summary + steg) från en
   *  beskrivning. Kräver att lärarens ai_enabled=true. Lärar-vyn visar
   *  utkastet i en modal innan modul + steg sparas via separata POSTs. */
  teacherAIGenerateModuleDraft: (prompt: string) =>
    api<{
      raw: string;
      parsed: {
        title: string;
        summary: string;
        steps: {
          kind: "read" | "watch" | "reflect" | "task" | "quiz";
          title: string;
          body?: string;
          sort_order?: number;
        }[];
      };
      model: string;
      input_tokens: number;
      output_tokens: number;
    }>("/ai/modules/generate", {
      method: "POST",
      body: JSON.stringify({ prompt }),
    }),
  // Aktiehandel (existerande /stocks-API från gamla dashboarden)
  stocksPortfolio: (accountId?: number) =>
    api<{
      cash_balance: number;
      total_market_value: number;
      total_unrealized_pnl: number;
      positions: Array<{
        ticker: string;
        quantity: number;
        avg_cost: number;
        last_price: number;
        market_value: number;
        unrealized_pnl: number;
        unrealized_pnl_pct: number;
      }>;
    }>(`/stocks/portfolio${accountId ? `?account_id=${accountId}` : ""}`),
  stocksLedger: (limit = 200, ticker?: string) =>
    api<{
      ledger: Array<{
        id: number;
        ticker: string;
        side: string;
        quantity: number;
        price: number;
        courtage: number;
        total_amount: number;
        realized_pnl: number | null;
        executed_at: string;
        student_rationale: string | null;
      }>;
      count: number;
    }>(
      `/stocks/ledger?limit=${limit}${ticker ? `&ticker=${ticker}` : ""}`,
    ),
  iskHistory: (days = 30) => {
    const ts = Date.now();
    return api<{
      days: number;
      points: Array<{ ts: string; total_value: number }>;
    }>(`/v2/avanza/isk-history?days=${days}&_=${ts}`);
  },
  stocksActivity: () => {
    const ts = Date.now();
    return api<{
      recent_trades: Array<{
        id: number;
        ticker: string;
        side: "buy" | "sell";
        quantity: number;
        price: number;
        courtage: number;
        total_amount: number;
        realized_pnl: number | null;
        executed_at: string;
        student_rationale: string | null;
      }>;
      pending_orders: Array<{
        id: number;
        ticker: string;
        side: "buy" | "sell";
        quantity: number;
        reference_price: number;
        status: string;
        requested_at: string;
        student_rationale: string | null;
      }>;
    }>(`/v2/aktier/activity?_=${ts}`);
  },
  stocksMarket: () => {
    // Cache-buster · samma URL utan query-string riskerar att cachas
    // av browser/CDN → 'Kurser uppdaterade 2 h sedan' fastnar trots
    // att backenden har färska kurser. Lägg till monoton timestamp.
    const ts = Date.now();
    return api<{
      stocks: Array<{
        ticker: string;
        name: string;
        sector: string | null;
        currency: string;
        last: number;
        change_pct: number | null;
        bid: number | null;
        ask: number | null;
      }>;
      count: number;
      market_open: boolean;
      last_updated_at: string | null;
    }>(`/v2/aktier/market?_=${ts}`);
  },
  stocksBuy: (ticker: string, body: {
    account_id: number;
    quantity: number;
    student_rationale?: string;
  }) =>
    api<Record<string, unknown>>(`/stocks/${ticker}/buy`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  stocksSell: (ticker: string, body: {
    account_id: number;
    quantity: number;
    student_rationale?: string;
  }) =>
    api<Record<string, unknown>>(`/stocks/${ticker}/sell`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
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
      // SKV-2 · pipeline-info för UI-banner
      status?: string;
      besked_due_on?: string;
      payout_wave?: number;
      payout_due_on?: string;
      late_fee?: number;
      wave_message?: string;
      case_no?: string;
    }>(`/v2/skatten/${year}/submit`, { method: "POST", body: "{}" }),
  /** Skatteverket-fönsterstatus · för låsning/banner i SkattenV2. */
  skattenWindow: () =>
    api<{
      phase: "off_season" | "granska" | "inlamna" | "stangd";
      tax_year: number;
      can_read: boolean;
      submit_open: boolean;
      today_game: string;
      opens_on: string | null;
      closes_on: string | null;
      description: string;
    }>(`/v2/skatten/window`),
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
  /** Huvudbok / Ledger · period kan vara YYYY-MM eller YYYY. */
  huvudbok: (period: string) => {
    const isMonth = period.length === 7 && period.includes("-");
    const qs = isMonth ? `month=${period}` : `year=${period}`;
    return api<LedgerData>(`/v2/ledger/?${qs}`);
  },
  /** Räkna KALP för ett tänkt lånebelopp (sparas i scope-DB). */
  kalp: (loanAmount: number, loanTermMonths: number = 300) =>
    api<V2KALPResponse>("/v2/lan/kalp", {
      method: "POST",
      body: JSON.stringify({
        loan_amount: loanAmount,
        loan_term_months: loanTermMonths,
      }),
    }),
  /** Eleven ansöker om lån. accept_offer=false = bara prövning. */
  loanApply: (req: V2LoanApplyRequest) =>
    api<V2LoanApplyResponse>("/v2/lan/apply", {
      method: "POST",
      body: JSON.stringify(req),
    }),
  /** Lista alla godkända men ej accepterade låneerbjudanden (Fas 2). */
  creditPendingOffers: () =>
    api<{
      offers: Array<{
        application_id: number;
        kind: string;
        requested_amount: number;
        requested_months: number;
        offered_rate: number | null;
        offered_monthly_payment: number | null;
        simulated_lender: string | null;
        score_value: number | null;
        created_at: string;
      }>;
    }>("/credit/pending-offers"),
  /** Acceptera ett pending privatlån direkt från postlådan
   * (auto-default till första checking-konto). */
  creditAcceptFromMail: (applicationId: number) =>
    api<{
      loan_id: number;
      transaction_id: number;
      deposited_amount: number;
      monthly_payment: number;
      interest_rate: number;
      months: number;
      pedagogical_note: string;
    }>("/credit/private/accept-from-mail", {
      method: "POST",
      body: JSON.stringify({ application_id: applicationId }),
    }),
  creditDecline: (applicationId: number) =>
    api<{ ok: boolean; application_id: number; result: string }>(
      "/credit/private/decline",
      {
        method: "POST",
        body: JSON.stringify({ application_id: applicationId }),
      },
    ),
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
  postladan: (
    filter?: V2MailType | "unhandled" | "other",
    month?: string,
  ) => {
    // month · "YYYY-MM" begränsar till en spel-månad, "all" visar hela
    // historiken, undefined = backend defaultar till aktuell spel-månad.
    // Cache-buster `_=ts` förhindrar browser/CDN att cacha samma URL.
    const ts = Date.now();
    const params = new URLSearchParams();
    if (filter) params.set("filter", filter);
    if (month) params.set("month", month);
    params.set("_", String(ts));
    return api<MailData>(`/v2/postladan?${params.toString()}`);
  },
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

  // === Klasskompis-anställning (Fas C-E) ===
  employmentList: () =>
    api<{ employments: EmploymentOut[] }>("/v2/employment/employments"),
  employmentOffers: () =>
    api<{ employments: EmploymentOut[] }>("/v2/employment/offers"),
  employmentHireOffer: (body: {
    classmate_student_id: number;
    role: string;
    monthly_gross: number;
  }) =>
    api<EmploymentOut>("/v2/employment/hire-offer", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  employmentAccept: (employmentId: number) =>
    api<EmploymentOut>(`/v2/employment/offers/${employmentId}/accept`, {
      method: "POST",
      body: JSON.stringify({}),
    }),
  employmentDecline: (employmentId: number, reason?: string) =>
    api<EmploymentOut>(`/v2/employment/offers/${employmentId}/decline`, {
      method: "POST",
      body: JSON.stringify({ reason: reason ?? null }),
    }),
  employmentPayrollRun: (yearMonth?: string) =>
    api<PayrollRunOut>(
      "/v2/employment/payroll/run"
        + (yearMonth ? `?year_month=${yearMonth}` : ""),
      { method: "POST", body: JSON.stringify({}) },
    ),
  employmentTerminate: (employmentId: number, reason: string) =>
    api<EmploymentOut>(
      `/v2/employment/employments/${employmentId}/terminate`,
      { method: "POST", body: JSON.stringify({ reason }) },
    ),
};

export type PayrollRunOut = {
  year_month: string;
  paid_on: string;
  n_paid: number;
  n_skipped: number;
  total_gross: number;
  total_net: number;
  total_employer_fee: number;
  total_cost: number;
  details: Array<{
    employment_id: number;
    status: string;
    gross?: number;
    net?: number;
    employer_fee?: number;
  }>;
};

export type EmploymentOut = {
  id: number;
  company_id: number;
  company_name: string;
  owner_student_id: number;
  employee_student_id: number;
  role: string;
  monthly_gross: number;
  status:
    | "pending_offer"
    | "active"
    | "declined"
    | "terminated";
  offer_sent_on: string;
  accepted_on: string | null;
  last_day: string | null;
  termination_reason: string | null;
};
