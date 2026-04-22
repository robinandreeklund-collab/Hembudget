export interface Account {
  id: number;
  name: string;
  bank: string;
  type: string;
  currency: string;
  account_number?: string | null;
  opening_balance?: number | null;
  opening_balance_date?: string | null;
  credit_limit?: number | null;
  bankgiro?: string | null;
  pays_credit_account_id?: number | null;
}

export interface Category {
  id: number;
  name: string;
  parent_id: number | null;
  budget_monthly: string | null;
  color: string | null;
  icon: string | null;
}

export interface Transaction {
  id: number;
  account_id: number;
  date: string;
  amount: number;
  currency: string;
  raw_description: string;
  normalized_merchant: string | null;
  category_id: number | null;
  tags: string[] | null;
  notes: string | null;
  ai_confidence: number | null;
  user_verified: boolean;
  is_transfer: boolean;
  transfer_pair_id: number | null;
}

export interface MonthSummary {
  month: string;
  income: number;
  expenses: number;
  savings: number;
  savings_rate: number;
  lines: Array<{
    category_id: number;
    category: string;
    planned: number;
    actual: number;
    diff: number;
  }>;
}

export interface ForecastPoint {
  month: string;
  income: number;
  expenses: number;
  net: number;
}

export interface Subscription {
  merchant: string;
  amount: number;
  interval_days: number;
  next_expected_date: string;
  occurrences?: number;
}

export type ScenarioKind = "mortgage" | "savings_goal" | "move";
