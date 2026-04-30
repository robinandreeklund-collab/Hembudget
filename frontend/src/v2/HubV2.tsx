/**
 * V2-hub · stomme. Den fulla designen finns i
 * `/proposals/vol-7/elev.html`-prototypen.
 *
 * Denna sida är en migrations-status-tavla som visar vilka v2-vyer
 * som är byggda och vilka som är kvar. Speciellt nyttig för
 * super-admin under parallell-migrationen.
 */
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { v2Api, type V2Status } from "./api";
import { V2Banner } from "./V2Banner";

const ROADMAP = [
  { module: "Onboarding", status: "live", note: "3-stegs · sparar level/profile/fairness" },
  { module: "Pentagon-hub", status: "demo", note: "Finns i /proposals/vol-7/elev.html" },
  { module: "Postlådan", status: "demo", note: "Demo-prototyp · backend MailItem-tabell saknas" },
  { module: "Banken (kontoutdrag, kommande fakturor)", status: "demo", note: "Demo · återanvänder /transactions API" },
  { module: "Arbetsgivaren + Maria-lönesamtal", status: "demo", note: "Demo · /employer + AI-prompts" },
  { module: "Bokföring · klassa transaktioner", status: "demo", note: "Demo · /transactions/classify finns" },
  { module: "Budget · plan vs utfall", status: "demo", note: "Demo · /budget API finns" },
  { module: "Skatteverket · deklaration", status: "demo", note: "Demo · /tax API finns" },
  { module: "Avanza · ISK + aktier", status: "demo", note: "Demo · /stocks finns" },
  { module: "Lånegivaren · CSN, bolån, KALP", status: "demo", note: "Demo · /loans + KALP-kalk" },
  { module: "Förbrukning · el, vatten, abon.", status: "demo", note: "Demo · /utility + /elpris finns" },
  { module: "Försäkringar (Folksam, Trygg-Hansa)", status: "demo", note: "Demo · ny modul · ej i v1" },
  { module: "Pension-myndigheten · 3 pelare", status: "demo", note: "Demo · backend prognos behövs" },
  { module: "Hyresvärden", status: "demo", note: "Demo · ny aktör · ej i v1" },
  { module: "Mina moduler · skol-flow", status: "demo", note: "Demo · /modules + /modules/:id finns" },
  { module: "Min portfolio · 14 kompetenser", status: "demo", note: "Demo · backend StudentMastery finns" },
  { module: "Mina uppdrag", status: "demo", note: "Demo · /assignments finns" },
  { module: "Chat med Anders Lind", status: "demo", note: "Demo · ny tabell behövs" },
  { module: "Lärar-feedback (modul + reflektion)", status: "demo", note: "Demo · finns i /modules-feedback" },
  { module: "Realtids notis-system", status: "demo", note: "Demo · ny tabell + WS-stream behövs" },
  { module: "Företagsmodul (Mitt företag)", status: "demo", note: "Demo · 13 nya tabeller per analysen" },
  { module: "Sambo-system (3 modeller)", status: "partial", note: "Backend partner_model fält finns" },
  { module: "Nivå-system 1/2/3", status: "partial", note: "Backend v2_level fält finns · lärar-CTA saknas" },
];

