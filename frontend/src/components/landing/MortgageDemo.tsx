import { useEffect, useState } from "react";
import { Home, Lock, TrendingUp } from "lucide-react";

/**
 * Animerad demo av bolåne-beslutet:
 * - Visar en ränte-graf (historiska data)
 * - Eleven väljer rörlig eller bunden
 * - Facit: visar kostnaden efter horisonten
 */
export default function MortgageDemo() {
  const [step, setStep] = useState(0); // 0 = graf, 1 = välj, 2 = facit
  const [selected, setSelected] = useState<"rorlig" | "3ar" | null>(null);

  useEffect(() => {
    const t = setInterval(() => {
      setStep((x) => {
        const next = (x + 1) % 3;
        if (next === 1) setSelected("3ar");
        if (next === 0) setSelected(null);
        return next;
      });
    }, 3000);
    return () => clearInterval(t);
  }, []);

  // Simulerad ränte-timeline 2022-2025 (policy + spread ~1,5pp)
  const rates = [
    0.015, 0.020, 0.025, 0.030, 0.035, 0.040, 0.045, 0.050,
    0.055, 0.058, 0.060, 0.058, 0.055, 0.050, 0.045, 0.040,
  ];
  const maxR = Math.max(...rates);
  const minR = Math.min(...rates);

  return (
    <div className="bg-white rounded-2xl shadow-xl border border-slate-200 p-5 h-full min-h-[380px] flex flex-col">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2 text-sm font-semibold text-slate-700">
          <Home className="w-4 h-4 text-brand-600" /> Bolåne-beslut 2023
        </div>
        <div className="text-xs text-slate-500">
          {step === 0 && "Studera räntan"}
          {step === 1 && "Välj strategi"}
          {step === 2 && "Facit 2 år senare"}
        </div>
      </div>

      {/* Ränte-graf */}
      <div className="bg-slate-50 rounded-lg p-3 mb-3">
        <div className="text-[10px] text-slate-500 mb-1">
          Rörlig bolåneränta
        </div>
        <svg viewBox="0 0 240 60" className="w-full h-16" preserveAspectRatio="none">
          <polyline
            points={rates
              .map((r, i) => {
                const x = (i / (rates.length - 1)) * 240;
                const y = 60 - ((r - minR) / (maxR - minR)) * 55;
                return `${x},${y}`;
              })
              .join(" ")}
            fill="none"
            stroke="#0ea5e9"
            strokeWidth="2"
          />
          {/* Markör för beslutsmånad */}
          <line
            x1="90" y1="0" x2="90" y2="60"
            stroke="#f59e0b" strokeWidth="1" strokeDasharray="3 2"
          />
        </svg>
        <div className="flex justify-between text-[10px] text-slate-500 mt-1">
          <span>2022</span>
          <span className="text-amber-600 font-medium">↑ Mars 2023</span>
          <span>2025</span>
        </div>
      </div>

      {/* Val-kort */}
      <div className="grid grid-cols-2 gap-2 mb-3">
        <ChoiceCard
          label="Rörlig"
          rate={4.5}
          selected={selected === "rorlig"}
          highlight={step === 2 && selected !== "rorlig"}
          result={step === 2 ? "224 000 kr" : undefined}
        />
        <ChoiceCard
          label="Bind 3 år"
          rate={4.2}
          selected={selected === "3ar"}
          highlight={step === 2 && selected === "3ar"}
          result={step === 2 ? "168 000 kr" : undefined}
          best={step === 2}
        />
      </div>

      {step === 2 && (
        <div className="bg-emerald-50 border-l-4 border-emerald-500 rounded p-2.5 text-xs text-emerald-900 animate-fadeup flex items-start gap-2">
          <TrendingUp className="w-4 h-4 shrink-0 mt-0.5" />
          <div>
            <strong>Bra val!</strong> Du sparade 56 000 kr mot rörlig.
            Räntan steg rejält under perioden.
          </div>
        </div>
      )}
    </div>
  );
}

function ChoiceCard({
  label, rate, selected, highlight, result, best,
}: {
  label: string; rate: number;
  selected: boolean; highlight?: boolean;
  result?: string; best?: boolean;
}) {
  return (
    <div
      className={`rounded-lg p-3 border-2 transition-all ${
        best
          ? "border-emerald-500 bg-emerald-50"
          : selected
          ? "border-brand-500 bg-brand-50"
          : "border-slate-200 bg-white"
      }`}
    >
      <div className="flex items-center justify-between">
        <span className="text-sm font-medium text-slate-700">{label}</span>
        {selected && <Lock className="w-3.5 h-3.5 text-brand-600" />}
      </div>
      <div className="text-lg font-bold text-slate-900 mt-1">
        {rate.toFixed(2)}%
      </div>
      {result && (
        <div
          className={`text-xs mt-1 ${
            best ? "text-emerald-700 font-semibold" : "text-slate-500"
          }`}
        >
          Kostnad: {result}
        </div>
      )}
    </div>
  );
}
