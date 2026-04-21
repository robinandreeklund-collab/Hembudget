import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import {
  AlertTriangle, Trash2, TrendingDown, TrendingUp, Users, Zap,
} from "lucide-react";
import { api, formatSEK } from "@/api/client";
import { Card, Stat } from "@/components/Card";
import { ResetDialog } from "@/components/ResetDialog";
import { Bar, BarChart, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { ForecastPoint, MonthSummary } from "@/types/models";

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

interface ElprisHour {
  start: string;
  end: string;
  sek_per_kwh: number;
  sek_per_kwh_inc_vat: number;
}

interface ElprisDay {
  date: string;
  zone: string;
  avg_sek_per_kwh_inc_vat: number;
  cheapest_hours: Array<{ start: string; end: string; sek_per_kwh_inc_vat: number }>;
  hours: ElprisHour[];
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
}

export default function Dashboard() {
  const [showReset, setShowReset] = useState(false);
  const [month, setMonth] = useState<string>(currentMonth());

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
  const balancesQ = useQuery({
    queryKey: ["balances"],
    queryFn: () =>
      api<{ as_of: string; accounts: BalanceRow[]; total_balance: number }>(
        "/balances/",
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
  const elprisZone = (localStorage.getItem("elpris_zone") || "SE3") as
    | "SE1" | "SE2" | "SE3" | "SE4";
  const elprisQ = useQuery({
    queryKey: ["elpris", "today", elprisZone],
    queryFn: () => api<ElprisDay>(`/elpris/today?zone=${elprisZone}`),
    retry: false,
  });
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
          <h1 className="text-2xl font-semibold">Dashboard</h1>
          <div className="text-sm text-slate-500">
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
          <button
            onClick={() => setShowReset(true)}
            className="flex items-center gap-1.5 px-3 py-1.5 text-sm rounded-lg border border-rose-200 text-rose-600 bg-white hover:bg-rose-50"
            title="Nollställ all data"
          >
            <Trash2 className="w-4 h-4" />
            Nollställ
          </button>
        </div>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 md:gap-4">
        <Stat label="Inkomst" value={s ? formatSEK(s.income) : "—"} tone="good" />
        <Stat label="Utgifter" value={s ? formatSEK(s.expenses) : "—"} tone="bad" />
        <Stat label="Sparande" value={s ? formatSEK(s.savings) : "—"} tone={s && s.savings > 0 ? "good" : "bad"} />
        <Stat label="Sparkvot" value={s ? `${(s.savings_rate * 100).toFixed(1)} %` : "—"} />
      </div>

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
              const label =
                key === "gemensamt"
                  ? "Gemensamt konto"
                  : key.replace("user_", "Användare ");
              return (
                <div
                  key={key}
                  className="flex items-start justify-between py-2 border-b last:border-0"
                >
                  <div>
                    <div className="font-medium text-sm">{label}</div>
                    <div className="text-xs text-slate-500">
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
            <span className="text-sm font-semibold">
              Totalt {formatSEK(balancesQ.data.total_balance)}
            </span>
          }
        >
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs uppercase text-slate-500 border-b">
                <th className="py-1.5 pr-3">Konto</th>
                <th className="py-1.5 pr-3 text-right">Ingående</th>
                <th className="py-1.5 pr-3 text-right">Rörelse</th>
                <th className="py-1.5 pr-3 text-right">Nuvarande saldo</th>
              </tr>
            </thead>
            <tbody>
              {balancesQ.data.accounts.map((a) => (
                <tr key={a.id} className="border-b last:border-0">
                  <td className="py-1.5 pr-3">
                    <div className="font-medium">{a.name}</div>
                    <div className="text-xs text-slate-500">
                      {a.bank} · {a.type}
                      {a.opening_balance_date && ` · från ${a.opening_balance_date}`}
                    </div>
                  </td>
                  <td className="py-1.5 pr-3 text-right text-slate-500">
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
                    {formatSEK(a.current_balance)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {!balancesQ.data.accounts.some((a) => a.opening_balance_date) && (
            <div className="text-xs text-slate-500 mt-2">
              Tips: ange ingående saldo + startdatum på varje konto (Import-sidan)
              för mer exakt saldo — just nu summeras bara alla transaktioner från 0.
            </div>
          )}
        </Card>
      )}

      <Card title={`Utgifter per kategori — ${month}`}>
        {topExpenses.length === 0 ? (
          <div className="text-sm text-slate-500">
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
            <span className="text-xs text-slate-500">
              z‑score mot 6 mån snitt
            </span>
          }
        >
          {anomaliesQ.isLoading ? (
            <div className="text-sm text-slate-500">Analyserar…</div>
          ) : !anomaliesQ.data || anomaliesQ.data.anomalies.length === 0 ? (
            <div className="text-sm text-slate-500">
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
                    <div className="text-xs text-slate-500">
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
                <li className="text-xs text-slate-500 pt-1">
                  …och {anomaliesQ.data.anomalies.length - 5} till
                </li>
              )}
            </ul>
          )}
        </Card>

        <Card
          title={`Familj — ${month}`}
          action={
            <span className="text-xs text-slate-500 inline-flex items-center gap-1">
              <Users className="w-3.5 h-3.5" />
              per ägare
            </span>
          }
        >
          {familyQ.isLoading ? (
            <div className="text-sm text-slate-500">Räknar…</div>
          ) : !familyQ.data ||
            Object.keys(familyQ.data.by_owner).length === 0 ? (
            <div className="text-sm text-slate-500">
              Ingen data denna månad. Koppla konton till ägare för att se
              vem som betalat vad.
            </div>
          ) : (
            <div className="space-y-3">
              {Object.entries(familyQ.data.by_owner).map(([key, v]) => {
                const label = key === "gemensamt" ? "Gemensamt" : key.replace("user_", "Användare ");
                const net = v.income - v.expenses;
                return (
                  <div
                    key={key}
                    className="flex items-center justify-between py-2 border-b last:border-0"
                  >
                    <div>
                      <div className="font-medium text-sm">{label}</div>
                      <div className="text-xs text-slate-500">
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
                  <div className="text-xs text-slate-500 flex items-start gap-1.5">
                    <AlertTriangle className="w-3.5 h-3.5 mt-0.5 flex-none" />
                    Alla konton saknar ägare. Sätt <code>owner_id</code> på
                    kontona för en "vem betalade vad"-vy.
                  </div>
                )}
            </div>
          )}
        </Card>
      </div>

      {elprisQ.data && elprisQ.data.hours.length > 0 && (
        <Card
          title={`Elpris idag — ${elprisQ.data.zone}`}
          action={
            <div className="flex items-center gap-2 text-xs">
              <span className="text-slate-500">Snitt</span>
              <span className="font-semibold">
                {(elprisQ.data.avg_sek_per_kwh_inc_vat * 100).toFixed(0)} öre/kWh
              </span>
              <select
                value={elprisZone}
                onChange={(e) => {
                  localStorage.setItem("elpris_zone", e.target.value);
                  location.reload();
                }}
                className="border rounded px-1.5 py-0.5 text-xs"
              >
                <option value="SE1">SE1</option>
                <option value="SE2">SE2</option>
                <option value="SE3">SE3</option>
                <option value="SE4">SE4</option>
              </select>
            </div>
          }
        >
          <ResponsiveContainer width="100%" height={160}>
            <BarChart
              data={elprisQ.data.hours.map((h) => ({
                hour: new Date(h.start).getHours(),
                öre: Math.round(h.sek_per_kwh_inc_vat * 100),
              }))}
            >
              <XAxis dataKey="hour" tick={{ fontSize: 11 }} />
              <YAxis tick={{ fontSize: 11 }} tickFormatter={(v) => `${v}`} />
              <Tooltip
                formatter={(v: number) => `${v} öre/kWh`}
                labelFormatter={(h) => `Timme ${h}:00`}
              />
              <Bar dataKey="öre" fill="#4f46e5" radius={[2, 2, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
          <div className="mt-2 text-xs text-slate-600">
            <Zap className="inline w-3.5 h-3.5 mr-1 text-amber-500" />
            Billigaste timmar:{" "}
            {elprisQ.data.cheapest_hours.map((h) => {
              const hr = new Date(h.start).getHours();
              return (
                <span key={h.start} className="mx-1 font-mono">
                  {String(hr).padStart(2, "0")}:00 ({(h.sek_per_kwh_inc_vat * 100).toFixed(0)}öre)
                </span>
              );
            })}
          </div>
        </Card>
      )}

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
          <div className="text-xs text-slate-500 mt-2">
            Tillgångar = summa alla bankkonton. Skuld = aktuellt lånesaldo
            (approximation — historisk låneutveckling kommer i framtida version).
          </div>
        </Card>
      )}

      <Card title="Kassaflödesprognos (6 mån)">
        {fc.length === 0 ? (
          <div className="text-sm text-slate-500">Behöver minst 2 månaders historik.</div>
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

      {showReset && <ResetDialog onClose={() => setShowReset(false)} />}
    </div>
  );
}
