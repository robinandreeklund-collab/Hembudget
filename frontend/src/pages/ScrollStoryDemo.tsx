/**
 * ScrollStoryDemo — separat publik marknadsförings-demo på
 * /demo/scroll-story.
 *
 * En cinematic pinned scroll-storytelling som visar "En vecka i
 * Ekonomilabbet" — sju kapitel som triggas av scroll-position via
 * GSAP ScrollTrigger med scrub. Återanvänder data och designspråk
 * från Variant C (theme, EchoAvatar, Wellbeing-pentagonens matematik).
 *
 * Layout:
 * 1. Intro-frame (statisk tills scroll, hero med stort budskap)
 * 2. Pinned storytelling-zon (en stor pinnad container ~400vh)
 * 3. Final CTA (visar sig efter att storyn är klar)
 *
 * Reduced-motion: hela tidslinjen ersätts av en enkel vertikal kort-
 * lista där varje kapitel visas statiskt.
 */
import { useEffect, useRef } from "react";
import { Link } from "react-router-dom";
import gsap from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";
import { QRCodeSVG } from "qrcode.react";
import { registerScrollTrigger, useReducedMotion } from "@/hooks/useScrollAnimation";

// ─── Pentagon-matematik (återanvänt från WellbeingSection) ────────
// Wellbeing över 5 dimensioner: Ek (ekonomi), Hl (mat & hälsa),
// Sb (sociala band), Fr (fritid), Tr (trygghet).
type WBKey = "ek" | "hl" | "sb" | "fr" | "tr";
type WBScores = Record<WBKey, number>;
const DIMS: { key: WBKey; label: string }[] = [
  { key: "ek", label: "EKONOMI" },
  { key: "hl", label: "MAT & HÄLSA" },
  { key: "sb", label: "SOCIALA BAND" },
  { key: "fr", label: "FRITID" },
  { key: "tr", label: "TRYGGHET" },
];
const CX = 200, CY = 200, R = 140;
const angleAt = (i: number) => (Math.PI * 2 * i) / 5 - Math.PI / 2;
const point = (i: number, v: number): [number, number] => {
  const a = angleAt(i);
  const r = R * (v / 100);
  return [CX + Math.cos(a) * r, CY + Math.sin(a) * r];
};
const polyFor = (s: WBScores): string =>
  DIMS.map((d, i) => point(i, s[d.key]).join(",")).join(" ");
const wellbeingScore = (s: WBScores): number =>
  Math.round(
    s.ek * 0.25 + s.hl * 0.20 + s.sb * 0.20 + s.fr * 0.15 + s.tr * 0.20,
  );

// ─── Kapitel-tabell — copy + målvärden för Wellbeing per scen ───
type Chapter = {
  id: string;
  range: string;
  title: string;
  body: string;
  delta?: string;
  wb: WBScores;
};

const START: WBScores = { ek: 50, hl: 62, sb: 50, fr: 50, tr: 60 };

