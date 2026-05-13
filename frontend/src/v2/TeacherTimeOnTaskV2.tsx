/**
 * Lärar-vy · Time on task v2.
 *
 * Bug #16 · v2-port av v1 TeacherTimeOnTask. Visar median-tid per
 * modul-steg + antal elever som fastnat — i v2-design med samma
 * pill-pattern, JetBrains Mono-eyebrows och dark surface.
 */
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { V2Banner } from "./V2Banner";
import { useAutoStartTeacherGuide } from "./guides/GuideContext";
import { getToken } from "@/api/client";

type Row = {
  step_id: number;
  step_title: string;
  module_id: number;
  module_title: string;
  n_completed: number;
  median_minutes: number | null;
  n_stuck: number;
};


async function api<T>(path: string): Promise<T> {
  const r = await fetch(path, {
    headers: { Authorization: `Bearer ${getToken() || ""}` },
  });
  if (!r.ok) throw new Error(`HTTP ${r.status}: ${await r.text()}`);
  return r.json();
}


export function TeacherTimeOnTaskV2() {
  useAutoStartTeacherGuide();
  const [rows, setRows] = useState<Row[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const [filter, setFilter] = useState<"all" | "stuck" | "fast">("all");

  useEffect(() => {
    api<Row[]>("/teacher/time-on-task")
      .then(setRows)
      .catch((e) => setErr(e instanceof Error ? e.message : String(e)));
  }, []);

  const filtered = rows.filter((r) => {
    if (filter === "stuck") return r.n_stuck > 0;
    if (filter === "fast") {
      return r.median_minutes !== null && r.median_minutes < 5;
    }
    return true;
  });

  const totalStuck = rows.reduce((acc, r) => acc + r.n_stuck, 0);
  const totalCompleted = rows.reduce((acc, r) => acc + r.n_completed, 0);
  const overallMedian =
    rows.length > 0
      ? rows
          .filter((r) => r.median_minutes != null)
          .reduce((acc, r) => acc + (r.median_minutes || 0), 0) /
        Math.max(1, rows.filter((r) => r.median_minutes != null).length)
      : 0;

  return (
    <div className="v2-larare-root">
      <V2Banner status={{ role: "teacher", is_super_admin: false }} />

      <div className="shell">
        <Link
          to="/teacher/v2"
          style={{
            color: "rgba(255,255,255,0.6)",
            textDecoration: "none",
            display: "inline-block",
            marginBottom: 18,
          }}
        >
          ← Tillbaka till klassen
        </Link>

        <header className="larare-head">
          <div>
            <span className="pill warm">Time-on-task · klass-snitt</span>
            <h1 className="larare-head-h1">
              Var <em>fastnar</em> klassen?
            </h1>
            <p
              style={{
                fontFamily: "Source Serif 4, Georgia, serif",
                fontSize: 16,
                color: "rgba(255,255,255,0.6)",
                marginTop: 12,
              }}
            >
              Medianlängd per steg över alla dina elever + antal som har
              börjat men inte avslutat. Fastnat-kolumnen visar var
              eleverna behöver din hjälp.
            </p>
          </div>
          <div className="larare-head-meta">
            <div className="larare-meta-row">
              <span>Snitt-tid:</span>
              <strong>{Math.round(overallMedian)} min</strong>
            </div>
            <div className="larare-meta-row">
              <span>Klara:</span>
              <strong>{totalCompleted}</strong>
            </div>
            <div
              className="larare-meta-row"
              style={{
                color:
                  totalStuck > 5
                    ? "#fda594"
                    : totalStuck > 0
                      ? "var(--warm)"
                      : "#6ee7b7",
              }}
            >
              <span>Fastnat:</span>
              <strong>{totalStuck}</strong>
            </div>
          </div>
        </header>

        {/* Filter-tabs */}
        <div
          style={{
            display: "flex",
            gap: 8,
            marginTop: 24,
            marginBottom: 18,
          }}
        >
          {(
            [
              ["all", `Alla (${rows.length})`],
              ["stuck", `Fastnat (${rows.filter((r) => r.n_stuck > 0).length})`],
              ["fast", "Snabba (< 5 min)"],
            ] as const
          ).map(([key, label]) => (
            <button
              key={key}
              onClick={() => setFilter(key as typeof filter)}
              style={{
                padding: "8px 16px",
                background:
                  filter === key
                    ? "rgba(251,191,36,0.18)"
                    : "rgba(255,255,255,0.04)",
                border: `1px solid ${
                  filter === key
                    ? "rgba(251,191,36,0.4)"
                    : "rgba(255,255,255,0.12)"
                }`,
                color:
                  filter === key ? "var(--warm, #fbbf24)" : "rgba(255,255,255,0.7)",
                borderRadius: 100,
                cursor: "pointer",
                fontSize: "0.85rem",
                fontWeight: 600,
              }}
            >
              {label}
            </button>
          ))}
        </div>

        {err && (
          <div
            style={{
              padding: 14,
              background: "rgba(220,76,43,0.12)",
              border: "1px solid rgba(220,76,43,0.3)",
              borderRadius: 8,
              color: "#fda594",
              marginBottom: 16,
            }}
          >
            Kunde inte ladda time-on-task: {err}
          </div>
        )}

        {filtered.length === 0 && !err ? (
          <div
            style={{
              padding: "40px 28px",
              textAlign: "center",
              color: "rgba(255,255,255,0.5)",
              fontFamily: "Source Serif 4, Georgia, serif",
              border: "1px solid rgba(255,255,255,0.1)",
              borderRadius: 8,
            }}
          >
            {filter === "stuck"
              ? "Inga elever har fastnat — bra jobbat!"
              : filter === "fast"
                ? "Inga steg avklaras under 5 minuter."
                : "Ingen data ännu — elever behöver öppna minst ett steg."}
          </div>
        ) : (
          <div className="tx-list">
            {filtered.map((r) => (
              <article
                key={r.step_id}
                className="tx-row"
                style={{
                  display: "grid",
                  gridTemplateColumns: "2fr 3fr 1fr 1fr 1fr",
                  alignItems: "center",
                  padding: "14px 18px",
                  borderBottom: "1px solid rgba(255,255,255,0.05)",
                }}
              >
                <div
                  style={{
                    color: "rgba(255,255,255,0.6)",
                    fontFamily: "JetBrains Mono, monospace",
                    fontSize: "0.8rem",
                    textTransform: "uppercase",
                    letterSpacing: 1.2,
                  }}
                >
                  {r.module_title}
                </div>
                <div style={{ color: "white", fontWeight: 500 }}>
                  {r.step_title}
                </div>
                <div
                  style={{
                    textAlign: "right",
                    color: "rgba(255,255,255,0.85)",
                    fontFamily: "JetBrains Mono, monospace",
                  }}
                >
                  {r.median_minutes != null
                    ? `${r.median_minutes} min`
                    : "—"}
                </div>
                <div
                  style={{
                    textAlign: "right",
                    color: "#6ee7b7",
                    fontFamily: "JetBrains Mono, monospace",
                  }}
                >
                  {r.n_completed}
                </div>
                <div
                  style={{
                    textAlign: "right",
                    color:
                      r.n_stuck > 5
                        ? "#fda594"
                        : r.n_stuck > 0
                          ? "var(--warm)"
                          : "rgba(255,255,255,0.4)",
                    fontWeight: 700,
                    fontFamily: "JetBrains Mono, monospace",
                  }}
                >
                  {r.n_stuck}
                </div>
              </article>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
