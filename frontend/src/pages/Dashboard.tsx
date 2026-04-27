import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import React, { useEffect, useMemo, useState } from "react";
import {
  AlertTriangle, Trash2, TrendingDown, TrendingUp, Users,
} from "lucide-react";
import { api, formatSEK } from "@/api/client";
import { Card, Stat } from "@/components/Card";
import { useAuth } from "@/hooks/useAuth";
import { ClassLeaderboard } from "@/components/ClassLeaderboard";
import { EventInbox } from "@/components/EventInbox";
import { HouseholdSplitQuiz } from "@/components/HouseholdSplitQuiz";
import { HouseholdSummaryCard } from "@/components/HouseholdSummaryCard";
import { InvitationsInbox } from "@/components/InvitationsInbox";
import { ResetDialog } from "@/components/ResetDialog";
import { StudentPedagogyCards } from "@/components/StudentPedagogyCards";
import { WellbeingCard } from "@/components/WellbeingCard";
import { Bar, BarChart, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { ForecastPoint, HouseholdUser, MonthSummary } from "@/types/models";

interface Anomaly {
  category: string;
  current: number;
  average: number;
  stdev: number;
  z_score: number;
  direction: "higher" | "lower";
}

interface YtdIncome {
  year: number;
  category: string;
  category_matched: boolean;
  by_owner: Record<string, { total: number; count: number; accounts: Array<{ name: string; amount: number }> }>;
  grand_total: number;
}

interface NetWorthPoint {
  date: string;
  assets: number;
  debt: number;
  net_worth: number;
}

interface FamilyBreakdown {
  month: string;
  by_owner: Record<string, { income: number; expenses: number }>;
  by_account: Array<{
    account_id: number;
    account: string;
    type: string;
    owner_id: number | null;
    income: number;
    expenses: number;
  }>;
}

function currentMonth(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

interface MonthOption { month: string; count: number }
interface BalanceRow {
  id: number; name: string; bank: string; type: string;
  account_number: string | null;
  opening_balance: number; opening_balance_date: string | null;
  movement_since_opening: number; current_balance: number;
  fund_value?: number;
  total_value?: number;
  transactions_total_all_time?: number;
  first_transaction_date?: string | null;
  incognito?: boolean;
}

export default function Dashboard() {
  const qc = useQueryClient();
  const { role } = useAuth();
  const isStudent = role === "student";
  const [showReset, setShowReset] = useState(false);
  const [month, setMonth] = useState<string>(currentMonth());
  const [editBalanceFor, setEditBalanceFor] = useState<number | null>(null);
  const [breakdownMode, setBreakdownMode] = useState<"income" | "expense" | null>(null);
  const [balanceDraft, setBalanceDraft] = useState<{
    opening_balance: string;
    opening_balance_date: string;
  }>({ opening_balance: "", opening_balance_date: "" });
  const updateAccountMut = useMutation({
    mutationFn: (p: {
      id: number;
      opening_balance: number;
      opening_balance_date: string | null;
    }) =>
      api(`/accounts/${p.id}`, {
        method: "PATCH",
        body: JSON.stringify({
          opening_balance: p.opening_balance,
          opening_balance_date: p.opening_balance_date,
        }),
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["balances"] });
      qc.invalidateQueries({ queryKey: ["accounts"] });
      qc.invalidateQueries({ queryKey: ["ledger"] });
      setEditBalanceFor(null);
    },
  });

  const monthsQ = useQuery({
    queryKey: ["budget-months"],
    queryFn: () => api<{ months: MonthOption[] }>(`/budget/months`),
  });

  // Smart default: om aktuell månad saknar data, välj senaste månad med data.
  useEffect(() => {
    const months = monthsQ.data?.months ?? [];
    if (months.length === 0) return;
    const has = months.some((m) => m.month === month);
    if (!has) {
      setMonth(months[months.length - 1].month);
    }
  }, [monthsQ.data]); // eslint-disable-line react-hooks/exhaustive-deps

  const summaryQ = useQuery({
    queryKey: ["budget", month],
    queryFn: () => api<MonthSummary>(`/budget/${month}`),
  });
  // Saldo per konto för den valda månaden — as_of = sista dagen
  // i månaden (eller idag om det är innevarande månad). Matchar
  // månadsväljaren överst i Dashboard så saldot byter med den.
  const balancesAsOf = useMemo(() => {
    const todayYm = currentMonth();
    if (month === todayYm) return undefined; // default: idag
    const [y, m] = month.split("-").map(Number);
    // Sista dagen i månaden (nästa månads dag 0 = sista i denna)
    const last = new Date(y, m, 0);
    return `${last.getFullYear()}-${String(last.getMonth() + 1).padStart(2, "0")}-${String(last.getDate()).padStart(2, "0")}`;
  }, [month]);
  const balancesQ = useQuery({
    queryKey: ["balances", balancesAsOf ?? "today"],
    queryFn: () =>
      api<{ as_of: string; accounts: BalanceRow[]; total_balance: number }>(
        balancesAsOf
          ? `/balances/?as_of=${balancesAsOf}`
          : "/balances/",
      ),
  });
  const forecastQ = useQuery({
    queryKey: ["forecast", 6],
    queryFn: () => api<{ forecast: ForecastPoint[] }>(`/budget/forecast/cashflow?months=6`),
  });
  const anomaliesQ = useQuery({
    queryKey: ["anomalies", month],
    queryFn: () => api<{ month: string; anomalies: Anomaly[] }>(
      `/budget/anomalies/${month}`,
    ),
    enabled: !!month,
  });
  const familyQ = useQuery({
    queryKey: ["family", month],
    queryFn: () => api<FamilyBreakdown>(`/budget/family/${month}`),
    enabled: !!month,
  });
  const usersQ = useQuery({
    queryKey: ["users"],
    queryFn: () => api<HouseholdUser[]>("/users"),
  });
  const userNameById: Record<string, string> = {};
  for (const u of usersQ.data ?? []) userNameById[String(u.id)] = u.name;
  const resolveOwnerLabel = (key: string): string => {
    if (key === "gemensamt") return "Gemensamt";
    // Backend kan returnera antingen 'user_{id}' (när kontot har owner_id
    // eller owner-strängen matchar en User) eller en rå sträng som 'Evelina'
    // (manuell upcoming innan användaren är skapad i Settings).
    if (key.startsWith("user_")) {
      const id = key.slice(5);
      return userNameById[id] ?? `Användare ${id}`;
    }
    return key;
  };
  const ytdIncomeQ = useQuery({
    queryKey: ["ytd-income"],
    queryFn: () => api<YtdIncome>(`/budget/ytd-income`),
  });
  const netWorthQ = useQuery({
    queryKey: ["net-worth", 12],
    queryFn: () =>
      api<{ points: NetWorthPoint[]; current_debt: number }>(
        `/balances/net-worth?months=12`,
      ),
  });

  const s = summaryQ.data;
  const topExpenses = s ? s.lines.filter((l) => l.actual < 0).slice(0, 8) : [];
  const fc = forecastQ.data?.forecast ?? [];
  const availableMonths = monthsQ.data?.months ?? [];
  const hasAnyData = availableMonths.length > 0;

  return (
    <div className="p-3 md:p-6 space-y-4 md:space-y-5">
      <div className="flex items-start justify-between">
        <div>
          <h1 className="serif text-3xl leading-tight">Dashboard</h1>
          <div className="text-sm text-slate-700">
            {hasAnyData ? `${availableMonths.length} månader med data` : "Ingen data importerad ännu"}
          </div>
        </div>
        <div className="flex items-center gap-2">
          {hasAnyData && (
            <select
              value={month}
              onChange={(e) => setMonth(e.target.value)}
              className="border rounded-lg px-3 py-1.5 text-sm bg-white"
            >
              {availableMonths.map((m) => (
                <option key={m.month} value={m.month}>
                  {m.month} ({m.count})
                </option>
              ))}
            </select>
          )}
          {/* Elever får inte nollställa sin data — det är klassrumets-data
              och måste hanteras av läraren via lärar-panelen. */}
          {!isStudent && (
            <button
              onClick={() => setShowReset(true)}
              className="flex items-center gap-1.5 px-3 py-1.5 text-sm rounded-lg border border-rose-200 text-rose-600 bg-white hover:bg-rose-50"
              title="Nollställ all data"
            >
              <Trash2 className="w-4 h-4" />
              Nollställ
            </button>
          )}
        </div>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 md:gap-4">
        <button
          type="button"
          onClick={() => s && setBreakdownMode("income")}
          disabled={!s}
          className="text-left"
          title="Klicka för att se alla inkomstposter"
        >
          <Stat label="Inkomst" value={s ? formatSEK(s.income) : "—"} tone="good" />
        </button>
        <button
          type="button"
          onClick={() => s && setBreakdownMode("expense")}
          disabled={!s}
          className="text-left"
          title="Klicka för att se alla utgiftsposter"
        >
          <Stat label="Utgifter" value={s ? formatSEK(s.expenses) : "—"} tone="bad" />
        </button>
        <Stat label="Sparande" value={s ? formatSEK(s.savings) : "—"} tone={s && s.savings > 0 ? "good" : "bad"} />
        <Stat label="Sparkvot" value={s ? `${(s.savings_rate * 100).toFixed(1)} %` : "—"} />
      </div>

      {breakdownMode && (
        <MonthBreakdownModal
          month={month}
          mode={breakdownMode}
          onClose={() => setBreakdownMode(null)}
        />
      )}

      {/* Pedagogiska elev-vy-element (greeting, budget-bars, oväntade
          utgifter, uppdrag, streak, mastery). Tidigare bara i den
          separata EkoDashboard. Visas för båda elev OCH lärare-via-
          impersonation så vyn är konsistent. */}
      <StudentPedagogyCards month={month} />

      <HouseholdSplitQuiz />

      <HouseholdSummaryCard />

      <WellbeingCard />

      <InvitationsInbox />

      <EventInbox />

      <ClassLeaderboard />

      {ytdIncomeQ.data && ytdIncomeQ.data.grand_total > 0 && (
        <Card
          title={`Lön i år (${ytdIncomeQ.data.year})`}
          action={
            <span className="text-sm font-semibold">
              Totalt {formatSEK(ytdIncomeQ.data.grand_total)}
            </span>
          }
        >
          {!ytdIncomeQ.data.category_matched && (
            <div className="text-xs text-amber-700 mb-2">
              Inga transaktioner kategoriserade som "Lön" hittades — visar
              alla positiva inkomster som fallback. Sätt kategori "Lön" på dina
              lönerader för mer exakt siffra.
            </div>
          )}
          <div className="space-y-2">
            {Object.entries(ytdIncomeQ.data.by_owner).map(([key, v]) => {
              const label = resolveOwnerLabel(key);
              return (
                <div
                  key={key}
                  className="flex items-start justify-between py-2 border-b last:border-0"
                >
                  <div>
                    <div className="font-medium text-sm">{label}</div>
                    <div className="text-xs text-slate-700">
                      {v.count} inkomster · {v.accounts.map((a) => a.name).join(", ")}
                    </div>
                  </div>
                  <div className="text-sm font-semibold text-emerald-600">
                    {formatSEK(v.total)}
                  </div>
                </div>
              );
            })}
          </div>
        </Card>
      )}

      {balancesQ.data && balancesQ.data.accounts.length > 0 && (
        <Card
          title={`Saldo per konto — ${balancesQ.data.as_of}`}
          action={
            (() => {
              const incognitoCount = balancesQ.data.accounts.filter((a) => a.incognito).length;
              const visibleSum = balancesQ.data.accounts.reduce(
                (s, a) => s + (a.total_value ?? a.current_balance),
                0,
              );
              const totalApi = balancesQ.data.total_balance;
              const showNote = incognitoCount > 0 || Math.abs(visibleSum - totalApi) > 1;
              return (
                <div className="text-right">
                  <div className="text-sm font-semibold" title="Total nettoförmögenhet (exkl. inkognito-konton)">
                    Totalt {formatSEK(totalApi)}
                  </div>
                  {showNote && (
                    <div
                      className="text-[10px] text-slate-500"
                      title={`Summa av alla rader i tabellen: ${formatSEK(visibleSum)}. ${
                        incognitoCount > 0
                          ? "Inkognito-konton räknas inte med i nettoförmögenheten."
                          : ""
                      }`}
                    >
                      {incognitoCount > 0
                        ? `exkl. ${incognitoCount} inkognito-konto`
                        : `(summa i tabell: ${formatSEK(visibleSum)})`}
                    </div>
                  )}
                </div>
              );
            })()
          }
        >
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs uppercase text-slate-700 border-b">
                <th className="py-1.5 pr-3">Konto</th>
                <th className="py-1.5 pr-3 text-right">Ingående</th>
                <th className="py-1.5 pr-3 text-right">Rörelse</th>
                <th className="py-1.5 pr-3 text-right">Nuvarande saldo</th>
                <th className="py-1.5 pr-3"></th>
              </tr>
            </thead>
            <tbody>
              {balancesQ.data.accounts.map((a) => {
                const isEditing = editBalanceFor === a.id;
                return (
                  <React.Fragment key={a.id}>
                <tr className="border-b last:border-0">
                  <td className="py-1.5 pr-3">
                    <div className="font-medium">{a.name}</div>
                    <div className="text-xs text-slate-700">
                      {a.bank} · {a.type}
                      {a.opening_balance_date && ` · från ${a.opening_balance_date}`}
                    </div>
                  </td>
                  <td className="py-1.5 pr-3 text-right text-slate-700">
                    {a.opening_balance_date ? formatSEK(a.opening_balance) : "—"}
                  </td>
                  <td
                    className={`py-1.5 pr-3 text-right ${
                      a.movement_since_opening < 0 ? "text-rose-600" : "text-emerald-600"
                    }`}
                  >
                    {formatSEK(a.movement_since_opening)}
                  </td>
                  <td className="py-1.5 pr-3 text-right font-semibold">
                    {(a.fund_value ?? 0) > 0 ? (
                      <div>
                        <div>{formatSEK(a.total_value ?? a.current_balance)}</div>
                        <div className="text-xs font-normal text-slate-600">
                          cash {formatSEK(a.current_balance)} + fonder{" "}
                          {formatSEK(a.fund_value ?? 0)}
                        </div>
                      </div>
                    ) : (
                      formatSEK(a.current_balance)
                    )}
                  </td>
                  <td className="py-1.5 pr-3 text-right">
                    <button
                      onClick={() => {
                        if (isEditing) {
                          setEditBalanceFor(null);
                          return;
                        }
                        setEditBalanceFor(a.id);
                        setBalanceDraft({
                          opening_balance: String(a.opening_balance ?? 0),
                          opening_balance_date:
                            a.opening_balance_date ??
                            a.first_transaction_date ??
                            "",
                        });
                      }}
                      className="text-xs nav-link"
                      title="Justera ingående saldo + startdatum om saldot inte stämmer mot banken"
                    >
                      Justera
                    </button>
                  </td>
                </tr>
                {isEditing && (
                  <tr className="bg-amber-50 border-b">
                    <td colSpan={5} className="px-4 py-3">
                      <div className="text-xs text-slate-700 mb-2">
                        Stämmer inte saldot mot banken? Systemet räknar
                        <strong> opening_balance + alla transaktioner efter startdatum</strong>.
                        {" "}Om transactions_total_all_time ={" "}
                        <strong>{formatSEK(a.transactions_total_all_time ?? 0)}</strong>
                        {" "}ska du antingen sätta opening_balance = bank-saldo
                        - alla transaktioner (och datum = dagen före första
                        transaktionen, {a.first_transaction_date ?? "—"}),
                        eller opening_balance = 0 och startdatum = null om
                        du importerat hela historiken.
                      </div>
                      <div className="flex flex-wrap items-end gap-3 text-sm">
                        <label className="flex flex-col">
                          <span className="text-xs text-slate-700">Ingående saldo (kr)</span>
                          <input
                            type="number"
                            step="0.01"
                            value={balanceDraft.opening_balance}
                            onChange={(e) =>
                              setBalanceDraft({
                                ...balanceDraft,
                                opening_balance: e.target.value,
                              })
                            }
                            className="border rounded px-2 py-1 w-40"
                          />
                        </label>
                        <label className="flex flex-col">
                          <span className="text-xs text-slate-700">Startdatum (tomt = från början)</span>
                          <input
                            type="date"
                            value={balanceDraft.opening_balance_date}
                            onChange={(e) =>
                              setBalanceDraft({
                                ...balanceDraft,
                                opening_balance_date: e.target.value,
                              })
                            }
                            className="border rounded px-2 py-1"
                          />
                        </label>
                        <button
                          onClick={() =>
                            updateAccountMut.mutate({
                              id: a.id,
                              opening_balance: Number(balanceDraft.opening_balance || 0),
                              opening_balance_date:
                                balanceDraft.opening_balance_date || null,
                            })
                          }
                          disabled={updateAccountMut.isPending}
                          className="bg-brand-600 text-white px-3 py-1.5 rounded"
                        >
                          Spara
                        </button>
                        <button
                          onClick={() => setEditBalanceFor(null)}
                          className="px-3 py-1.5 rounded border border-slate-300 bg-white"
                        >
                          Avbryt
                        </button>
                      </div>
                    </td>
                  </tr>
                )}
                  </React.Fragment>
                );
              })}
            </tbody>
          </table>
          {!balancesQ.data.accounts.some((a) => a.opening_balance_date) && (
            <div className="text-xs text-slate-700 mt-2">
              Tips: ange ingående saldo + startdatum på varje konto (Import-sidan)
              för mer exakt saldo — just nu summeras bara alla transaktioner från 0.
            </div>
          )}
        </Card>
      )}

      <Card title={`Utgifter per kategori — ${month}`}>
        {topExpenses.length === 0 ? (
          <div className="text-sm text-slate-700">
            {hasAnyData
              ? "Inga utgifter i denna månad. Välj en annan i listan ovan."
              : "Ingen data ännu. Gå till Importera och ladda upp en CSV."}
          </div>
        ) : (
          <ResponsiveContainer width="100%" height={280}>
            <BarChart data={topExpenses.map((l) => ({ ...l, abs: Math.abs(l.actual) }))}>
              <XAxis dataKey="category" tick={{ fontSize: 12 }} />
              <YAxis tickFormatter={(v) => `${Math.round(v / 1000)}k`} />
              <Tooltip formatter={(v: number) => formatSEK(v)} />
              <Bar dataKey="abs" fill="#4f46e5" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        )}
      </Card>

      <div className="grid md:grid-cols-2 gap-4">
        <Card
          title={`Avvikelser — ${month}`}
          action={
            <span className="text-xs text-slate-700">
              z‑score mot 6 mån snitt
            </span>
          }
        >
          {anomaliesQ.isLoading ? (
            <div className="text-sm text-slate-700">Analyserar…</div>
          ) : !anomaliesQ.data || anomaliesQ.data.anomalies.length === 0 ? (
            <div className="text-sm text-slate-700">
              Inga större avvikelser denna månad — allt ligger inom 2σ av
              ditt vanliga mönster.
            </div>
          ) : (
            <ul className="space-y-2">
              {anomaliesQ.data.anomalies.slice(0, 5).map((a) => (
                <li
                  key={a.category}
                  className="flex items-start gap-3 text-sm"
                >
                  <span
                    className={`mt-0.5 w-7 h-7 rounded-full flex items-center justify-center ${
                      a.direction === "higher"
                        ? "bg-rose-50 text-rose-600"
                        : "bg-emerald-50 text-emerald-600"
                    }`}
                  >
                    {a.direction === "higher" ? (
                      <TrendingUp className="w-4 h-4" />
                    ) : (
                      <TrendingDown className="w-4 h-4" />
                    )}
                  </span>
                  <div className="flex-1 min-w-0">
                    <div className="font-medium truncate">{a.category}</div>
                    <div className="text-xs text-slate-700">
                      {formatSEK(a.current)} denna månad —{" "}
                      snitt {formatSEK(a.average)} (±{formatSEK(a.stdev)})
                    </div>
                  </div>
                  <span
                    className={`text-xs font-mono font-semibold ${
                      Math.abs(a.z_score) >= 3
                        ? "text-rose-600"
                        : "text-amber-600"
                    }`}
                  >
                    {a.z_score > 0 ? "+" : ""}
                    {a.z_score.toFixed(1)}σ
                  </span>
                </li>
              ))}
              {anomaliesQ.data.anomalies.length > 5 && (
                <li className="text-xs text-slate-700 pt-1">
                  …och {anomaliesQ.data.anomalies.length - 5} till
                </li>
              )}
            </ul>
          )}
        </Card>

        <Card
          title={`Familj — ${month}`}
          action={
            <span className="text-xs text-slate-700 inline-flex items-center gap-1">
              <Users className="w-3.5 h-3.5" />
              per ägare
            </span>
          }
        >
          {familyQ.isLoading ? (
            <div className="text-sm text-slate-700">Räknar…</div>
          ) : !familyQ.data ||
            Object.keys(familyQ.data.by_owner).length === 0 ? (
            <div className="text-sm text-slate-700">
              Ingen data denna månad. Koppla konton till ägare för att se
              vem som betalat vad.
            </div>
          ) : (
            <div className="space-y-3">
              {Object.entries(familyQ.data.by_owner).map(([key, v]) => {
                const label = resolveOwnerLabel(key);
                const net = v.income - v.expenses;
                return (
                  <div
                    key={key}
                    className="flex items-center justify-between py-2 border-b last:border-0"
                  >
                    <div>
                      <div className="font-medium text-sm">{label}</div>
                      <div className="text-xs text-slate-700">
                        In {formatSEK(v.income)} · Ut {formatSEK(v.expenses)}
                      </div>
                    </div>
                    <div
                      className={`text-sm font-semibold ${
                        net >= 0 ? "text-emerald-600" : "text-rose-600"
                      }`}
                    >
                      {net >= 0 ? "+" : ""}
                      {formatSEK(net)}
                    </div>
                  </div>
                );
              })}
              {Object.keys(familyQ.data.by_owner).length === 1 &&
                familyQ.data.by_owner["gemensamt"] && (
                  <div className="text-xs text-slate-700 flex items-start gap-1.5">
                    <AlertTriangle className="w-3.5 h-3.5 mt-0.5 flex-none" />
                    Alla konton saknar ägare. Sätt <code>owner_id</code> på
                    kontona för en "vem betalade vad"-vy.
                  </div>
                )}
            </div>
          )}
        </Card>
      </div>

      {/* Elpris-widgeten flyttad till /utility — naturlig plats där
          eleven också ser sin förbrukning. */}

      {netWorthQ.data && netWorthQ.data.points.length > 0 && (
        <Card
          title="Nettoförmögenhet (12 mån)"
          action={
            (() => {
              const pts = netWorthQ.data.points;
              const latest = pts[pts.length - 1];
              return (
                <span className="text-sm font-semibold">
                  {formatSEK(latest.net_worth)}
                </span>
              );
            })()
          }
        >
          <ResponsiveContainer width="100%" height={220}>
            <LineChart data={netWorthQ.data.points}>
              <XAxis
                dataKey="date"
                tickFormatter={(v) => v.slice(0, 7)}
                tick={{ fontSize: 11 }}
              />
              <YAxis tickFormatter={(v) => `${Math.round(v / 1000)}k`} />
              <Tooltip
                formatter={(v: number) => formatSEK(v)}
                labelFormatter={(v) => `Slutet av ${v}`}
              />
              <Legend />
              <Line
                type="monotone"
                dataKey="assets"
                name="Tillgångar"
                stroke="#10b981"
                strokeWidth={2}
                dot={false}
              />
              <Line
                type="monotone"
                dataKey="debt"
                name="Skuld"
                stroke="#ef4444"
                strokeWidth={2}
                dot={false}
              />
              <Line
                type="monotone"
                dataKey="net_worth"
                name="Netto"
                stroke="#4f46e5"
                strokeWidth={3}
              />
            </LineChart>
          </ResponsiveContainer>
          <div className="text-xs text-slate-700 mt-2">
            Tillgångar = summa alla bankkonton. Skuld = aktuellt lånesaldo
            (approximation — historisk låneutveckling kommer i framtida version).
          </div>
        </Card>
      )}

      <Card title="Kassaflödesprognos (6 mån)">
        {fc.length === 0 ? (
          <div className="text-sm text-slate-700">Behöver minst 2 månaders historik.</div>
        ) : (
          <ResponsiveContainer width="100%" height={240}>
            <LineChart data={fc}>
              <XAxis dataKey="month" />
              <YAxis tickFormatter={(v) => `${Math.round(v / 1000)}k`} />
              <Tooltip formatter={(v: number) => formatSEK(v)} />
              <Legend />
              <Line type="monotone" dataKey="income" stroke="#10b981" strokeWidth={2} />
              <Line type="monotone" dataKey="expenses" stroke="#ef4444" strokeWidth={2} />
              <Line type="monotone" dataKey="net" stroke="#4f46e5" strokeWidth={2} />
            </LineChart>
          </ResponsiveContainer>
        )}
      </Card>

      {showReset && !isStudent && <ResetDialog onClose={() => setShowReset(false)} />}
    </div>
  );
}

function MonthBreakdownModal({
  month,
  mode,
  onClose,
}: {
  month: string;
  mode: "income" | "expense";
  onClose: () => void;
}) {
  // Använd backend-endpointen som matchar EXAKT samma regler som
  // KPI-kortets summa: inga transfers, inga privata incognito-utgifter,
  // och inkluderar omatchade UpcomingTransaction (partnerlöner etc).
  type BreakdownItem = {
    id: number | string;
    date: string;
    description: string;
    amount: number;
    category_id: number | null;
    category: string | null;
    account: string | null;
    source: "transaction" | "upcoming";
  };

  const brQ = useQuery({
    queryKey: ["dashboard-breakdown", month, mode],
    queryFn: () =>
      api<{ items: BreakdownItem[]; total: number }>(
        `/budget/${month}/breakdown?kind=${mode}`,
      ),
  });

  const items = brQ.data?.items ?? [];
  const filtered = items;

  // Gruppera per kategori
  const byCat = new Map<string, BreakdownItem[]>();
  for (const it of filtered) {
    const name = it.category || "Okategoriserat";
    if (!byCat.has(name)) byCat.set(name, []);
    byCat.get(name)!.push(it);
  }
  const sortedCats = [...byCat.entries()].sort(
    ([, a], [, b]) => {
      const aSum = a.reduce((s, t) => s + Math.abs(t.amount), 0);
      const bSum = b.reduce((s, t) => s + Math.abs(t.amount), 0);
      return bSum - aSum;
    },
  );
  const total = filtered.reduce((s, t) => s + Math.abs(t.amount), 0);

  return (
    <div className="fixed inset-0 bg-black/40 flex items-start justify-center z-50 p-4 overflow-y-auto">
      <div className="bg-white rounded-lg shadow-xl max-w-4xl w-full my-8">
        <div className="flex items-center justify-between p-4 border-b">
          <div>
            <h2 className="text-lg font-semibold">
              {mode === "income" ? "Inkomst" : "Utgifter"} — {month}
            </h2>
            <div className="text-sm text-slate-700 mt-0.5">
              {filtered.length} poster · totalt {formatSEK(total)}
            </div>
          </div>
          <button onClick={onClose} className="text-slate-600 hover:text-slate-900">
            <Trash2 className="w-5 h-5 hidden" />
            ✕
          </button>
        </div>
        <div className="p-4 space-y-3">
          {brQ.isLoading ? (
            <div className="text-sm text-slate-700">Laddar…</div>
          ) : sortedCats.length === 0 ? (
            <div className="text-sm text-slate-700">Inga poster i denna månad.</div>
          ) : (
            sortedCats.map(([cat, items]) => (
              <CategoryBreakdownGroup
                key={cat}
                categoryName={cat}
                items={items}
                total={items.reduce((s, t) => s + Math.abs(t.amount), 0)}
              />
            ))
          )}
        </div>
        <div className="flex justify-end p-4 border-t">
          <button
            onClick={onClose}
            className="px-4 py-2 rounded border border-slate-300 bg-white text-sm"
          >
            Stäng
          </button>
        </div>
      </div>
    </div>
  );
}

type BreakdownRow = {
  id: number | string;
  date: string;
  description: string;
  amount: number;
  account: string | null;
  source: "transaction" | "upcoming";
};

function CategoryBreakdownGroup({
  categoryName,
  items,
  total,
}: {
  categoryName: string;
  items: BreakdownRow[];
  total: number;
}) {
  const [open, setOpen] = useState(false);
  return (
    <div className="border rounded">
      <button
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center justify-between p-2 hover:bg-slate-50 text-left text-sm"
      >
        <span className="font-medium">{categoryName}</span>
        <div className="flex items-center gap-2">
          <span className="text-xs text-slate-600">{items.length} st</span>
          <span className="font-semibold">{formatSEK(total)}</span>
          <span className="text-slate-500 text-xs">
            {open ? "▾" : "▸"}
          </span>
        </div>
      </button>
      {open && (
        <div className="border-t divide-y text-xs">
          {items
            .sort((a, b) => (a.date < b.date ? 1 : -1))
            .map((tx) => (
              <div key={tx.id} className="flex items-center gap-3 p-2">
                <span className="text-slate-700 w-20 shrink-0">{tx.date}</span>
                <span
                  className={
                    "w-24 text-right shrink-0 font-medium " +
                    (tx.amount < 0 ? "text-rose-600" : "text-emerald-700")
                  }
                >
                  {formatSEK(Math.abs(tx.amount))}
                </span>
                <span className="flex-1 min-w-0 truncate">
                  {tx.description}
                  {tx.source === "upcoming" && (
                    <span className="ml-2 inline-block text-[10px] bg-sky-100 text-sky-800 px-1 rounded">
                      planerat
                    </span>
                  )}
                </span>
              </div>
            ))}
        </div>
      )}
    </div>
  );
}
