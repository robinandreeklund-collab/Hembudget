/**
 * V2 onboarding · första riktiga PR:n från demo till produktion.
 *
 * Minimal version: 3 steg (välkommen, värdering, klar). Designspråk
 * från `/proposals/vol-7/elev.html`-prototypen. Sparar svaret via
 * /v2/onboarding/complete och redirectar till /v2/hub.
 *
 * Nästa iteration: full 8-stegs-flow med karaktärs-kort, pentagon-
 * intro, postlådan-mock, Echo-intro, sambo-fråga med 3 partner-modeller.
 */
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { v2Api, type FairnessChoice } from "./api";
import { V2Banner } from "./V2Banner";

type Step = 1 | 2 | 3;

export function OnboardingV2() {
  const [step, setStep] = useState<Step>(1);
  const [fairness, setFairness] = useState<FairnessChoice | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const nav = useNavigate();

  async function complete() {
    setSaving(true);
    setError(null);
    try {
      const result = await v2Api.completeOnboarding({
        spend_profile: "sparsam",
        fairness_choice: fairness,
        partner_model: "ai",
      });
      nav(result.redirect_to);
    } catch (e) {
      setError(String((e as Error)?.message || e));
    } finally {
      setSaving(false);
    }
  }

  return (
    <div style={{ minHeight: "100vh", background: "#0a0e1a", color: "#fff", paddingTop: 44 }}>
      <V2Banner status={{ role: "student", is_super_admin: false }} />

      <div style={{ maxWidth: 880, margin: "60px auto", padding: "0 24px" }}>
        <div
          style={{
            background: "rgba(15,21,37,0.85)",
            border: "1px solid rgba(255,255,255,0.18)",
            borderTop: "3px solid #fbbf24",
            borderRadius: 10,
            padding: "32px 36px",
          }}
        >
          {/* Progress */}
          <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 4, marginBottom: 22 }}>
            <span style={{ height: 4, background: step >= 1 ? (step === 1 ? "#dc4c2b" : "#fbbf24") : "rgba(255,255,255,0.08)", borderRadius: 100 }} />
            <span style={{ height: 4, background: step >= 2 ? (step === 2 ? "#dc4c2b" : "#fbbf24") : "rgba(255,255,255,0.08)", borderRadius: 100 }} />
            <span style={{ height: 4, background: step >= 3 ? (step === 3 ? "#dc4c2b" : "#fbbf24") : "rgba(255,255,255,0.08)", borderRadius: 100 }} />
          </div>

          {step === 1 && (
            <div>
              <div style={{ fontFamily: "JetBrains Mono", fontSize: 10, fontWeight: 700, letterSpacing: 1.6, textTransform: "uppercase", color: "#fbbf24", marginBottom: 14 }}>
                ● V2 Onboarding · steg 1 av 3
              </div>
              <h1 style={{ fontFamily: "Source Serif 4, Georgia, serif", fontWeight: 700, fontSize: 44, letterSpacing: -1.4, lineHeight: 1.05, color: "#fff", marginBottom: 18 }}>
                Välkommen till <em style={{ fontStyle: "italic", color: "#dc4c2b" }}>Ekonomilabbet v2</em>.
              </h1>
              <p style={{ fontFamily: "Source Serif 4", fontSize: 17, lineHeight: 1.5, color: "rgba(255,255,255,0.92)", marginBottom: 24 }}>
                Det här är ny grund-arkitektur som vi bygger ut modul för modul. Just nu är onboarding live.
                Resten av appen är fortfarande v1 — länken uppe till vänster tar dig dit.
              </p>
              <p style={{ fontFamily: "Source Serif 4", fontSize: 15, lineHeight: 1.5, color: "rgba(255,255,255,0.6)", marginBottom: 24, fontStyle: "italic" }}>
                Du börjar på Nivå 1 · spenderprofil <em style={{ color: "#fbbf24" }}>Sparsam</em>. Läraren öppnar Nivå 2 när du klarat första.
              </p>
              <button onClick={() => setStep(2)} style={btnStyle("solid")}>Fortsätt →</button>
            </div>
          )}

          {step === 2 && (
            <div>
              <div style={{ fontFamily: "JetBrains Mono", fontSize: 10, fontWeight: 700, letterSpacing: 1.6, textTransform: "uppercase", color: "#fbbf24", marginBottom: 14 }}>
                ● V2 Onboarding · steg 2 av 3 · värderingar
              </div>
              <h1 style={{ fontFamily: "Source Serif 4", fontWeight: 700, fontSize: 36, letterSpacing: -1.2, lineHeight: 1.05, color: "#fff", marginBottom: 14 }}>
                Hur fördelar man <em style={{ fontStyle: "italic", color: "#dc4c2b" }}>gemensamma kostnader</em>?
              </h1>
              <p style={{ fontFamily: "Source Serif 4", fontSize: 15, lineHeight: 1.5, color: "rgba(255,255,255,0.7)", marginBottom: 22 }}>
                Innan vi avslöjar din partners ekonomi (om karaktären har en) — svara på vad du själv tycker. Det är värderingar, inte matematik.
              </p>
              <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                {(
                  [
                    { v: "50_50", t: "50/50 · vi delar lika", d: "Båda betalar exakt halva av varje gemensam kostnad." },
                    { v: "proportionellt", t: "Proportionellt · efter lön", d: "Den som tjänar mer betalar mer — så ni har samma marginal kvar." },
                    { v: "pool", t: "Allt delas · gemensam ekonomi", d: "Båda löner går in på ett gemensamt konto. Inga 'mina' eller 'dina' pengar." },
                  ] as { v: FairnessChoice; t: string; d: string }[]
                ).map((opt) => (
                  <button
                    key={opt.v}
                    onClick={() => setFairness(opt.v)}
                    style={{
                      textAlign: "left",
                      background: fairness === opt.v ? "rgba(251,191,36,0.10)" : "rgba(255,255,255,0.04)",
                      border: `2px solid ${fairness === opt.v ? "#fbbf24" : "rgba(255,255,255,0.18)"}`,
                      borderRadius: 8,
                      padding: "16px 20px",
                      cursor: "pointer",
                      color: "#fff",
                    }}
                  >
                    <div style={{ fontFamily: "Source Serif 4", fontSize: 17, fontWeight: 700, marginBottom: 4 }}>{opt.t}</div>
                    <div style={{ fontFamily: "Source Serif 4", fontSize: 14, color: "rgba(255,255,255,0.6)" }}>{opt.d}</div>
                  </button>
                ))}
              </div>
              <div style={{ display: "flex", gap: 10, marginTop: 20 }}>
                <button onClick={() => setStep(1)} style={btnStyle("ghost")}>← Tillbaka</button>
                <button onClick={() => setStep(3)} disabled={!fairness} style={{ ...btnStyle("solid"), opacity: fairness ? 1 : 0.4 }}>
                  Fortsätt →
                </button>
              </div>
            </div>
          )}

          {step === 3 && (
            <div>
              <div style={{ fontFamily: "JetBrains Mono", fontSize: 10, fontWeight: 700, letterSpacing: 1.6, textTransform: "uppercase", color: "#fbbf24", marginBottom: 14 }}>
                ● V2 Onboarding · steg 3 av 3 · klart
              </div>
              <h1 style={{ fontFamily: "Source Serif 4", fontWeight: 700, fontSize: 44, letterSpacing: -1.4, lineHeight: 1.05, color: "#fff", marginBottom: 14 }}>
                Du är <em style={{ fontStyle: "italic", color: "#dc4c2b" }}>laddad</em>.
              </h1>
              <p style={{ fontFamily: "Source Serif 4", fontSize: 17, lineHeight: 1.5, color: "rgba(255,255,255,0.85)", marginBottom: 22 }}>
                Onboarding-svar sparas på ditt konto. Nivå 1 · Sparsam · värdering "{fairness}". När du klickar Klar går du till v2-hubben (under utveckling).
              </p>
              {error && <p style={{ color: "#fca5a5", marginBottom: 12 }}>{error}</p>}
              <div style={{ display: "flex", gap: 10 }}>
                <button onClick={() => setStep(2)} style={btnStyle("ghost")}>← Tillbaka</button>
                <button onClick={complete} disabled={saving} style={btnStyle("solid")}>
                  {saving ? "Sparar..." : "Klar · gå till v2-hubben →"}
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function btnStyle(kind: "solid" | "ghost"): React.CSSProperties {
  return {
    fontFamily: "JetBrains Mono",
    fontSize: 11,
    fontWeight: 700,
    letterSpacing: 1.2,
    textTransform: "uppercase",
    padding: "12px 22px",
    borderRadius: 100,
    cursor: "pointer",
    border: kind === "solid" ? "1px solid #dc4c2b" : "1px solid rgba(255,255,255,0.18)",
    background: kind === "solid" ? "#dc4c2b" : "rgba(255,255,255,0.04)",
    color: "#fff",
  };
}
