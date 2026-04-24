import { useEffect, useState } from "react";
import { AlertTriangle, Target, TrendingDown } from "lucide-react";

/**
 * Visar hur eleven sätter en budget och sedan ser verkligheten — med en
 * oväntad händelse som knockar budgeten, följt av insikt.
 */
export default function BudgetDemo() {
  const [step, setStep] = useState(0); // 0 = sätter budget, 1 = månaden rullar, 2 = overshoot!, 3 = insikt
  useEffect(() => {
    const t = setInterval(() => setStep((x) => (x + 1) % 4), 2600);
    return () => clearInterval(t);
  }, []);

  const rows = [
    {
      label: "Mat",
      budget: 5000,
      spent: [0, 3200, 4800, 4800],
    },
    {
      label: "Shopping",
      budget: 1500,
      spent: [0, 900, 3400, 3400], // overshoot!
    },
    {
      label: "Transport",
      budget: 1200,
      spent: [0, 700, 950, 950],
    },
  ];

  return (
    <div className="bg-white rounded-2xl shadow-xl border border-slate-200 p-5 h-full min-h-[380px] flex flex-col">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2 text-sm font-semibold text-slate-700">
          <Target className="w-4 h-4 text-brand-600" /> Din budget
        </div>
        <div className="text-xs text-slate-500">
          {step === 0 && "Sätter budget…"}
          {step === 1 && "Vecka 2"}
          {step === 2 && "Vecka 3"}
          {step === 3 && "Slutet av månaden"}
        </div>
      </div>

      <ul className="space-y-3 flex-1">
        {rows.map((r) => {
          const spent = r.spent[step];
          const pct = Math.min(160, Math.round((spent / r.budget) * 100));
          const over = spent > r.budget;
          return (
            <li key={r.label}>
              <div className="flex justify-between text-xs mb-1">
                <span className="font-medium text-slate-700">{r.label}</span>
                <span
                  className={
                    over
                      ? "text-rose-600 font-bold"
                      : pct > 85
                      ? "text-amber-600"
                      : "text-slate-600"
                  }
                >
                  {spent.toLocaleString("sv-SE")} /{" "}
                  {r.budget.toLocaleString("sv-SE")} kr
                </span>
              </div>
              <div className="h-3 bg-slate-100 rounded-full overflow-hidden relative">
                {/* Budget-marker */}
                <div
                  className="absolute top-0 bottom-0 w-0.5 bg-slate-400 z-10"
                  style={{ left: `${Math.min(100, 100)}%` }}
                />
                <div
                  className={`h-full rounded-full transition-all duration-1000 ease-out ${
                    over
                      ? "bg-rose-500"
                      : pct > 85
                      ? "bg-amber-500"
                      : "bg-emerald-500"
                  }`}
                  style={{ width: `${Math.min(100, pct)}%` }}
                />
              </div>
            </li>
          );
        })}
      </ul>

      {step >= 2 && (
        <div className="mt-3 flex items-start gap-2 bg-rose-50 border-l-4 border-rose-400 rounded p-2.5 text-xs text-rose-900 animate-fadeup">
          <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" />
          <div>
            <strong>En trasig diskmaskin!</strong> Shopping-budgeten sprängdes
            med 1&nbsp;900 kr.
          </div>
        </div>
      )}
      {step === 3 && (
        <div className="mt-2 flex items-start gap-2 bg-emerald-50 border-l-4 border-emerald-500 rounded p-2.5 text-xs text-emerald-900 animate-fadeup">
          <TrendingDown className="w-4 h-4 shrink-0 mt-0.5" />
          <div>
            <strong>Lärdom:</strong> Utan buffertsparande hamnar du på minus.
          </div>
        </div>
      )}
    </div>
  );
}
