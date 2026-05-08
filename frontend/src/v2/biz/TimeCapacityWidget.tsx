/**
 * TimeCapacityWidget · återanvändbar widget för tids-kapacitet.
 *
 * Spec: Fas K · dev/feature-allabolag.md
 *
 * Återanvänds på:
 *  - BizHub (kompakt)
 *  - BizTillvaxt (full breakdown)
 *  - Offert-modal (jämför med tier-prediktion)
 */
import { useEffect, useState } from "react";
import { api } from "@/api/client";


export type TimeCapacity = {
  available_hours: number;
  used_hours: number;
  remaining_hours: number;
  utilization_pct: number;
  ratio: number;
  tier: number;
  tier_label: string;
  tier_color: string;
  tier_desc: string;
  weeks_overloaded: number;
  employment_status: string;
  breakdown: {
    student_self_hours: number;
    private_job_hours: number;
    n_employees: number;
    employee_hours_total: number;
    employee_names: string[];
    mcp_hours: number;
    mcp_active: boolean;
  };
  active_jobs: Array<{
    id: number;
    title: string;
    customer_name: string;
    hours_per_week: number;
    estimated_hours: number;
    expected_complete_on: string;
    delays_count: number;
  }>;
};


export function useTimeCapacity() {
  const [data, setData] = useState<TimeCapacity | null>(null);
  const [error, setError] = useState<string | null>(null);

  function refresh() {
    api<TimeCapacity>("/v2/foretag/capacity/time")
      .then(setData)
      .catch((e) => setError(String((e as Error).message || e)));
  }
  useEffect(() => { refresh(); }, []);
  return { data, error, refresh };
}


/** Kompakt version · för BizHub-banner */
export function TimeCapacityBar({ data, onQuit, onClick }: {
  data: TimeCapacity;
  onQuit?: () => void;
  onClick?: () => void;
}) {
  const pct = Math.min(100, data.utilization_pct);
  return (
    <div
      onClick={onClick}
      style={{
        background: "rgba(15,21,37,0.55)",
        border: `1px solid ${data.tier > 0 ? data.tier_color : "rgba(255,255,255,0.10)"}`,
        borderLeft: `3px solid ${data.tier_color}`,
        borderRadius: 10,
        padding: "12px 16px",
        cursor: onClick ? "pointer" : "default",
      }}
    >
      <div style={{ display: "flex", alignItems: "baseline", gap: 12 }}>
        <span style={{
          fontFamily: "JetBrains Mono, monospace", fontSize: 9.5,
          fontWeight: 700, letterSpacing: 1.4,
          color: data.tier_color,
        }}>
          ● TIDS-KAPACITET · {data.tier_label.toUpperCase()}
        </span>
        <span style={{ flex: 1 }} />
        <span style={{ fontFamily: "JetBrains Mono, monospace", fontSize: 11, color: "rgba(255,255,255,0.7)" }}>
          {data.used_hours} / {data.available_hours} h
        </span>
        <span style={{
          fontFamily: "JetBrains Mono, monospace", fontSize: 11, fontWeight: 700,
          color: data.tier_color,
        }}>
          {data.utilization_pct} %
        </span>
      </div>
      <div style={{ height: 6, marginTop: 8, background: "rgba(255,255,255,0.08)", borderRadius: 100 }}>
        <div style={{
          height: "100%",
          width: `${pct}%`,
          background: data.tier_color,
          borderRadius: 100,
          transition: "width 0.3s",
        }} />
      </div>
      {data.tier >= 2 && (
        <div style={{ marginTop: 6, fontFamily: "Source Serif 4, Georgia, serif", fontSize: 12.5, color: "rgba(255,255,255,0.75)", fontStyle: "italic" }}>
          ⚠ {data.tier_desc}
          {data.weeks_overloaded > 0 && ` · ${data.weeks_overloaded} v rakt`}
        </div>
      )}
      {onQuit && data.employment_status === "employed" && data.tier >= 2 && (
        <button
          onClick={(e) => { e.stopPropagation(); onQuit(); }}
          style={{
            marginTop: 8, background: "rgba(220,76,43,0.18)",
            border: "1px solid rgba(220,76,43,0.45)",
            color: "#fda594", padding: "5px 10px", borderRadius: 4,
            fontFamily: "JetBrains Mono, monospace", fontSize: 9.5,
            fontWeight: 700, letterSpacing: 1.2, cursor: "pointer",
          }}
        >
          SÄG UPP PRIVAT-JOBBET (+{data.breakdown.private_job_hours} H/V)
        </button>
      )}
    </div>
  );
}