const CHAPTERS: Chapter[] = [
  {
    id: "ch1",
    range: "Vecka 1 · måndag 09:14",
    title: "Lönesamtalet",
    body:
      "Du börjar med ett lönesamtal. Marknadslönen ligger 1 500 kr över dig — du argumenterar och Maria höjer 3,5 %. Trygghet stiger.",
    delta: "+3,5 % lön · Trygghet ↗",
    wb: { ek: 58, hl: 62, sb: 50, fr: 50, tr: 68 },
  },
  {
    id: "ch2",
    range: "Vecka 1 · onsdag",
    title: "Du flyttar 5 000 kr till ISK",
    body:
      "Nytt sparmål: 25 % av lönen direkt till ISK. Ekonomi-dimensionen växer — bufferten blir två månadshyror.",
    delta: "+5 000 kr till ISK · Ekonomi ↗",
    wb: { ek: 70, hl: 62, sb: 50, fr: 50, tr: 70 },
  },
  {
    id: "ch3",
    range: "Vecka 1 · fredag 17:32",
    title: "\"Bio på Filmstaden — 180 kr?\"",
    body:
      "Kompisen pingar. 180 kr för biobiljett + popcorn. Säga ja eller nej? Systemet pausar — du måste välja.",
    wb: { ek: 70, hl: 62, sb: 50, fr: 50, tr: 70 },
  },
  {
    id: "ch4",
    range: "Vecka 1 · fredag 17:33",
    title: "Du säger ja",
    body:
      "180 kr dras. Sociala band stiger med 4 — fritidens tre poäng följer med. Saldot är fortfarande grönt.",
    delta: "−180 kr · Sociala +4 · Fritid +3",
    wb: { ek: 67, hl: 62, sb: 64, fr: 58, tr: 70 },
  },
  {
    id: "ch5",
    range: "Vecka 4 · söndag 19:18",
    title: "Månadsslut: ekonomin går inte ihop",
    body:
      "Hyran 8 500 kr, autogirot drar imorgon. Saldot: 7 300 kr. Du saknar 1 200 kr. Systemet pausar och tvingar fram ett beslut.",
    delta: "Saknas: −1 200 kr",
    wb: { ek: 42, hl: 60, sb: 64, fr: 58, tr: 50 },
  },
  {
    id: "ch6",
    range: "Vecka 4 · söndag 19:21",
    title: "Du väljer privatlån",
    body:
      "Privatlån 6,4 % över 36 mån. Banken kollar din inkomst, lånet hamnar i huvudboken. Lugnt val — ränta i normalsegmentet.",
    delta: "Lånar 1 500 kr · 460 kr/mån",
    wb: { ek: 52, hl: 60, sb: 64, fr: 58, tr: 58 },
  },
  {
    id: "ch7",
    range: "Vecka 5 · måndag 08:00",
    title: "Läraren ser hela bilden",
    body:
      "Tid på uppgift, varje val loggat, Wellbeing-trenden över hela veckan. Inte i ett separat verktyg — i samma vy som klassen.",
    delta: "Wellbeing 60 → live",
    wb: { ek: 56, hl: 62, sb: 66, fr: 60, tr: 62 },
  },
];

const REDUCED_THEME = {
  bg: "linear-gradient(180deg, #f0f9ff 0%, #fafaf9 50%, #ffffff 100%)",
  fg: "#0f172a",
  accent: "#dc4c2b",
  amber: "#fbbf24",
};

// Scaffold — polyFor och START konsumeras av PinnedStory:s timeline
// i fas 2. Tas bort när tidslinjen är wired.
const __SSD_SCAFFOLD = { polyFor, START };
void __SSD_SCAFFOLD;

export default function ScrollStoryDemo() {
  const reduced = useReducedMotion();
  return (
    <div
      style={{
        minHeight: "100vh",
        background: REDUCED_THEME.bg,
        color: REDUCED_THEME.fg,
        fontFamily: '"Inter", "Helvetica Neue", system-ui, sans-serif',
        overflowX: "hidden",
      }}
    >
      <style>{`
        .ssd-mono { font-family: "JetBrains Mono", ui-monospace, monospace; }
        .ssd-h1 { font-size: clamp(40px, 7vw, 80px); line-height: 1.02; font-weight: 700; letter-spacing: -2px; }
        .ssd-h2 { font-size: clamp(26px, 3.5vw, 38px); line-height: 1.1; font-weight: 600; letter-spacing: -0.6px; }
        .ssd-eyebrow { font-family: "JetBrains Mono", ui-monospace, monospace; font-size: 11px; letter-spacing: 1.8px; text-transform: uppercase; color: #64748b; }
        .ssd-btn { display: inline-flex; align-items: center; gap: 8px; padding: 12px 20px; border-radius: 10px; font-size: 14.5px; font-weight: 500; text-decoration: none; transition: all .15s; cursor: pointer; border: 0; }
        .ssd-btn-primary { background: #0f172a; color: #fff; }
        .ssd-btn-primary:hover { background: #000; }
        .ssd-btn-outline { background: #fff; color: #0f172a; border: 1px solid #cbd5e1; }
        .ssd-btn-outline:hover { border-color: #0f172a; }
        @keyframes ssd-bounce {
          0%, 20%, 50%, 80%, 100% { transform: translateY(0); }
          40% { transform: translateY(-8px); }
          60% { transform: translateY(-4px); }
        }
        .ssd-bounce { animation: ssd-bounce 2.4s ease-in-out infinite; }
      `}</style>

      <IntroFrame />
      {reduced ? <ReducedMotionStory /> : <PinnedStory />}
      <FinalCTA />
    </div>
  );
}

