/**
 * Bug #7 · Företag-toggle med flip + Coming Soon-vy.
 *
 * Tillhandahåller:
 *   - useCompanyMode() hook · läser/skriver mode i localStorage
 *   - <CompanyModeToggle /> · pill-knapp i topbar som flippar
 *   - <CompanyComingSoon /> · panel som visas när mode = "business"
 *
 * Speglar vol-7-prototypens .mode-switch + body[data-mode="business"]-
 * mönster, men anpassat för React/Vite.
 */
import { useEffect, useState } from "react";

type Mode = "private" | "business";

const KEY = "hb_company_mode";

function readMode(): Mode {
  return (localStorage.getItem(KEY) as Mode) || "private";
}

function writeMode(m: Mode) {
  localStorage.setItem(KEY, m);
  document.body.setAttribute("data-mode", m);
}

export function useCompanyMode(): [Mode, () => void] {
  const [mode, setMode] = useState<Mode>(readMode());

  useEffect(() => {
    document.body.setAttribute("data-mode", mode);
  }, [mode]);

  const toggle = () => {
    // Steg 1: flip-out
    const app = document.querySelector(".v2-hub-root, .v2-larare-root");
    app?.classList.add("flip-out");
    setTimeout(() => {
      const next: Mode = mode === "private" ? "business" : "private";
      writeMode(next);
      setMode(next);
      app?.classList.remove("flip-out");
      app?.classList.add("flip-in");
      setTimeout(() => app?.classList.remove("flip-in"), 550);
    }, 460);
  };

  return [mode, toggle];
}


export function CompanyModeToggle() {
  const [mode, toggle] = useCompanyMode();

  return (
    <button
      type="button"
      onClick={toggle}
      className="company-mode-switch"
      title={
        mode === "private"
          ? "Byt till företag (Coming soon)"
          : "Byt till privat"
      }
      style={{
        background:
          mode === "business"
            ? "rgba(99,102,241,0.15)"
            : "rgba(255,255,255,0.04)",
        border: `1px solid ${
          mode === "business"
            ? "rgba(99,102,241,0.4)"
            : "rgba(255,255,255,0.18)"
        }`,
        color:
          mode === "business" ? "#c7d2fe" : "rgba(255,255,255,0.85)",
        padding: "6px 12px",
        borderRadius: 100,
        cursor: "pointer",
        fontSize: "0.78rem",
        fontFamily: "JetBrains Mono, monospace",
        fontWeight: 600,
        letterSpacing: 1.1,
        textTransform: "uppercase",
        transition: "all 0.2s",
      }}
    >
      {mode === "private" ? "→ Företag" : "→ Privat"}
    </button>
  );
}


/**
 * Coming Soon-panel som visas när mode === "business".
 * Wrappa innehållet i hub-vyer med detta — om mode är business
 * visas Coming Soon, annars renderas children.
 */
export function CompanyModeWrapper({ children }: { children: React.ReactNode }) {
  const [mode] = useCompanyMode();

  if (mode === "business") {
    return <CompanyComingSoon />;
  }
  return <>{children}</>;
}


export function CompanyComingSoon() {
  return (
    <div
      style={{
        padding: "60px 40px",
        textAlign: "center",
        maxWidth: 720,
        margin: "40px auto",
        background:
          "linear-gradient(135deg, rgba(99,102,241,0.05), rgba(168,85,247,0.05))",
        border: "1px solid rgba(99,102,241,0.25)",
        borderRadius: 16,
      }}
    >
      <div
        style={{
          fontFamily: "JetBrains Mono, monospace",
          fontSize: 11,
          color: "#818cf8",
          fontWeight: 700,
          letterSpacing: 1.6,
          textTransform: "uppercase",
        }}
      >
        Företagsläge · KOMMER SNART
      </div>
      <h1
        style={{
          color: "white",
          fontSize: "2rem",
          margin: "16px 0",
          fontFamily: "Source Serif 4, Georgia, serif",
        }}
      >
        Driv ditt eget <em style={{ color: "#c7d2fe" }}>aktiebolag</em>.
      </h1>
      <p
        style={{
          color: "rgba(255,255,255,0.7)",
          fontFamily: "Source Serif 4, Georgia, serif",
          fontSize: "1.1rem",
          maxWidth: 520,
          margin: "0 auto 24px",
        }}
      >
        Snart kan eleven starta enskild firma eller AB, hantera moms
        kvartalsvis, sätta lön till sig själv, deklarera bolagets
        resultat och hantera kunder/fakturor.
      </p>
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))",
          gap: 12,
          marginTop: 32,
          textAlign: "left",
        }}
      >
        {[
          { e: "01", t: "Bolagsform", d: "Enskild firma · AB · Handelsbolag" },
          { e: "02", t: "Moms-deklaration", d: "Kvartalsvis till Skatteverket" },
          { e: "03", t: "Bokföring", d: "Inkomster, utgifter, balansrapport" },
          { e: "04", t: "Lön till dig själv", d: "AGI + arbetsgivaravgift" },
          { e: "05", t: "Kunder & fakturor", d: "Sälja tjänster, ROT/RUT" },
          { e: "06", t: "Bolagsskatt", d: "Årsdeklaration K10" },
        ].map((card) => (
          <div
            key={card.e}
            style={{
              padding: 14,
              background: "rgba(255,255,255,0.03)",
              border: "1px solid rgba(99,102,241,0.15)",
              borderRadius: 10,
            }}
          >
            <div
              style={{
                fontFamily: "JetBrains Mono, monospace",
                fontSize: 9,
                color: "#818cf8",
                fontWeight: 700,
              }}
            >
              {card.e}
            </div>
            <strong style={{ color: "white", fontSize: "0.95rem" }}>
              {card.t}
            </strong>
            <div
              style={{
                color: "rgba(255,255,255,0.6)",
                fontSize: "0.8rem",
                marginTop: 2,
              }}
            >
              {card.d}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
