/**
 * V2-roster · lärar-vy för att toggla v2 per elev.
 *
 * Lista av alla lärarens elever med:
 * - Aktuell v2-status (toggle-switch)
 * - Onboarding-status
 * - Nivå (1/2/3)
 * - Bulk-knappar: "Aktivera v2 för alla", "Inaktivera alla"
 *
 * Routas till /teacher/v2 — separat sida från v1-Teacher-vyn så
 * inget befintligt påverkas.
 */
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { v2Api, type V2RosterRow } from "./api";
import { V2Banner } from "./V2Banner";

export function V2RosterPage() {
  const [rows, setRows] = useState<V2RosterRow[] | null>(null);
  const [busy, setBusy] = useState<Set<number>>(new Set());
  const [bulkBusy, setBulkBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    try {
      const data = await v2Api.roster();
      setRows(data);
    } catch (e) {
      setError(String((e as Error)?.message || e));
    }
  }

  useEffect(() => { load(); }, []);

  async function toggle(studentId: number, enabled: boolean) {
    setBusy((s) => new Set(s).add(studentId));
    try {
      await v2Api.toggleStudent(studentId, enabled);
      await load();
    } catch (e) {
      setError(String((e as Error)?.message || e));
    } finally {
      setBusy((s) => {
        const next = new Set(s);
        next.delete(studentId);
        return next;
      });
    }
  }

  async function bulkAll(enabled: boolean) {
    if (!confirm(enabled ? "Aktivera v2 för alla elever?" : "Inaktivera v2 för alla?")) return;
    setBulkBusy(true);
    try {
      await v2Api.bulkToggle(enabled);
      await load();
    } catch (e) {
      setError(String((e as Error)?.message || e));
    } finally {
      setBulkBusy(false);
    }
  }

  const counts = rows ? {
    enabled: rows.filter((r) => r.v2_enabled).length,
    onboarded: rows.filter((r) => r.v2_onboarding_completed).length,
    total: rows.length,
  } : null;

  return (
    <div style={{ minHeight: "100vh", background: "#0a0e1a", color: "#fff", paddingTop: 44 }}>
      <V2Banner status={{ role: "teacher", is_super_admin: false }} />

      <div style={{ maxWidth: 1100, margin: "60px auto", padding: "0 24px" }}>
        <div style={{ marginBottom: 28 }}>
          <div style={{ fontFamily: "JetBrains Mono", fontSize: 11, fontWeight: 700, letterSpacing: 1.6, textTransform: "uppercase", color: "#fbbf24" }}>● V2 / Lärar-roster</div>
          <h1 style={{ fontFamily: "Source Serif 4, Georgia, serif", fontWeight: 700, fontSize: 48, letterSpacing: -1.4, lineHeight: 1, marginTop: 12, marginBottom: 12 }}>
            Aktivera <em style={{ fontStyle: "italic", color: "#dc4c2b" }}>v2</em> per elev.
          </h1>
          <p style={{ fontFamily: "Source Serif 4", fontSize: 16, color: "rgba(255,255,255,0.7)", lineHeight: 1.5, maxWidth: 720 }}>
            Eleven får v2 vid nästa inloggning. Default är v1. När v2 är på leds eleven först till onboardingen, sen till hub. Du kan när som helst stänga av igen — eleven hamnar då på v1 igen.
          </p>
          {counts && (
            <div style={{ marginTop: 14, fontFamily: "JetBrains Mono", fontSize: 11, color: "rgba(255,255,255,0.6)", letterSpacing: 0.6 }}>
              <strong style={{ color: "#fff" }}>{counts.enabled}</strong> av <strong style={{ color: "#fff" }}>{counts.total}</strong> elever har v2 aktiverat · <strong style={{ color: "#6ee7b7" }}>{counts.onboarded}</strong> har klarat v2-onboardingen
            </div>
          )}
        </div>

        {/* Bulk-knappar */}
        <div style={{ display: "flex", gap: 10, marginBottom: 18, flexWrap: "wrap" }}>
          <button
            disabled={bulkBusy}
            onClick={() => bulkAll(true)}
            style={btnSolid()}
          >
            ✓ Aktivera v2 för alla elever
          </button>
          <button
            disabled={bulkBusy}
            onClick={() => bulkAll(false)}
            style={btnGhost()}
          >
            × Inaktivera alla
          </button>
          <Link to="/teacher" style={{ ...btnGhost(), textDecoration: "none", display: "inline-block", marginLeft: "auto" }}>
            ← Tillbaka till lärar-vyn
          </Link>
        </div>

        {error && <p style={{ color: "#fca5a5", marginBottom: 12 }}>{error}</p>}

        {/* Roster-tabell */}
        {!rows ? (
          <p style={{ fontFamily: "Inter, sans-serif" }}>Laddar elever…</p>
        ) : rows.length === 0 ? (
          <p style={{ fontFamily: "Inter, sans-serif", color: "rgba(255,255,255,0.6)" }}>Inga elever hittades.</p>
        ) : (
          <div style={{ background: "rgba(15,21,37,0.7)", border: "1px solid rgba(255,255,255,0.1)", borderRadius: 8, overflow: "hidden" }}>
            <div style={{
              display: "grid",
              gridTemplateColumns: "1.6fr 100px 110px 90px 200px",
              gap: 14,
              padding: "12px 18px",
              background: "rgba(0,0,0,0.15)",
              borderBottom: "1px solid rgba(255,255,255,0.08)",
              fontFamily: "JetBrains Mono",
              fontSize: 9.5,
              fontWeight: 700,
              letterSpacing: 1.2,
              textTransform: "uppercase",
              color: "rgba(255,255,255,0.4)",
            }}>
              <span>Elev</span><span>Klass</span><span>Onboarding</span><span>Nivå</span><span>v2-status</span>
            </div>
            {rows.map((r) => (
              <div key={r.student_id} style={{
                display: "grid",
                gridTemplateColumns: "1.6fr 100px 110px 90px 200px",
                gap: 14,
                padding: "12px 18px",
                borderBottom: "1px solid rgba(255,255,255,0.08)",
                alignItems: "center",
                fontFamily: "Inter, sans-serif",
                fontSize: 13,
              }}>
                <span style={{ fontFamily: "Source Serif 4", fontWeight: 700, color: "#fff" }}>{r.display_name}</span>
                <span style={{ fontFamily: "JetBrains Mono", fontSize: 10.5, color: "rgba(255,255,255,0.6)" }}>{r.class_label || "—"}</span>
                <span style={{ fontFamily: "JetBrains Mono", fontSize: 10, color: r.v2_onboarding_completed ? "#6ee7b7" : "rgba(255,255,255,0.4)", letterSpacing: 0.6 }}>
                  {r.v2_onboarding_completed ? "✓ klar" : "ej klar"}
                </span>
                <span style={{ fontFamily: "Source Serif 4", fontStyle: "italic", color: "#fbbf24", fontWeight: 700 }}>{r.v2_level}</span>
                <button
                  disabled={busy.has(r.student_id)}
                  onClick={() => toggle(r.student_id, !r.v2_enabled)}
                  style={{
                    fontFamily: "JetBrains Mono",
                    fontSize: 9.5,
                    fontWeight: 700,
                    letterSpacing: 1.2,
                    textTransform: "uppercase",
                    padding: "8px 14px",
                    borderRadius: 100,
                    cursor: busy.has(r.student_id) ? "wait" : "pointer",
                    background: r.v2_enabled ? "rgba(110,231,183,0.18)" : "rgba(255,255,255,0.04)",
                    border: r.v2_enabled ? "1px solid #6ee7b7" : "1px solid rgba(255,255,255,0.18)",
                    color: r.v2_enabled ? "#6ee7b7" : "rgba(255,255,255,0.6)",
                  }}
                >
                  {r.v2_enabled ? "✓ V2 PÅ · stäng av" : "○ V1 · aktivera v2"}
                </button>
                <Link
                  to={`/teacher/v2/credit/${r.student_id}`}
                  style={{
                    fontFamily: "JetBrains Mono",
                    fontSize: 9.5,
                    fontWeight: 700,
                    letterSpacing: 1.2,
                    textTransform: "uppercase",
                    padding: "8px 14px",
                    borderRadius: 100,
                    background: "rgba(220,76,43,0.12)",
                    border: "1px solid rgba(220,76,43,0.4)",
                    color: "#fbbf24",
                    textDecoration: "none",
                    marginLeft: 8,
                  }}
                >
                  Kreditprofil →
                </Link>
                <Link
                  to={`/teacher/v2/tax/${r.student_id}`}
                  style={{
                    fontFamily: "JetBrains Mono",
                    fontSize: 9.5,
                    fontWeight: 700,
                    letterSpacing: 1.2,
                    textTransform: "uppercase",
                    padding: "8px 14px",
                    borderRadius: 100,
                    background: "rgba(99,102,241,0.12)",
                    border: "1px solid rgba(99,102,241,0.4)",
                    color: "#a5b4fc",
                    textDecoration: "none",
                    marginLeft: 8,
                  }}
                >
                  Deklaration →
                </Link>
                <Link
                  to={`/teacher/v2/employer/${r.student_id}`}
                  style={{
                    fontFamily: "JetBrains Mono",
                    fontSize: 9.5,
                    fontWeight: 700,
                    letterSpacing: 1.2,
                    textTransform: "uppercase",
                    padding: "8px 14px",
                    borderRadius: 100,
                    background: "rgba(110,231,183,0.10)",
                    border: "1px solid rgba(110,231,183,0.4)",
                    color: "#6ee7b7",
                    textDecoration: "none",
                    marginLeft: 8,
                  }}
                >
                  Arbetsgivare →
                </Link>
                <Link
                  to={`/teacher/v2/insurance/${r.student_id}`}
                  style={{
                    fontFamily: "JetBrains Mono",
                    fontSize: 9.5,
                    fontWeight: 700,
                    letterSpacing: 1.2,
                    textTransform: "uppercase",
                    padding: "8px 14px",
                    borderRadius: 100,
                    background: "rgba(251,191,36,0.10)",
                    border: "1px solid rgba(251,191,36,0.4)",
                    color: "#fbbf24",
                    textDecoration: "none",
                    marginLeft: 8,
                  }}
                >
                  Försäkringar →
                </Link>
                <Link
                  to={`/teacher/v2/utility/${r.student_id}`}
                  style={{
                    fontFamily: "JetBrains Mono",
                    fontSize: 9.5,
                    fontWeight: 700,
                    letterSpacing: 1.2,
                    textTransform: "uppercase",
                    padding: "8px 14px",
                    borderRadius: 100,
                    background: "rgba(168,85,247,0.10)",
                    border: "1px solid rgba(168,85,247,0.4)",
                    color: "#c4b5fd",
                    textDecoration: "none",
                    marginLeft: 8,
                  }}
                >
                  Förbrukning →
                </Link>
                <Link
                  to={`/teacher/v2/rental/${r.student_id}`}
                  style={{
                    fontFamily: "JetBrains Mono",
                    fontSize: 9.5,
                    fontWeight: 700,
                    letterSpacing: 1.2,
                    textTransform: "uppercase",
                    padding: "8px 14px",
                    borderRadius: 100,
                    background: "rgba(56,189,248,0.10)",
                    border: "1px solid rgba(56,189,248,0.4)",
                    color: "#7dd3fc",
                    textDecoration: "none",
                    marginLeft: 8,
                  }}
                >
                  Hyresvärden →
                </Link>
                <Link
                  to={`/teacher/v2/pension/${r.student_id}`}
                  style={{
                    fontFamily: "JetBrains Mono",
                    fontSize: 9.5,
                    fontWeight: 700,
                    letterSpacing: 1.2,
                    textTransform: "uppercase",
                    padding: "8px 14px",
                    borderRadius: 100,
                    background: "rgba(244,114,182,0.10)",
                    border: "1px solid rgba(244,114,182,0.4)",
                    color: "#f9a8d4",
                    textDecoration: "none",
                    marginLeft: 8,
                  }}
                >
                  Pension →
                </Link>
                <Link
                  to={`/teacher/v2/avanza/${r.student_id}`}
                  style={{
                    fontFamily: "JetBrains Mono",
                    fontSize: 9.5,
                    fontWeight: 700,
                    letterSpacing: 1.2,
                    textTransform: "uppercase",
                    padding: "8px 14px",
                    borderRadius: 100,
                    background: "rgba(34,197,94,0.10)",
                    border: "1px solid rgba(34,197,94,0.4)",
                    color: "#86efac",
                    textDecoration: "none",
                    marginLeft: 8,
                  }}
                >
                  Avanza →
                </Link>
                <Link
                  to={`/teacher/v2/bokforing/${r.student_id}`}
                  style={{
                    fontFamily: "JetBrains Mono",
                    fontSize: 9.5,
                    fontWeight: 700,
                    letterSpacing: 1.2,
                    textTransform: "uppercase",
                    padding: "8px 14px",
                    borderRadius: 100,
                    background: "rgba(255,255,255,0.04)",
                    border: "1px solid rgba(255,255,255,0.18)",
                    color: "rgba(255,255,255,0.8)",
                    textDecoration: "none",
                    marginLeft: 8,
                  }}
                >
                  Bokföring →
                </Link>
                <Link
                  to={`/teacher/v2/moduler/${r.student_id}`}
                  style={{
                    fontFamily: "JetBrains Mono",
                    fontSize: 9.5,
                    fontWeight: 700,
                    letterSpacing: 1.2,
                    textTransform: "uppercase",
                    padding: "8px 14px",
                    borderRadius: 100,
                    background: "rgba(167,139,250,0.10)",
                    border: "1px solid rgba(167,139,250,0.4)",
                    color: "#c4b5fd",
                    textDecoration: "none",
                    marginLeft: 8,
                  }}
                >
                  Moduler →
                </Link>
                <Link
                  to={`/teacher/v2/simulator/${r.student_id}`}
                  style={{
                    fontFamily: "JetBrains Mono",
                    fontSize: 9.5,
                    fontWeight: 700,
                    letterSpacing: 1.2,
                    textTransform: "uppercase",
                    padding: "8px 14px",
                    borderRadius: 100,
                    background: "rgba(251,146,60,0.10)",
                    border: "1px solid rgba(251,146,60,0.4)",
                    color: "#fb923c",
                    textDecoration: "none",
                    marginLeft: 8,
                  }}
                >
                  Simulator →
                </Link>
                <Link
                  to={`/teacher/v2/feedback/${r.student_id}`}
                  style={{
                    fontFamily: "JetBrains Mono",
                    fontSize: 9.5,
                    fontWeight: 700,
                    letterSpacing: 1.2,
                    textTransform: "uppercase",
                    padding: "8px 14px",
                    borderRadius: 100,
                    background: "rgba(192,132,252,0.10)",
                    border: "1px solid rgba(192,132,252,0.4)",
                    color: "#d8b4fe",
                    textDecoration: "none",
                    marginLeft: 8,
                  }}
                >
                  Feedback →
                </Link>
                <Link
                  to={`/teacher/v2/maria/${r.student_id}`}
                  style={{
                    fontFamily: "JetBrains Mono",
                    fontSize: 9.5,
                    fontWeight: 700,
                    letterSpacing: 1.2,
                    textTransform: "uppercase",
                    padding: "8px 14px",
                    borderRadius: 100,
                    background: "rgba(245,158,11,0.10)",
                    border: "1px solid rgba(245,158,11,0.4)",
                    color: "#fcd34d",
                    textDecoration: "none",
                    marginLeft: 8,
                  }}
                >
                  Maria →
                </Link>
                <Link
                  to={`/teacher/v2/bankid/${r.student_id}`}
                  style={{
                    fontFamily: "JetBrains Mono",
                    fontSize: 9.5,
                    fontWeight: 700,
                    letterSpacing: 1.2,
                    textTransform: "uppercase",
                    padding: "8px 14px",
                    borderRadius: 100,
                    background: "rgba(20,184,166,0.10)",
                    border: "1px solid rgba(20,184,166,0.4)",
                    color: "#5eead4",
                    textDecoration: "none",
                    marginLeft: 8,
                  }}
                >
                  BankID →
                </Link>
                <Link
                  to={`/teacher/v2/messages/${r.student_id}`}
                  style={{
                    fontFamily: "JetBrains Mono",
                    fontSize: 9.5,
                    fontWeight: 700,
                    letterSpacing: 1.2,
                    textTransform: "uppercase",
                    padding: "8px 14px",
                    borderRadius: 100,
                    background: "rgba(96,165,250,0.10)",
                    border: "1px solid rgba(96,165,250,0.4)",
                    color: "#93c5fd",
                    textDecoration: "none",
                    marginLeft: 8,
                  }}
                >
                  Chatta →
                </Link>
                <Link
                  to={`/teacher/v2/portfolio/${r.student_id}`}
                  style={{
                    fontFamily: "JetBrains Mono",
                    fontSize: 9.5,
                    fontWeight: 700,
                    letterSpacing: 1.2,
                    textTransform: "uppercase",
                    padding: "8px 14px",
                    borderRadius: 100,
                    background: "rgba(110,231,183,0.10)",
                    border: "1px solid rgba(110,231,183,0.4)",
                    color: "#6ee7b7",
                    textDecoration: "none",
                    marginLeft: 8,
                  }}
                >
                  Portfolio →
                </Link>
                <Link
                  to={`/teacher/v2/uppdrag/${r.student_id}`}
                  style={{
                    fontFamily: "JetBrains Mono",
                    fontSize: 9.5,
                    fontWeight: 700,
                    letterSpacing: 1.2,
                    textTransform: "uppercase",
                    padding: "8px 14px",
                    borderRadius: 100,
                    background: "rgba(220,76,43,0.10)",
                    border: "1px solid rgba(220,76,43,0.4)",
                    color: "#fda594",
                    textDecoration: "none",
                    marginLeft: 8,
                  }}
                >
                  Uppdrag →
                </Link>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function btnSolid(): React.CSSProperties {
  return {
    fontFamily: "JetBrains Mono",
    fontSize: 11,
    fontWeight: 700,
    letterSpacing: 1.2,
    textTransform: "uppercase",
    padding: "10px 18px",
    borderRadius: 100,
    cursor: "pointer",
    border: "1px solid #dc4c2b",
    background: "#dc4c2b",
    color: "#fff",
  };
}
function btnGhost(): React.CSSProperties {
  return {
    fontFamily: "JetBrains Mono",
    fontSize: 11,
    fontWeight: 700,
    letterSpacing: 1.2,
    textTransform: "uppercase",
    padding: "10px 18px",
    borderRadius: 100,
    cursor: "pointer",
    border: "1px solid rgba(255,255,255,0.18)",
    background: "rgba(255,255,255,0.04)",
    color: "#fff",
  };
}
