/**
 * TeacherSeasonEventsV2 · lärare aktiverar säsong-events.
 * Spec: Fas J · dev/feature-allabolag.md
 */
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "@/api/client";
import { V2Banner } from "./V2Banner";


type Event = {
  id: number;
  event_kind: string;
  label: string;
  desc: string;
  started_at: string;
  ends_at: string;
  is_active: boolean;
};


const KINDS = [
  { key: "black_friday", emoji: "🔥", label: "Black Friday-vecka", desc: "Shared-opp-frekvens × 3 i 7 dagar." },
  { key: "recruitment_crisis", emoji: "💼", label: "Rekryteringskris", desc: "MCP-priser × 1.5 + klass-jobb-löner +20 % i 14 dagar." },
  { key: "sustainability", emoji: "🌱", label: "Hållbarhetsbonus-månad", desc: "Specialist-utrustning ger +10 % rykte i 30 dagar." },
  { key: "bankruptcy_chain", emoji: "💥", label: "Konkurs-event", desc: "En stor kund går omkull · obetalda fakturor får 50 % i 7 dagar." },
];


export function TeacherSeasonEventsV2() {
  const [events, setEvents] = useState<Event[]>([]);
  const [error, setError] = useState<string | null>(null);

  function refresh() {
    api<Event[]>("/v2/teacher/season-events")
      .then(setEvents)
      .catch((e) => setError(String((e as Error).message || e)));
  }
  useEffect(() => { refresh(); }, []);

  async function trigger(kind: string) {
    if (!confirm(`Aktivera ${kind}? Påverkar hela klassen.`)) return;
    try {
      await api("/v2/teacher/season-events", {
        method: "POST",
        body: JSON.stringify({ event_kind: kind }),
      });
      refresh();
    } catch (e) { alert((e as Error).message); }
  }

  async function endEvent(id: number) {
    if (!confirm("Avsluta event manuellt?")) return;
    try {
      await api(`/v2/teacher/season-events/${id}`, { method: "DELETE" });
      refresh();
    } catch (e) { alert((e as Error).message); }
  }

  const active = events.filter((e) => e.is_active);
  const past = events.filter((e) => !e.is_active);

  return (
    <div className="v2-shell">
      <V2Banner status={{ role: "teacher", is_super_admin: false }} />
      <div style={shellStyle}>
        <Link to="/teacher/v2" style={backLinkStyle}>← Lärar-hub</Link>
        <header style={{ marginBottom: 28 }}>
          <span style={pillStyle}>● LÄRARE · SÄSONG-EVENT</span>
          <h1 style={h1Style}>
            Driva <em>dramaturgin</em> i klassen.
          </h1>
          <p style={leadStyle}>
            Aktivera säsong-events för att lägga till variation och övningstillfällen.
            Eleverna ser status i sina företags-vyer.
          </p>
        </header>

        {error && <div style={errorBoxStyle}>{error}</div>}

        {active.length > 0 && (
          <section style={{ marginBottom: 28 }}>
            <div style={{ ...sectionEyeStyle, color: "#6ee7b7" }}>● PÅGÅENDE EVENTS</div>
            <div style={{ display: "grid", gap: 10, marginTop: 12 }}>
              {active.map((e) => (
                <div key={e.id} style={{
                  padding: 16,
                  background: "linear-gradient(135deg, rgba(110,231,183,0.06), rgba(15,21,37,0.55))",
                  border: "1px solid rgba(110,231,183,0.30)",
                  borderRadius: 10,
                  display: "flex",
                  gap: 12,
                  alignItems: "baseline",
                }}>
                  <div style={{ flex: 1 }}>
                    <div style={{ fontFamily: "Source Serif 4, Georgia, serif", fontSize: 16, fontWeight: 700, color: "#fff" }}>
                      {e.label}
                    </div>
                    <div style={{ fontFamily: "JetBrains Mono, monospace", fontSize: 10, color: "rgba(255,255,255,0.55)", letterSpacing: 0.5, marginTop: 4 }}>
                      Avslutas: {new Date(e.ends_at).toLocaleString("sv-SE")}
                    </div>
                  </div>
                  <button onClick={() => endEvent(e.id)} style={btnGhost}>Avsluta</button>
                </div>
              ))}
            </div>
          </section>
        )}

        <div style={{ ...sectionEyeStyle, marginBottom: 12 }}>● TRIGGA NYTT EVENT</div>
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
          {KINDS.map((k) => {
            const isOn = active.some((e) => e.event_kind === k.key);
            return (
              <div key={k.key} style={{
                padding: 18,
                background: isOn ? "rgba(110,231,183,0.06)" : "rgba(15,21,37,0.55)",
                border: `1px solid ${isOn ? "rgba(110,231,183,0.30)" : "rgba(255,255,255,0.10)"}`,
                borderRadius: 10,
              }}>
                <div style={{ fontSize: 26, marginBottom: 8 }}>{k.emoji}</div>
                <div style={{ fontFamily: "Source Serif 4, Georgia, serif", fontSize: 17, fontWeight: 700, color: "#fff" }}>
                  {k.label}
                </div>
                <p style={{ fontFamily: "Source Serif 4, Georgia, serif", fontSize: 13, color: "rgba(255,255,255,0.7)", lineHeight: 1.55, margin: "8px 0" }}>
                  {k.desc}
                </p>
                {isOn ? (
                  <span style={{ fontFamily: "JetBrains Mono, monospace", fontSize: 10, color: "#6ee7b7", letterSpacing: 1.2 }}>● PÅGÅR</span>
                ) : (
                  <button onClick={() => trigger(k.key)} style={btnPrimary}>Aktivera →</button>
                )}
              </div>
            );
          })}
        </div>

        {past.length > 0 && (
          <div style={{ marginTop: 30 }}>
            <div style={sectionEyeStyle}>● HISTORIK</div>
            <div style={{ display: "grid", gap: 6, marginTop: 10 }}>
              {past.slice(0, 10).map((e) => (
                <div key={e.id} style={{ padding: "8px 12px", background: "rgba(15,21,37,0.4)", border: "1px solid rgba(255,255,255,0.06)", borderRadius: 6, fontFamily: "JetBrains Mono, monospace", fontSize: 11, color: "rgba(255,255,255,0.6)" }}>
                  {e.label} · {new Date(e.started_at).toLocaleDateString("sv-SE")} → {new Date(e.ends_at).toLocaleDateString("sv-SE")}
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}


// Styles
const shellStyle: React.CSSProperties = { maxWidth: 1000, margin: "0 auto", padding: "32px 24px 80px" };
const backLinkStyle: React.CSSProperties = { fontFamily: "JetBrains Mono, monospace", fontSize: 10.5, color: "rgba(255,255,255,0.55)", letterSpacing: 1.2, textDecoration: "none", display: "inline-block", marginBottom: 18 };
const pillStyle: React.CSSProperties = { display: "inline-block", padding: "5px 14px", borderRadius: 100, background: "rgba(99,102,241,0.10)", border: "1px solid rgba(99,102,241,0.30)", fontFamily: "JetBrains Mono, monospace", fontSize: 10, fontWeight: 700, letterSpacing: 1.6, color: "#c7d2fe" };
const h1Style: React.CSSProperties = { fontFamily: "Source Serif 4, Georgia, serif", fontWeight: 700, fontSize: 38, letterSpacing: -0.6, color: "#fff", margin: "12px 0 8px", lineHeight: 1.1 };
const leadStyle: React.CSSProperties = { fontFamily: "Source Serif 4, Georgia, serif", fontSize: 17, lineHeight: 1.55, color: "rgba(255,255,255,0.7)", margin: 0, maxWidth: 720 };
const sectionEyeStyle: React.CSSProperties = { fontFamily: "JetBrains Mono, monospace", fontSize: 10.5, fontWeight: 700, letterSpacing: 1.4, color: "#c7d2fe" };
const btnPrimary: React.CSSProperties = { background: "#fbbf24", border: "none", color: "#422006", padding: "8px 14px", borderRadius: 6, fontFamily: "JetBrains Mono, monospace", fontSize: 10.5, fontWeight: 700, letterSpacing: 1.2, textTransform: "uppercase", cursor: "pointer" };
const btnGhost: React.CSSProperties = { background: "transparent", border: "1px solid rgba(255,255,255,0.18)", color: "rgba(255,255,255,0.7)", padding: "8px 14px", borderRadius: 6, fontFamily: "JetBrains Mono, monospace", fontSize: 10.5, fontWeight: 700, letterSpacing: 1.2, textTransform: "uppercase", cursor: "pointer" };
const errorBoxStyle: React.CSSProperties = { padding: 12, background: "rgba(220,76,43,0.08)", border: "1px solid rgba(220,76,43,0.35)", borderRadius: 6, color: "#fda594", fontFamily: "Source Serif 4, Georgia, serif", marginBottom: 14 };
