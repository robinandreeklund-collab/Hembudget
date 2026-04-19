import { useQuery } from "@tanstack/react-query";
import { api, formatSEK } from "@/api/client";
import { Card, Stat } from "@/components/Card";
import { Bar, BarChart, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { ForecastPoint, MonthSummary } from "@/types/models";

function currentMonth(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

export default function Dashboard() {
  const month = currentMonth();
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

  return (
    <div className="p-6 space-y-5">
      <div>
        <h1 className="text-2xl font-semibold">Dashboard</h1>
        <div className="text-sm text-slate-500">Månad: {month}</div>
      </div>

      <div className="grid grid-cols-4 gap-4">
        <Stat label="Inkomst" value={s ? formatSEK(s.income) : "—"} tone="good" />
        <Stat label="Utgifter" value={s ? formatSEK(s.expenses) : "—"} tone="bad" />
        <Stat label="Sparande" value={s ? formatSEK(s.savings) : "—"} tone={s && s.savings > 0 ? "good" : "bad"} />
        <Stat label="Sparkvot" value={s ? `${(s.savings_rate * 100).toFixed(1)} %` : "—"} />
      </div>

      <Card title="Utgifter per kategori (denna månad)">
        {topExpenses.length === 0 ? (
          <div className="text-sm text-slate-500">Ingen data ännu. Importera en CSV.</div>
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
    </div>
  );
}
