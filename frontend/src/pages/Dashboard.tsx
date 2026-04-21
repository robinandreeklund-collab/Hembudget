import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Trash2 } from "lucide-react";
import { api, formatSEK } from "@/api/client";
import { Card, Stat } from "@/components/Card";
import { ResetDialog } from "@/components/ResetDialog";
import { Bar, BarChart, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { ForecastPoint, MonthSummary } from "@/types/models";

function currentMonth(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

interface MonthOption { month: string; count: number }

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
  const forecastQ = useQuery({
    queryKey: ["forecast", 6],
    queryFn: () => api<{ forecast: ForecastPoint[] }>(`/budget/forecast/cashflow?months=6`),
  });

  const s = summaryQ.data;
  const topExpenses = s ? s.lines.filter((l) => l.actual < 0).slice(0, 8) : [];
  const fc = forecastQ.data?.forecast ?? [];
  const availableMonths = monthsQ.data?.months ?? [];
  const hasAnyData = availableMonths.length > 0;

  return (
    <div className="p-6 space-y-5">
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

      <div className="grid grid-cols-4 gap-4">
        <Stat label="Inkomst" value={s ? formatSEK(s.income) : "—"} tone="good" />
        <Stat label="Utgifter" value={s ? formatSEK(s.expenses) : "—"} tone="bad" />
        <Stat label="Sparande" value={s ? formatSEK(s.savings) : "—"} tone={s && s.savings > 0 ? "good" : "bad"} />
        <Stat label="Sparkvot" value={s ? `${(s.savings_rate * 100).toFixed(1)} %` : "—"} />
      </div>

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
