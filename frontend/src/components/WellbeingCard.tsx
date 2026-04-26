/**
 * WellbeingCard — pentagon-radar med 5 dimensioner + faktor-uppdelning.
 *
 * Visar elevens välbefinnande baserat på ekonomi, hälsa, sociala band,
 * fritid, trygghet. Pedagogiskt: alla bidrag är transparenta.
 */
import { useMutation, useQuery } from "@tanstack/react-query";
import { Loader2, Sparkles, TrendingDown } from "lucide-react";
import { useMemo, useState } from "react";
import { api } from "@/api/client";
import { Card } from "@/components/Card";

interface Factor {
  dimension: string;
  points: number;
  explanation: string;
}

interface WellbeingOut {
  year_month: string;
  total_score: number;
  economy: number;
  health: number;
  social: number;
  leisure: number;
  safety: number;
  factors: Factor[];
  explanation: string;
  events_accepted: number;
  events_declined: number;
  budget_violations: number;
}

const DIMENSIONS = [
  { key: "economy", label: "Ekonomi", color: "#0ea5e9" },
  { key: "health", label: "Mat & hälsa", color: "#10b981" },
  { key: "social", label: "Sociala band", color: "#f59e0b" },
  { key: "leisure", label: "Fritid", color: "#a855f7" },
  { key: "safety", label: "Trygghet", color: "#ef4444" },
] as const;

function PentagonRadar({ data }: { data: WellbeingOut }) {
  const size = 220;
  const cx = size / 2;
  const cy = size / 2;
  const maxRadius = size / 2 - 30;

  // 5 hörn i pentagon (start uppåt)
  const angles = useMemo(() => {
    return DIMENSIONS.map((_, i) => (Math.PI * 2 * i) / 5 - Math.PI / 2);
  }, []);

  const values = DIMENSIONS.map((d) => data[d.key as keyof WellbeingOut] as number);

  const points = values.map((v, i) => {
    const r = (v / 100) * maxRadius;
    const x = cx + Math.cos(angles[i]) * r;
    const y = cy + Math.sin(angles[i]) * r;
    return `${x},${y}`;
  });

  // Bakgrundsringar 25/50/75/100
  const gridRings = [0.25, 0.5, 0.75, 1].map((frac) => {
    const ringPoints = angles.map((ang) => {
      const r = frac * maxRadius;
      return `${cx + Math.cos(ang) * r},${cy + Math.sin(ang) * r}`;
    });
    return ringPoints.join(" ");
  });

  return (
    <svg
      viewBox={`0 0 ${size} ${size}`}
      width="100%"
      height={size}
      className="block"
      aria-label="Wellbeing pentagon"
    >
      {/* Grid */}
      {gridRings.map((p, i) => (
        <polygon
          key={i}
          points={p}
          fill="none"
          stroke="#e2e8f0"
          strokeWidth="1"
        />
      ))}
      {/* Axlar */}
      {angles.map((ang, i) => (
        <line
          key={i}
          x1={cx} y1={cy}
          x2={cx + Math.cos(ang) * maxRadius}
          y2={cy + Math.sin(ang) * maxRadius}
          stroke="#e2e8f0"
          strokeWidth="1"
        />
      ))}
      {/* Värde-polygon */}
      <polygon
        points={points.join(" ")}
        fill="rgba(14, 165, 233, 0.18)"
        stroke="#0ea5e9"
        strokeWidth="2"
      />
      {/* Punkter */}
      {points.map((p, i) => {
        const [x, y] = p.split(",").map(Number);
        return (
          <circle
            key={i}
            cx={x} cy={y} r="3.5"
            fill={DIMENSIONS[i].color}
            stroke="#fff"
            strokeWidth="1.5"
          />
        );
      })}
      {/* Etiketter */}
      {DIMENSIONS.map((d, i) => {
        const ang = angles[i];
        const lx = cx + Math.cos(ang) * (maxRadius + 18);
        const ly = cy + Math.sin(ang) * (maxRadius + 18);
        return (
          <text
            key={d.key}
            x={lx}
            y={ly}
            textAnchor="middle"
            dominantBaseline="middle"
            fontSize="10"
            fontWeight="500"
            fill="#475569"
          >
            {d.label}
          </text>
        );
      })}
      {/* Total i mitten */}
      <text
        x={cx} y={cy - 4}
        textAnchor="middle"
        fontSize="22"
        fontWeight="700"
        fill="#0f172a"
      >
        {data.total_score}
      </text>
      <text
        x={cx} y={cy + 12}
        textAnchor="middle"
        fontSize="9"
        fill="#94a3b8"
      >
        / 100
      </text>
    </svg>
  );
}

interface AIFeedbackOut {
  feedback: string;
  model: string;
  input_tokens: number;
  output_tokens: number;
}

interface DeclineStreakOut {
  current_streak: number;
}