// ─────────────────────────────────────────────────────────────
// Intro frame (above the fold)
// ─────────────────────────────────────────────────────────────
function IntroFrame() {
  return (
    <section
      style={{
        minHeight: "100vh",
        padding: "32px 24px 56px",
        display: "grid",
        placeItems: "center",
        position: "relative",
      }}
    >
      <div
        style={{
          maxWidth: 880,
          margin: "0 auto",
          textAlign: "center",
          paddingTop: 24,
        }}
      >
        <span
          className="ssd-mono"
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: 6,
            fontSize: 11,
            padding: "5px 12px",
            background: "#fef3c7",
            color: "#78350f",
            borderRadius: 100,
            marginBottom: 28,
            letterSpacing: 1.2,
          }}
        >
          <span
            style={{
              width: 6,
              height: 6,
              background: "#dc4c2b",
              borderRadius: "50%",
              boxShadow: "0 0 0 3px rgba(220,76,43,.18)",
            }}
          />
          DEMO · EN VECKA I EKONOMILABBET
        </span>
        <h1 className="ssd-h1" style={{ marginBottom: 18 }}>
          Ekonomilabbet
          <br />
          <span style={{ color: "#dc4c2b" }}>där varje val har en konsekvens</span>
        </h1>
        <p
          style={{
            fontSize: 18,
            lineHeight: 1.55,
            color: "#475569",
            maxWidth: 620,
            margin: "0 auto 36px",
          }}
        >
          Ett pedagogiskt livslabb för skolan, hemmet och familjen. Pengar är
          ett medel för välmående — inte ett mål. Scrolla nedåt för att se en
          vecka spelas upp.
        </p>
        <div
          style={{
            display: "inline-flex",
            flexDirection: "column",
            alignItems: "center",
            gap: 14,
          }}
        >
          <div className="ssd-eyebrow">Scrolla för att starta</div>
          <div className="ssd-bounce" style={{ color: "#0f172a", fontSize: 28, lineHeight: 1 }}>
            ↓
          </div>
        </div>
      </div>
    </section>
  );
}

// ─────────────────────────────────────────────────────────────
// Pinned scroll storytelling — placeholder; fylls i Fas 2.
// ─────────────────────────────────────────────────────────────
function PinnedStory() {
  const sectionRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!sectionRef.current) return;
    registerScrollTrigger();
    const el = sectionRef.current;
    const ctx = gsap.context(() => {
      ScrollTrigger.create({
        trigger: el,
        start: "top top",
        end: "+=400%",
        pin: true,
        scrub: 1.2,
        anticipatePin: 1,
      });
    }, sectionRef);
    return () => ctx.revert();
  }, []);

  return (
    <section
      ref={sectionRef}
      style={{
        height: "100vh",
        background: "#0f172a",
        color: "#fff",
        position: "relative",
        overflow: "hidden",
      }}
    >
      <div
        style={{
          position: "absolute",
          inset: 0,
          display: "grid",
          placeItems: "center",
          padding: 24,
        }}
      >
        <div
          style={{
            textAlign: "center",
            maxWidth: 600,
          }}
        >
          <div className="ssd-eyebrow" style={{ color: "#94a3b8", marginBottom: 16 }}>
            Scrolla — storyn kommer i nästa commit
          </div>
          <h2 className="ssd-h2" style={{ color: "#fff" }}>
            Pinnad scroll-zon (Fas 2)
          </h2>
        </div>
      </div>
    </section>
  );
}

