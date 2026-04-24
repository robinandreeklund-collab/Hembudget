import { useEffect, useState } from "react";
import {
  AlertTriangle,
  BookOpenCheck,
  Coins,
  Flame,
  PiggyBank,
  TrendingDown,
  TrendingUp,
  Wallet,
} from "lucide-react";
import { api } from "@/api/client";
import { AssignmentList } from "@/components/AssignmentList";

type DashboardRow = { category: string; budget: number; spent: number; pct: number };
type Overshoot = {
  date: string;
  description: string;
  amount: number;
  category_hint: string | null;
};

type Dashboard = {
  year_month: string;
  net_income: number;
  total_spent: number;
  balance: number;
  savings_done: number;
  savings_goal: number | null;
  category_rows: DashboardRow[];
  recent_overshoots: Overshoot[];
  assignments_done: number;
  assignments_total: number;
  personality: string;
  profession: string;
  display_name: string;
};

const formatKr = (n: number): string =>
  n.toLocaleString("sv-SE") + " kr";

function thisMonth(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

export default function EkoDashboard() {
  const [data, setData] = useState<Dashboard | null>(null);
  const [month, setMonth] = useState(thisMonth());
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    api<Dashboard>(`/student/dashboard?year_month=${month}`)
      .then(setData)
      .catch((e) => setErr(e instanceof Error ? e.message : String(e)));
  }, [month]);

  if (err) {
    return (
      <div className="p-6">
        <div className="bg-rose-50 text-rose-700 border border-rose-200 rounded p-3">
          {err}
        </div>
      </div>
    );
  }
  if (!data) {
    return <div className="p-6 text-slate-500">Laddar…</div>;
  }

  const overBudgetCount = data.category_rows.filter((r) => r.pct > 100).length;

  return (
    <div className="p-6 max-w-6xl mx-auto space-y-6">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-2xl font-bold">
            Hej {data.display_name.split(" ")[0]}!
          </h1>
          <p className="text-sm text-slate-600">
            Du är {data.profession.toLowerCase()} — {data.personality} typ.
          </p>
        </div>
        <select
          value={month}
          onChange={(e) => setMonth(e.target.value)}
          className="border rounded px-3 py-1.5"
        >
          {[0, 1, 2, 3, 4, 5].map((back) => {
            const d = new Date();
            d.setMonth(d.getMonth() - back);
            const ym = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
            return <option key={ym} value={ym}>{ym}</option>;
          })}
        </select>
      </div>

      {/* Toppkort */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
        <KpiCard
          icon={<Coins className="w-5 h-5 text-emerald-600" />}
          label="Nettolön"
          value={formatKr(data.net_income)}
          bgClass="bg-emerald-50"
        />
        <KpiCard
          icon={<Wallet className="w-5 h-5 text-slate-600" />}
          label="Utgifter"
          value={formatKr(data.total_spent)}
          bgClass="bg-slate-50"
        />
        <KpiCard
          icon={<PiggyBank className="w-5 h-5 text-brand-600" />}
          label="Sparat"
          value={
            data.savings_goal
              ? `${formatKr(data.savings_done)} / ${formatKr(data.savings_goal)}`
              : formatKr(data.savings_done)
          }
          bgClass="bg-brand-50"
        />
        <KpiCard
          icon={
            data.balance >= 0 ? (
              <TrendingUp className="w-5 h-5 text-emerald-600" />
            ) : (
              <TrendingDown className="w-5 h-5 text-rose-600" />
            )
          }
          label={data.balance >= 0 ? "Överskott" : "Underskott"}
          value={formatKr(Math.abs(data.balance))}
          bgClass={data.balance >= 0 ? "bg-emerald-50" : "bg-rose-50"}
        />
      </div>

      {/* Budget-status */}
      <section className="bg-white rounded-xl border p-4 space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="font-semibold text-lg">Budget denna månad</h2>
          {overBudgetCount > 0 && (
            <span className="text-xs text-rose-600 flex items-center gap-1">
              <AlertTriangle className="w-4 h-4" />
              {overBudgetCount} överskridna
            </span>
          )}
        </div>
        {data.category_rows.length === 0 ? (
          <p className="text-sm text-slate-500">
            Ingen budget satt för denna månad.
          </p>
        ) : (
          <ul className="space-y-2">
            {data.category_rows.map((r) => (
              <li key={r.category} className="text-sm">
                <div className="flex items-center justify-between mb-0.5">
                  <span>{r.category}</span>
                  <span
                    className={
                      r.pct > 100
                        ? "text-rose-600 font-medium"
                        : r.pct > 80
                        ? "text-amber-600"
                        : "text-slate-600"
                    }
                  >
                    {formatKr(r.spent)} / {formatKr(r.budget)} ({r.pct}%)
                  </span>
                </div>
                <div className="h-2 bg-slate-100 rounded">
                  <div
                    className={`h-full rounded ${
                      r.pct > 100
                        ? "bg-rose-500"
                        : r.pct > 80
                        ? "bg-amber-500"
                        : "bg-emerald-500"
                    }`}
                    style={{ width: `${Math.min(r.pct, 100)}%` }}
                  />
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>

      {/* Överraskande utgifter */}
      {data.recent_overshoots.length > 0 && (
        <section className="bg-white rounded-xl border p-4 space-y-3">
          <h2 className="font-semibold text-lg flex items-center gap-2">
            <Flame className="w-5 h-5 text-amber-500" />
            Oväntade utgifter denna månad
          </h2>
          <p className="text-sm text-slate-600">
            Livet händer! Så här har det sett ut:
          </p>
          <ul className="divide-y">
            {data.recent_overshoots.map((o, i) => (
              <li key={i} className="py-2 flex items-center justify-between text-sm">
                <span>
                  <span className="text-slate-500 text-xs mr-2">{o.date}</span>
                  {o.description}
                </span>
                <span className="font-semibold text-rose-600">
                  -{formatKr(o.amount)}
                </span>
              </li>
            ))}
          </ul>
        </section>
      )}

      {/* Uppdrag */}
      <section className="bg-white rounded-xl border p-4 space-y-3">
        <h2 className="font-semibold text-lg flex items-center gap-2">
          <BookOpenCheck className="w-5 h-5 text-brand-600" />
          Uppdrag ({data.assignments_done}/{data.assignments_total} klara)
        </h2>
        <AssignmentList />
      </section>
    </div>
  );
}

function KpiCard({
  icon, label, value, bgClass,
}: { icon: React.ReactNode; label: string; value: string; bgClass: string }) {
  return (
    <div className={`${bgClass} rounded-lg p-4`}>
      <div className="flex items-center gap-2 text-xs text-slate-600 mb-1">
        {icon} {label}
      </div>
      <div className="text-xl font-bold text-slate-800">{value}</div>
    </div>
  );
}
