import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { CheckCircle2, XCircle } from "lucide-react";
import { Card } from "@/components/Card";
import { api, formatSEK, getToken } from "@/api/client";

function defaultMonth(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
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
}

interface Ledger {
  period: { label: string; start: string; end: string };
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
      <h1 className="text-2xl font-semibold">Rapporter</h1>

      <Card title="Månadsrapport (export)">
        <div className="flex items-end gap-3">
          <label className="text-sm">
            <div className="text-slate-700">Månad</div>
            <input
              type="month"
              value={month}
              onChange={(e) => setMonth(e.target.value)}
              className="border rounded px-2 py-1"
            />
          </label>
          <button
            className="bg-slate-800 text-white px-3 py-1.5 rounded"
            onClick={() => download(`/reports/month/${month}/excel`, `hembudget-${month}.xlsx`)}
          >
            Ladda ner Excel
          </button>
          <button
            className="bg-brand-600 text-white px-3 py-1.5 rounded"
            onClick={() => download(`/reports/month/${month}/pdf`, `hembudget-${month}.pdf`)}
          >
            Ladda ner PDF
          </button>
        </div>
      </Card>

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
                  <div
                    key={i}
                    className={`flex items-start gap-2 text-sm p-2 rounded ${
                      c.passed ? "bg-emerald-50" : "bg-amber-50"
                    }`}
                  >
                    {c.passed ? (
                      <CheckCircle2 className="w-4 h-4 text-emerald-600 mt-0.5 shrink-0" />
                    ) : (
                      <XCircle className="w-4 h-4 text-amber-700 mt-0.5 shrink-0" />
                    )}
                    <div className="flex-1">
                      <div className="font-medium">
                        {c.name}
                        {!c.passed && (
                          <span className="text-amber-700 ml-2">
                            ({c.value})
                          </span>
                        )}
                      </div>
                      <div className="text-xs text-slate-700">{c.detail}</div>
                    </div>
                  </div>
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