export function WellbeingCard() {
  const [aiFeedback, setAiFeedback] = useState<string | null>(null);
  const [aiError, setAiError] = useState<string | null>(null);

  const wellbeingQ = useQuery({
    queryKey: ["wellbeing-current"],
    queryFn: () => api<WellbeingOut>("/wellbeing/current"),
    refetchInterval: 60_000,
  });

  const streakQ = useQuery({
    queryKey: ["wellbeing-decline-streak"],
    queryFn: () => api<DeclineStreakOut>("/events/decline-streak"),
  });

  const aiMut = useMutation({
    mutationFn: (body: WellbeingOut & { decline_streak: number }) =>
      api<AIFeedbackOut>("/ai/wellbeing/monthly-feedback", {
        method: "POST",
        body: JSON.stringify({
          year_month: body.year_month,
          total_score: body.total_score,
          economy: body.economy,
          health: body.health,
          social: body.social,
          leisure: body.leisure,
          safety: body.safety,
          events_accepted: body.events_accepted,
          events_declined: body.events_declined,
          budget_violations: body.budget_violations,
          decline_streak: body.decline_streak,
        }),
      }),
    onSuccess: (data) => {
      setAiFeedback(data.feedback);
      setAiError(null);
    },
    onError: (e: unknown) => {
      // 503: AI ej aktivt (kräver Teacher.ai_enabled). Tysta felet
      // i UI:t — bara dölj knappen om läraren inte slagit på AI.
      const msg = e instanceof Error ? e.message : "AI inte tillgängligt";
      setAiError(msg);
    },
  });

  const data = wellbeingQ.data;

  if (!data) {
    return (
      <Card title="Wellbeing">
        <div className="text-sm text-slate-500">Beräknar…</div>
      </Card>
    );
  }

  return (
    <Card title={`Wellbeing — ${data.year_month}`}>
      <div className="grid grid-cols-1 md:grid-cols-[260px_1fr] gap-4">
        <div className="flex flex-col items-center">
          <PentagonRadar data={data} />
          <div className="text-xs text-slate-500 mt-1 text-center">
            Pengar är medel — välbefinnande är målet
          </div>
        </div>

        <div className="space-y-3">
          {/* Per-dimension */}
          <div className="grid grid-cols-1 gap-1.5">
            {DIMENSIONS.map((d) => {
              const v = data[d.key as keyof WellbeingOut] as number;
              return (
                <div key={d.key} className="flex items-center gap-2 text-sm">
                  <div
                    className="w-2.5 h-2.5 rounded-full shrink-0"
                    style={{ background: d.color }}
                  />
                  <div className="flex-1 text-slate-700">{d.label}</div>
                  <div className="font-mono text-xs">{v}/100</div>
                  <div className="w-20 bg-slate-100 rounded-full h-1.5 overflow-hidden">
                    <div
                      className="h-full rounded-full"
                      style={{ width: `${v}%`, background: d.color }}
                    />
                  </div>
                </div>
              );
            })}
          </div>

          {/* Top faktorer */}
          {data.factors.length > 0 && (
            <div>
              <div className="text-xs font-medium text-slate-600 mb-1">
                Viktigaste bidrag
              </div>
              <div className="space-y-1.5">
                {data.factors
                  .slice()
                  .sort((a, b) => Math.abs(b.points) - Math.abs(a.points))
                  .slice(0, 3)
                  .map((f, i) => (
                    <div
                      key={i}
                      className="text-xs border rounded p-1.5 bg-slate-50 flex gap-2 items-start"
                    >
                      <span
                        className={`font-mono font-semibold shrink-0 ${
                          f.points >= 0
                            ? "text-emerald-700"
                            : "text-red-700"
                        }`}
                        style={{ minWidth: 36 }}
                      >
                        {f.points >= 0 ? "+" : ""}
                        {f.points}
                      </span>
                      <span className="text-slate-700">{f.explanation}</span>
                    </div>
                  ))}
              </div>
            </div>
          )}

          {data.budget_violations > 0 && (
            <div className="text-xs text-amber-800 bg-amber-50 border border-amber-200 rounded p-1.5 flex gap-1">
              <TrendingDown className="w-3 h-3 mt-0.5 shrink-0" />
              {data.budget_violations} budget(ar) under Konsumentverket-minimum
            </div>
          )}

          {/* AI-feedback (opt-in via Teacher.ai_enabled) */}
          <div className="border-t pt-2">
            {!aiFeedback && (
              <button
                onClick={() =>
                  aiMut.mutate({
                    ...data,
                    decline_streak: streakQ.data?.current_streak ?? 0,
                  })
                }
                disabled={aiMut.isPending}
                className="w-full flex items-center justify-center gap-1 text-xs px-2 py-1.5 rounded border border-amber-300 bg-amber-50 hover:bg-amber-100 text-amber-900 disabled:opacity-50"
              >
                {aiMut.isPending ? (
                  <>
                    <Loader2 className="w-3 h-3 animate-spin" />
                    AI tänker…
                  </>
                ) : (
                  <>
                    <Sparkles className="w-3 h-3" />
                    Be AI-coach om en månadsreflektion
                  </>
                )}
              </button>
            )}
            {aiFeedback && (
              <div className="bg-amber-50 border border-amber-200 rounded p-2 text-xs whitespace-pre-line">
                <div className="font-medium mb-1 flex items-center gap-1">
                  <Sparkles className="w-3 h-3 text-amber-600" />
                  AI-coachens reflektion
                </div>
                {aiFeedback}
                <button
                  onClick={() => setAiFeedback(null)}
                  className="text-[10px] text-slate-500 underline mt-2"
                >
                  Dölj
                </button>
              </div>
            )}
            {aiError && !aiFeedback && (
              <div className="text-[10px] text-slate-400 text-center mt-1">
                AI-coach är inte tillgänglig (kräver att läraren slagit på AI).
              </div>
            )}
          </div>
        </div>
      </div>
    </Card>
  );
}