/** Full-breakdown · för Tillväxt-vyn */
export function TimeCapacityBreakdown({ data, onQuit }: {
  data: TimeCapacity;
  onQuit?: () => void;
}) {
  return (
    <div style={{
      background: "rgba(15,21,37,0.55)",
      border: `1px solid ${data.tier > 0 ? data.tier_color : "rgba(255,255,255,0.10)"}`,
      borderRadius: 10, padding: 16,
    }}>
      <div style={{
        fontFamily: "JetBrains Mono, monospace", fontSize: 10.5,
        fontWeight: 700, letterSpacing: 1.4, color: data.tier_color,
      }}>
        ● TIDS-KAPACITET · {data.tier_label.toUpperCase()}
      </div>
      <p style={{ fontFamily: "Source Serif 4, Georgia, serif", fontSize: 13.5, color: "rgba(255,255,255,0.78)", lineHeight: 1.55, margin: "8px 0 14px" }}>
        {data.tier_desc}
      </p>

      <div style={{ display: "flex", alignItems: "baseline", gap: 14 }}>
        <span style={{ fontFamily: "Source Serif 4, Georgia, serif", fontStyle: "italic", fontWeight: 700, fontSize: 32, color: data.tier_color }}>
          {data.used_hours} / {data.available_hours} h
        </span>
        <span style={{ fontFamily: "JetBrains Mono, monospace", fontSize: 12, color: "rgba(255,255,255,0.6)" }}>
          {data.utilization_pct} % belastning
        </span>
      </div>
      <div style={{ height: 8, marginTop: 8, marginBottom: 16, background: "rgba(255,255,255,0.08)", borderRadius: 100 }}>
        <div style={{
          height: "100%",
          width: `${Math.min(100, data.utilization_pct)}%`,
          background: data.tier_color,
          borderRadius: 100,
        }} />
      </div>

      {/* Var timmarna kommer ifrån */}
      <div style={{
        fontFamily: "JetBrains Mono, monospace", fontSize: 9.5,
        color: "rgba(255,255,255,0.5)", letterSpacing: 1.2, marginBottom: 8,
      }}>
        VARFRÅN ARBETSTIMMARNA KOMMER
      </div>
      <div style={{ display: "grid", gap: 6 }}>
        <BreakdownRow
          label="Du själv (84 h/v − privat-jobb)"
          minus={data.breakdown.private_job_hours}
          plus={data.breakdown.student_self_hours}
          actionLabel={data.employment_status === "employed" ? "Säg upp" : null}
          onAction={onQuit}
        />
        {data.breakdown.n_employees > 0 && (
          <BreakdownRow
            label={`Anställda · ${data.breakdown.employee_names.join(", ")}`}
            plus={data.breakdown.employee_hours_total}
          />
        )}
        {data.breakdown.mcp_active && (
          <BreakdownRow
            label="MCP-frilans (aktiv vecka)"
            plus={data.breakdown.mcp_hours}
          />
        )}
      </div>

      {/* Vad timmarna går till */}
      {data.active_jobs.length > 0 && (
        <>
          <div style={{
            fontFamily: "JetBrains Mono, monospace", fontSize: 9.5,
            color: "rgba(255,255,255,0.5)", letterSpacing: 1.2,
            marginTop: 18, marginBottom: 8,
          }}>
            AKTIVA UPPDRAG
          </div>
          <div style={{ display: "grid", gap: 4 }}>
            {data.active_jobs.map((j) => (
              <div key={j.id} style={{
                display: "grid",
                gridTemplateColumns: "1fr 80px 100px 90px",
                gap: 10,
                padding: "5px 8px",
                background: j.delays_count > 0 ? "rgba(220,76,43,0.05)" : "transparent",
                borderRadius: 4,
                fontSize: 12,
              }}>
                <span style={{ fontFamily: "Source Serif 4, Georgia, serif", color: "#fff" }}>
                  {j.title} <span style={{ color: "rgba(255,255,255,0.5)" }}>· {j.customer_name}</span>
                </span>
                <span style={{ fontFamily: "JetBrains Mono, monospace", fontSize: 11, color: "#fbbf24" }}>
                  {j.hours_per_week} h/v
                </span>
                <span style={{ fontFamily: "JetBrains Mono, monospace", fontSize: 10, color: "rgba(255,255,255,0.55)" }}>
                  → {j.expected_complete_on}
                </span>
                {j.delays_count > 0 && (
                  <span style={{ fontFamily: "JetBrains Mono, monospace", fontSize: 9, color: "#fda594", letterSpacing: 1, fontWeight: 700 }}>
                    ⚠ {j.delays_count} FÖRS.
                  </span>
                )}
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  );
}


function BreakdownRow({ label, plus, minus, actionLabel, onAction }: {
  label: string;
  plus?: number;
  minus?: number;
  actionLabel?: string | null;
  onAction?: () => void;
}) {
  return (
    <div style={{
      display: "grid",
      gridTemplateColumns: "1fr auto auto auto",
      gap: 10,
      padding: "4px 0",
      alignItems: "baseline",
    }}>
      <span style={{ fontFamily: "Source Serif 4, Georgia, serif", fontSize: 13, color: "rgba(255,255,255,0.85)" }}>
        {label}
      </span>
      {minus !== undefined && minus > 0 && (
        <span style={{ fontFamily: "JetBrains Mono, monospace", fontSize: 11, color: "#fda594" }}>
          −{minus} h
        </span>
      )}
      {plus !== undefined && (
        <span style={{ fontFamily: "JetBrains Mono, monospace", fontSize: 12, color: "#6ee7b7", fontWeight: 700 }}>
          +{plus} h
        </span>
      )}
      {actionLabel && onAction && (
        <button onClick={onAction} style={{
          background: "rgba(220,76,43,0.15)",
          border: "1px solid rgba(220,76,43,0.4)",
          color: "#fda594",
          padding: "3px 8px", borderRadius: 4,
          fontFamily: "JetBrains Mono, monospace", fontSize: 9, fontWeight: 700,
          letterSpacing: 1.1, textTransform: "uppercase", cursor: "pointer",
        }}>
          {actionLabel}
        </button>
      )}
    </div>
  );
}


/** Liten tier-prediktor för offert-modal */
export type ImpactPreview = {
  job_estimated_hours: number;
  job_hours_per_week: number;
  job_weeks: number;
  current_used_hours: number;
  current_available_hours: number;
  after_used_hours: number;
  after_ratio: number;
  after_utilization_pct: number;
  after_tier: number;
  after_tier_label: string;
  after_tier_color: string;
  after_tier_desc: string;
  delay_risk_pct: number;
  health_impact_per_week: number;
  safety_impact_per_week: number;
};

export function ImpactPreviewBox({ preview }: { preview: ImpactPreview }) {
  return (
    <div style={{
      background: "rgba(15,21,37,0.6)",
      border: `1px solid ${preview.after_tier_color}`,
      borderLeft: `3px solid ${preview.after_tier_color}`,
      borderRadius: 8,
      padding: 14,
      marginTop: 12,
    }}>
      <div style={{
        fontFamily: "JetBrains Mono, monospace", fontSize: 9.5,
        fontWeight: 700, letterSpacing: 1.4, color: preview.after_tier_color,
      }}>
        ● TIDS-PREDIKTION OM DU TAR DETTA UPPDRAG
      </div>
      <div style={{ marginTop: 10, fontFamily: "Source Serif 4, Georgia, serif", fontSize: 13.5, lineHeight: 1.5, color: "rgba(255,255,255,0.85)" }}>
        Tar <strong style={{ color: "#fbbf24" }}>≈ {preview.job_estimated_hours} h</strong> över <strong>{preview.job_weeks} v</strong>
        {" · "}
        <strong style={{ color: "#fbbf24" }}>{preview.job_hours_per_week} h/v</strong>
      </div>
      <div style={{ marginTop: 8, fontFamily: "JetBrains Mono, monospace", fontSize: 11, color: "rgba(255,255,255,0.7)" }}>
        Aktuellt: {preview.current_used_hours}/{preview.current_available_hours} h
        → med detta: <strong style={{ color: preview.after_tier_color }}>
          {preview.after_used_hours}/{preview.current_available_hours} h ({preview.after_utilization_pct} %)
        </strong>
      </div>
      <div style={{
        marginTop: 10, padding: "8px 12px",
        background: "rgba(0,0,0,0.25)", borderRadius: 4,
        fontFamily: "Source Serif 4, Georgia, serif", fontSize: 13,
        color: "rgba(255,255,255,0.9)",
      }}>
        <strong style={{ color: preview.after_tier_color }}>{preview.after_tier_label}</strong>:
        {" "}{preview.after_tier_desc}
      </div>
      {preview.after_tier > 0 && (
        <ul style={{ marginTop: 8, paddingLeft: 18, color: "rgba(255,255,255,0.75)", fontFamily: "Source Serif 4, Georgia, serif", fontSize: 12.5, lineHeight: 1.5 }}>
          <li>Risk för försening per jobb: <strong>{preview.delay_risk_pct} %</strong></li>
          {preview.health_impact_per_week !== 0 && (
            <li>Hälsa-axel: <strong>{preview.health_impact_per_week}</strong>/v</li>
          )}
          {preview.safety_impact_per_week !== 0 && (
            <li>Trygghet-axel: <strong>{preview.safety_impact_per_week}</strong>/v</li>
          )}
        </ul>
      )}
    </div>
  );
}
