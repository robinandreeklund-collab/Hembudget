/**
 * Renodlad lön-sida — flyttad från /upcoming där den låg blandat med
 * fakturor. Visar:
 *  - KPI-strip: total i år, denna månad, snitt/mån, antal utbetalningar
 *  - Per person breakdown (cards) med fördelning CSV/manuellt
 *  - Lägg till lön (collapsible quick-form)
 *  - Kommande löner (månadsgrupperat, expanderbart)
 *  - Historiska löner (matchade + manuellt registrerade i år)
 *
 * All datakälla: /upcoming/?kind=income + /budget/ytd-income.
 */
import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Briefcase, ChevronDown, ChevronRight, Plus, Trash2, X, CheckCircle2,
} from "lucide-react";
import { api, formatSEK } from "@/api/client";
import { Card } from "@/components/Card";
import type { Account, HouseholdUser } from "@/types/models";

interface IncomeUpcoming {
  id: number;
  kind: "bill" | "income";
  name: string;
  amount: number;
  expected_date: string;
  owner: string | null;
  debit_account_id: number | null;
  matched_transaction_id: number | null;
  source: string;
  notes: string | null;
  payment_status?: "unpaid" | "partial" | "paid" | "overpaid";
  paid_amount?: number;
}

interface YtdIncome {
  year: number;
  category: string;
  category_matched: boolean;
  grand_total: number;
  total_from_transactions?: number;
  total_from_manual?: number;
  by_owner: Record<string, {
    total: number;
    count: number;
    accounts: Array<{ name: string; amount: number; source: string }>;
    from_transactions?: number;
    from_manual?: number;
  }>;
}

const SV_MONTHS = [
  "januari", "februari", "mars", "april", "maj", "juni",
  "juli", "augusti", "september", "oktober", "november", "december",
];

function fmtMonth(ym: string): string {
  const [y, m] = ym.split("-").map(Number);
  if (!y || !m) return ym;
  return `${SV_MONTHS[m - 1]} ${y}`;
}

function todayIso(): string {
  return new Date().toISOString().slice(0, 10);
}

