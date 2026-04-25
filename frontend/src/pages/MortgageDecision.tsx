import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { AlertCircle, Check, Home, TrendingDown, TrendingUp } from "lucide-react";
import { api } from "@/api/client";

type RatePoint = { year_month: string; rate: number };
type Series = { rate_type: string; points: RatePoint[] };

type Assignment = {
  id: number;
  title: string;
  description: string;
  kind: string;
  params: Record<string, unknown> | null;
};

type Outcome = {
  chosen: string;
  decision_month: string;
  horizon_months: number;
  principal: number;
  locked_rate: number | null;
  cost_rorlig: number;
  cost_3ar: number;
  cost_5ar: number;
  cost_chosen: number;
  best_choice: string;
  diff_vs_best: number;
  horizon_completed: boolean;
};

const formatKr = (n: number) =>
  n.toLocaleString("sv-SE", { maximumFractionDigits: 0 }) + " kr";
const formatPct = (r: number) => (r * 100).toFixed(2) + " %";

export default function MortgageDecision() {
  const { assignmentId } = useParams<{ assignmentId: string }>();
  const aid = parseInt(assignmentId ?? "0", 10);
  const [assignment, setAssignment] = useState<Assignment | null>(null);
  const [series, setSeries] = useState<Series | null>(null);
  const [outcome, setOutcome] = useState<Outcome | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function loadAll() {
    try {
      const list = await api<Assignment[]>("/student/assignments");
      setAssignment(list.find((a) => a.id === aid) ?? null);
      const s = await api<Series>("/school/rates/bolan_rorlig");
      setSeries(s);
      try {
        const o = await api<Outcome>(`/student/mortgage/${aid}/outcome`);
        setOutcome(o);
      } catch {
        setOutcome(null);
      }
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    }
  }

  useEffect(() => {
    loadAll();
  }, [aid]);

  async function choose(chosen: string) {
    setSubmitting(true);
    setErr(null);
    try {
      await api("/student/mortgage/choose", {
        method: "POST",
        body: JSON.stringify({ assignment_id: aid, chosen }),
      });
      await loadAll();
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setSubmitting(false);
    }
  }

  if (!assignment) {
    return <div className="p-6 text-slate-500">Laddar uppdraget…</div>;
  }

  const params = assignment.params ?? {};
  const dm = (params.decision_month as string) || "—";
  const horizon = params.horizon_months as number;
  const principal = params.principal as number;
  const hasDecided = !!outcome;

  // Enkel graf: hitta min/max och rita SVG
  const chartHeight = 160;
  const chartWidth = 600;
  let polyline = "";
  if (series && series.points.length > 0) {
    const rates = series.points.map((p) => p.rate);
    const min = Math.min(...rates);
    const max = Math.max(...rates);
    const range = max - min || 0.01;
    polyline = series.points
      .map((p, i) => {
        const x = (i / (series.points.length - 1)) * chartWidth;
        const y = chartHeight - ((p.rate - min) / range) * chartHeight;
        return `${x.toFixed(1)},${y.toFixed(1)}`;
      })
      .join(" ");
  }

  return (
    <div className="p-6 max-w-4xl mx-auto space-y-6">
      <div className="flex items-center gap-2">
        <Home className="w-6 h-6 text-brand-600" />
        <h1 className="serif text-3xl leading-tight">{assignment.title}</h1>
      </div>
      <p className="text-slate-700">{assignment.description}</p>

      <section className="bg-white border rounded-xl p-4 space-y-2">
        <h2 className="font-semibold">Grunddata</h2>
        <div className="grid grid-cols-3 gap-4 text-sm">
          <div>
            <div className="text-slate-500 text-xs">Beslutsmånad</div>
            <div className="font-semibold">{dm}</div>
          </div>
          <div>
            <div className="text-slate-500 text-xs">Lånebelopp</div>
            <div className="font-semibold">{formatKr(principal ?? 0)}</div>
          </div>
          <div>
            <div className="text-slate-500 text-xs">Horisont</div>
            <div className="font-semibold">{horizon} mån</div>
          </div>
        </div>
      </section>

      {series && (
        <section className="bg-white border rounded-xl p-4 space-y-2">
          <h2 className="font-semibold">Historisk bolåneränta (rörlig)</h2>
          <svg
            viewBox={`0 0 ${chartWidth} ${chartHeight}`}
            className="w-full"
            preserveAspectRatio="none"
          >
            <polyline
              points={polyline}
              fill="none"
              stroke="#0ea5e9"
              strokeWidth="2"
            />
          </svg>
          <div className="flex justify-between text-xs text-slate-500">
            <span>{series.points[0]?.year_month}</span>
            <span>
              {series.points[series.points.length - 1]?.year_month}
            </span>
          </div>
          <p className="text-xs text-slate-500">
            Visar bolåne-rörlig ~= styrränta + 1,5 procentenheter. Källa:
            Riksbanken + SCB-spreadar.
          </p>
        </section>
      )}

      {err && (
        <div className="bg-rose-50 border border-rose-200 rounded p-3 text-sm text-rose-700">
          {err}
        </div>
      )}

      {!hasDecided ? (
        <section className="bg-amber-50 border-l-4 border-amber-400 rounded p-4 space-y-3">
          <div className="flex items-center gap-2 font-semibold text-amber-900">
            <AlertCircle className="w-5 h-5" />
            Ditt beslut — välj bindningstyp
          </div>
          <p className="text-sm text-amber-900">
            När du bundit ränta är valet låst för resten av horisonten. Kör
            rörlig = du följer räntan upp och ner.
          </p>
          <div className="grid grid-cols-3 gap-2">
            {[
              { key: "rorlig", label: "Rörlig" },
              { key: "3ar", label: "Bind 3 år" },
              { key: "5ar", label: "Bind 5 år" },
            ].map((opt) => (
              <button
                key={opt.key}
                disabled={submitting}
                onClick={() => choose(opt.key)}
                className="bg-brand-600 hover:bg-brand-700 text-white rounded py-3 font-medium disabled:opacity-50"
              >
                {opt.label}
              </button>
            ))}
          </div>
        </section>
      ) : (
        <section className="bg-white border rounded-xl p-4 space-y-4">
          <h2 className="font-semibold flex items-center gap-2">
            <Check className="w-5 h-5 text-emerald-600" />
            Ditt val: <span className="text-brand-700">{outcome.chosen}</span>
            {outcome.locked_rate && (
              <span className="text-sm text-slate-500">
                (låst {formatPct(outcome.locked_rate)})
              </span>
            )}
          </h2>
          <div className="grid grid-cols-3 gap-3 text-sm">
            <CostCard
              label="Rörlig" amount={outcome.cost_rorlig}
              chosen={outcome.chosen === "rorlig"}
              best={outcome.best_choice === "rorlig"}
            />
            <CostCard
              label="3 år" amount={outcome.cost_3ar}
              chosen={outcome.chosen === "3ar"}
              best={outcome.best_choice === "3ar"}
            />
            <CostCard
              label="5 år" amount={outcome.cost_5ar}
              chosen={outcome.chosen === "5ar"}
              best={outcome.best_choice === "5ar"}
            />
          </div>
          <div className="bg-slate-50 rounded p-3 text-sm space-y-1">
            <div className="flex justify-between">
              <span>Ditt val: <strong>{outcome.chosen}</strong></span>
              <span>{formatKr(outcome.cost_chosen)}</span>
            </div>
            <div className="flex justify-between">
              <span>Billigast hade varit: <strong>{outcome.best_choice}</strong></span>
              <span>{formatKr(outcome.cost_rorlig)}</span>
            </div>
            <div className="flex justify-between font-semibold border-t pt-1">
              <span>Skillnad</span>
              {outcome.diff_vs_best === 0 ? (
                <span className="text-emerald-700 flex items-center gap-1">
                  <TrendingDown className="w-4 h-4" /> Du valde bäst!
                </span>
              ) : (
                <span className="text-rose-600 flex items-center gap-1">
                  <TrendingUp className="w-4 h-4" />
                  +{formatKr(outcome.diff_vs_best)} (kostade extra)
                </span>
              )}
            </div>
          </div>
          {!outcome.horizon_completed && (
            <p className="text-xs text-slate-500">
              Obs: horisonten är inte helt passerad — siffrorna speglar
              bara de månader vi har räntedata för hittills.
            </p>
          )}
        </section>
      )}
    </div>
  );
}

function CostCard({ label, amount, chosen, best }: {
  label: string; amount: number; chosen: boolean; best: boolean;
}) {
  return (
    <div className={`rounded p-3 ${
      best ? "bg-emerald-50 border-2 border-emerald-400" :
      chosen ? "bg-brand-50 border-2 border-brand-400" :
      "bg-slate-50"
    }`}>
      <div className="text-xs text-slate-500">
        {label}{chosen && " (ditt val)"}{best && " ★ bäst"}
      </div>
      <div className="font-bold text-lg">{formatKr(amount)}</div>
    </div>
  );
}
