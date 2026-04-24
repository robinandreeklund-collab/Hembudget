import { useEffect, useState } from "react";
import {
  Briefcase, Coins, PiggyBank, TrendingUp, Wallet,
} from "lucide-react";

/**
 * En animerad mock av elevens dashboard som visas i landningssidans hero.
 * Siffror räknar upp, budget-staplar fylls, transaktioner tickar in.
 * Helt inline — ingen riktig data.
 */
export default function DashboardPreview() {
  const [tick, setTick] = useState(0);
  useEffect(() => {
    const t = setInterval(() => setTick((x) => (x + 1) % 4), 2500);
    return () => clearInterval(t);
  }, []);

  const budgets = [
    { label: "Mat", spent: [3200, 4100, 4800, 5100], budget: 5000 },
    { label: "Nöje", spent: [800, 1200, 1600, 2100], budget: 1500 },
    { label: "Transport", spent: [600, 950, 1050, 1100], budget: 1200 },
  ];

  const netIncome = 22840;
  const spentVals = [8400, 12300, 16800, 18500];

  return (
    <div className="bg-white rounded-2xl shadow-2xl border border-slate-200 overflow-hidden">
      {/* Fejk-toolbar */}
      <div className="bg-slate-100 px-4 py-2 border-b flex items-center gap-1.5">
        <div className="w-2.5 h-2.5 rounded-full bg-rose-400" />
        <div className="w-2.5 h-2.5 rounded-full bg-amber-400" />
        <div className="w-2.5 h-2.5 rounded-full bg-emerald-400" />
        <div className="flex-1 text-center text-xs text-slate-500 font-mono">
          ekonomilabbet.org/dashboard
        </div>
      </div>

      <div className="p-5 space-y-4">
        {/* Header med elevdata */}
        <div>
          <div className="text-xs text-slate-500">
            <Briefcase className="inline w-3 h-3 mr-1" />
            Undersköterska · Region Stockholm
          </div>
          <div className="text-xl font-bold text-slate-900">
            Hej Anna!
          </div>
        </div>

        {/* KPI-rad */}
        <div className="grid grid-cols-3 gap-2">
          <KpiMini
            icon={<Coins className="w-4 h-4 text-emerald-600" />}
            label="Nettolön"
            value={netIncome}
            bg="bg-emerald-50"
          />
          <KpiMini
            icon={<Wallet className="w-4 h-4 text-slate-600" />}
            label="Utgifter"
            value={spentVals[tick]}
            bg="bg-slate-50"
          />
          <KpiMini
            icon={<PiggyBank className="w-4 h-4 text-brand-600" />}
            label="Sparat"
            value={1500 + tick * 200}
            bg="bg-brand-50"
          />
        </div>

        {/* Budget-staplar */}
        <div className="space-y-2">
          <div className="text-xs font-medium text-slate-600 flex items-center gap-1">
            <TrendingUp className="w-3 h-3" /> Budget april 2026
          </div>
          {budgets.map((b) => {
            const pct = Math.min(
              150,
              Math.round((b.spent[tick] / b.budget) * 100),
            );
            const over = pct > 100;
            return (
              <div key={b.label}>
                <div className="flex justify-between text-xs mb-0.5">
                  <span className="text-slate-700">{b.label}</span>
                  <span
                    className={over ? "text-rose-600 font-medium" : "text-slate-500"}
                  >
                    {b.spent[tick].toLocaleString("sv-SE")} / {b.budget.toLocaleString("sv-SE")} kr
                  </span>
                </div>
                <div className="h-2 bg-slate-100 rounded overflow-hidden">
                  <div
                    className={`h-full rounded transition-all duration-1000 ease-out ${
                      over
                        ? "bg-rose-500"
                        : pct > 85
                        ? "bg-amber-500"
                        : "bg-emerald-500"
                    }`}
                    style={{ width: `${Math.min(100, pct)}%` }}
                  />
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

function KpiMini({
  icon, label, value, bg,
}: { icon: React.ReactNode; label: string; value: number; bg: string }) {
  return (
    <div className={`${bg} rounded-lg p-2`}>
      <div className="flex items-center gap-1 text-[10px] text-slate-600 mb-0.5">
        {icon} {label}
      </div>
      <div className="text-sm font-bold text-slate-800 tabular-nums transition-all">
        {value.toLocaleString("sv-SE")} kr
      </div>
    </div>
  );
}