export default function Salaries() {
  const qc = useQueryClient();
  const [showAddForm, setShowAddForm] = useState(false);

  const incomesQ = useQuery({
    queryKey: ["upcoming", "income"],
    queryFn: () => api<IncomeUpcoming[]>("/upcoming/?only_future=false&kind=income"),
  });
  const ytdQ = useQuery({
    queryKey: ["ytd-income"],
    queryFn: () => api<YtdIncome>("/budget/ytd-income"),
  });
  const accountsQ = useQuery({
    queryKey: ["accounts"],
    queryFn: () => api<Account[]>("/accounts"),
  });
  const usersQ = useQuery({
    queryKey: ["users"],
    queryFn: () => api<HouseholdUser[]>("/users"),
  });

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ["upcoming"] });
    qc.invalidateQueries({ queryKey: ["upcoming", "income"] });
    qc.invalidateQueries({ queryKey: ["ytd-income"] });
    qc.invalidateQueries({ queryKey: ["budget"] });
    qc.invalidateQueries({ queryKey: ["transactions"] });
    qc.invalidateQueries({ queryKey: ["balances"] });
    qc.invalidateQueries({ queryKey: ["ledger"] });
  };

  const createMut = useMutation({
    mutationFn: (data: Partial<IncomeUpcoming> & { kind: "income" }) =>
      api<IncomeUpcoming>("/upcoming/", {
        method: "POST",
        body: JSON.stringify(data),
      }),
    onSuccess: () => {
      invalidate();
      setShowAddForm(false);
    },
  });
  const deleteMut = useMutation({
    mutationFn: (id: number) =>
      api(`/upcoming/${id}`, { method: "DELETE" }),
    onSuccess: invalidate,
  });
  const updateMut = useMutation({
    mutationFn: ({ id, data }: { id: number; data: Partial<IncomeUpcoming> }) =>
      api<IncomeUpcoming>(`/upcoming/${id}`, {
        method: "PATCH",
        body: JSON.stringify(data),
      }),
    onSuccess: invalidate,
  });

  const incomes = incomesQ.data ?? [];
  const accounts = accountsQ.data ?? [];
  const users = usersQ.data ?? [];

  // Open = inte fullt betald (samma logik som /upcoming).
  const open = incomes.filter((i) => i.payment_status !== "paid");
  const past = incomes.filter((i) => i.payment_status === "paid");

  // KPIs
  const ytd = ytdQ.data;
  const thisMonthYm = todayIso().slice(0, 7);
  const thisMonthTotal = past
    .filter((i) => i.expected_date.startsWith(thisMonthYm))
    .reduce((s, i) => s + Number(i.amount), 0);
  const monthsWithIncome = new Set(
    past.map((i) => i.expected_date.slice(0, 7)),
  ).size;
  const avgPerMonth =
    monthsWithIncome > 0 && ytd
      ? ytd.grand_total / monthsWithIncome
      : 0;
  const totalPayouts = past.length + open.length;

  // Per arbetsgivare (gruppera på namn) — användbart för översikt
  const byEmployer = useMemo(() => {
    const map = new Map<string, { total: number; count: number; latest: string }>();
    for (const i of past) {
      const name = i.name || "Okänd";
      const existing = map.get(name);
      const amt = Number(i.amount);
      if (existing) {
        existing.total += amt;
        existing.count += 1;
        if (i.expected_date > existing.latest) existing.latest = i.expected_date;
      } else {
        map.set(name, { total: amt, count: 1, latest: i.expected_date });
      }
    }
    return [...map.entries()]
      .map(([name, v]) => ({ name, ...v }))
      .sort((a, b) => b.total - a.total);
  }, [past]);

  return (
    <div className="p-3 md:p-6 space-y-4 md:space-y-5 max-w-6xl">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold flex items-center gap-2">
          <Briefcase className="w-6 h-6" />
          Lön
        </h1>
        <button
          onClick={() => setShowAddForm((v) => !v)}
          className="flex items-center gap-1.5 px-3 py-1.5 bg-brand-600 text-white rounded-lg text-sm"
        >
          <Plus className="w-4 h-4" />
          {showAddForm ? "Stäng" : "Lägg till lön"}
        </button>
      </div>

      {/* KPI-strip */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <Kpi
          label={`Total i år ${ytd?.year ?? new Date().getFullYear()}`}
          value={ytd ? formatSEK(ytd.grand_total) : "—"}
          tone="good"
        />
        <Kpi
          label={`Denna månad (${fmtMonth(thisMonthYm)})`}
          value={formatSEK(thisMonthTotal)}
        />
        <Kpi
          label="Snitt per månad"
          value={avgPerMonth > 0 ? formatSEK(avgPerMonth) : "—"}
          hint={
            monthsWithIncome > 0
              ? `${monthsWithIncome} månader med inkomst`
              : undefined
          }
        />
        <Kpi
          label="Antal utbetalningar"
          value={String(totalPayouts)}
          hint={
            open.length > 0 ? `${open.length} kommande, ${past.length} historik` : undefined
          }
        />
      </div>

      {/* Add-form */}
      {showAddForm && (
        <Card title="Lägg till lön (kommande eller historisk)">
          <AddSalaryForm
            accounts={accounts}
            users={users}
            busy={createMut.isPending}
            error={createMut.error as Error | null}
            onSubmit={(data) => createMut.mutate({ kind: "income", ...data })}
            onCancel={() => setShowAddForm(false)}
          />
        </Card>
      )}

      {/* Per person breakdown */}
      {ytd && Object.keys(ytd.by_owner).length > 0 && (
        <Card title={`Lön per person — ${ytd.year}`}>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            {Object.entries(ytd.by_owner)
              .sort(([, a], [, b]) => b.total - a.total)
              .map(([key, b]) => {
                const userName = key === "gemensamt"
                  ? "Gemensamt"
                  : key.startsWith("user_")
                  ? users.find((u) => u.id === Number(key.slice(5)))?.name ?? key
                  : key;
                return (
                  <div
                    key={key}
                    className="border rounded-lg p-3 bg-emerald-50/30"
                  >
                    <div className="flex items-baseline justify-between">
                      <div className="font-medium">{userName}</div>
                      <div className="text-xs text-slate-700">{b.count} st</div>
                    </div>
                    <div className="text-2xl font-semibold text-emerald-700 mt-1">
                      {formatSEK(b.total)}
                    </div>
                    {((b.from_manual ?? 0) > 0 ||
                      (b.from_transactions ?? 0) > 0) && (
                      <div className="text-xs text-slate-700 mt-2 space-y-0.5">
                        {(b.from_transactions ?? 0) > 0 && (
                          <div>
                            Från kontoutdrag:{" "}
                            <span className="font-medium">
                              {formatSEK(b.from_transactions ?? 0)}
                            </span>
                          </div>
                        )}
                        {(b.from_manual ?? 0) > 0 && (
                          <div>
                            Manuellt tillagda:{" "}
                            <span className="font-medium">
                              {formatSEK(b.from_manual ?? 0)}
                            </span>
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                );
              })}
          </div>
          {!ytd.category_matched && (
            <div className="text-xs text-slate-700 mt-3">
              Använder fallback (alla positiva non-transfer-rader) — ingen
              kategori "Lön" matchade.
            </div>
          )}
        </Card>
      )}

      {/* Per arbetsgivare */}
      {byEmployer.length > 0 && (
        <Card title="Inkomstkällor (i år)">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs uppercase text-slate-700 border-b">
                  <th className="py-2 pr-3">Källa</th>
                  <th className="py-2 pr-3 text-right">Antal</th>
                  <th className="py-2 pr-3">Senaste</th>
                  <th className="py-2 pr-3 text-right">Summa i år</th>
                </tr>
              </thead>
              <tbody>
                {byEmployer.map((e) => (
                  <tr key={e.name} className="border-b last:border-b-0">
                    <td className="py-1.5 pr-3 font-medium">{e.name}</td>
                    <td className="py-1.5 pr-3 text-right text-slate-700">
                      {e.count}
                    </td>
                    <td className="py-1.5 pr-3 text-slate-700 text-xs">
                      {e.latest}
                    </td>
                    <td className="py-1.5 pr-3 text-right font-medium">
                      {formatSEK(e.total)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}

      {/* Kommande löner */}
      <Card title={`Kommande löner (${open.length})`}>
        {open.length === 0 ? (
          <div className="text-sm text-slate-700">
            Inga planerade löner. Lägg till en med "+ Lägg till lön" ovan.
          </div>
        ) : (
          <SalaryMonthList
            items={open}
            accounts={accounts}
            onDelete={(id) => deleteMut.mutate(id)}
            onUpdate={(id, data) => updateMut.mutate({ id, data })}
            startExpanded
          />
        )}
      </Card>

      {/* Historiska löner */}
      {past.length > 0 && (
        <Card title={`Historiska löner (${past.length})`}>
          <SalaryMonthList
            items={past}
            accounts={accounts}
            onDelete={(id) => deleteMut.mutate(id)}
            onUpdate={(id, data) => updateMut.mutate({ id, data })}
          />
        </Card>
      )}
    </div>
  );
}

function Kpi({
  label,
  value,
  hint,
  tone,
}: {
  label: string;
  value: string;
  hint?: string;
  tone?: "good" | "neutral";
}) {
  return (
    <div className="border rounded-lg p-3 bg-white">
      <div className="text-xs uppercase text-slate-700 tracking-wide">
        {label}
      </div>
      <div
        className={
          "text-xl font-semibold mt-1 " +
          (tone === "good" ? "text-emerald-700" : "text-slate-800")
        }
      >
        {value}
      </div>
      {hint && (
        <div className="text-xs text-slate-600 mt-0.5">{hint}</div>
      )}
    </div>
  );
}

function AddSalaryForm({
  accounts,
  users,
  busy,
  error,
  onSubmit,
  onCancel,
}: {
  accounts: Account[];
  users: HouseholdUser[];
  busy: boolean;
  error: Error | null;
  onSubmit: (data: {
    name: string;
    amount: number;
    expected_date: string;
    owner: string | null;
    debit_account_id: number | null;
    recurring_monthly: boolean;
  }) => void;
  onCancel: () => void;
}) {
  const [name, setName] = useState("");
  const [amount, setAmount] = useState("");
  const [date, setDate] = useState(todayIso());
  const [owner, setOwner] = useState<string>("");
  const [accountId, setAccountId] = useState<string>("");
  const [recurring, setRecurring] = useState(true);

  return (
    <div className="space-y-3 text-sm">
      <div className="text-xs text-slate-700">
        Skapar en kommande löneutbetalning. Om datumet ligger i det
        förflutna och kontot är ett inkognito-konto kommer raden auto-
        materialiseras till kontot direkt så saldo + huvudbok stämmer.
      </div>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <label className="block">
          <div className="text-xs text-slate-700 mb-0.5">Arbetsgivare/källa</div>
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="t.ex. Inkab, VP Capital, FK"
            className="border rounded px-2 py-1.5 w-full"
          />
        </label>
        <label className="block">
          <div className="text-xs text-slate-700 mb-0.5">Belopp (kr)</div>
          <input
            type="number"
            step="0.01"
            value={amount}
            onChange={(e) => setAmount(e.target.value)}
            placeholder="35000"
            className="border rounded px-2 py-1.5 w-full"
          />
        </label>
        <label className="block">
          <div className="text-xs text-slate-700 mb-0.5">Utbetalningsdatum</div>
          <input
            type="date"
            value={date}
            onChange={(e) => setDate(e.target.value)}
            className="border rounded px-2 py-1.5 w-full"
          />
        </label>
        <label className="block">
          <div className="text-xs text-slate-700 mb-0.5">
            Tillhör (för YTD per person)
          </div>
          <select
            value={owner}
            onChange={(e) => setOwner(e.target.value)}
            className="border rounded px-2 py-1.5 w-full"
          >
            <option value="">— gemensamt / härled från konto</option>
            {users.map((u) => (
              <option key={u.id} value={u.name}>
                {u.name}
              </option>
            ))}
          </select>
        </label>
        <label className="block">
          <div className="text-xs text-slate-700 mb-0.5">Konto (mottagare)</div>
          <select
            value={accountId}
            onChange={(e) => setAccountId(e.target.value)}
            className="border rounded px-2 py-1.5 w-full"
          >
            <option value="">— välj —</option>
            {accounts
              .filter((a) => a.type !== "credit")
              .map((a) => (
                <option key={a.id} value={a.id}>
                  {a.name} ({a.bank})
                </option>
              ))}
          </select>
        </label>
        <label className="flex items-center gap-2 mt-6">
          <input
            type="checkbox"
            checked={recurring}
            onChange={(e) => setRecurring(e.target.checked)}
          />
          <span>Återkommande månadsvis</span>
        </label>
      </div>
      {error && (
        <div className="text-xs text-rose-600">{error.message}</div>
      )}
      <div className="flex justify-end gap-2">
        <button
          onClick={onCancel}
          className="px-3 py-1.5 rounded border border-slate-300 bg-white"
        >
          Avbryt
        </button>
        <button
          onClick={() =>
            onSubmit({
              name: name.trim() || "Lön",
              amount: Number(amount),
              expected_date: date,
              owner: owner || null,
              debit_account_id: accountId ? Number(accountId) : null,
              recurring_monthly: recurring,
            })
          }
          disabled={busy || !amount || !date}
          className="px-4 py-1.5 rounded bg-brand-600 text-white disabled:opacity-50"
        >
          {busy ? "Sparar…" : "Spara"}
        </button>
      </div>
    </div>
  );
}

function SalaryMonthList({
  items,
  accounts,
  onDelete,
  onUpdate,
  startExpanded = false,
}: {
  items: IncomeUpcoming[];
  accounts: Account[];
  onDelete: (id: number) => void;
  onUpdate: (id: number, data: Partial<IncomeUpcoming>) => void;
  startExpanded?: boolean;
}) {
  // Gruppera per YYYY-MM, senaste månaden överst
  const byMonth = useMemo(() => {
    const map = new Map<string, IncomeUpcoming[]>();
    for (const i of items) {
      const ym = i.expected_date.slice(0, 7);
      if (!map.has(ym)) map.set(ym, []);
      map.get(ym)!.push(i);
    }
    return [...map.entries()]
      .sort(([a], [b]) => (a < b ? 1 : -1))
      .map(([ym, list]) => ({
        ym,
        items: list.sort((a, b) =>
          a.expected_date < b.expected_date ? 1 : -1,
        ),
      }));
  }, [items]);

  return (
    <div className="space-y-2">
      {byMonth.map((m, idx) => (
        <SalaryMonthSection
          key={m.ym}
          ym={m.ym}
          items={m.items}
          accounts={accounts}
          startExpanded={startExpanded || idx === 0}
          onDelete={onDelete}
          onUpdate={onUpdate}
        />
      ))}
    </div>
  );
}

function SalaryMonthSection({
  ym,
  items,
  accounts,
  startExpanded,
  onDelete,
  onUpdate,
}: {
  ym: string;
  items: IncomeUpcoming[];
  accounts: Account[];
  startExpanded: boolean;
  onDelete: (id: number) => void;
  onUpdate: (id: number, data: Partial<IncomeUpcoming>) => void;
}) {
  const [open, setOpen] = useState(startExpanded);
  const total = items.reduce((s, i) => s + Number(i.amount), 0);

  return (
    <div className="border rounded-lg overflow-hidden">
      <button
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center gap-3 px-3 py-2 hover:bg-slate-50 text-left"
      >
        {open ? (
          <ChevronDown className="w-4 h-4 text-slate-600 shrink-0" />
        ) : (
          <ChevronRight className="w-4 h-4 text-slate-600 shrink-0" />
        )}
        <div className="flex-1">
          <div className="font-medium capitalize">{fmtMonth(ym)}</div>
          <div className="text-xs text-slate-700">
            {items.length} st · {items.filter((i) => i.payment_status === "paid").length} matchade
          </div>
        </div>
        <div className="font-semibold text-emerald-700 shrink-0">
          +{formatSEK(total)}
        </div>
      </button>
      {open && (
        <div className="border-t divide-y">
          {items.map((i) => (
            <SalaryRow
              key={i.id}
              item={i}
              accounts={accounts}
              onDelete={() => onDelete(i.id)}
              onUpdate={(data) => onUpdate(i.id, data)}
            />
          ))}
        </div>
      )}
    </div>
  );
}

function SalaryRow({
  item,
  accounts,
  onDelete,
  onUpdate,
}: {
  item: IncomeUpcoming;
  accounts: Account[];
  onDelete: () => void;
  onUpdate: (data: Partial<IncomeUpcoming>) => void;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState({
    name: item.name,
    amount: String(item.amount),
    expected_date: item.expected_date,
    owner: item.owner ?? "",
  });
  const account = accounts.find((a) => a.id === item.debit_account_id);

  return (
    <div className="px-3 py-2 hover:bg-slate-50">
      <div className="flex items-center gap-3">
        <div className="flex-1 min-w-0">
          <div className="font-medium truncate">{item.name}</div>
          <div className="text-xs text-slate-700 flex flex-wrap gap-x-2">
            <span>Utbetalas {item.expected_date}</span>
            {account && <span>· till {account.name}</span>}
            {item.owner && <span>· {item.owner}</span>}
            {item.source !== "manual" && <span>· {item.source}</span>}
            {item.payment_status === "paid" && (
              <span className="text-emerald-600 inline-flex items-center gap-1">
                <CheckCircle2 className="w-3 h-3" /> fullt betald
              </span>
            )}
            {item.payment_status === "partial" && (
              <span className="text-amber-700">
                ⚠ delbetalt {formatSEK(item.paid_amount ?? 0)} av{" "}
                {formatSEK(item.amount)}
              </span>
            )}
            {item.payment_status === "overpaid" && (
              <span className="text-rose-600">
                ⚠ överbetald {formatSEK(item.paid_amount ?? 0)} av{" "}
                {formatSEK(item.amount)}
              </span>
            )}
          </div>
        </div>
        <div className="font-semibold text-emerald-700 shrink-0">
          +{formatSEK(Math.abs(Number(item.amount)))}
        </div>
        <button
          onClick={() => setEditing((v) => !v)}
          className="text-xs text-brand-600 hover:underline shrink-0"
        >
          {editing ? "Stäng" : "Redigera"}
        </button>
        <button
          onClick={() => {
            if (confirm(`Ta bort "${item.name}" (${formatSEK(item.amount)})?`)) {
              onDelete();
            }
          }}
          className="text-slate-600 hover:text-rose-600 shrink-0"
        >
          <Trash2 className="w-4 h-4" />
        </button>
      </div>
      {editing && (
        <div className="mt-2 pt-2 border-t bg-slate-50 -mx-3 px-3 pb-2 grid grid-cols-2 gap-2 text-xs">
          <label className="block">
            <div className="text-slate-700 mb-0.5">Källa</div>
            <input
              value={draft.name}
              onChange={(e) => setDraft({ ...draft, name: e.target.value })}
              className="border rounded px-2 py-1 w-full"
            />
          </label>
          <label className="block">
            <div className="text-slate-700 mb-0.5">Belopp</div>
            <input
              type="number"
              step="0.01"
              value={draft.amount}
              onChange={(e) => setDraft({ ...draft, amount: e.target.value })}
              className="border rounded px-2 py-1 w-full"
            />
          </label>
          <label className="block">
            <div className="text-slate-700 mb-0.5">Datum</div>
            <input
              type="date"
              value={draft.expected_date}
              onChange={(e) =>
                setDraft({ ...draft, expected_date: e.target.value })
              }
              className="border rounded px-2 py-1 w-full"
            />
          </label>
          <label className="block">
            <div className="text-slate-700 mb-0.5">Tillhör</div>
            <input
              value={draft.owner}
              onChange={(e) => setDraft({ ...draft, owner: e.target.value })}
              placeholder="t.ex. Robin"
              className="border rounded px-2 py-1 w-full"
            />
          </label>
          <div className="col-span-2 flex justify-end gap-2 pt-1">
            <button
              onClick={() => setEditing(false)}
              className="px-3 py-1 rounded border border-slate-300 bg-white"
            >
              <X className="w-3 h-3" />
            </button>
            <button
              onClick={() => {
                onUpdate({
                  name: draft.name,
                  amount: Number(draft.amount),
                  expected_date: draft.expected_date,
                  owner: draft.owner || null,
                });
                setEditing(false);
              }}
              className="px-3 py-1 rounded bg-brand-600 text-white"
            >
              Spara
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