// ─────────────────────────────────────────────────────────────
// Reduced-motion fallback — vertikal kortlista istället för pin.
// ─────────────────────────────────────────────────────────────
function ReducedMotionStory() {
  return (
    <section style={{ padding: "48px 24px", background: "#0f172a", color: "#fff" }}>
      <div style={{ maxWidth: 720, margin: "0 auto" }}>
        <div className="ssd-eyebrow" style={{ color: "#fbbf24", marginBottom: 16 }}>
          En vecka i sju kapitel
        </div>
        <h2 className="ssd-h2" style={{ marginBottom: 24, color: "#fff" }}>
          Du har valt minskad rörelse — så här ser kapitlen ut.
        </h2>
        <ol style={{ listStyle: "none", padding: 0, margin: 0, display: "flex", flexDirection: "column", gap: 18 }}>
          {CHAPTERS.map((c, i) => (
            <li
              key={c.id}
              style={{
                background: "rgba(255,255,255,0.04)",
                border: "1px solid rgba(255,255,255,0.08)",
                borderRadius: 12,
                padding: "20px 22px",
              }}
            >
              <div
                className="ssd-mono"
                style={{
                  fontSize: 11,
                  letterSpacing: 1.2,
                  color: "#94a3b8",
                  marginBottom: 6,
                  textTransform: "uppercase",
                }}
              >
                Kapitel {i + 1} · {c.range}
              </div>
              <h3 style={{ fontSize: 20, fontWeight: 600, marginBottom: 8, color: "#fff" }}>
                {c.title}
              </h3>
              <p style={{ fontSize: 14.5, lineHeight: 1.55, color: "#cbd5e1", margin: 0 }}>
                {c.body}
              </p>
              {c.delta && (
                <div
                  className="ssd-mono"
                  style={{ fontSize: 12, color: "#fbbf24", marginTop: 10 }}
                >
                  → {c.delta}
                </div>
              )}
              <div
                className="ssd-mono"
                style={{
                  fontSize: 11.5,
                  color: "#10b981",
                  marginTop: 8,
                  letterSpacing: 0.5,
                }}
              >
                Wellbeing: {wellbeingScore(c.wb)} / 100
              </div>
            </li>
          ))}
        </ol>
      </div>
    </section>
  );
}

// ─────────────────────────────────────────────────────────────
// Final CTA — efter pinnade zonen
// ─────────────────────────────────────────────────────────────
function FinalCTA() {
  return (
    <section
      style={{
        padding: "96px 24px",
        background: "linear-gradient(180deg, #0f172a 0%, #1e293b 100%)",
        color: "#fff",
        textAlign: "center",
      }}
    >
      <div style={{ maxWidth: 720, margin: "0 auto" }}>
        <div className="ssd-eyebrow" style={{ color: "#fbbf24", marginBottom: 16 }}>
          Det är detta klassen får uppleva
        </div>
        <h2 className="ssd-h2" style={{ color: "#fff", marginBottom: 18 }}>
          Vill du testa själv?
        </h2>
        <p
          style={{
            fontSize: 16,
            lineHeight: 1.55,
            color: "#cbd5e1",
            maxWidth: 560,
            margin: "0 auto 32px",
          }}
        >
          Gratis under pilotåret 2026. Ingen bindningstid. Du väljer själv om
          du kör med en klass eller med dina egna barn.
        </p>
        <div
          style={{
            display: "flex",
            justifyContent: "center",
            gap: 12,
            flexWrap: "wrap",
            marginBottom: 36,
          }}
        >
          <Link to="/signup/teacher" className="ssd-btn ssd-btn-primary" style={{ background: "#fbbf24", color: "#0f172a" }}>
            Starta som lärare →
          </Link>
          <Link to="/signup/parent" className="ssd-btn ssd-btn-outline" style={{ background: "transparent", color: "#fff", border: "1px solid rgba(255,255,255,0.25)" }}>
            Starta som förälder →
          </Link>
        </div>

        <div
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: 14,
            padding: "14px 18px",
            background: "rgba(255,255,255,0.04)",
            border: "1px solid rgba(255,255,255,0.08)",
            borderRadius: 12,
          }}
        >
          <div
            style={{
              background: "#fff",
              padding: 6,
              borderRadius: 6,
              lineHeight: 0,
            }}
          >
            <QRCodeSVG
              value="https://ekonomilabbet.org"
              size={64}
              bgColor="#ffffff"
              fgColor="#0f172a"
              level="M"
            />
          </div>
          <div style={{ textAlign: "left" }}>
            <div className="ssd-mono" style={{ fontSize: 11, color: "#94a3b8", letterSpacing: 1, marginBottom: 2 }}>
              SKANNA & DELA
            </div>
            <div style={{ fontSize: 14, color: "#fff" }}>
              ekonomilabbet.org
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
