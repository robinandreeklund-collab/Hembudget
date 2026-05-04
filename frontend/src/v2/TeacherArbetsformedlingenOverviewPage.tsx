/**
 * Lärar-vy · full insyn i en elevs Arbetsförmedlingen-aktivitet.
 *
 * Använder /v2/teacher/arbetsformedlingen/overview/{id} (sammanställning)
 * + /v2/teacher/arbetsformedlingen/applications/{id} (lista).
 *
 * Visar:
 * - Antal ansökningar totalt + per status (aktiv, accepterad, declined,
 *   abandoned)
 * - Snitt match-score + final-score
 * - Sammanfattning (auto-genererad)
 * - Lista över alla ansökningar med rond, status och slutscore
 *
 * Routas via /teacher/v2/arbetsformedlingen/:studentId.
 */
import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import {
  v2Api,
  type V2TeacherAFOverview,
  type V2ArbetsformedlingenApplication,
} from "./api";
import { V2Banner } from "./V2Banner";
import "./lan.css";

const SHORT_DATE = (iso: string | null): string => {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleDateString("sv-SE", {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
};

const STATUS_LABEL: Record<string, string> = {
  round_1: "Rond 1",
  round_2: "Rond 2",
  round_3: "Rond 3",
  round_4: "Rond 4",
  round_5: "Rond 5",
  offer_pending: "Erbjudande",
  accepted: "Accepterad",
  rejected: "Avböjd av AG",
  declined: "Avböjd av elev",
  abandoned: "Avbruten",
};

const STATUS_COLOR: Record<string, string> = {
  accepted: "#6ee7b7",
  rejected: "#fda594",
  declined: "#fda594",
  abandoned: "#aab",
  offer_pending: "#fbbf24",
};

export function TeacherArbetsformedlingenOverviewPage() {
  const { studentId } = useParams<{ studentId: string }>();
  const sid = studentId ? parseInt(studentId, 10) : 0;
  const [overview, setOverview] = useState<V2TeacherAFOverview | null>(null);
  const [applications, setApplications] = useState<
    V2ArbetsformedlingenApplication[]
  >([]);
  const [error, setError] = useState<string | null>(null);
  const navigate = useNavigate();

  useEffect(() => {
    if (!sid) return;
    Promise.all([
      v2Api.teacherAFOverview(sid),
      v2Api.teacherAFApplications(sid),
    ])
      .then(([ov, apps]) => {
        setOverview(ov);
        setApplications(apps);
      })
      .catch((e) => setError(String((e as Error)?.message || e)));
  }, [sid]);

  if (error) {
    return (
      <div className="v2-shell">
        <V2Banner status={{ role: "teacher", is_super_admin: false }} />
        <div className="lan-container">
          <p className="error">Fel: {error}</p>
          <button onClick={() => navigate("/teacher/v2/roster")}>
            Tillbaka
          </button>
        </div>
      </div>
    );
  }

  if (!overview) {
    return (
      <div className="v2-shell">
        <V2Banner status={{ role: "teacher", is_super_admin: false }} />
        <div className="lan-container">
          <p>Laddar elevens AF-data…</p>
        </div>
      </div>
    );
  }

  return (
    <div className="v2-shell">
      <V2Banner status={{ role: "teacher", is_super_admin: false }} />
      <div className="lan-container" style={{ paddingBottom: 64 }}>
        <button
          onClick={() => navigate(`/teacher/v2/elev/${sid}`)}
          style={{
            background: "transparent",
            border: "1px solid rgba(99,102,241,0.3)",
            color: "#c7d2fe",
            padding: "6px 12px",
            borderRadius: 6,
            cursor: "pointer",
            marginBottom: 16,
          }}
        >
          ← Tillbaka till elev
        </button>

        <h1 style={{ margin: "0 0 8px 0" }}>
          {overview.student_name} — Arbetsförmedlingen
        </h1>
        <p style={{ color: "rgba(255,255,255,0.55)", marginTop: 0 }}>
          Aktör 10 · Mats listar lediga tjänster och simulerar
          intervjuprocessen i 5 ronder.
        </p>

        {/* Stat-rad */}
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fit, minmax(140px, 1fr))",
            gap: 12,
            marginTop: 24,
          }}
        >
          <Stat label="Ansökningar" value={overview.n_applications_total.toString()} />
          <Stat label="Aktiva" value={overview.n_active.toString()} />
          <Stat label="Accepterade" value={overview.n_completed.toString()} />
          <Stat
            label="Avböjda av AG"
            value={overview.n_declined.toString()}
            color={overview.n_declined > 0 ? "#fda594" : undefined}
          />
          <Stat
            label="Avbrutna"
            value={overview.n_abandoned.toString()}
            color={overview.n_abandoned > 0 ? "#fbbf24" : undefined}
          />
          <Stat
            label="Snitt match"
            value={
              overview.avg_match_score !== null
                ? `${overview.avg_match_score.toFixed(0)}/100`
                : "—"
            }
          />
          <Stat
            label="Snitt final"
            value={
              overview.avg_final_score !== null
                ? `${overview.avg_final_score.toFixed(0)}/100`
                : "—"
            }
          />
          <Stat
            label="Senaste"
            value={SHORT_DATE(overview.last_application_date)}
          />
        </div>

        {/* Sammanfattning */}
        <div
          style={{
            background: "rgba(15,21,37,0.4)",
            border: "1px solid rgba(99,102,241,0.18)",
            borderRadius: 12,
            padding: 20,
            marginTop: 16,
            whiteSpace: "pre-wrap",
            fontSize: "0.95rem",
            lineHeight: 1.55,
          }}
        >
          {overview.summary_md.split("\n").map((line, i) => {
            if (line.startsWith("## ")) {
              return (
                <h2
                  key={i}
                  style={{ marginTop: i === 0 ? 0 : 16, marginBottom: 8 }}
                >
                  {line.slice(3)}
                </h2>
              );
            }
            if (line.startsWith("- ")) {
              return (
                <div key={i} style={{ marginLeft: 16, marginTop: 4 }}>
                  • {line
                    .slice(2)
                    .split(/(\*\*[^*]+\*\*)/)
                    .map((part, j) =>
                      part.startsWith("**") ? (
                        <strong key={j}>{part.slice(2, -2)}</strong>
                      ) : (
                        part
                      ),
                    )}
                </div>
              );
            }
            return <div key={i}>{line}</div>;
          })}
        </div>

        {/* Ansökningslista */}
        {applications.length > 0 && (
          <div
            style={{
              background: "rgba(15,21,37,0.4)",
              border: "1px solid rgba(99,102,241,0.18)",
              borderRadius: 12,
              padding: 20,
              marginTop: 16,
            }}
          >
            <h3 style={{ marginTop: 0 }}>
              Alla ansökningar ({applications.length})
            </h3>
            <table
              style={{
                width: "100%",
                borderCollapse: "collapse",
                fontSize: "0.9rem",
              }}
            >
              <thead>
                <tr
                  style={{
                    color: "#aab",
                    textAlign: "left",
                    borderBottom: "1px solid rgba(99,102,241,0.2)",
                  }}
                >
                  <th style={{ padding: "8px 4px" }}>Yrke / Arbetsgivare</th>
                  <th style={{ padding: "8px 4px" }}>Stad</th>
                  <th style={{ padding: "8px 4px" }}>Status</th>
                  <th style={{ padding: "8px 4px", textAlign: "right" }}>
                    Match
                  </th>
                  <th style={{ padding: "8px 4px", textAlign: "right" }}>
                    Final
                  </th>
                  <th style={{ padding: "8px 4px" }}>Startad</th>
                </tr>
              </thead>
              <tbody>
                {applications.map((a) => (
                  <tr
                    key={a.id}
                    style={{
                      borderBottom: "1px solid rgba(99,102,241,0.08)",
                    }}
                  >
                    <td style={{ padding: "8px 4px" }}>
                      <div style={{ fontWeight: 600 }}>{a.yrke_display}</div>
                      <div style={{ fontSize: "0.8rem", color: "#aab" }}>
                        {a.employer_name}
                      </div>
                    </td>
                    <td style={{ padding: "8px 4px" }}>{a.city_display}</td>
                    <td
                      style={{
                        padding: "8px 4px",
                        color: STATUS_COLOR[a.status] || "white",
                      }}
                    >
                      {STATUS_LABEL[a.status] || a.status}
                    </td>
                    <td
                      style={{ padding: "8px 4px", textAlign: "right" }}
                    >
                      {a.match_score}
                    </td>
                    <td
                      style={{ padding: "8px 4px", textAlign: "right" }}
                    >
                      {a.final_score ?? "—"}
                    </td>
                    <td style={{ padding: "8px 4px" }}>
                      {SHORT_DATE(a.started_on)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}


function Stat({
  label,
  value,
  color,
}: {
  label: string;
  value: string;
  color?: string;
}) {
  return (
    <div
      style={{
        background: "rgba(15,21,37,0.4)",
        border: "1px solid rgba(99,102,241,0.18)",
        borderRadius: 8,
        padding: 12,
      }}
    >
      <div
        style={{
          fontSize: 9,
          letterSpacing: 1.3,
          color: "#818cf8",
          textTransform: "uppercase",
          fontFamily: "JetBrains Mono, monospace",
        }}
      >
        {label}
      </div>
      <div
        style={{
          fontSize: "1.4rem",
          fontWeight: 700,
          color: color || "white",
          marginTop: 4,
        }}
      >
        {value}
      </div>
    </div>
  );
}
