import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, ChevronDown, ChevronRight, XCircle } from "lucide-react";
import { Card } from "@/components/Card";
import { api, formatSEK, getToken } from "@/api/client";
import type { Account, Category } from "@/types/models";

function currentMonth(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

// Default: föregående (senast avslutade) månad. Huvudboken blir missvisande
// för pågående månad eftersom import ofta sker i efterhand — användaren vill
// normalt se en KOMPLETT period när de öppnar /reports.
function defaultMonth(): string {
  const d = new Date();
  d.setDate(1);
  d.setMonth(d.getMonth() - 1);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

function isCurrentOrFutureMonth(m: string): boolean {
  return m >= currentMonth();
}

interface LedgerAccount {
  id: number;
  name: string;
  bank: string;
  type: string;
  owner_id: number | null;
  opening_balance: number;
  income: number;
  expenses: number;
  transfer_in: number;
  transfer_out: number;
  closing_balance: number;
  transaction_count: number;
}

interface LedgerCategory {
  category_id: number | null;
  category: string;
  income: number;
  expenses: number;
  net: number;
  count: number;
}

interface LedgerLoan {
  id: number;
  name: string;
  lender: string;
  principal_amount: number;
  current_balance_at_creation: number | null;
  outstanding_balance: number;
  interest_rate: number;
  payments_in_period: number;
}

interface LedgerCheck {
  name: string;
  passed: boolean;
  value: number;
  detail: string;
  check_type?: string | null;
}

interface Ledger {
  period: { label: string; start: string; end: string };
  locked_months?: string[];
  accounts: LedgerAccount[];
  categories: LedgerCategory[];
  loans: LedgerLoan[];
  upcoming_summary: {
    total: number; matched: number; unmatched: number; unmatched_past: number;
    matched_sum: number; unmatched_sum: number;
  };
  checks: LedgerCheck[];
  totals: {
    income: number; expenses: number; net_result: number;
    assets: number; liabilities: number; net_worth: number;
    uncategorized_count: number;
  };
}

export default function Reports() {
  const [month, setMonth] = useState(defaultMonth());
  const [scope, setScope] = useState<"month" | "year">("year");
  const [year, setYear] = useState(new Date().getFullYear());
  const token = getToken();
  const port = localStorage.getItem("hembudget_api_port") || "8765";
  const base = `http://127.0.0.1:${port}`;

  const ledgerQ = useQuery({
    queryKey: ["ledger", scope, scope === "month" ? month : year],
    queryFn: () =>
      api<Ledger>(
        scope === "month"
          ? `/ledger/?month=${month}`
          : `/ledger/?year=${year}`,
      ),
  });

  async function download(path: string, filename: string) {
    const res = await fetch(`${base}${path}`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!res.ok) {
      alert(`Kunde inte hämta rapporten (${res.status})`);
      return;
    }
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
  }

  const ledger = ledgerQ.data;

  return (
    <div className="p-3 md:p-6 space-y-4 md:space-y-4 max-w-5xl">
      <h1 className="serif text-3xl leading-tight">Rapporter</h1>

      <Card
        title="Huvudbok — avstämning av ekonomin"
        action={
          <div className="flex items-center gap-2 text-sm">
            <label>
              <select
                value={scope}
                onChange={(e) => setScope(e.target.value as "month" | "year")}
                className="border rounded px-2 py-1 bg-white"
              >
                <option value="year">Helt år</option>
                <option value="month">Månad</option>
              </select>
            </label>
            {scope === "month" ? (
              <input
                type="month"
                value={month}
                onChange={(e) => setMonth(e.target.value)}
                className="border rounded px-2 py-1"
              />
            ) : (
              <input
                type="number"
                value={year}
                onChange={(e) => setYear(Number(e.target.value))}
                className="border rounded px-2 py-1 w-24"
              />
            )}
          </div>
        }
      >
        <div className="text-sm text-slate-700 mb-3">
          Huvudboken visar ALLA pengar under perioden: opening-saldo per
          konto, alla rörelser, closing-saldo, samt en resultaträkning per
          kategori. Längst ner visas avstämnings-checkar så du snabbt ser
          om något inte balanserar.
        </div>
        {scope === "month" && isCurrentOrFutureMonth(month) && (
          <div className="mb-3 rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-800">
            <strong>Pågående månad.</strong> Du tittar på {month} — data kan
            vara ofullständig eftersom du oftast importerar transaktioner i
            efterhand. Välj föregående månad för ett avstämt resultat.
          </div>
        )}
        {scope === "year" && year >= new Date().getFullYear() && (
          <div className="mb-3 rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-800">
            <strong>Pågående år.</strong> {year} är inte avslutat — siffrorna
            är YTD och kommer förändras allt eftersom fler transaktioner
            importeras.
          </div>
        )}
        <MonthLockBanner
          scope={scope}
          month={month}
          year={year}
          lockedMonths={ledger?.locked_months ?? []}
        />
        <div className="flex gap-2 mb-4 text-sm">
          <button
            className="bg-slate-800 text-white px-3 py-1.5 rounded"
            onClick={() => {
              const q = scope === "month" ? `month=${month}` : `year=${year}`;
              const label = scope === "month" ? month : String(year);
              download(`/ledger/export.pdf?${q}`, `huvudbok-${label}.pdf`);
            }}
          >
            Ladda ner som PDF
          </button>
          <button
            className="bg-slate-600 text-white px-3 py-1.5 rounded"
            onClick={() => {
              const q = scope === "month" ? `month=${month}` : `year=${year}`;
              const label = scope === "month" ? month : String(year);
              download(`/ledger/export.yaml?${q}`, `huvudbok-${label}.yaml`);
            }}
            title="YAML-fil med all rådata — klistra in vid felsökning"
          >
            Ladda ner YAML (rådata)
          </button>
        </div>

        {ledgerQ.isLoading ? (
          <div className="text-sm text-slate-700">Räknar…</div>
        ) : !ledger ? (
          <div className="text-sm text-rose-600">Kunde inte ladda huvudbok</div>
        ) : (
          <div className="space-y-5">
            {/* Översikt-KPIer */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              <Kpi label="Inkomster" value={formatSEK(ledger.totals.income)} tone="good" />
              <Kpi label="Utgifter" value={formatSEK(ledger.totals.expenses)} tone="bad" />
              <Kpi
                label="Netto-resultat"
                value={formatSEK(ledger.totals.net_result)}
                tone={ledger.totals.net_result >= 0 ? "good" : "bad"}
              />
              <Kpi
                label="Nettoförmögenhet"
                value={formatSEK(ledger.totals.net_worth)}
              />
            </div>

            {/* Kontroller */}
            <Section title={`Avstämning (${ledger.checks.filter(c => c.passed).length}/${ledger.checks.length} OK)`}>
              <div className="space-y-1.5">
                {ledger.checks.map((c, i) => (
                  <CheckRow
                    key={i}
                    check={c}
                    scope={scope}
                    month={month}
                    year={year}
                  />
                ))}
              </div>
            </Section>

            {/* Balansrapport */}
            <Section title={`Balansrapport per konto — tillgångar: ${formatSEK(ledger.totals.assets)} · skulder: ${formatSEK(ledger.totals.liabilities)}`}>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-left text-xs uppercase text-slate-700 border-b">
                      <th className="py-1.5 pr-3">Konto</th>
                      <th className="py-1.5 pr-3 text-right">Ingående</th>
                      <th className="py-1.5 pr-3 text-right">In</th>
                      <th className="py-1.5 pr-3 text-right">Ut</th>
                      <th className="py-1.5 pr-3 text-right">Transfer +</th>
                      <th className="py-1.5 pr-3 text-right">Transfer −</th>
                      <th className="py-1.5 pr-3 text-right font-semibold">Utgående</th>
                      <th className="py-1.5 pr-3 text-right">Rader</th>
                    </tr>
                  </thead>
                  <tbody>
                    {ledger.accounts.map((a) => (
                      <tr key={a.id} className="border-b last:border-0">
                        <td className="py-1.5 pr-3">
                          <div className="font-medium">{a.name}</div>
                          <div className="text-xs text-slate-600">
                            {a.bank} · {a.type}
                          </div>
                        </td>
                        <td className="py-1.5 pr-3 text-right">{formatSEK(a.opening_balance)}</td>
                        <td className="py-1.5 pr-3 text-right text-emerald-700">
                          {formatSEK(a.income)}
                        </td>
                        <td className="py-1.5 pr-3 text-right text-rose-600">
                          {formatSEK(a.expenses)}
                        </td>
                        <td className="py-1.5 pr-3 text-right text-slate-700">
                          {a.transfer_in > 0 ? formatSEK(a.transfer_in) : "—"}
                        </td>
                        <td className="py-1.5 pr-3 text-right text-slate-700">
                          {a.transfer_out > 0 ? formatSEK(a.transfer_out) : "—"}
                        </td>
                        <td className="py-1.5 pr-3 text-right font-semibold">
                          {formatSEK(a.closing_balance)}
                        </td>
                        <td className="py-1.5 pr-3 text-right text-xs text-slate-600">
                          {a.transaction_count}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Section>

            {/* Resultaträkning */}
            <Section title="Resultaträkning per kategori">
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-left text-xs uppercase text-slate-700 border-b">
                      <th className="py-1.5 pr-3">Kategori</th>
                      <th className="py-1.5 pr-3 text-right">Inkomst</th>
                      <th className="py-1.5 pr-3 text-right">Utgift</th>
                      <th className="py-1.5 pr-3 text-right">Netto</th>
                      <th className="py-1.5 pr-3 text-right">Antal</th>
                    </tr>
                  </thead>
                  <tbody>
                    {ledger.categories.map((c) => (
                      <tr
                        key={`${c.category_id}-${c.category}`}
                        className={`border-b last:border-0 ${
                          c.category === "Okategoriserat" ? "bg-amber-50" : ""
                        }`}
                      >
                        <td className="py-1.5 pr-3 font-medium">{c.category}</td>
                        <td className="py-1.5 pr-3 text-right text-emerald-700">
                          {c.income > 0 ? formatSEK(c.income) : "—"}
                        </td>
                        <td className="py-1.5 pr-3 text-right text-rose-600">
                          {c.expenses > 0 ? formatSEK(c.expenses) : "—"}
                        </td>
                        <td
                          className={`py-1.5 pr-3 text-right font-medium ${
                            c.net >= 0 ? "text-emerald-700" : "text-rose-600"
                          }`}
                        >
                          {formatSEK(c.net)}
                        </td>
                        <td className="py-1.5 pr-3 text-right text-xs text-slate-600">
                          {c.count}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Section>

            {/* Lån */}
            {ledger.loans.length > 0 && (
              <Section title="Lån">
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="text-left text-xs uppercase text-slate-700 border-b">
                        <th className="py-1.5 pr-3">Lån</th>
                        <th className="py-1.5 pr-3 text-right">Ursprung</th>
                        <th className="py-1.5 pr-3 text-right">Kvarvarande</th>
                        <th className="py-1.5 pr-3 text-right">Ränta</th>
                        <th className="py-1.5 pr-3 text-right">Betalt i period</th>
                      </tr>
                    </thead>
                    <tbody>
                      {ledger.loans.map((l) => (
                        <tr key={l.id} className="border-b last:border-0">
                          <td className="py-1.5 pr-3">
                            <div className="font-medium">{l.name}</div>
                            <div className="text-xs text-slate-600">{l.lender}</div>
                          </td>
                          <td className="py-1.5 pr-3 text-right">
                            {formatSEK(l.principal_amount)}
                          </td>
                          <td className="py-1.5 pr-3 text-right font-semibold">
                            {formatSEK(l.outstanding_balance)}
                          </td>
                          <td className="py-1.5 pr-3 text-right">
                            {(l.interest_rate * 100).toFixed(2)} %
                          </td>
                          <td className="py-1.5 pr-3 text-right">
                            {formatSEK(l.payments_in_period)}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </Section>
            )}

            {/* Kommande/matchade */}
            <Section title="Kommande-rader (upcomings)">
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
                <Kpi label="Totalt" value={String(ledger.upcoming_summary.total)} />
                <Kpi
                  label="Matchade"
                  value={`${ledger.upcoming_summary.matched} st`}
                  hint={formatSEK(ledger.upcoming_summary.matched_sum)}
                />
                <Kpi
                  label="Omatchade"
                  value={`${ledger.upcoming_summary.unmatched} st`}
                  hint={formatSEK(ledger.upcoming_summary.unmatched_sum)}
                />
                <Kpi
                  label="Passerat utan match"
                  value={String(ledger.upcoming_summary.unmatched_past)}
                  tone={ledger.upcoming_summary.unmatched_past > 0 ? "bad" : "good"}
                />
              </div>
            </Section>
          </div>
        )}
      </Card>

      {/* Hembudget-rapporter (månads-PDF + överföringsplan) tonas ner —
          de är desktop-funktioner för par som vill skicka något till
          varandra. Huvudboken ovan är den primära rapporten i
          undervisningen. */}
      <details className="border border-slate-200 rounded-md bg-white">
        <summary className="cursor-pointer px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50">
          Övriga exporter (månadsrapport, överföringsplan)
        </summary>
        <div className="px-4 pb-4 pt-1 space-y-3 text-sm">
          <div className="text-xs text-slate-600">
            Visuella partnar-rapporter — månads-PDF med diagram och
            överföringsförslag, samt en framåtriktad överföringsplan med
            förväntad lön och kommande fakturor. Praktiska för hushåll men
            sekundära i klassrumsanvändning.
          </div>
          <div className="flex items-end gap-2 flex-wrap">
            <label className="text-xs">
              <div className="text-slate-600">Månad</div>
              <input
                type="month"
                value={month}
                onChange={(e) => setMonth(e.target.value)}
                className="border rounded px-2 py-1 text-sm"
              />
            </label>
            <button
              className="bg-slate-200 text-slate-800 px-3 py-1 rounded text-xs hover:bg-slate-300"
              onClick={() => download(`/reports/month/${month}/pdf`, `hembudget-${month}.pdf`)}
            >
              Månadsrapport (PDF)
            </button>
            <button
              className="bg-slate-200 text-slate-800 px-3 py-1 rounded text-xs hover:bg-slate-300"
              onClick={() => download(`/reports/month/${month}/excel`, `hembudget-${month}.xlsx`)}
            >
              Månadsrapport (Excel)
            </button>
            <button
              className="bg-slate-200 text-slate-800 px-3 py-1 rounded text-xs hover:bg-slate-300"
              onClick={() => download(
                `/reports/upcoming/${month}/pdf`,
                `overforingsplan-${month}.pdf`,
              )}
            >
              Överföringsplan
            </button>
          </div>
        </div>
      </details>
    </div>
  );
}

function Kpi({
  label, value, hint, tone,
}: {
  label: string;
  value: string;
  hint?: string;
  tone?: "good" | "bad";
}) {
  const color =
    tone === "good" ? "text-emerald-700" : tone === "bad" ? "text-rose-600" : "text-slate-800";
  return (
    <div className="bg-white border rounded p-3">
      <div className="text-xs text-slate-600 uppercase tracking-wide">{label}</div>
      <div className={`text-lg font-semibold mt-0.5 ${color}`}>{value}</div>
      {hint && <div className="text-xs text-slate-600">{hint}</div>}
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div>
      <h3 className="text-sm font-semibold text-slate-800 mb-2">{title}</h3>
      {children}
    </div>
  );
}

interface CheckTxRow {
  id: number;
  date: string;
  amount: number;
  description: string;
  account_id: number;
  account_name: string | null;
  category_id: number | null;
  is_transfer: boolean;
  transfer_pair_id: number | null;
}

interface CheckUpcomingRow {
  id: number;
  kind: "bill" | "income";
  name: string;
  amount: number;
  expected_date: string;
  owner: string | null;
  debit_account_id: number | null;
  source: string;
}

function CheckRow({
  check,
  scope,
  month,
  year,
}: {
  check: LedgerCheck;
  scope: "month" | "year";
  month: string;
  year: number;
}) {
  const [open, setOpen] = useState(false);
  const clickable = !check.passed && !!check.check_type;
  return (
    <div
      className={`text-sm p-2 rounded ${
        check.passed ? "bg-emerald-50" : "bg-amber-50"
      }`}
    >
      <div
        onClick={() => clickable && setOpen((o) => !o)}
        className={`flex items-start gap-2 ${
          clickable ? "cursor-pointer" : ""
        }`}
      >
        {check.passed ? (
          <CheckCircle2 className="w-4 h-4 text-emerald-600 mt-0.5 shrink-0" />
        ) : (
          <XCircle className="w-4 h-4 text-amber-700 mt-0.5 shrink-0" />
        )}
        <div className="flex-1">
          <div className="font-medium flex items-center gap-2">
            {check.name}
            {!check.passed && (
              <span className="text-amber-700">({check.value})</span>
            )}
            {clickable && (
              <span className="text-xs text-brand-600 ml-auto flex items-center">
                {open ? (
                  <ChevronDown className="w-4 h-4" />
                ) : (
                  <ChevronRight className="w-4 h-4" />
                )}
                {open ? "dölj" : "åtgärda"}
              </span>
            )}
          </div>
          <div className="text-xs text-slate-700">{check.detail}</div>
        </div>
      </div>
      {open && clickable && check.check_type && (
        <CheckDetails
          checkType={check.check_type}
          checkValue={check.value}
          scope={scope}
          month={month}
          year={year}
        />
      )}
    </div>
  );
}

function CheckDetails({
  checkType,
  checkValue,
  scope,
  month,
  year,
}: {
  checkType: string;
  checkValue: number;
  scope: "month" | "year";
  month: string;
  year: number;
}) {
  const qc = useQueryClient();
  const queryStr = scope === "month" ? `month=${month}` : `year=${year}`;
  const dataQ = useQuery({
    queryKey: ["ledger-check", checkType, scope, month, year],
    queryFn: () =>
      api<{
        count: number;
        transactions?: CheckTxRow[];
        upcomings?: CheckUpcomingRow[];
        net_diff?: number;
        mismatched_pairs?: Array<{
          source: CheckTxRow;
          destination: CheckTxRow;
          pair_sum: number;
        }>;
        mismatched_net?: number;
      }>(`/ledger/check/${checkType}?${queryStr}`),
  });
  const accountsQ = useQuery({
    queryKey: ["accounts"],
    queryFn: () => api<Account[]>("/accounts"),
  });
  const categoriesQ = useQuery({
    queryKey: ["categories"],
    queryFn: () => api<Category[]>("/categories"),
  });

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ["ledger-check", checkType] });
    qc.invalidateQueries({ queryKey: ["ledger"] });
    qc.invalidateQueries({ queryKey: ["transactions"] });
    qc.invalidateQueries({ queryKey: ["upcoming"] });
    qc.invalidateQueries({ queryKey: ["transfers-unpaired"] });
  };

  if (dataQ.isLoading) {
    return <div className="mt-2 text-xs text-slate-700">Laddar…</div>;
  }
  if (!dataQ.data) return null;

  if (checkType === "uncategorized" && dataQ.data.transactions) {
    return (
      <UncategorizedList
        rows={dataQ.data.transactions}
        categories={categoriesQ.data ?? []}
        onDone={invalidate}
      />
    );
  }
  if (checkType === "transfers_imbalance" && dataQ.data.transactions) {
    return (
      <OrphanTransferList
        rows={dataQ.data.transactions}
        mismatchedPairs={dataQ.data.mismatched_pairs}
        mismatchedNet={dataQ.data.mismatched_net}
        checkValue={checkValue}
        accounts={accountsQ.data ?? []}
        onDone={invalidate}
      />
    );
  }
  if (checkType === "unmatched_past_upcomings" && dataQ.data.upcomings) {
    return (
      <UnmatchedPastUpcomingList
        rows={dataQ.data.upcomings}
        accounts={accountsQ.data ?? []}
        onDone={invalidate}
      />
    );
  }
  return null;
}

function UncategorizedList({
  rows,
  categories,
  onDone,
}: {
  rows: CheckTxRow[];
  categories: Category[];
  onDone: () => void;
}) {
  const setCatMut = useMutation({
    mutationFn: (p: { id: number; category_id: number }) =>
      api(`/transactions/${p.id}`, {
        method: "PATCH",
        body: JSON.stringify({ category_id: p.category_id, create_rule: true }),
      }),
    onSuccess: onDone,
  });
  const autoPairMut = useMutation({
    mutationFn: (txIds: number[]) =>
      api<{
        linked: number;
        ambiguous_count: number;
        no_match_count: number;
        scanned: number;
      }>("/transfers/auto-pair-uncategorized", {
        method: "POST",
        body: JSON.stringify({ tx_ids: txIds }),
      }),
    onSuccess: (data) => {
      if (data.linked > 0) onDone();
    },
  });
  const diagnoseMut = useMutation({
    mutationFn: (txIds: number[]) =>
      api<{
        rows: Array<{
          tx_id: number;
          date: string;
          amount: number;
          description: string;
          reason: string;
          is_transfer?: boolean;
          transfer_pair_id?: number | null;
          category_id?: number | null;
          partner_candidates?: Array<{
            tx_id: number;
            date: string;
            amount: number;
            description: string;
            account_id: number;
          }>;
        }>;
      }>("/transfers/diagnose-pairing", {
        method: "POST",
        body: JSON.stringify({ tx_ids: txIds }),
      }),
  });

  return (
    <div className="mt-2 pt-2 border-t border-amber-200 space-y-1">
      {rows.length > 1 && (
        <div className="bg-emerald-50 border border-emerald-200 rounded p-2 mb-2 flex items-center gap-2 text-xs">
          <span className="flex-1">
            <strong>Tips:</strong> rader där en negativ + positiv på olika
            konton har samma datum + exakt belopp är troligtvis interna
            överföringar (t.ex. kreditkortsbetalningar). Para alla sådana
            i ett klick:
          </span>
          <button
            onClick={() => autoPairMut.mutate(rows.map((r) => r.id))}
            disabled={autoPairMut.isPending}
            className="bg-emerald-600 text-white px-3 py-1.5 rounded text-xs disabled:opacity-50"
          >
            {autoPairMut.isPending ? "Parar…" : "Auto-para uppenbara"}
          </button>
        </div>
      )}
      {autoPairMut.data && (
        <div
          className={
            "text-xs rounded p-2 mb-2 border " +
            (autoPairMut.data.linked > 0
              ? "bg-emerald-50 border-emerald-200 text-emerald-800"
              : "bg-amber-50 border-amber-200 text-amber-800")
          }
        >
          {autoPairMut.data.linked > 0 ? "✓ " : "⚠ "}
          Scannade {autoPairMut.data.scanned} rader →{" "}
          <strong>{autoPairMut.data.linked} par hopparade</strong> som
          överföringar.
          {autoPairMut.data.ambiguous_count > 0 &&
            ` ${autoPairMut.data.ambiguous_count} hade flera kandidater.`}
          {autoPairMut.data.no_match_count > 0 &&
            ` ${autoPairMut.data.no_match_count} hade ingen motpart inom ±3 dagar.`}
          {autoPairMut.data.linked === 0 && (
            <div className="mt-2 flex items-center gap-2">
              <span>Klicka för att se exakt varför per rad:</span>
              <button
                onClick={() => diagnoseMut.mutate(rows.map((r) => r.id))}
                disabled={diagnoseMut.isPending}
                className="text-brand-600 underline"
              >
                {diagnoseMut.isPending ? "Diagnostiserar…" : "Diagnos"}
              </button>
            </div>
          )}
        </div>
      )}
      {diagnoseMut.data && (
        <div className="text-xs bg-slate-50 border border-slate-200 rounded p-2 mb-2 space-y-1 max-h-80 overflow-y-auto">
          <div className="font-medium text-slate-800 mb-1">
            Diagnostik per rad:
          </div>
          {diagnoseMut.data.rows.map((r) => (
            <div key={r.tx_id} className="bg-white rounded px-2 py-1 border border-slate-100">
              <div className="flex items-baseline gap-2">
                <span className="font-mono text-slate-700">{r.date}</span>
                <span
                  className={
                    "font-medium " +
                    (r.amount < 0 ? "text-rose-600" : "text-emerald-700")
                  }
                >
                  {formatSEK(r.amount)}
                </span>
                <span className="flex-1 truncate">{r.description}</span>
              </div>
              <div className="text-slate-600 mt-0.5">→ {r.reason}</div>
              {r.partner_candidates && r.partner_candidates.length > 0 && (
                <div className="ml-4 mt-1 space-y-0.5">
                  {r.partner_candidates.map((p) => (
                    <div
                      key={p.tx_id}
                      className="text-xs text-slate-600 flex gap-2"
                    >
                      <span className="font-mono">{p.date}</span>
                      <span
                        className={
                          p.amount < 0 ? "text-rose-600" : "text-emerald-700"
                        }
                      >
                        {formatSEK(p.amount)}
                      </span>
                      <span className="truncate">{p.description}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
      {autoPairMut.error && (
        <div className="text-xs bg-rose-50 border border-rose-200 rounded p-2 mb-2 text-rose-700">
          Fel: {(autoPairMut.error as Error).message}
        </div>
      )}
      {rows.length === 0 ? (
        <div className="text-xs text-slate-700">Allt åtgärdat ✓</div>
      ) : (
        rows.map((tx) => (
          <div
            key={tx.id}
            className="flex items-center gap-2 text-xs bg-white rounded px-2 py-1.5"
          >
            <span className="text-slate-700 w-20 shrink-0">{tx.date}</span>
            <span
              className={`w-24 text-right shrink-0 font-medium ${
                tx.amount < 0 ? "text-rose-600" : "text-emerald-700"
              }`}
            >
              {formatSEK(tx.amount)}
            </span>
            <span className="flex-1 min-w-0 truncate">{tx.description}</span>
            <span className="text-slate-600 w-32 shrink-0 truncate">
              {tx.account_name}
            </span>
            <select
              defaultValue=""
              onChange={(e) => {
                if (e.target.value) {
                  setCatMut.mutate({
                    id: tx.id,
                    category_id: Number(e.target.value),
                  });
                }
              }}
              className="border rounded px-1 py-0.5 text-xs bg-white"
            >
              <option value="">Välj kategori…</option>
              {categories.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </select>
          </div>
        ))
      )}
    </div>
  );
}

function OrphanTransferList({
  rows,
  mismatchedPairs,
  mismatchedNet,
  checkValue,
  accounts,
  onDone,
}: {
  rows: CheckTxRow[];
  mismatchedPairs?: Array<{
    source: CheckTxRow;
    destination: CheckTxRow;
    pair_sum: number;
  }>;
  mismatchedNet?: number;
  checkValue: number;
  accounts: Account[];
  onDone: () => void;
}) {
  const counterpartMut = useMutation({
    mutationFn: (p: { tx_id: number; account_id: number }) =>
      api(`/transfers/${p.tx_id}/create-counterpart`, {
        method: "POST",
        body: JSON.stringify({
          account_id: p.account_id,
          description: "Motpart från huvudboksfix",
        }),
      }),
    onSuccess: onDone,
  });
  const unlinkMut = useMutation({
    mutationFn: (tx_id: number) =>
      api(`/transfers/unlink/${tx_id}`, { method: "POST" }),
    onSuccess: onDone,
  });

  const sorted = [...accounts].sort((a, b) =>
    (b.incognito ? 1 : 0) - (a.incognito ? 1 : 0),
  );

  const hasOrphans = rows.length > 0;
  const hasMismatched = (mismatchedPairs ?? []).length > 0;

  return (
    <div className="mt-2 pt-2 border-t border-amber-200 space-y-1">
      {!hasOrphans && !hasMismatched && (
        <div className="text-xs text-slate-700 bg-white rounded p-2 space-y-1">
          <div>
            Inga orphan-överföringar eller belopps-diff större än 1 öre
            hittade i datan.
          </div>
          {Math.abs(checkValue) > 2 && (
            <div className="text-amber-700">
              Men transfer_in − transfer_out = {formatSEK(checkValue)} —
              detta kommer från transaktioner utanför perioden (t.ex. en
              överföring som har sin motpart i nästa/föregående månad/år)
              eller en pair där en sida är kopplad till en kommande
              faktura/lön (delbetalning) som reklassificerats till utgift
              medan motparten fortfarande står som transfer. Kolla
              balansrapporten nedan — vilket konto har TRANSFER +/− som
              inte matchar ett annat konto?
            </div>
          )}
        </div>
      )}
      {rows.map((tx) => (
        <div
          key={tx.id}
          className="flex items-center gap-2 text-xs bg-white rounded px-2 py-1.5 flex-wrap"
        >
          <span className="text-slate-700 w-20 shrink-0">{tx.date}</span>
          <span
            className={`w-24 text-right shrink-0 font-medium ${
              tx.amount < 0 ? "text-rose-600" : "text-emerald-700"
            }`}
          >
            {formatSEK(tx.amount)}
          </span>
          <span className="flex-1 min-w-0 truncate">{tx.description}</span>
          <span className="text-slate-600 shrink-0 truncate">
            {tx.account_name}
          </span>
          <select
            defaultValue=""
            onChange={(e) => {
              if (e.target.value) {
                counterpartMut.mutate({
                  tx_id: tx.id,
                  account_id: Number(e.target.value),
                });
              }
            }}
            className="border rounded px-1 py-0.5 text-xs bg-white"
            title="Skapa motsvarande transaktion på valt konto"
          >
            <option value="">Skapa motpart…</option>
            {sorted
              .filter((a) => a.id !== tx.account_id)
              .map((a) => (
                <option key={a.id} value={a.id}>
                  {a.name}
                  {a.incognito ? " (inkognito)" : ""}
                </option>
              ))}
          </select>
          <button
            onClick={() => unlinkMut.mutate(tx.id)}
            className="text-xs text-slate-700 hover:text-rose-600"
            title="Avmarkera som överföring (räkna som vanlig utgift)"
          >
            Avmarkera
          </button>
        </div>
      ))}
      {hasMismatched && (
        <>
          <div className="text-xs text-slate-700 pt-2 pb-1 font-medium">
            Parade överföringar med belopps-diff (
            {formatSEK(mismatchedNet ?? 0)} totalt):
          </div>
          {(mismatchedPairs ?? []).map((p) => (
            <div
              key={`${p.source.id}-${p.destination.id}`}
              className="flex items-center gap-2 text-xs bg-white rounded px-2 py-1.5 flex-wrap"
            >
              <span className="text-slate-700 w-20 shrink-0">
                {p.source.date}
              </span>
              <span className="flex-1 min-w-0 truncate">
                {p.source.description} → {p.destination.description}
              </span>
              <span className="text-slate-600 text-xs shrink-0">
                {formatSEK(p.source.amount)} +{" "}
                {formatSEK(p.destination.amount)}
              </span>
              <span
                className={`font-semibold shrink-0 ${
                  Math.abs(p.pair_sum) < 1
                    ? "text-slate-700"
                    : "text-amber-700"
                }`}
                title="Om diff är < 1 kr är det öresavrundning. Större diff tyder på fel."
              >
                Δ {p.pair_sum.toFixed(2)}
              </span>
            </div>
          ))}
        </>
      )}
    </div>
  );
}

function UnmatchedPastUpcomingList({
  rows,
  accounts,
  onDone,
}: {
  rows: CheckUpcomingRow[];
  accounts: Account[];
  onDone: () => void;
}) {
  const deleteMut = useMutation({
    mutationFn: (id: number) =>
      api(`/upcoming/${id}`, { method: "DELETE" }),
    onSuccess: onDone,
  });
  const materializeMut = useMutation({
    mutationFn: (p: { id: number; account_id: number }) =>
      api(`/upcoming/${p.id}/materialize-to-account`, {
        method: "POST",
        body: JSON.stringify({ account_id: p.account_id }),
      }),
    onSuccess: onDone,
  });

  const sorted = [...accounts].sort((a, b) =>
    (b.incognito ? 1 : 0) - (a.incognito ? 1 : 0),
  );

  return (
    <div className="mt-2 pt-2 border-t border-amber-200 space-y-1">
      {rows.map((u) => (
        <div
          key={u.id}
          className="flex items-center gap-2 text-xs bg-white rounded px-2 py-1.5 flex-wrap"
        >
          <span className="text-slate-700 w-20 shrink-0">
            {u.expected_date}
          </span>
          <span className="w-10 text-slate-600 shrink-0 text-xs uppercase">
            {u.kind === "income" ? "lön" : "fakt."}
          </span>
          <span
            className={`w-24 text-right shrink-0 font-medium ${
              u.kind === "income" ? "text-emerald-700" : "text-rose-600"
            }`}
          >
            {formatSEK(u.amount)}
          </span>
          <span className="flex-1 min-w-0 truncate">{u.name}</span>
          {u.owner && (
            <span className="text-slate-600 text-xs">{u.owner}</span>
          )}
          <select
            defaultValue=""
            onChange={(e) => {
              if (e.target.value) {
                materializeMut.mutate({
                  id: u.id,
                  account_id: Number(e.target.value),
                });
              }
            }}
            className="border rounded px-1 py-0.5 text-xs bg-white"
          >
            <option value="">Koppla till konto…</option>
            {sorted.map((a) => (
              <option key={a.id} value={a.id}>
                {a.name}
                {a.incognito ? " (inkognito)" : ""}
              </option>
            ))}
          </select>
          <button
            onClick={() => {
              if (confirm(`Radera "${u.name}"?`)) deleteMut.mutate(u.id);
            }}
            className="text-xs text-slate-700 hover:text-rose-600"
          >
            Radera
          </button>
        </div>
      ))}
    </div>
  );
}

function MonthLockBanner({
  scope,
  month,
  year,
  lockedMonths,
}: {
  scope: "month" | "year";
  month: string;
  year: number;
  lockedMonths: string[];
}) {
  const qc = useQueryClient();
  const lockMut = useMutation({
    mutationFn: (m: string) =>
      api(`/ledger/locks/${m}`, { method: "POST", body: JSON.stringify({}) }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["ledger"] }),
  });
  const unlockMut = useMutation({
    mutationFn: (m: string) =>
      api(`/ledger/locks/${m}`, { method: "DELETE" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["ledger"] }),
  });

  if (scope === "year") {
    if (lockedMonths.length === 0) {
      return (
        <div className="mb-3 rounded-md border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-700">
          <strong>Inga låsta månader för {year}.</strong> Byt till månad-vy
          och lås när du är klar med avstämningen så ändringar blockeras.
        </div>
      );
    }
    return (
      <div className="mb-3 rounded-md border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-800">
        <strong>{lockedMonths.length} låsta månader:</strong>{" "}
        {lockedMonths.join(", ")}
      </div>
    );
  }

  const isLocked = lockedMonths.includes(month);
  if (isLocked) {
    return (
      <div className="mb-3 rounded-md border border-emerald-300 bg-emerald-50 px-3 py-2 text-sm text-emerald-800 flex items-center gap-3">
        <div className="flex-1">
          <strong>🔒 {month} är låst och godkänd.</strong> Inga transaktioner
          i månaden kan ändras, flyttas eller raderas.
        </div>
        <button
          onClick={() => {
            if (confirm(`Lås upp ${month}? Ändringar tillåts igen.`)) {
              unlockMut.mutate(month);
            }
          }}
          disabled={unlockMut.isPending}
          className="text-xs text-rose-700 hover:text-rose-900 underline disabled:opacity-50"
        >
          {unlockMut.isPending ? "Låser upp…" : "Lås upp"}
        </button>
      </div>
    );
  }
  return (
    <div className="mb-3 rounded-md border border-slate-200 bg-white px-3 py-2 text-sm text-slate-700 flex items-center gap-3">
      <div className="flex-1">
        Klar med avstämningen för <strong>{month}</strong>? Lås månaden så
        blockeras retroaktiva ändringar.
      </div>
      <button
        onClick={() => {
          if (confirm(`Lås ${month}? Efter lås kan inga transaktioner i månaden ändras eller raderas. Du kan låsa upp igen senare om det behövs.`)) {
            lockMut.mutate(month);
          }
        }}
        disabled={lockMut.isPending}
        className="bg-emerald-600 text-white px-3 py-1.5 rounded text-xs disabled:opacity-50"
      >
        {lockMut.isPending ? "Låser…" : "🔒 Lås månad"}
      </button>
    </div>
  );
}