export function HubV2() {
  const [status, setStatus] = useState<V2Status | null>(null);

  useEffect(() => { v2Api.status().then(setStatus); }, []);

  return (
    <div style={{ minHeight: "100vh", background: "#0a0e1a", color: "#fff", paddingTop: 44 }}>
      {status && <V2Banner status={status} />}

      <div style={{ maxWidth: 1100, margin: "60px auto", padding: "0 24px" }}>
        <div style={{ marginBottom: 32 }}>
          <div style={{ fontFamily: "JetBrains Mono", fontSize: 11, fontWeight: 700, letterSpacing: 1.6, textTransform: "uppercase", color: "#fbbf24" }}>● V2 / Hub · migrations-status</div>
          <h1 style={{ fontFamily: "Source Serif 4", fontWeight: 700, fontSize: 56, letterSpacing: -1.6, lineHeight: 1, marginTop: 12, marginBottom: 12 }}>
            Vad är <em style={{ fontStyle: "italic", color: "#dc4c2b" }}>klart</em> i v2.
          </h1>
          <p style={{ fontFamily: "Source Serif 4", fontSize: 17, color: "rgba(255,255,255,0.7)", lineHeight: 1.5, maxWidth: 720 }}>
            Den här tavlan visar exakt var migrationen står. <em style={{ color: "#fbbf24" }}>Live</em> = i produktion mot riktig backend. <em style={{ color: "#c084fc" }}>Demo</em> = finns som prototyp i /proposals/vol-7/elev.html. <em style={{ color: "#6ee7b7" }}>Partial</em> = backend klar, frontend pågår.
          </p>
          {status && (
            <div style={{ marginTop: 18, fontFamily: "JetBrains Mono", fontSize: 11, color: "rgba(255,255,255,0.6)", letterSpacing: 0.6 }}>
              Du är: <strong style={{ color: "#fff" }}>{status.role}</strong> · v2-eligible: <strong style={{ color: status.v2_eligible ? "#6ee7b7" : "#fca5a5" }}>{String(status.v2_eligible)}</strong> · onboarding: <strong style={{ color: status.v2_onboarding_completed ? "#6ee7b7" : "#fbbf24" }}>{status.v2_onboarding_completed ? "klar" : "ej klar"}</strong> · level: <strong style={{ color: "#fbbf24" }}>{status.v2_level}</strong> · profile: <strong>{status.v2_spend_profile}</strong> · partner: <strong>{status.v2_partner_model}</strong>
              {status.is_super_admin && <> · <strong style={{ color: "#fbbf24" }}>SUPER-ADMIN</strong></>}
            </div>
          )}
        </div>

        <div style={{ background: "rgba(15,21,37,0.7)", border: "1px solid rgba(255,255,255,0.1)", borderRadius: 8, overflow: "hidden" }}>
          {ROADMAP.map((r) => (
            <div
              key={r.module}
              style={{
                display: "grid",
                gridTemplateColumns: "1.5fr 110px 1fr",
                gap: 14,
                padding: "12px 18px",
                borderBottom: "1px solid rgba(255,255,255,0.08)",
                alignItems: "center",
                fontFamily: "Inter, sans-serif",
                fontSize: 13,
              }}
            >
              <span style={{ fontFamily: "Source Serif 4", fontSize: 14, color: "#fff" }}>{r.module}</span>
              <span style={{
                fontFamily: "JetBrains Mono",
                fontSize: 9,
                fontWeight: 700,
                letterSpacing: 1.2,
                textTransform: "uppercase",
                padding: "4px 10px",
                borderRadius: 100,
                textAlign: "center",
                background: r.status === "live" ? "rgba(110,231,183,0.18)" : r.status === "partial" ? "rgba(251,191,36,0.18)" : "rgba(168,85,247,0.18)",
                color: r.status === "live" ? "#6ee7b7" : r.status === "partial" ? "#fbbf24" : "#c084fc",
                border: `1px solid ${r.status === "live" ? "rgba(110,231,183,0.35)" : r.status === "partial" ? "rgba(251,191,36,0.35)" : "rgba(168,85,247,0.35)"}`,
              }}>{r.status}</span>
              <span style={{ fontFamily: "JetBrains Mono", fontSize: 10.5, color: "rgba(255,255,255,0.6)" }}>{r.note}</span>
            </div>
          ))}
        </div>

        <div style={{ marginTop: 32, display: "flex", gap: 12 }}>
          <Link to="/proposals/vol-7/elev.html" style={{
            fontFamily: "JetBrains Mono", fontSize: 11, fontWeight: 700, letterSpacing: 1.2, textTransform: "uppercase",
            padding: "12px 22px", borderRadius: 100, background: "#fbbf24", color: "#422006", textDecoration: "none",
          }}>Öppna full demo-prototyp →</Link>
          <Link to="/dashboard" style={{
            fontFamily: "JetBrains Mono", fontSize: 11, fontWeight: 700, letterSpacing: 1.2, textTransform: "uppercase",
            padding: "12px 22px", borderRadius: 100, background: "transparent", border: "1px solid rgba(255,255,255,0.18)", color: "#fff", textDecoration: "none",
          }}>← Tillbaka till v1-dashboarden</Link>
        </div>
      </div>
    </div>
  );
}
