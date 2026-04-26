import type { CSSProperties } from "react";

type Mastery = {
  competency: {
    id: number;
    name: string;
    level: string;
    description?: string | null;
  };
  mastery: number;
  evidence_count: number;
  next_threshold?: number | null;
  steps_remaining?: number;
};

const MILESTONES = [0.25, 0.5, 0.75, 1.0];

export function MasteryChart({
  data,
  compact = false,
}: { data: Mastery[]; compact?: boolean }) {
  const byLevel: Record<string, Mastery[]> = { grund: [], fordjup: [], expert: [] };
  for (const m of data) {
    (byLevel[m.competency.level] ?? byLevel.grund).push(m);
  }
  const levelLabels: Record<string, string> = {
    grund: "Grund",
    fordjup: "Fördjupning",
    expert: "Expert",
  };
  const levelColor: Record<string, string> = {
    grund: "#10b981",
    fordjup: "#f59e0b",
    expert: "#8b5cf6",
  };
  return (
    <div className="space-y-4">
      {(["grund", "fordjup", "expert"] as const).map((lvl) => {
        const items = byLevel[lvl];
        if (!items || items.length === 0) return null;
        return (
          <div key={lvl}>
            <div className="text-xs uppercase tracking-wide text-slate-500 font-semibold mb-2">
              {levelLabels[lvl]}
            </div>
            <ul className={`space-y-${compact ? "1" : "2"}`}>
              {items.map((m) => {
                const pct = Math.round(m.mastery * 100);
                const barColor = levelColor[lvl];
                const nextPct =
                  m.next_threshold != null
                    ? Math.round(m.next_threshold * 100)
                    : null;
                return (
                  <li key={m.competency.id}>
                    <div className="flex items-baseline justify-between text-xs">
                      <span className="font-medium text-slate-700">
                        {m.competency.name}
                      </span>
                      <span className="text-slate-500">
                        {pct}%
                        {m.evidence_count > 0 &&
                          ` · ${m.evidence_count} bevis`}
                      </span>
                    </div>
                    <div className="relative h-2 bg-slate-100 rounded overflow-hidden">
                      <div
                        className="h-full rounded transition-all"
                        style={
                          {
                            width: `${Math.max(pct, 2)}%`,
                            background: barColor,
                            opacity: pct === 0 ? 0.2 : 1,
                          } as CSSProperties
                        }
                      />
                      {/* Milestone-tickmarks */}
                      {MILESTONES.slice(0, -1).map((t) => (
                        <span
                          key={t}
                          aria-hidden
                          className="absolute top-0 bottom-0 w-px bg-white/70"
                          style={{ left: `${t * 100}%` }}
                        />
                      ))}
                    </div>
                    {nextPct != null && (m.steps_remaining ?? 0) > 0 && (
                      <div className="text-[11px] text-slate-500 mt-0.5">
                        Nästa milstolpe: {nextPct} % · {m.steps_remaining}{" "}
                        {m.steps_remaining === 1 ? "steg" : "steg"} kvar
                      </div>
                    )}
                    {nextPct == null && pct >= 100 && (
                      <div className="text-[11px] text-emerald-700 mt-0.5">
                        Mästrad — snyggt!
                      </div>
                    )}
                  </li>
                );
              })}
            </ul>
          </div>
        );
      })}
    </div>
  );
}
