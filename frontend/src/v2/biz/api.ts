/**
 * API-klient för /v2/foretag/*-endpoints (Företagsläget · Bug #7-utbyggnad).
 * Använder raw fetch + localStorage-token (samma som övriga v2-vyer).
 */

const TOKEN = () => localStorage.getItem("hb_token") || "";

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
  active: boolean;
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


export const bizApi = {
  getCompany: () => call<Company | null>("/v2/foretag"),
  createCompany: (b: Partial<Company> & { name: string }) =>
    call<Company>("/v2/foretag", { method: "POST", body: JSON.stringify(b) }),
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
};
