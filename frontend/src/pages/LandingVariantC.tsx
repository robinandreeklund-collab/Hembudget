/**
 * LandingVariantC.tsx — alternativ landing-design (SaaS/dashboard-stil).
 *
 * Aktiveras av super-admin via /admin/landing/variant ('c'). Frontend
 * fetchar /landing/variant vid mount och App.tsx routar dit.
 *
 * Designskillnader mot Landing.tsx (paper-stil):
 *  - Inter + JetBrains Mono i stället för Spectral serif
 *  - Mjuk pastel-palett (#f8fafc bakgrund)
 *  - Tab-navigation, command-palette-sök, status-strip
 *  - Mascoten "Ugglan" som AI-coach-personlighet
 *  - Tre-vyer-kort som inkluderar kommande riktig-ekonomi-pitch
 *
 * Innehåll byggs ut sektion för sektion. Just nu: Header + Hero.
 */
import { useEffect, useRef, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import gsap from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";
import { CELL_INFO, type CellInfo } from "@/data/landingCells";
import { registerScrollTrigger, useReducedMotion } from "@/hooks/useScrollAnimation";

// ---------- Delade data ----------

type CellCat = "grund" | "fordj" | "expert" | "konto" | "risk" | "prof";

type Cell = {
  n: number;
  sym: string;
  name: string;
  desc: string;
  cat: CellCat;
};

// 32 celler i periodiska systemet — språkfix från Variant C-bundlen:
// "Övärnt" → "Övertid", "tygg" → "trygg", "Räntek." → "Räntebind."
const PERIODIC_CELLS: Cell[] = [
  { n: 1, sym: "Lö", name: "Lön", desc: "brutto", cat: "grund" },
  { n: 2, sym: "Sk", name: "Skatt", desc: "netto", cat: "grund" },
  { n: 3, sym: "Bu", name: "Budget", desc: "månad", cat: "grund" },
  { n: 4, sym: "Ku", name: "Kontoutdr.", desc: "läsa", cat: "fordj" },
  { n: 5, sym: "Ka", name: "Kalkyl", desc: "verklig.", cat: "fordj" },
  { n: 6, sym: "Sa", name: "Saldo", desc: "koll", cat: "expert" },
  { n: 7, sym: "Sp", name: "Sparande", desc: "mål", cat: "konto" },
  { n: 8, sym: "Hu", name: "Hushåll", desc: "delat", cat: "risk" },
  { n: 9, sym: "Bl", name: "Bolån", desc: "amort.", cat: "grund" },
  { n: 10, sym: "Am", name: "Amort.", desc: "krav", cat: "grund" },
  { n: 11, sym: "Ot", name: "Övertid", desc: "lön+", cat: "fordj" },
  { n: 12, sym: "Kk", name: "Kreditk.", desc: "kostn.", cat: "fordj" },
  { n: 13, sym: "Lg", name: "Lägenhet", desc: "köp", cat: "expert" },
  { n: 14, sym: "Rb", name: "Räntebind.", desc: "rörl/fast", cat: "konto" },
  { n: 15, sym: "AI", name: "Fråga Ekon", desc: "AI", cat: "risk" },
  { n: 16, sym: "Pf", name: "Portfolio", desc: "PDF-export", cat: "prof" },
  { n: 17, sym: "In", name: "Inkomst", desc: "flöde", cat: "grund" },
  { n: 18, sym: "Ut", name: "Utgift", desc: "flöde", cat: "grund" },
  { n: 19, sym: "Öv", name: "Översk.", desc: "spar", cat: "fordj" },
  { n: 20, sym: "Un", name: "Underskott", desc: "lån", cat: "fordj" },
  { n: 21, sym: "Rä", name: "Ränta", desc: "fast/rör.", cat: "expert" },
  { n: 22, sym: "Ef", name: "Effekt.r.", desc: "verklig", cat: "konto" },
  { n: 23, sym: "Rp", name: "Rubric", desc: "bedömn.", cat: "risk" },
  { n: 24, sym: "Qr", name: "QR-kod", desc: "elev-login", cat: "prof" },
  { n: 25, sym: "Pe", name: "Pension", desc: "premie", cat: "grund" },
  { n: 26, sym: "Fs", name: "Försäkr.", desc: "trygg", cat: "grund" },
  { n: 27, sym: "Fo", name: "Fond", desc: "risk", cat: "fordj" },
  { n: 28, sym: "Ak", name: "Aktie", desc: "split", cat: "fordj" },
  { n: 29, sym: "Sn", name: "SMS-lån", desc: "ränta", cat: "expert" },
  { n: 30, sym: "Bg", name: "Bra köp", desc: "jmf", cat: "konto" },
  { n: 31, sym: "El", name: "EkonomilabbetID", desc: "PIN-scen.", cat: "risk" },
  { n: 32, sym: "Mo", name: "Modul", desc: "7 steg", cat: "prof" },
  // Rad 5 — nya feature-områden i v5 (Ag/Ls/Bk/Ek).
  { n: 33, sym: "Ag", name: "Arbetsgiv.", desc: "satisf.", cat: "fordj" },
  { n: 34, sym: "Ls", name: "Lönesamtal", desc: "5 ronder", cat: "expert" },
  { n: 35, sym: "Bk", name: "Banken", desc: "EklabbID", cat: "konto" },
  { n: 36, sym: "Ek", name: "EkonomiSkalan", desc: "kreditb.", cat: "risk" },
];

const PALETTE: Record<CellCat, { bg: string; fg: string; border: string }> = {
  grund: { bg: "#fef3c7", fg: "#78350f", border: "rgba(120,53,15,.2)" },
  fordj: { bg: "#dbeafe", fg: "#1e3a8a", border: "rgba(30,58,138,.2)" },
  expert: { bg: "#ede9fe", fg: "#4c1d95", border: "rgba(76,29,149,.2)" },
  konto: { bg: "#d1fae5", fg: "#064e3b", border: "rgba(6,78,59,.2)" },
  risk: { bg: "#fee2e2", fg: "#7f1d1d", border: "rgba(127,29,29,.2)" },
  prof: { bg: "#0f172a", fg: "#fef3c7", border: "#0f172a" },
};

const CATEGORY_META: Record<CellCat, { label: string; count: number }> = {
  grund: { label: "Grundkompetens", count: 9 },
  fordj: { label: "Fördjupning", count: 9 },
  expert: { label: "Expert", count: 5 },
  konto: { label: "Konto & flöde", count: 5 },
  risk: { label: "Riskgrupp", count: 5 },
  prof: { label: "Professorns tillskott", count: 3 },
};

// 9 features med målgrupp-tagg så tab-filtret fungerar.
const FEATURES: Array<{
  sym: string;
  title: string;
  desc: string;
  cat: CellCat;
  audience: ("larare" | "hem" | "elev")[];
}> = [
  {
    sym: "Pf",
    title: "Unik elev-profil",
    desc: "Varje elev får slumpat yrke, lön, stad och livssituation. Ingen i klassen har samma utgångsläge.",
    cat: "prof",
    audience: ["larare", "elev"],
  },
  {
    sym: "Ku",
    title: "Riktiga PDF:er",
    desc: "Du genererar kontoutdrag, lönespec, lånebesked och kreditkortsfakturor som eleven själv importerar.",
    cat: "fordj",
    audience: ["larare", "hem"],
  },
  {
    sym: "Bu",
    title: "Budget mot verklighet",
    desc: "Eleven sätter månadsbudget från Konsumentverkets 2026-siffror — sedan jämförs den mot faktiska köp.",
    cat: "grund",
    audience: ["larare", "hem", "elev"],
  },
  {
    sym: "Bl",
    title: "Bolåne-beslut",
    desc: "Historiska räntor från Riksbanken. Eleven väljer rörlig eller bunden — systemet visar facit efter horisonten.",
    cat: "grund",
    audience: ["larare", "hem", "elev"],
  },
  {
    sym: "Ov",
    title: "Livet händer",
    desc: "Diskmaskinen går sönder. Sjukdagar sänker lönen. Julshopping exploderar. Eleven övar på det oväntade.",
    cat: "fordj",
    audience: ["larare", "elev"],
  },
  {
    sym: "Hu",
    title: "Familjer",
    desc: "Två elever kan dela ekonomi — sambohushåll med gemensam budget, räkningar och sparmål.",
    cat: "risk",
    audience: ["larare", "hem"],
  },
  {
    sym: "Rp",
    title: "Översiktsmatris",
    desc: "Status per elev/kompetens och uppdrag. Facit för varje kategorisering — grönt eller rött på en blick.",
    cat: "risk",
    audience: ["larare", "hem"],
  },
  {
    sym: "AI",
    title: "Fråga Ekon (AI)",
    desc: "Multi-turn coach på Claude Sonnet. Anpassar språket till elevens nivå — mer Sokrates där grunder saknas.",
    cat: "risk",
    audience: ["larare", "hem", "elev"],
  },
  {
    sym: "Sp",
    title: "Sparmål & uppdrag",
    desc: "Tydliga uppdrag: spara 2 000 kr, balansera månaden, kategorisera alla köp. Status uppdateras live.",
    cat: "konto",
    audience: ["larare", "hem", "elev"],
  },
  // De tre nya v5-områdena (Ag/Ls/Bk).
  {
    sym: "Ag",
    title: "Arbetsgivare med personlighet",
    desc: "17 yrken får riktiga kollektivavtal. Sjukanmälan, VAB och slumpade arbetsplats-frågor flyttar elevens nöjdhetsfaktor 0–100.",
    cat: "fordj",
    audience: ["larare", "elev"],
  },
  {
    sym: "Ls",
    title: "Förhandla lön mot AI",
    desc: "5-rond lönesamtal med AI-chefen Maria. Slutbudet jämförs mot avtalets revisionsutrymme — och syns i nästa månads lönespec, inte direkt.",
    cat: "expert",
    audience: ["larare", "elev"],
  },
  {
    sym: "Bk",
    title: "Banken som ett eget rum",
    desc: "EkonomilabbetID med QR + PIN, signering av kommande betalningar, och EkonomiSkalan som mäter hur sena betalningar påverkar elevens kreditbetyg.",
    cat: "konto",
    audience: ["larare", "hem", "elev"],
  },
];

// ---------- Root ----------

export default function LandingVariantC() {
  const rootRef = useRef<HTMLDivElement | null>(null);
  const reduced = useReducedMotion();

  // Registrera ScrollTrigger + sätt upp generiska fade-up för alla
  // sektioner utom Hero (som har egen pin) + stagger för periodiska
  // tabellens celler. Reduced-motion: hoppar over alla animationer.
  useEffect(() => {
    registerScrollTrigger();
    if (reduced || !rootRef.current) return;
    const root = rootRef.current;

    const ctx = gsap.context(() => {
      // Fade-up: alla sektioner utom första (Hero, pinned).
      const sections = root.querySelectorAll<HTMLElement>("section");
      sections.forEach((s, i) => {
        if (i === 0) return;
        gsap.from(s, {
          opacity: 0,
          y: 28,
          duration: 0.85,
          ease: "power2.out",
          scrollTrigger: { trigger: s, start: "top 85%", once: true },
        });
      });

      // Periodic-table-cellerna staggrar in slumpmässigt.
      const grids = root.querySelectorAll<HTMLElement>(".vc-periodic-grid");
      grids.forEach((grid) => {
        const cells = grid.querySelectorAll<HTMLElement>(".cell");
        if (!cells.length) return;
        gsap.from(cells, {
          opacity: 0,
          scale: 0.6,
          duration: 0.45,
          stagger: { amount: 0.7, from: "random" },
          ease: "back.out(1.5)",
          scrollTrigger: { trigger: grid, start: "top 80%", once: true },
        });
      });
    }, rootRef);

    return () => ctx.revert();
  }, [reduced]);
  return (
    <div
      ref={rootRef}
      className="vc-root"
      style={{
        width: "100%",
        minHeight: "100vh",
        background: "#f8fafc",
        fontFamily: '"Inter", "Helvetica Neue", system-ui, sans-serif',
        color: "#0f172a",
      }}
    >
      <SharedStyles />
      <Header />
      <Hero />
      <Features />
      <ManifestoSection theme={THEME} />
      <WellbeingSection theme={THEME} />
      <AccountingSection theme={THEME} />
      <ThreeModesSection theme={THEME} />
      <StocksSection theme={THEME} />
      <CreditTriggerSection theme={THEME} />
      <LifeSimSection theme={THEME} />
      <EmployerSection theme={THEME} />
      <SalaryTalkSection theme={THEME} />
      <BankSection theme={THEME} />
      <SocraticAISection theme={THEME} />
      <MyCompanySection theme={THEME} />
      <PriceSection theme={THEME} />
      <Faq />
      <FoundersQuoteSection theme={THEME} />
      <Cta />
      <Contact />
      <Footer />
    </div>
  );
}

const FAQS = [
  {
    q: "Vad kostar Ekonomilabbet?",
    a: "Gratis under pilotåret 2026 — både för skolor och föräldrar. Inga dolda kostnader. Från 2027 sätts en avgift per användare i dialog med pilotkunderna.",
  },
  {
    q: "Är det GDPR-säkert?",
    a: "Ja. All användardata sparas i svensk molntjänst (Google Cloud Run, europe-west1). Vi delar inga personuppgifter med tredje part. AI-anropen anonymiseras — Claude ser aldrig namn eller personnummer.",
  },
  {
    q: "Vad behöver vi installera?",
    a: "Inget. Ekonomilabbet är en webbapp. Den vuxna (lärare eller förälder) skapar konto, lägger in elever/barn och de loggar in med en 6-teckenskod eller QR-kod.",
  },
  {
    q: "Kan föräldrar använda detta hemma?",
    a: "Ja, det är ett av tre huvudspår. Som förälder skapar du ett familjekonto, lägger till dina barn och följer deras arbete i samma admin-vy som en lärare.",
  },
  {
    q: "Går det att använda utan AI?",
    a: "Absolut. Alla pedagogiska flöden (moduler, reflektioner, quiz, rubric, portfolio) fungerar utan AI. AI är en ren extra-funktion som kan aktiveras per konto.",
  },
  {
    q: "Kan elever eller barn komma åt varandras data?",
    a: "Nej. Varje elev/barn har en egen tenant-isolerad dataström, ingen cross-access. Den vuxna ser bara sina egna användare.",
  },
  {
    q: "Vad händer med elevernas data när året är slut?",
    a: "Du som lärare/förälder bestämmer. Du kan exportera portfolio-PDF:er per elev eller hela klassen som ZIP, och sedan radera kontona. Datan tas bort permanent — vi behåller ingen kopia.",
  },
  {
    q: "Vilken AI-modell används?",
    a: "Claude Sonnet 4.6 för coachning och rubric-förslag, Haiku 4.5 för snabba interaktioner som lönesamtal. AI-anropen är gatade per lärarkonto och kan stängas av helt.",
  },
  {
    q: "Kan jag importera befintliga moduler från andra system?",
    a: "Inte i pilotåret. Modulerna är inbyggda i Ekonomilabbet och uppdateras tillsammans med läroplansförändringar. Egna uppdrag kan läggas in fritt — moduler som format kommer 2027.",
  },
];

// Tema som delas av alla v5-sektioner. Klassnamn matchar SharedStyles nedan.
type Theme = {
  h2: string;
  body: string;
  eyebrow: string;
  mono: string;
  btn: string;
  btnPrimary: string;
  rule: string;
  cardBg: string;
  cardBg2: string;
  fg: string;
  muted: string;
  accent: string;
  radius: number;
  serifFont: string;
};

const THEME: Theme = {
  h2: "vc-h2",
  body: "",
  eyebrow: "vc-eyebrow-c",
  mono: "vc-mono",
  btn: "vc-btn",
  btnPrimary: "vc-btn-primary",
  rule: "#e2e8f0",
  cardBg: "#fff",
  cardBg2: "#fef3c7",
  fg: "#0f172a",
  muted: "#64748b",
  accent: "#dc4c2b",
  radius: 10,
  serifFont: '"Source Serif 4", Georgia, serif',
};

// ─── Atomer ───────────────────────────────────────────────────────
// EchoAvatar: AI-coach-avatar med koncentriska "ekot"-ringar runt en
// glödande kärna. Ingen ansikte, ingen djur — läses som intelligens + ljud.
function EchoAvatar({ size = 56 }: { size?: number }) {
  const [hover, setHover] = useState(false);
  return (
    <div
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      style={{
        width: size,
        height: size,
        flexShrink: 0,
        borderRadius: "50%",
        position: "relative",
        overflow: "hidden",
        background:
          "radial-gradient(circle at 35% 30%, #1e293b 0%, #0f172a 60%, #020617 100%)",
        border: "1.5px solid rgba(251,191,36,0.35)",
        boxShadow: hover
          ? "0 0 0 3px rgba(251,191,36,0.15), 0 6px 20px -4px rgba(217,119,6,0.5)"
          : "0 4px 14px -3px rgba(15,23,42,0.4)",
        transition: "box-shadow .25s ease",
        display: "grid",
        placeItems: "center",
      }}
    >
      <style>{`
        @keyframes vc-echo-ripple {
          0%   { transform: scale(0.4); opacity: 0.9; }
          100% { transform: scale(1.6); opacity: 0; }
        }
        @keyframes vc-echo-core {
          0%, 100% { transform: scale(1);    filter: brightness(1); }
          50%      { transform: scale(1.18); filter: brightness(1.3); }
        }
        .vc-echo-ring { animation: vc-echo-ripple 2.4s cubic-bezier(.2,.6,.2,1) infinite; }
        .vc-echo-ring.r2 { animation-delay: 0.8s; }
        .vc-echo-ring.r3 { animation-delay: 1.6s; }
        .vc-echo-active .vc-echo-ring { animation-duration: 1.4s; }
        .vc-echo-core { animation: vc-echo-core 2.2s ease-in-out infinite; }
      `}</style>
      <svg
        viewBox="0 0 100 100"
        width={size}
        height={size}
        className={hover ? "vc-echo-active" : ""}
        style={{ display: "block", overflow: "visible" }}
      >
        <defs>
          <radialGradient id="vc-echo-core-grad" cx="50%" cy="50%" r="50%">
            <stop offset="0%" stopColor="#fef3c7" />
            <stop offset="40%" stopColor="#fbbf24" />
            <stop offset="80%" stopColor="#d97706" />
            <stop offset="100%" stopColor="#92400e" stopOpacity="0" />
          </radialGradient>
        </defs>
        <g style={{ transformOrigin: "50px 50px" }}>
          <circle className="vc-echo-ring" cx="50" cy="50" r="14" fill="none" stroke="#fbbf24" strokeWidth="1.2" style={{ transformOrigin: "50px 50px" }} />
          <circle className="vc-echo-ring r2" cx="50" cy="50" r="14" fill="none" stroke="#fbbf24" strokeWidth="1.2" style={{ transformOrigin: "50px 50px" }} />
          <circle className="vc-echo-ring r3" cx="50" cy="50" r="14" fill="none" stroke="#fbbf24" strokeWidth="1.2" style={{ transformOrigin: "50px 50px" }} />
        </g>
        <g className="vc-echo-core" style={{ transformOrigin: "50px 50px" }}>
          <circle cx="50" cy="50" r="16" fill="url(#vc-echo-core-grad)" opacity="0.7" />
          <circle cx="50" cy="50" r="9" fill="#fef3c7" />
          <circle cx="50" cy="50" r="5" fill="#fff" />
        </g>
      </svg>
    </div>
  );
}

// SectionCellData: liten cell som inleder varje v5-sektion (Wb/Hb/Lg…).
type SectionCellData = { sym: string; n: string; label: string };

function SectionCell({ cell, dark }: { cell: SectionCellData; dark?: boolean }) {
  const isDark = !!dark;
  const bg = isDark ? "#0f172a" : "#fef3c7";
  const fg = isDark ? "#fef3c7" : "#78350f";
  const border = isDark ? "#0f172a" : "rgba(120,53,15,0.25)";
  return (
    <div
      style={{
        width: 64,
        height: 64,
        padding: 6,
        background: bg,
        color: fg,
        border: `1px solid ${border}`,
        borderRadius: 6,
        position: "relative",
        fontFamily: 'ui-monospace, "JetBrains Mono", monospace',
        flexShrink: 0,
        display: "flex",
        flexDirection: "column",
        justifyContent: "space-between",
      }}
    >
      <div style={{ fontSize: 9, opacity: 0.7, letterSpacing: 0.5 }}>{cell.n}</div>
      <div style={{ fontSize: 22, fontWeight: 700, letterSpacing: -0.3, lineHeight: 1, textAlign: "left" }}>{cell.sym}</div>
      <div style={{ fontSize: 8, opacity: 0.7, letterSpacing: 0.5, textTransform: "uppercase" }}>{cell.label}</div>
    </div>
  );
}

function SectionHeader({
  cell,
  eyebrow,
  children,
  theme,
  dark,
}: {
  cell: SectionCellData;
  eyebrow: string;
  children: ReactNode;
  theme: Theme;
  dark?: boolean;
}) {
  return (
    <div style={{ display: "flex", alignItems: "flex-start", gap: 24, marginBottom: 24 }}>
      <SectionCell cell={cell} dark={dark} />
      <div style={{ paddingTop: 4 }}>
        <div className={theme.eyebrow} style={{ marginBottom: 12, color: dark ? "#94a3b8" : "#64748b" }}>
          {eyebrow}
        </div>
        <h2 className={theme.h2} style={{ margin: 0, color: dark ? "#fff" : "#0f172a", maxWidth: 820 }}>
          {children}
        </h2>
      </div>
    </div>
  );
}

// NewSectionHeader — alias för SectionHeader, används av v5:s tre
// extrasektioner (Employer/SalaryTalk/Bank). Behåller separat namn så
// att källkoden mappar 1:1 mot v5-mockupen.
const NewSectionHeader = SectionHeader;

function SharedStyles() {
  return (
    <style>{`
      .vc-mono { font-family: "JetBrains Mono", ui-monospace, monospace; }
      .vc-h1 { font-size: 56px; line-height: 1.02; font-weight: 700; letter-spacing: -1.6px; }
      .vc-h2 { font-size: 36px; line-height: 1.05; font-weight: 700; letter-spacing: -.8px; }
      .vc-kbd { display: inline-flex; align-items: center; justify-content: center; min-width: 18px; padding: 1px 5px; border: 1px solid rgba(0,0,0,.15); border-bottom-width: 2px; border-radius: 4px; font-family: ui-monospace, monospace; font-size: 10.5px; background: #fff; color: #475569; }
      .vc-btn { padding: 9px 14px; border-radius: 8px; font-size: 13.5px; font-weight: 500; transition: all .12s; display: inline-flex; align-items: center; gap: 6px; cursor: pointer; border: 0; font-family: inherit; }
      .vc-btn-primary { background: #0f172a; color: #fff; }
      .vc-btn-primary:hover { background: #000; }
      .vc-btn-ghost { color: #334155; background: transparent; }
      .vc-btn-ghost:hover { background: rgba(0,0,0,.05); }
      .vc-btn-outline { border: 1px solid #cbd5e1; background: #fff; color: #0f172a; }
      .vc-btn-outline:hover { border-color: #0f172a; }
      .vc-card { background: #fff; border: 1px solid #e2e8f0; border-radius: 10px; transition: all .12s; }
      .vc-card:hover { border-color: #94a3b8; box-shadow: 0 4px 14px rgba(15,23,42,.06); }
      .vc-tab { padding: 7px 12px; border-radius: 6px; font-size: 13px; font-weight: 500; cursor: pointer; transition: all .12s; background: transparent; border: 0; font-family: inherit; }
      .vc-tab-on { background: #fff; color: #0f172a; box-shadow: 0 1px 2px rgba(0,0,0,.05), 0 0 0 1px rgba(0,0,0,.05); }
      .vc-tab-off { color: #64748b; }
      .vc-tab-off:hover { color: #0f172a; }
      .vc-eyebrow { font-family: "JetBrains Mono", ui-monospace, monospace; font-size: 11px; letter-spacing: 1.5px; text-transform: uppercase; color: #64748b; }
      .vc-eyebrow-c { font-family: "JetBrains Mono", ui-monospace, monospace; font-size: 11px; letter-spacing: 1.5px; text-transform: uppercase; color: #64748b; }
      .vc-dot { width: 6px; height: 6px; border-radius: 50%; background: #10b981; box-shadow: 0 0 0 3px rgba(16,185,129,.18); }
      .vc-hamburger { display: none; }
      .vc-periodic-grid { display: grid; grid-template-columns: repeat(8, 1fr); gap: 4px; }
      .vc-hero-section { padding: 32px 24px 16px; }
      @media (max-width: 768px) {
        .vc-h1 { font-size: 36px; letter-spacing: -1.2px; }
        .vc-h2 { font-size: 28px; }
        .vc-nav-desktop { display: none !important; }
        .vc-search-desktop { display: none !important; }
        .vc-login-desktop { display: none !important; }
        .vc-hamburger { display: inline-flex !important; }
        .vc-hero-section { padding: 24px 16px 8px !important; }
      }
      @media (max-width: 600px) {
        .vc-periodic-grid { grid-template-columns: repeat(6, 1fr) !important; gap: 3px !important; }
      }
      @media (max-width: 420px) {
        .vc-periodic-grid { grid-template-columns: repeat(4, 1fr) !important; }
      }
      /* Mobile-padding för alla sektioner i Variant C — override:ar
         inline-paddings från komponentinnerligheten (kräver !important
         pga inline-spec). Vertikalt halveras nästan, horisontellt 16px.*/
      @media (max-width: 768px) {
        .vc-root section:not(.vc-hero-section) {
          padding: 40px 16px !important;
        }
        .vc-root header { padding-left: 16px !important; padding-right: 16px !important; }
        .vc-root footer > div:first-child { padding-left: 16px !important; padding-right: 16px !important; }
      }
    `}</style>
  );
}

// ---------- Header ----------

function Header() {
  const [searchOpen, setSearchOpen] = useState(false);
  const [pickedCell, setPickedCell] = useState<CellInfo | null>(null);
  const [mobileOpen, setMobileOpen] = useState(false);
  const closeMobile = () => setMobileOpen(false);

  // Cmd/Ctrl+K aktiverar söket. Esc stänger.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setSearchOpen((v) => !v);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  return (
    <header
      style={{
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        padding: "12px 24px",
        borderBottom: "1px solid #e2e8f0",
        background: "#fff",
        position: "sticky",
        top: 0,
        zIndex: 10,
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 24 }}>
        <Link
          to="/"
          style={{
            display: "flex",
            alignItems: "center",
            gap: 8,
            textDecoration: "none",
            color: "inherit",
          }}
        >
          <div
            style={{
              width: 24,
              height: 24,
              background: "#0f172a",
              color: "#fef3c7",
              borderRadius: 6,
              display: "grid",
              placeItems: "center",
              fontSize: 11,
              fontWeight: 700,
              fontFamily: 'ui-monospace, "SF Mono", monospace',
            }}
          >
            El
          </div>
          <span style={{ fontSize: 15, fontWeight: 600, letterSpacing: -0.2 }}>
            Ekonomilabbet
          </span>
          <span
            className="vc-mono"
            style={{
              fontSize: 10,
              color: "#64748b",
              padding: "2px 6px",
              background: "#f1f5f9",
              borderRadius: 4,
              marginLeft: 4,
            }}
          >
            v.2026
          </span>
        </Link>
        <nav style={{ display: "flex", gap: 4 }} className="vc-nav vc-nav-desktop">
          {([
            { label: "Översikt", href: "#oversikt", external: false },
            { label: "Funktioner", href: "#funktioner", external: false },
            { label: "Pris", href: "#pris", external: false },
            { label: "Dokumentation", href: "/docs", external: true },
            { label: "FAQ", href: "#faq", external: false },
          ] as Array<{ label: string; href: string; external: boolean }>).map(
            (t, i) =>
              t.external ? (
                <Link
                  key={t.label}
                  to={t.href}
                  className="vc-tab vc-tab-off"
                  style={{ textDecoration: "none" }}
                >
                  {t.label}
                </Link>
              ) : (
                <a
                  key={t.label}
                  href={t.href}
                  className={`vc-tab ${i === 0 ? "vc-tab-on" : "vc-tab-off"}`}
                  style={{ textDecoration: "none" }}
                >
                  {t.label}
                </a>
              ),
          )}
        </nav>
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
        <button
          type="button"
          onClick={() => setSearchOpen(true)}
          aria-label="Sök i kursplanen"
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: 8,
            padding: "7px 12px",
            border: "1px solid #e2e8f0",
            background: "#f8fafc",
            color: "#64748b",
            borderRadius: 8,
            fontSize: 13,
            cursor: "pointer",
            fontFamily: "inherit",
            minWidth: 200,
          }}
          className="vc-search-btn vc-search-desktop"
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <circle cx="11" cy="11" r="7" />
            <path d="m20 20-3.5-3.5" />
          </svg>
          <span style={{ flex: 1, textAlign: "left" }}>Sök i kursplanen…</span>
          <span style={{ display: "inline-flex", gap: 2 }}>
            <span className="vc-kbd">⌘</span>
            <span className="vc-kbd">K</span>
          </span>
        </button>
        <div className="vc-login-desktop" style={{ display: "flex", gap: 10 }}>
          <Link
            to="/login"
            className="vc-btn vc-btn-ghost"
            style={{ textDecoration: "none" }}
          >
            Logga in
          </Link>
          <a
            href="mailto:info@ekonomilabbet.org?subject=Boka%20demo"
            className="vc-btn vc-btn-primary"
            style={{ textDecoration: "none" }}
          >
            Boka demo →
          </a>
        </div>
        <button
          type="button"
          onClick={() => setMobileOpen((v) => !v)}
          aria-label={mobileOpen ? "Stäng meny" : "Öppna meny"}
          aria-expanded={mobileOpen}
          className="vc-hamburger"
          style={{
            alignItems: "center",
            justifyContent: "center",
            width: 38,
            height: 38,
            border: "1px solid #e2e8f0",
            background: "#fff",
            borderRadius: 8,
            cursor: "pointer",
            color: "#0f172a",
          }}
        >
          {mobileOpen ? (
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M6 6 L18 18 M6 18 L18 6" />
            </svg>
          ) : (
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M4 7h16 M4 12h16 M4 17h16" />
            </svg>
          )}
        </button>
      </div>
      {mobileOpen && (
        <div
          style={{
            position: "absolute",
            top: "100%",
            left: 0,
            right: 0,
            background: "#fff",
            borderBottom: "1px solid #e2e8f0",
            boxShadow: "0 6px 18px rgba(15,23,42,.06)",
            padding: "12px 24px 16px",
            display: "flex",
            flexDirection: "column",
            gap: 4,
          }}
        >
          <button
            type="button"
            onClick={() => {
              closeMobile();
              setSearchOpen(true);
            }}
            style={{
              display: "flex",
              alignItems: "center",
              gap: 8,
              padding: "10px 12px",
              background: "#f8fafc",
              border: "1px solid #e2e8f0",
              borderRadius: 8,
              color: "#64748b",
              fontFamily: "inherit",
              fontSize: 14,
              cursor: "pointer",
              marginBottom: 6,
            }}
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <circle cx="11" cy="11" r="7" />
              <path d="m20 20-3.5-3.5" />
            </svg>
            Sök i kursplanen…
          </button>
          {[
            { label: "Översikt", href: "#oversikt" },
            { label: "Funktioner", href: "#funktioner" },
            { label: "Pris", href: "#pris" },
            { label: "FAQ", href: "#faq" },
          ].map((t) => (
            <a
              key={t.label}
              href={t.href}
              onClick={closeMobile}
              style={{
                padding: "10px 4px",
                fontSize: 14,
                color: "#0f172a",
                textDecoration: "none",
                borderBottom: "1px solid #f1f5f9",
              }}
            >
              {t.label}
            </a>
          ))}
          <Link
            to="/docs"
            onClick={closeMobile}
            style={{
              padding: "10px 4px",
              fontSize: 14,
              color: "#0f172a",
              textDecoration: "none",
              borderBottom: "1px solid #f1f5f9",
            }}
          >
            Dokumentation
          </Link>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8, marginTop: 12 }}>
            <Link
              to="/login"
              onClick={closeMobile}
              className="vc-btn vc-btn-outline"
              style={{ textAlign: "center", textDecoration: "none", justifyContent: "center" }}
            >
              Logga in
            </Link>
            <a
              href="mailto:info@ekonomilabbet.org?subject=Boka%20demo"
              onClick={closeMobile}
              className="vc-btn vc-btn-primary"
              style={{ textAlign: "center", textDecoration: "none", justifyContent: "center" }}
            >
              Boka demo →
            </a>
          </div>
        </div>
      )}
      {searchOpen && (
        <SearchPalette
          onClose={() => setSearchOpen(false)}
          onPick={(c) => {
            setSearchOpen(false);
            setPickedCell(c);
          }}
        />
      )}
      {pickedCell && (
        <CellModal cell={pickedCell} onClose={() => setPickedCell(null)} />
      )}
    </header>
  );
}

// ---------- Hero ----------

function Hero() {
  const [hovered, setHovered] = useState<number | null>(null);
  const [openCell, setOpenCell] = useState<CellInfo | null>(null);
  const sectionRef = useRef<HTMLElement | null>(null);
  const cardRef = useRef<HTMLDivElement | null>(null);
  const reduced = useReducedMotion();

  // GSAP: pin hero while scrolling + scrub-animera kursplan-kortet +
  // counter-up för stats. Bara desktop (≥ 900px) för pin/scrub — mobil
  // får native scroll. Counter-up körs på alla bredder (men hoppas över
  // vid reduced-motion).
  useEffect(() => {
    if (reduced) return;
    if (typeof window === "undefined") return;
    if (!sectionRef.current) return;
    registerScrollTrigger();
    const isDesktop = window.innerWidth >= 900;

    const ctx = gsap.context(() => {
      if (isDesktop && cardRef.current) {
        ScrollTrigger.create({
          trigger: sectionRef.current,
          start: "top top",
          end: "+=70%",
          pin: true,
          pinSpacing: true,
          anticipatePin: 1,
        });
        gsap.to(cardRef.current, {
          scale: 0.86,
          opacity: 0.5,
          y: -20,
          rotateX: 6,
          ease: "none",
          scrollTrigger: {
            trigger: sectionRef.current,
            start: "top top",
            end: "+=70%",
            scrub: 0.6,
          },
        });
      }

      // Counter-up: alla [data-vc-stat]-element animerar text 0 → num.
      ScrollTrigger.create({
        trigger: sectionRef.current,
        start: "top 80%",
        once: true,
        onEnter: () => {
          const root = sectionRef.current;
          if (!root) return;
          const els = root.querySelectorAll<HTMLElement>("[data-vc-stat]");
          els.forEach((el) => {
            const target = Number(el.dataset.num) || 0;
            const suffix = el.dataset.suffix ?? "";
            const obj = { v: 0 };
            gsap.to(obj, {
              v: target,
              duration: 1.4,
              ease: "power2.out",
              onUpdate: () => {
                el.textContent = `${Math.round(obj.v)}${suffix}`;
              },
            });
          });
        },
      });
    }, sectionRef);

    return () => ctx.revert();
  }, [reduced]);

  return (
    <section id="oversikt" className="vc-hero-section" ref={sectionRef}>
      {/* Status-strip — proof-row enligt v5 */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 18,
          marginBottom: 28,
          fontSize: 12.5,
          color: "#64748b",
          flexWrap: "wrap",
          maxWidth: 1200,
          marginLeft: "auto",
          marginRight: "auto",
        }}
      >
        <span style={{ display: "inline-flex", alignItems: "center", gap: 8 }}>
          <span className="vc-dot" />
          <span style={{ color: "#0f172a", fontWeight: 500 }}>Pilot · läsåret 26/27</span>
        </span>
        <span style={{ width: 1, height: 12, background: "#cbd5e1" }} />
        <span>Kursplan-anpassad: SO · Hkk · Matematik</span>
      </div>

      <div
        style={{
          display: "grid",
          gridTemplateColumns: "minmax(0,1fr) minmax(0,1.3fr)",
          gap: 48,
          alignItems: "start",
          maxWidth: 1200,
          margin: "0 auto",
        }}
        className="vc-hero-grid"
      >
        <style>{`
          @media (max-width: 900px) {
            .vc-hero-grid { grid-template-columns: 1fr !important; gap: 24px !important; }
          }
        `}</style>

        <div>
          <span
            className="vc-mono"
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: 6,
              fontSize: 11,
              padding: "4px 10px",
              background: "#fef3c7",
              color: "#78350f",
              borderRadius: 100,
              marginBottom: 20,
            }}
          >
            <span
              style={{
                width: 5,
                height: 5,
                background: "#78350f",
                borderRadius: "50%",
              }}
            />
            EKONOMI MED KONSEKVENSER
          </span>
          <h1 className="vc-h1">
            Pengar är ett medel
            <br />
            för <span style={{ color: "#dc4c2b" }}>välmående</span> —<br />
            inte ett mål.
          </h1>
          <p
            style={{
              fontSize: 16,
              lineHeight: 1.55,
              marginTop: 22,
              color: "#475569",
              maxWidth: 480,
            }}
          >
            Ett pedagogiskt redovisningssystem för privatekonomi.
            Huvudbok, kontoplan, balansräkning — och en livssimulator
            ovanpå där den centrala mätaren inte är saldot, utan
            välmående över fem dimensioner. För klassrummet, köksbordet
            och (snart) er riktiga ekonomi.
          </p>

          {/* Stats-rad enligt v5 — siffrorna animeras 0 → mål via GSAP
              counter-up i useEffect:en ovan. */}
          <div
            style={{
              display: "flex",
              gap: 32,
              marginTop: 28,
              paddingTop: 24,
              borderTop: "1px solid #e2e8f0",
              flexWrap: "wrap",
            }}
          >
            {[
              { num: 32, suffix: "", label: "grundbegrepp" },
              { num: 80, suffix: "+", label: "mikrouppgifter" },
              { num: 6, suffix: "", label: "kategorier" },
            ].map((s) => (
              <div
                key={s.label}
                style={{ display: "flex", flexDirection: "column", alignItems: "flex-start", gap: 6 }}
              >
                <span
                  data-vc-stat
                  data-num={s.num}
                  data-suffix={s.suffix}
                  style={{ fontSize: 26, fontWeight: 700, letterSpacing: -0.5, color: "#0f172a" }}
                >
                  0{s.suffix}
                </span>
                <span style={{ fontSize: 12, color: "#64748b" }}>{s.label}</span>
              </div>
            ))}
          </div>

          <div style={{ display: "flex", gap: 10, marginTop: 28, flexWrap: "wrap" }}>
            <Link
              to="/signup/teacher"
              className="vc-btn vc-btn-primary"
              style={{ padding: "11px 18px", textDecoration: "none" }}
            >
              För skolan →
            </Link>
            <Link
              to="/signup/parent"
              className="vc-btn vc-btn-primary"
              style={{ padding: "11px 18px", textDecoration: "none" }}
            >
              För hemmet →
            </Link>
            <a
              href="#funktioner"
              className="vc-btn vc-btn-outline"
              style={{ padding: "11px 18px", textDecoration: "none" }}
            >
              Se hur det funkar
            </a>
          </div>

          {/* Echo greeting — AI-coach-card enligt v5 */}
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: 14,
              marginTop: 32,
              padding: "14px 16px",
              background: "#fff",
              border: "1px solid #e2e8f0",
              borderRadius: 12,
              boxShadow: "0 1px 3px rgba(15,23,42,0.04)",
            }}
          >
            <EchoAvatar size={56} />
            <div style={{ minWidth: 0 }}>
              <div
                className="vc-mono"
                style={{
                  fontSize: 11,
                  color: "#64748b",
                  letterSpacing: 0.6,
                  textTransform: "uppercase",
                  marginBottom: 2,
                }}
              >
                Möt Echo · din AI-coach
              </div>
              <div style={{ fontSize: 13.5, color: "#0f172a", lineHeight: 1.4 }}>
                Frågar mer än den svarar. Hjälper eleven att tänka, inte tycka.
              </div>
            </div>
          </div>
        </div>

        <div ref={cardRef} className="vc-card" style={{ padding: 22, transformOrigin: "center top" }}>
          {/* Card-header med titel + Karta/Lista/Värmekarta-tabs */}
          <div
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              marginBottom: 18,
              flexWrap: "wrap",
              gap: 12,
            }}
          >
            <div>
              <div className="vc-eyebrow" style={{ marginBottom: 4 }}>
                KURSPLAN-KARTA
              </div>
              <div style={{ fontSize: 16, fontWeight: 600 }}>
                Det periodiska systemet för pengar
              </div>
            </div>
            <div
              style={{
                display: "flex",
                gap: 4,
                padding: 3,
                background: "#f1f5f9",
                borderRadius: 8,
              }}
            >
              <button type="button" className="vc-tab vc-tab-on">Karta</button>
              <button type="button" className="vc-tab vc-tab-off">Lista</button>
              <button type="button" className="vc-tab vc-tab-off">Värmekarta</button>
            </div>
          </div>

          <PeriodicGrid
            hovered={hovered}
            setHovered={setHovered}
            onPick={(c) => setOpenCell(c)}
          />

          <div
            style={{
              display: "flex",
              gap: 14,
              marginTop: 16,
              paddingTop: 14,
              borderTop: "1px solid #e2e8f0",
              flexWrap: "wrap",
            }}
          >
            {(Object.entries(CATEGORY_META) as Array<[CellCat, { label: string; count: number }]>).map(
              ([id, m]) => (
                <div
                  key={id}
                  style={{ display: "flex", alignItems: "center", gap: 6 }}
                >
                  <div
                    style={{
                      width: 12,
                      height: 12,
                      borderRadius: 3,
                      background: PALETTE[id].bg,
                      border: `1px solid ${PALETTE[id].border}`,
                    }}
                  />
                  <span style={{ fontSize: 11.5, color: "#475569" }}>
                    {m.label}
                  </span>
                  <span
                    className="vc-mono"
                    style={{ fontSize: 10.5, color: "#94a3b8" }}
                  >
                    {m.count}
                  </span>
                </div>
              ),
            )}
          </div>
        </div>
      </div>
      {openCell && (
        <CellModal cell={openCell} onClose={() => setOpenCell(null)} />
      )}
    </section>
  );
}

// ---------- Contact (samma copy som Landing.tsx, anpassat utseende) ----------

function Contact() {
  return (
    <section
      id="kontakt"
      style={{
        padding: "64px 24px",
        borderTop: "1px solid #e2e8f0",
        background: "#fff",
        textAlign: "center",
      }}
    >
      <div style={{ maxWidth: 720, margin: "0 auto" }}>
        <div className="vc-eyebrow" style={{ marginBottom: 12 }}>
          Kontakt
        </div>
        <h2 className="vc-h2">Frågor, förslag eller samarbeten?</h2>
        <p
          style={{
            fontSize: 15,
            color: "#475569",
            marginTop: 16,
            lineHeight: 1.65,
          }}
        >
          Vi hjälper gärna till om du vill komma igång i din klass eller
          med dina egna barn, har önskemål om nya funktioner, eller vill
          utforska samarbeten med skolor, kommuner, föreningar eller
          lärarorganisationer.
        </p>
        <a
          href="mailto:info@ekonomilabbet.org"
          className="vc-btn vc-btn-primary"
          style={{
            marginTop: 28,
            padding: "12px 22px",
            fontFamily: 'ui-monospace, "SF Mono", monospace',
            textDecoration: "none",
          }}
        >
          info@ekonomilabbet.org
        </a>
        <p
          style={{
            fontSize: 13,
            color: "#94a3b8",
            marginTop: 16,
            fontStyle: "italic",
          }}
        >
          Vi svarar oftast inom ett par arbetsdagar.
        </p>
        <div
          className="vc-mono"
          style={{
            marginTop: 28,
            display: "inline-flex",
            alignItems: "center",
            gap: 8,
            fontSize: 11,
            letterSpacing: 1.4,
            textTransform: "uppercase",
            color: "#64748b",
          }}
        >
          <span
            style={{
              width: 6,
              height: 6,
              borderRadius: "50%",
              background: "#10b981",
              boxShadow: "0 0 0 3px rgba(16,185,129,.15)",
            }}
          />
          Pilot 2026 · Stockholm · Svensk molntjänst
        </div>
      </div>
    </section>
  );
}

// ---------- Footer (samma struktur som Landing.tsx) ----------

function Footer() {
  return (
    <footer
      style={{
        borderTop: "1px solid #e2e8f0",
        background: "#fff",
        fontSize: 13,
        color: "#64748b",
      }}
    >
      <div
        style={{
          maxWidth: 1200,
          margin: "0 auto",
          padding: "40px 24px",
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))",
          gap: 24,
        }}
      >
        <div>
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: 8,
              marginBottom: 12,
            }}
          >
            <div
              style={{
                width: 22,
                height: 22,
                background: "#0f172a",
                color: "#fef3c7",
                borderRadius: 5,
                display: "grid",
                placeItems: "center",
                fontSize: 10,
                fontWeight: 700,
                fontFamily: 'ui-monospace, "SF Mono", monospace',
              }}
            >
              El
            </div>
            <span style={{ fontSize: 15, fontWeight: 600, color: "#0f172a" }}>
              Ekonomilabbet
            </span>
          </div>
          <p style={{ lineHeight: 1.55 }}>
            En öppen utbildningsplattform för privatekonomi — i klassrummet
            och vid köksbordet.
          </p>
        </div>
        <div>
          <div className="vc-eyebrow" style={{ marginBottom: 10 }}>
            Sidan
          </div>
          <ul style={{ listStyle: "none", padding: 0, margin: 0, lineHeight: 2 }}>
            <li>
              <a href="#funktioner" style={{ color: "#64748b" }}>
                Funktioner
              </a>
            </li>
            <li>
              <a href="#malgrupper" style={{ color: "#64748b" }}>
                Skola/Hemma
              </a>
            </li>
            <li>
              <a href="#pris" style={{ color: "#64748b" }}>
                Pris
              </a>
            </li>
            <li>
              <a href="#faq" style={{ color: "#64748b" }}>
                FAQ
              </a>
            </li>
          </ul>
        </div>
        <div>
          <div className="vc-eyebrow" style={{ marginBottom: 10 }}>
            Snabbstart
          </div>
          <ul style={{ listStyle: "none", padding: 0, margin: 0, lineHeight: 2 }}>
            <li>
              <Link to="/signup/teacher" style={{ color: "#64748b" }}>
                För skolan
              </Link>
            </li>
            <li>
              <Link to="/signup/parent" style={{ color: "#64748b" }}>
                För hemmet
              </Link>
            </li>
            <li>
              <Link to="/login/student" style={{ color: "#64748b" }}>
                Elev/barn-login
              </Link>
            </li>
            <li>
              <Link to="/login" style={{ color: "#64748b" }}>
                Logga in
              </Link>
            </li>
          </ul>
        </div>
        <div>
          <div className="vc-eyebrow" style={{ marginBottom: 10 }}>
            Kontakt &amp; juridik
          </div>
          <ul style={{ listStyle: "none", padding: 0, margin: 0, lineHeight: 2 }}>
            <li>
              <a
                href="mailto:info@ekonomilabbet.org"
                style={{ color: "#64748b" }}
              >
                info@ekonomilabbet.org
              </a>
            </li>
            <li>
              <Link to="/docs" style={{ color: "#64748b" }}>
                Dokumentation
              </Link>
            </li>
            <li>
              <a href="#faq" style={{ color: "#64748b" }}>
                FAQ
              </a>
            </li>
          </ul>
        </div>
      </div>
      <div style={{ borderTop: "1px solid #e2e8f0" }}>
        <div
          style={{
            maxWidth: 1200,
            margin: "0 auto",
            padding: "16px 24px",
            display: "flex",
            flexWrap: "wrap",
            justifyContent: "space-between",
            gap: 12,
            fontSize: 12,
            color: "#94a3b8",
          }}
        >
          <div>
            © {new Date().getFullYear()} Ekonomilabbet · För skolan och hemmet
          </div>
          <div style={{ fontStyle: "italic" }}>Variant C — utgåva 2026</div>
        </div>
      </div>
    </footer>
  );
}

// ---------- FAQ ----------

function Faq() {
  const [open, setOpen] = useState(0);
  return (
    <section
      id="faq"
      style={{
        padding: "64px 24px",
        borderTop: "1px solid #e2e8f0",
        maxWidth: 880,
        margin: "0 auto",
      }}
    >
      <div className="vc-eyebrow" style={{ marginBottom: 12 }}>
        FAQ
      </div>
      <h2 className="vc-h2">Vanliga frågor.</h2>
      <div style={{ marginTop: 32 }}>
        {FAQS.map((it, i) => (
          <div key={i} style={{ borderTop: "1px solid #e2e8f0" }}>
            <button
              type="button"
              onClick={() => setOpen(open === i ? -1 : i)}
              style={{
                width: "100%",
                textAlign: "left",
                padding: "18px 0",
                display: "flex",
                justifyContent: "space-between",
                fontSize: 16,
                fontWeight: 500,
                color: "#0f172a",
                background: "none",
                border: "none",
                cursor: "pointer",
                fontFamily: "inherit",
              }}
            >
              <span>{it.q}</span>
              <span
                style={{
                  color: "#64748b",
                  transform: open === i ? "rotate(180deg)" : "none",
                  transition: "transform .2s",
                }}
              >
                ⌄
              </span>
            </button>
            {open === i && (
              <p
                style={{
                  paddingBottom: 18,
                  paddingRight: 60,
                  fontSize: 14,
                  lineHeight: 1.6,
                  color: "#475569",
                }}
              >
                {it.a}
              </p>
            )}
          </div>
        ))}
      </div>
    </section>
  );
}

// ---------- CTA ----------

function Cta() {
  return (
    <section
      style={{
        padding: "80px 24px",
        borderTop: "1px solid #e2e8f0",
        textAlign: "center",
        maxWidth: 880,
        margin: "0 auto",
      }}
    >
      <div className="vc-eyebrow" style={{ marginBottom: 12 }}>
        Kom igång
      </div>
      <h2 className="vc-h2">
        Det vuxenlivs­ämne som varken skolan eller köksbordet riktigt
        hann med.
      </h2>
      <p
        style={{
          fontSize: 15,
          color: "#475569",
          marginTop: 18,
          marginBottom: 32,
          maxWidth: 560,
          marginLeft: "auto",
          marginRight: "auto",
          lineHeight: 1.6,
        }}
      >
        Gratis under pilotåret. Ingen bindningstid. Du väljer själv om
        du kör med en klass eller med dina egna barn.
      </p>
      <div
        style={{
          display: "flex",
          justifyContent: "center",
          gap: 10,
          flexWrap: "wrap",
        }}
      >
        <Link
          to="/signup/teacher"
          className="vc-btn vc-btn-primary"
          style={{ padding: "12px 22px", textDecoration: "none" }}
        >
          Starta som lärare →
        </Link>
        <Link
          to="/signup/parent"
          className="vc-btn vc-btn-primary"
          style={{ padding: "12px 22px", textDecoration: "none" }}
        >
          Starta som förälder →
        </Link>
        <a
          href="mailto:info@ekonomilabbet.org?subject=Boka%20introduktion"
          className="vc-btn vc-btn-outline"
          style={{ padding: "12px 22px", textDecoration: "none" }}
        >
          Boka introduktion
        </a>
      </div>
    </section>
  );
}





// ---------- Features ----------

type AudienceFilter = "alla" | "larare" | "hem" | "elev";

function Features() {
  const [filter, setFilter] = useState<AudienceFilter>("alla");
  const visible =
    filter === "alla"
      ? FEATURES
      : FEATURES.filter((f) => f.audience.includes(filter));
  const tabs: Array<[AudienceFilter, string]> = [
    ["alla", "Alla"],
    ["larare", "För lärare"],
    ["hem", "För hemmet"],
    ["elev", "För eleven"],
  ];
  return (
    <section
      id="funktioner"
      style={{ padding: "56px 24px 80px", maxWidth: 1200, margin: "0 auto" }}
    >
      <div
        style={{
          display: "flex",
          alignItems: "flex-end",
          justifyContent: "space-between",
          marginBottom: 28,
          flexWrap: "wrap",
          gap: 16,
        }}
      >
        <div>
          <span className="vc-eyebrow">FUNKTIONER · 12 / 12</span>
          <h2 className="vc-h2" style={{ marginTop: 10 }}>
            Allt en lärare eller förälder behöver.
          </h2>
          <p
            style={{
              fontSize: 15,
              color: "#475569",
              marginTop: 10,
              maxWidth: 540,
            }}
          >
            Från första lönen till bolåne-beslut. Varje funktion är ett
            element i kursplanen.
          </p>
        </div>
        <div
          style={{
            display: "flex",
            gap: 4,
            padding: 3,
            background: "#f1f5f9",
            borderRadius: 8,
          }}
        >
          {tabs.map(([key, label]) => (
            <button
              key={key}
              type="button"
              onClick={() => setFilter(key)}
              className={`vc-tab ${filter === key ? "vc-tab-on" : "vc-tab-off"}`}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))",
          gap: 12,
        }}
      >
        {visible.map((f, i) => {
          const p = PALETTE[f.cat];
          return (
            <div key={i} className="vc-card" style={{ padding: 18 }}>
              <div
                style={{
                  display: "flex",
                  alignItems: "flex-start",
                  justifyContent: "space-between",
                  marginBottom: 14,
                }}
              >
                <div
                  style={{
                    width: 38,
                    height: 38,
                    borderRadius: 7,
                    background: p.bg,
                    color: p.fg,
                    border: `1px solid ${p.border}`,
                    display: "flex",
                    flexDirection: "column",
                    justifyContent: "space-between",
                    padding: "3px 5px",
                  }}
                >
                  <span
                    className="vc-mono"
                    style={{ fontSize: 7, opacity: 0.55 }}
                  >
                    {(i + 1).toString().padStart(2, "0")}
                  </span>
                  <span
                    className="vc-mono"
                    style={{ fontSize: 14, fontWeight: 700, lineHeight: 1 }}
                  >
                    {f.sym}
                  </span>
                </div>
                <span
                  style={{
                    display: "inline-flex",
                    alignItems: "center",
                    gap: 4,
                    fontSize: 10.5,
                    padding: "3px 8px",
                    borderRadius: 100,
                    background: "#f1f5f9",
                    color: "#475569",
                    fontWeight: 500,
                  }}
                >
                  <span
                    style={{
                      width: 5,
                      height: 5,
                      borderRadius: "50%",
                      background: p.bg,
                      border: `1px solid ${p.border}`,
                    }}
                  />
                  {CATEGORY_META[f.cat].label}
                </span>
              </div>
              <h3
                style={{
                  fontSize: 15.5,
                  fontWeight: 600,
                  letterSpacing: -0.2,
                  marginBottom: 6,
                }}
              >
                {f.title}
              </h3>
              <p style={{ fontSize: 13, lineHeight: 1.5, color: "#475569" }}>
                {f.desc}
              </p>
            </div>
          );
        })}
      </div>
    </section>
  );
}

// ---------- ManifestoSection (v5) ----------

function ManifestoSection({ theme }: { theme: Theme }) {
  return (
    <section
      style={{
        padding: "120px 24px",
        borderTop: `1px solid ${theme.rule}`,
        background: theme.cardBg2 || theme.cardBg,
        position: "relative",
      }}
    >
      <div
        style={{
          maxWidth: 880,
          margin: "0 auto",
          display: "grid",
          gridTemplateColumns: "auto 1fr",
          gap: 48,
          alignItems: "start",
        }}
        className="vc-manifest-grid"
      >
        <style>{`
          @media (max-width: 768px) {
            .vc-manifest-grid { grid-template-columns: 1fr !important; gap: 24px !important; }
            .vc-manifest-eyebrow { writing-mode: horizontal-tb !important; transform: none !important; }
            .vc-manifest-cols { grid-template-columns: 1fr !important; gap: 24px !important; }
          }
        `}</style>
        <div
          className={`${theme.eyebrow} vc-manifest-eyebrow`}
          style={{
            writingMode: "vertical-rl",
            transform: "rotate(180deg)",
            fontSize: 11,
            letterSpacing: 2,
            paddingTop: 4,
            color: theme.muted,
          }}
        >
          MANIFEST · 2026
        </div>
        <div>
          <p
            style={{
              fontFamily: theme.serifFont,
              fontSize: 38,
              lineHeight: 1.25,
              fontWeight: 400,
              letterSpacing: -0.5,
              color: theme.fg,
              margin: 0,
              marginBottom: 36,
              textWrap: "balance",
            }}
          >
            <em style={{ color: theme.accent, fontStyle: "italic" }}>
              Pengar är ett medel
            </em>{" "}
            för välmående — inte ett mål i sig själv.
          </p>
          <div
            className="vc-manifest-cols"
            style={{
              display: "grid",
              gridTemplateColumns: "1fr 1fr",
              gap: 40,
              paddingTop: 32,
              borderTop: `1px solid ${theme.rule}`,
            }}
          >
            <p
              style={{
                fontSize: 16,
                lineHeight: 1.6,
                color: theme.fg,
                margin: 0,
                fontFamily: theme.serifFont,
              }}
            >
              Att maximera saldot till priset av sociala band och fritid är
              inte ekonomisk framgång — det är en form av{" "}
              <strong style={{ fontWeight: 600 }}>fattigdom</strong>. Att
              spendera allt på upplevelser utan buffert är heller inte rikedom
              — det är <strong style={{ fontWeight: 600 }}>skörhet</strong>.
            </p>
            <p
              style={{
                fontSize: 16,
                lineHeight: 1.6,
                color: theme.fg,
                margin: 0,
                fontFamily: theme.serifFont,
              }}
            >
              Ekonomi är konsten att balansera <em>idag</em> mot{" "}
              <em>imorgon</em>, <em>mig själv</em> mot{" "}
              <em>mina relationer</em>, <em>planering</em> mot{" "}
              <em>spontanitet</em>.
              <br />
              <br />
              <span
                className={theme.eyebrow}
                style={{ fontSize: 11, color: theme.muted, letterSpacing: 1.5 }}
              >
                — Det här är vad Wellbeing Score mäter.
              </span>
            </p>
          </div>
        </div>
      </div>
    </section>
  );
}

// ---------- WellbeingSection (v5) — radarn med 3 elev-profiler + flip-card ----------

function WellbeingSection({ theme }: { theme: Theme }) {
  const [hovered, setHovered] = useState(0);
  const [flipped, setFlipped] = useState(false);
  const sectionRef = useRef<HTMLElement | null>(null);
  const polyRef = useRef<SVGPolygonElement | null>(null);
  const scoreTextRef = useRef<SVGTextElement | null>(null);
  const reduced = useReducedMotion();

  const profiles = [
    {
      name: "Alex · saver",
      sub: "80 000 kr på sparkontot, säger nej till varje fest",
      score: 60,
      pts: { ek: 95, hl: 70, sb: 30, fr: 25, tr: 80 },
    },
    {
      name: "Maja · spender",
      sub: "Spenderar allt på upplevelser, ingen buffert",
      score: 50,
      pts: { ek: 20, hl: 75, sb: 90, fr: 95, tr: 25 },
    },
    {
      name: "Liam · balansen",
      sub: "Sparar 20 %, säger ja ibland, har en hyfsad buffert",
      score: 82,
      pts: { ek: 75, hl: 80, sb: 85, fr: 80, tr: 80 },
    },
  ];
  const cur = profiles[hovered];

  type DimKey = "ek" | "hl" | "sb" | "fr" | "tr";
  const dims: Array<{
    key: DimKey;
    label: string;
    short: string;
    weight: number;
    what: string;
    plus: string[];
    minus: string[];
  }> = [
    {
      key: "ek",
      label: "Ekonomi",
      short: "Ek",
      weight: 25,
      what: "Buffert, skuld, sparande, EkonomiSkalan",
      plus: ["+ Buffert ≥ 1 mån = +8", "+ Sparkvot ≥ 10 % = +5", "+ Höjd EkonomiSkalan = +3"],
      minus: ["− Saldo < 0 i 7 dgr = −12", "− SMS-lån = −15", "− Inkasso = −10"],
    },
    {
      key: "hl",
      label: "Mat & hälsa",
      short: "Hl",
      weight: 20,
      what: "Måltider, sömn, fysisk aktivitet, stress",
      plus: ["+ Hemlagad mat ≥ 4/v = +6", "+ Träning 2×/v = +5", "+ 7+ h sömn = +4"],
      minus: ["− Snabbmat 5+/v = −7", "− Stress över ekonomi = −5"],
    },
    {
      key: "sb",
      label: "Sociala band",
      short: "Sb",
      weight: 20,
      what: "Vänner, familj, romantik, kollegor",
      plus: ["+ Säga ja till middag = +4", "+ Hjälpa en vän = +6", "+ Familjemiddag = +3"],
      minus: ["− Tackat nej 3 ggr i rad = −5", "− Isolering helg = −4"],
    },
    {
      key: "fr",
      label: "Fritid",
      short: "Fr",
      weight: 15,
      what: "Hobbys, kultur, resor, vila utan skärm",
      plus: ["+ Bok / instrument = +3", "+ Resa / utflykt = +6", "+ Hobby-tid 2 h/v = +2"],
      minus: ["− Bara skärmtid en hel helg = −4"],
    },
    {
      key: "tr",
      label: "Trygghet",
      short: "Tr",
      weight: 20,
      what: "Bostad, försäkring, framtidsplaner, kontroll",
      plus: ["+ Hemförsäkring = +5", "+ Pensionssparande = +4", "+ Budget gjord = +3"],
      minus: ["− Saknar buffert = −8", "− Ingen försäkring = −5", "− Kronofogden = −20"],
    },
  ];

  const cx = 200;
  const cy = 200;
  const R = 140;
  const angleAt = (i: number) => (Math.PI * 2 * i) / 5 - Math.PI / 2;
  const point = (i: number, v: number): [number, number] => {
    const a = angleAt(i);
    const r = R * (v / 100);
    return [cx + Math.cos(a) * r, cy + Math.sin(a) * r];
  };
  const polyPts = dims.map((d, i) => point(i, cur.pts[d.key]).join(",")).join(" ");

  // GSAP scrub: när WellbeingSection kommer i view, rita in radarn och
  // räkna upp poängen 0 → cur.score. Körs en gång per mount; React tar
  // över textinnehållet vid profil-byte.
  useEffect(() => {
    if (reduced || !sectionRef.current) return;
    registerScrollTrigger();
    const ctx = gsap.context(() => {
      ScrollTrigger.create({
        trigger: sectionRef.current,
        start: "top 70%",
        once: true,
        onEnter: () => {
          if (polyRef.current) {
            gsap.from(polyRef.current, {
              scale: 0,
              opacity: 0,
              duration: 1.1,
              transformOrigin: "200px 200px",
              ease: "power3.out",
            });
          }
          if (scoreTextRef.current) {
            const target = Number(scoreTextRef.current.dataset.target) || 0;
            const obj = { v: 0 };
            gsap.to(obj, {
              v: target,
              duration: 1.4,
              ease: "power2.out",
              onUpdate: () => {
                if (scoreTextRef.current) {
                  scoreTextRef.current.textContent = String(Math.round(obj.v));
                }
              },
            });
          }
        },
      });
    }, sectionRef);
    return () => ctx.revert();
  }, [reduced]);

  return (
    <section
      ref={sectionRef}
      style={{
        padding: "96px 24px",
        borderTop: `1px solid ${theme.rule}`,
        background: "#0f172a",
        color: "#fff",
      }}
    >
      <SectionHeader cell={{ sym: "Wb", n: "01", label: "Wellbeing" }} eyebrow="Den centrala mätaren" theme={theme} dark>
        Saldot är inte huvudmätaren. <em style={{ color: "#fbbf24", fontStyle: "italic" }}>Wellbeing</em> är.
      </SectionHeader>
      <p
        style={{
          maxWidth: 640,
          marginBottom: 48,
          fontSize: 15.5,
          lineHeight: 1.55,
          color: "#94a3b8",
        }}
      >
        Wellbeing Score mäter elevens välmående över fem dimensioner — inte hur
        mycket pengar som finns på kontot. Det är möjligt att vara 80 000 kr rik
        och ha 60 i Wellbeing. Det är möjligt att vara skuldsatt och ha 75. Det
        är vad eleven faktiskt behöver lära sig.
      </p>

      <div
        style={{
          display: "grid",
          gridTemplateColumns: "1fr 1.1fr",
          gap: 56,
          alignItems: "center",
        }}
        className="vc-wb-grid"
      >
        <style>{`
          @media (max-width: 900px) {
            .vc-wb-grid { grid-template-columns: 1fr !important; gap: 36px !important; }
            .vc-wb-bottom { grid-template-columns: 1fr !important; gap: 18px !important; }
          }
        `}</style>

        {/* Radar viz — flip card */}
        <div style={{ perspective: "1600px", aspectRatio: "1 / 1", maxWidth: 460, width: "100%" }}>
          <div
            onClick={() => setFlipped((f) => !f)}
            role="button"
            tabIndex={0}
            onKeyDown={(e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                setFlipped((f) => !f);
              }
            }}
            style={{
              position: "relative",
              width: "100%",
              height: "100%",
              transformStyle: "preserve-3d",
              transition: "transform 0.85s cubic-bezier(.2,.7,.3,1)",
              transform: flipped ? "rotateY(180deg)" : "rotateY(0deg)",
              cursor: "pointer",
            }}
          >
            {/* FRONT */}
            <div
              style={{
                position: "absolute",
                inset: 0,
                backfaceVisibility: "hidden",
                WebkitBackfaceVisibility: "hidden",
                background: "rgba(255,255,255,0.03)",
                border: "1px solid rgba(255,255,255,0.08)",
                borderRadius: 14,
                padding: 28,
              }}
            >
              <div
                style={{
                  position: "absolute",
                  top: 14,
                  right: 16,
                  fontFamily: "ui-monospace, monospace",
                  fontSize: 10,
                  color: "#0f172a",
                  letterSpacing: 1,
                  textTransform: "uppercase",
                  display: "flex",
                  alignItems: "center",
                  gap: 6,
                  pointerEvents: "none",
                  background: "#fbbf24",
                  padding: "5px 9px",
                  borderRadius: 4,
                  fontWeight: 700,
                  zIndex: 2,
                }}
              >
                <span>klicka · poängsystem</span>
                <span style={{ fontSize: 12 }}>↻</span>
              </div>
              <svg viewBox="0 0 400 400" style={{ width: "100%", height: "100%" }}>
                {[0.25, 0.5, 0.75, 1].map((r, i) => (
                  <polygon
                    key={i}
                    points={dims
                      .map((_, j) => {
                        const a = angleAt(j);
                        return `${cx + Math.cos(a) * R * r},${cy + Math.sin(a) * R * r}`;
                      })
                      .join(" ")}
                    fill="none"
                    stroke="rgba(255,255,255,0.1)"
                    strokeWidth="1"
                  />
                ))}
                {dims.map((_, i) => {
                  const [x, y] = point(i, 100);
                  return (
                    <line
                      key={i}
                      x1={cx}
                      y1={cy}
                      x2={x}
                      y2={y}
                      stroke="rgba(255,255,255,0.08)"
                      strokeWidth="1"
                    />
                  );
                })}
                <polygon
                  ref={polyRef}
                  points={polyPts}
                  fill="rgba(251,191,36,0.18)"
                  stroke="#fbbf24"
                  strokeWidth="2"
                  style={{ transition: "all 0.5s cubic-bezier(.2,.7,.3,1)" }}
                />
                {dims.map((d, i) => {
                  const [x, y] = point(i, cur.pts[d.key]);
                  return (
                    <circle
                      key={i}
                      cx={x}
                      cy={y}
                      r="4"
                      fill="#fbbf24"
                      style={{ transition: "all 0.5s cubic-bezier(.2,.7,.3,1)" }}
                    />
                  );
                })}
                {dims.map((d, i) => {
                  const a = angleAt(i);
                  const lr = R + 28;
                  const lx = cx + Math.cos(a) * lr;
                  const ly = cy + Math.sin(a) * lr + 4;
                  return (
                    <text
                      key={i}
                      x={lx}
                      y={ly}
                      textAnchor="middle"
                      fontSize="11"
                      fontWeight="600"
                      fill="#e2e8f0"
                      fontFamily="ui-monospace, monospace"
                    >
                      {d.label.toUpperCase()}
                    </text>
                  );
                })}
                <text
                  ref={scoreTextRef}
                  data-target={cur.score}
                  x={cx}
                  y={cy - 6}
                  textAnchor="middle"
                  fontSize="44"
                  fontWeight="700"
                  fill="#fff"
                  style={{ transition: "all 0.5s" }}
                >
                  {cur.score}
                </text>
                <text
                  x={cx}
                  y={cy + 14}
                  textAnchor="middle"
                  fontSize="10"
                  fill="#94a3b8"
                  fontFamily="ui-monospace, monospace"
                  letterSpacing="1"
                >
                  WELLBEING
                </text>
              </svg>
            </div>

            {/* BACK — poängsystemet */}
            <div
              style={{
                position: "absolute",
                inset: 0,
                backfaceVisibility: "hidden",
                WebkitBackfaceVisibility: "hidden",
                transform: "rotateY(180deg)",
                background: "rgba(15, 23, 42, 0.6)",
                border: "1px solid rgba(251,191,36,0.25)",
                borderRadius: 14,
                padding: "22px 24px",
                display: "flex",
                flexDirection: "column",
                overflow: "hidden",
              }}
            >
              <div
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "baseline",
                  marginBottom: 14,
                  paddingBottom: 12,
                  borderBottom: "1px solid rgba(255,255,255,0.08)",
                }}
              >
                <div>
                  <div
                    style={{
                      fontFamily: "ui-monospace, monospace",
                      fontSize: 10,
                      color: "#fbbf24",
                      letterSpacing: 1,
                      textTransform: "uppercase",
                      marginBottom: 4,
                    }}
                  >
                    Wellbeing-poängsystemet
                  </div>
                  <div style={{ fontSize: 16, fontWeight: 600, color: "#fff" }}>
                    Så räknas talet i mitten
                  </div>
                </div>
                <div
                  style={{
                    fontFamily: "ui-monospace, monospace",
                    fontSize: 10,
                    color: "#64748b",
                    letterSpacing: 1,
                    textTransform: "uppercase",
                    display: "flex",
                    alignItems: "center",
                    gap: 6,
                  }}
                >
                  <span style={{ color: "#fbbf24" }}>↺</span>
                  <span>tillbaka</span>
                </div>
              </div>

              <div
                style={{
                  display: "grid",
                  gridTemplateColumns: "1fr",
                  gap: 8,
                  flex: 1,
                  overflowY: "auto",
                  minHeight: 0,
                }}
              >
                {dims.map((d) => (
                  <div
                    key={d.key}
                    style={{
                      padding: "10px 12px",
                      background: "rgba(255,255,255,0.03)",
                      border: "1px solid rgba(255,255,255,0.06)",
                      borderRadius: 10,
                    }}
                  >
                    <div
                      style={{
                        display: "flex",
                        alignItems: "center",
                        gap: 10,
                        marginBottom: 6,
                      }}
                    >
                      <div
                        style={{
                          width: 26,
                          height: 26,
                          borderRadius: 5,
                          background: "#fbbf24",
                          color: "#0f172a",
                          display: "grid",
                          placeItems: "center",
                          fontFamily: "ui-monospace, monospace",
                          fontSize: 11,
                          fontWeight: 700,
                          flexShrink: 0,
                        }}
                      >
                        {d.short}
                      </div>
                      <div style={{ fontSize: 13, fontWeight: 600, color: "#fff", flex: 1 }}>
                        {d.label}
                      </div>
                      <div
                        style={{
                          fontFamily: "ui-monospace, monospace",
                          fontSize: 10,
                          color: "#fbbf24",
                          letterSpacing: 0.5,
                        }}
                      >
                        vikt {d.weight}%
                      </div>
                    </div>
                    <div
                      style={{
                        height: 4,
                        borderRadius: 2,
                        background: "rgba(255,255,255,0.06)",
                        overflow: "hidden",
                        marginBottom: 8,
                      }}
                    >
                      <div
                        style={{
                          height: "100%",
                          width: `${d.weight * 4}%`,
                          background: "#fbbf24",
                        }}
                      />
                    </div>
                    <div
                      style={{
                        fontSize: 11,
                        color: "#94a3b8",
                        marginBottom: 6,
                        lineHeight: 1.4,
                      }}
                    >
                      {d.what}
                    </div>
                    <div style={{ display: "flex", flexWrap: "wrap", gap: "3px 8px" }}>
                      {d.plus.slice(0, 2).map((p, i) => (
                        <span
                          key={i}
                          style={{
                            fontFamily: "ui-monospace, monospace",
                            fontSize: 10,
                            color: "#86efac",
                          }}
                        >
                          {p}
                        </span>
                      ))}
                      {d.minus.slice(0, 2).map((m, i) => (
                        <span
                          key={i}
                          style={{
                            fontFamily: "ui-monospace, monospace",
                            fontSize: 10,
                            color: "#fca5a5",
                          }}
                        >
                          {m}
                        </span>
                      ))}
                    </div>
                  </div>
                ))}
              </div>

              <div
                style={{
                  marginTop: 12,
                  paddingTop: 12,
                  borderTop: "1px solid rgba(255,255,255,0.08)",
                  fontFamily: "ui-monospace, monospace",
                  fontSize: 10,
                  color: "#64748b",
                  lineHeight: 1.5,
                }}
              >
                Σ = Ek·0.25 + Hl·0.20 + Sb·0.20 + Fr·0.15 + Tr·0.20 → 0–100
              </div>
            </div>
          </div>
        </div>

        {/* Profile selector */}
        <div>
          <div
            className={theme.eyebrow}
            style={{ marginBottom: 14, color: "#94a3b8" }}
          >
            Tre elever, samma sandlåda
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            {profiles.map((p, i) => (
              <button
                key={i}
                type="button"
                onClick={() => setHovered(i)}
                onMouseEnter={() => setHovered(i)}
                style={{
                  textAlign: "left",
                  padding: 18,
                  cursor: "pointer",
                  background:
                    hovered === i
                      ? "rgba(251,191,36,0.08)"
                      : "rgba(255,255,255,0.03)",
                  border:
                    hovered === i
                      ? "2px solid #fbbf24"
                      : "1px solid rgba(255,255,255,0.08)",
                  borderRadius: 10,
                  transition: "all .18s",
                  color: "#fff",
                  display: "flex",
                  alignItems: "center",
                  gap: 16,
                  fontFamily: "inherit",
                }}
              >
                <div
                  style={{
                    width: 44,
                    height: 44,
                    borderRadius: "50%",
                    flexShrink: 0,
                    background:
                      hovered === i ? "#fbbf24" : "rgba(255,255,255,0.08)",
                    color: hovered === i ? "#0f172a" : "#94a3b8",
                    display: "grid",
                    placeItems: "center",
                    fontSize: 16,
                    fontWeight: 700,
                    fontFamily: "ui-monospace, monospace",
                  }}
                >
                  {p.score}
                </div>
                <div style={{ minWidth: 0 }}>
                  <div
                    style={{
                      fontSize: 14.5,
                      fontWeight: 600,
                      color: "#fff",
                      marginBottom: 2,
                    }}
                  >
                    {p.name}
                  </div>
                  <div
                    style={{ fontSize: 13, color: "#94a3b8", lineHeight: 1.4 }}
                  >
                    {p.sub}
                  </div>
                </div>
              </button>
            ))}
          </div>
          <p
            style={{
              marginTop: 24,
              fontSize: 13.5,
              color: "#94a3b8",
              lineHeight: 1.55,
              fontStyle: "italic",
            }}
          >
            Eleven ser inte bara ett tal. Hen ser <em>varför</em> talet ser ut
            så det gör — och kan röra sig mellan profiler genom sina egna val.
            Det är livslära, inte räknelära.
          </p>
        </div>
      </div>

      {/* Guldvägen i mitten — extremerna är båda fattigdom */}
      <div
        className="vc-wb-bottom"
        style={{
          marginTop: 64,
          paddingTop: 48,
          borderTop: "1px solid rgba(255,255,255,0.08)",
          display: "grid",
          gridTemplateColumns: "1fr 1fr 1fr",
          gap: 32,
        }}
      >
        <div>
          <div
            style={{
              fontFamily: "ui-monospace, monospace",
              fontSize: 11,
              color: "#94a3b8",
              letterSpacing: 1,
              marginBottom: 14,
              textTransform: "uppercase",
            }}
          >
            För mycket snålhet
          </div>
          <p style={{ fontSize: 15, lineHeight: 1.55, color: "#cbd5e1", margin: 0 }}>
            Aldrig ja till spontana planer. Bufferten växer, men de sociala
            banden vissnar. Wellbeing rasar — eleven har en perfekt huvudbok
            och en tom helg.
          </p>
        </div>
        <div
          style={{
            background: "rgba(251,191,36,0.06)",
            border: "1px solid rgba(251,191,36,0.25)",
            borderRadius: 14,
            padding: 24,
          }}
        >
          <div
            style={{
              fontFamily: "ui-monospace, monospace",
              fontSize: 11,
              color: "#fbbf24",
              letterSpacing: 1,
              marginBottom: 14,
              textTransform: "uppercase",
            }}
          >
            Guldvägen i mitten
          </div>
          <p
            style={{
              fontSize: 15,
              lineHeight: 1.55,
              color: "#fef3c7",
              margin: 0,
              fontWeight: 500,
            }}
          >
            Pengar är ett verktyg för att köpa frihet och trygghet — men frihet
            kräver också sociala sammanhang och fritid. Eleven lär sig att
            navigera mellan ytterligheterna.
          </p>
        </div>
        <div>
          <div
            style={{
              fontFamily: "ui-monospace, monospace",
              fontSize: 11,
              color: "#94a3b8",
              letterSpacing: 1,
              marginBottom: 14,
              textTransform: "uppercase",
            }}
          >
            För mycket spenderande
          </div>
          <p style={{ fontSize: 15, lineHeight: 1.55, color: "#cbd5e1", margin: 0 }}>
            Allt på upplevelser nu, ingen buffert sedan. Första oväntade
            tandläkar­räkning blir SMS-lån. Sociala banden lyser — ekonomi och
            trygghet brinner.
          </p>
        </div>
      </div>

      {/* Manifest pull-quote */}
      <blockquote
        style={{
          margin: "64px auto 0",
          maxWidth: 720,
          textAlign: "center",
          padding: 0,
        }}
      >
        <p
          style={{
            fontFamily: theme.serifFont,
            fontSize: 26,
            lineHeight: 1.35,
            color: "#fff",
            fontStyle: "italic",
            margin: 0,
            letterSpacing: -0.3,
          }}
        >
          "I matteuppgifter finns ett facit. I livet finns bara avvägningar.
          När eleven slutar leta efter rätt svar och börjar söka{" "}
          <em style={{ color: "#fbbf24" }}>en balans hen själv kan stå för</em>{" "}
          — då är vi framme."
        </p>
        <footer
          style={{
            marginTop: 18,
            fontSize: 12,
            color: "#64748b",
            fontFamily: "ui-monospace, monospace",
            letterSpacing: 1,
            textTransform: "uppercase",
          }}
        >
          — Pedagogisk grundprincip
        </footer>
      </blockquote>
    </section>
  );
}

// ---------- AccountingSection (v5) — dubbel bokföring ----------

function AccountingSection({ theme }: { theme: Theme }) {
  const features = [
    {
      sym: "Hb",
      title: "Huvudbok",
      desc: "Varje transaktion bokförs som debet och kredit. Ingen handvevad Excel — riktig dubbel bokföring som balanseras varje månad.",
      items: [
        "Importera kontoutdrag som PDF",
        "Automatisk kategorisering",
        "Bankavstämning vid månadsskifte",
      ],
    },
    {
      sym: "Kp",
      title: "Kontoplan",
      desc: "En förenklad svensk kontoplan anpassad för privatekonomi. 4-siffriga konton, kontogrupper, periodisering.",
      items: [
        "Tillgångar / skulder / inkomst / utgift",
        "Egna konton för varje barn",
        "Eget kapital över tid",
      ],
    },
    {
      sym: "Br",
      title: "Balansräkning",
      desc: "Vad äger ni, vad är ni skyldiga, vad har förändrats? Per månad, per kvartal, per år.",
      items: [
        "Tillgångar minus skulder",
        "Resultatrapport varje månad",
        "Trender över terminer och år",
      ],
    },
  ];
  return (
    <section
      style={{
        padding: "96px 24px",
        borderTop: `1px solid ${theme.rule}`,
        background: "#fafaf9",
      }}
    >
      <SectionHeader
        cell={{ sym: "Hb", n: "02", label: "Huvudbok" }}
        eyebrow="Under huven"
        theme={theme}
      >
        Dubbel bokföring, från första{" "}
        <em style={{ color: theme.accent, fontStyle: "italic" }}>fickpengen.</em>
      </SectionHeader>
      <p
        style={{
          maxWidth: 680,
          marginBottom: 48,
          fontSize: 15.5,
          lineHeight: 1.55,
          color: "#475569",
        }}
      >
        Inspirerat av Visma och Fortnox — fast enklare, roligare och faktiskt
        begripligt för en 13-åring. Eleven lär sig dubbel bokföring genom att
        leva ett liv, inte genom att läsa om det.
      </p>
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))",
          gap: 18,
        }}
      >
        {features.map((f, i) => (
          <div
            key={i}
            style={{
              background: "#fff",
              border: `1px solid ${theme.rule}`,
              borderRadius: 12,
              padding: 26,
            }}
          >
            <div
              style={{
                width: 48,
                height: 48,
                borderRadius: 8,
                background: theme.fg,
                color: "#fef3c7",
                display: "grid",
                placeItems: "center",
                fontFamily: "ui-monospace, monospace",
                fontWeight: 700,
                fontSize: 17,
                marginBottom: 18,
              }}
            >
              {f.sym}
            </div>
            <h3
              style={{
                fontSize: 20,
                fontWeight: 600,
                letterSpacing: -0.3,
                marginBottom: 10,
              }}
            >
              {f.title}
            </h3>
            <p
              style={{
                fontSize: 14,
                lineHeight: 1.55,
                color: "#475569",
                marginBottom: 14,
              }}
            >
              {f.desc}
            </p>
            <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
              {f.items.map((it, j) => (
                <li
                  key={j}
                  style={{
                    fontSize: 13,
                    color: "#0f172a",
                    paddingLeft: 16,
                    position: "relative",
                    marginBottom: 5,
                  }}
                >
                  <span style={{ position: "absolute", left: 0, color: theme.accent }}>—</span>
                  {it}
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>
    </section>
  );
}

// ---------- ThreeModesSection (v5) — Skola / Hemma / Desktop ----------

function ThreeModesSection({ theme }: { theme: Theme }) {
  const modes: Array<{
    kicker: string;
    title: string;
    desc: string;
    stats: string[];
    cta: string;
    soon?: boolean;
  }> = [
    {
      kicker: "Skolan",
      title: "Klassrummet",
      desc: "Multi-tenant labb. Lärare bjuder in en hel klass via 8-tecken-koder. Mastery-graf, portfolio-PDF, klass-ZIP.",
      stats: ["Multi-tenant per skola", "AI-coach per elev", "Bedömningsunderlag som PDF"],
      cta: "Skapa lärarkonto",
    },
    {
      kicker: "Hemmet",
      title: "Köksbordet",
      desc: "Förälder + barn delar samma sandlåda. Modulerna är desamma som i skolan — riktiga pengar är aldrig inblandade.",
      stats: ["Egen sandlåda per barn", "Gemensam vy med läraren", "AI-coach på familjens språk"],
      cta: "Skapa familjekonto",
    },
    {
      kicker: "Riktig ekonomi",
      title: "Hembudget desktop",
      desc: "Anslut riktiga bankkonton via Tink. Ladda upp fakturor. Krypterat lokalt med master-lösenord — datan lämnar aldrig din dator.",
      stats: ["Tauri-app · macOS / Windows", "Krypterad lokalt med argon2id", "PSD2 + PDF-fakturaimport"],
      cta: "Anmäl intresse",
      soon: true,
    },
  ];
  return (
    <section
      style={{
        padding: "96px 24px",
        borderTop: `1px solid ${theme.rule}`,
        background: "#fff",
      }}
    >
      <SectionHeader
        cell={{ sym: "Lg", n: "03", label: "Lägen" }}
        eyebrow="En motor, tre lägen"
        theme={theme}
      >
        Klassrummet, köksbordet — och snart{" "}
        <em style={{ color: theme.accent, fontStyle: "italic" }}>
          er riktiga ekonomi.
        </em>
      </SectionHeader>
      <p
        style={{
          maxWidth: 720,
          marginBottom: 48,
          fontSize: 15.5,
          lineHeight: 1.55,
          color: "#475569",
        }}
      >
        Samma kodbas, samma datamodell, samma motor. Eleven lär sig på simulerad
        data i klassrummet. Familjen övar på samma sandlåda hemma. När det är
        dags för riktiga pengar finns desktop-appen — med exakt samma logik,
        men din egen data, krypterad lokalt på din egen dator.
      </p>
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))",
          gap: 18,
        }}
      >
        {modes.map((m, i) => (
          <div
            key={i}
            style={{
              position: "relative",
              padding: 26,
              background: m.soon
                ? "linear-gradient(180deg, #fff 0%, #fef3c7 100%)"
                : "#fff",
              border: m.soon
                ? `1px dashed ${theme.fg}`
                : `1px solid ${theme.rule}`,
              borderRadius: 12,
            }}
          >
            {m.soon && (
              <span
                style={{
                  position: "absolute",
                  top: -10,
                  right: 18,
                  background: theme.fg,
                  color: "#fef3c7",
                  padding: "3px 10px",
                  borderRadius: 100,
                  fontSize: 10.5,
                  fontWeight: 600,
                  letterSpacing: 0.6,
                  fontFamily: "ui-monospace, monospace",
                  textTransform: "uppercase",
                }}
              >
                ● Kommer 2026
              </span>
            )}
            <div className={theme.eyebrow} style={{ marginBottom: 8 }}>
              {m.kicker}
            </div>
            <h3
              style={{
                fontSize: 22,
                fontWeight: 600,
                letterSpacing: -0.4,
                marginBottom: 12,
                lineHeight: 1.2,
              }}
            >
              {m.title}.
            </h3>
            <p
              style={{
                fontSize: 14,
                lineHeight: 1.55,
                color: "#475569",
                marginBottom: 18,
              }}
            >
              {m.desc}
            </p>
            <ul style={{ listStyle: "none", padding: 0, margin: "0 0 22px" }}>
              {m.stats.map((s, j) => (
                <li
                  key={j}
                  style={{
                    fontSize: 12.5,
                    color: "#0f172a",
                    paddingLeft: 16,
                    position: "relative",
                    marginBottom: 5,
                    fontFamily: "ui-monospace, monospace",
                  }}
                >
                  <span style={{ position: "absolute", left: 0, color: theme.accent }}>·</span>
                  {s}
                </li>
              ))}
            </ul>
            <button
              type="button"
              className={`${theme.btn} ${m.soon ? "" : theme.btnPrimary}`}
              style={
                m.soon
                  ? { borderColor: theme.fg, border: `1px solid ${theme.fg}` }
                  : {}
              }
            >
              {m.cta}
              {m.soon ? " →" : ""}
            </button>
          </div>
        ))}
      </div>
    </section>
  );
}

// ---------- StocksSection (v5) — Nasdaq + loss-aversion + månadsrapport ----------

function StocksSection({ theme }: { theme: Theme }) {
  const [selectedStock, setSelectedStock] = useState(0);
  const [scenario, setScenario] = useState<"loss" | "gain">("loss");
  const sectionRef = useRef<HTMLElement | null>(null);
  const reduced = useReducedMotion();

  // Ticker-animation: aktiepriserna räknar upp 0 → pris med stagger
  // när StocksSection kommer i view.
  useEffect(() => {
    if (reduced || !sectionRef.current) return;
    registerScrollTrigger();
    const ctx = gsap.context(() => {
      ScrollTrigger.create({
        trigger: sectionRef.current,
        start: "top 75%",
        once: true,
        onEnter: () => {
          const root = sectionRef.current;
          if (!root) return;
          const els = root.querySelectorAll<HTMLElement>("[data-vc-stockprice]");
          els.forEach((el, i) => {
            const target = Number(el.dataset.target) || 0;
            const obj = { v: 0 };
            gsap.to(obj, {
              v: target,
              duration: 1.0,
              delay: i * 0.08,
              ease: "power1.out",
              onUpdate: () => {
                el.textContent = `${obj.v.toFixed(2)} kr`;
              },
            });
          });
        },
      });
    }, sectionRef);
    return () => ctx.revert();
  }, [reduced]);

  const stocks = [
    { ticker: "VOLV-B", name: "Volvo B", price: 312.4, change: -2.1, color: "#dc4c2b" },
    { ticker: "ERIC-B", name: "Ericsson B", price: 78.65, change: 1.8, color: "#10b981" },
    { ticker: "HM-B", name: "H&M B", price: 178.2, change: -0.6, color: "#dc4c2b" },
    { ticker: "INVE-B", name: "Investor B", price: 285.0, change: 0.4, color: "#10b981" },
    { ticker: "SEB-A", name: "SEB A", price: 162.85, change: -1.2, color: "#dc4c2b" },
  ];
  const cur = stocks[selectedStock];
  const tradeAmount = 10;
  const tradeValue = cur.price * tradeAmount;
  const courtage = Math.max(1, tradeValue * 0.0025);
  const total = tradeValue + courtage;

  const portfolioValue = 24500;
  const change24h = scenario === "loss" ? -3.2 : 3.2;
  const moveKr = portfolioValue * (change24h / 100);
  const trygghetImpact =
    scenario === "loss"
      ? Math.round((moveKr / portfolioValue) * 100 * 2.0 * 0.6)
      : Math.round((moveKr / portfolioValue) * 100 * 1.0 * 0.6);
  const baseTrygghet = 62;
  const newTrygghet = Math.max(0, Math.min(100, baseTrygghet + trygghetImpact));

  return (
    <section
      ref={sectionRef}
      style={{
        padding: "96px 24px",
        borderTop: `1px solid ${theme.rule}`,
        background: "#fafaf9",
      }}
    >
      <SectionHeader
        cell={{ sym: "Ak", n: "04", label: "Aktier" }}
        eyebrow="Aktiesimulatorn"
        theme={theme}
      >
        Riktiga aktier, simulerade pengar —{" "}
        <em style={{ color: theme.accent, fontStyle: "italic" }}>
          känslan är på riktigt.
        </em>
      </SectionHeader>
      <p
        style={{
          maxWidth: 720,
          marginBottom: 48,
          fontSize: 15.5,
          lineHeight: 1.55,
          color: "#475569",
        }}
      >
        Eleven öppnar ett ISK, väljer från 30 svenska large-caps (Volvo,
        Ericsson, H&M, SEB, Investor…), handlar mot riktiga kurser med ~15 min
        försening. Avanza Mini-courtage. Marknaden stänger 17:30. Och — det
        här är poängen — varje köp och sälj påverkar Wellbeing. Inte i ett
        separat spel. I samma huvudbok som lönen, hyran och bufferten.
      </p>

      {/* Trading view + portfölj */}
      <div
        style={{
          background: "#fff",
          border: `1px solid ${theme.rule}`,
          borderRadius: 14,
          overflow: "hidden",
          marginBottom: 28,
        }}
      >
        <div
          style={{
            padding: "14px 20px",
            borderBottom: `1px solid ${theme.rule}`,
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            background: "#fafaf9",
            flexWrap: "wrap",
            gap: 8,
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
            <div
              style={{
                fontFamily: "ui-monospace, monospace",
                fontSize: 11,
                letterSpacing: 1,
                color: "#475569",
                textTransform: "uppercase",
              }}
            >
              NASDAQ STOCKHOLM
            </div>
            <span
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: 6,
                fontSize: 11,
                fontFamily: "ui-monospace, monospace",
                color: "#10b981",
              }}
            >
              <span
                style={{
                  width: 6,
                  height: 6,
                  borderRadius: "50%",
                  background: "#10b981",
                  boxShadow: "0 0 0 3px rgba(16,185,129,0.18)",
                }}
              />
              ÖPPEN · STÄNGER 17:30
            </span>
          </div>
          <div
            style={{
              fontFamily: "ui-monospace, monospace",
              fontSize: 10.5,
              color: "#94a3b8",
              letterSpacing: 0.5,
            }}
          >
            FÖRSENING ~15 MIN · KÄLLA: yfinance
          </div>
        </div>

        <div
          className="vc-stocks-grid"
          style={{
            display: "grid",
            gridTemplateColumns: "1.2fr 1fr",
            minHeight: 360,
          }}
        >
          <style>{`
            @media (max-width: 768px) {
              .vc-stocks-grid { grid-template-columns: 1fr !important; }
              .vc-stocks-list { border-right: 0 !important; border-bottom: 1px solid #e2e8f0 !important; }
              .vc-stocks-loss-grid { grid-template-columns: 1fr !important; gap: 20px !important; }
              .vc-stocks-mreport-grid { grid-template-columns: 1fr !important; }
              .vc-stocks-laq-grid { grid-template-columns: 1fr !important; gap: 14px !important; }
            }
          `}</style>
          <div
            className="vc-stocks-list"
            style={{ borderRight: `1px solid ${theme.rule}`, padding: "16px 0" }}
          >
            {stocks.map((s, i) => (
              <button
                key={s.ticker}
                type="button"
                onClick={() => setSelectedStock(i)}
                style={{
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                  width: "100%",
                  padding: "12px 22px",
                  cursor: "pointer",
                  background: selectedStock === i ? "#fef3c7" : "transparent",
                  border: "none",
                  borderLeft:
                    selectedStock === i
                      ? `3px solid ${theme.accent}`
                      : "3px solid transparent",
                  fontFamily: "inherit",
                  textAlign: "left",
                  transition: "all .12s",
                }}
              >
                <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                  <div
                    style={{
                      width: 36,
                      height: 36,
                      borderRadius: 7,
                      background: "#0f172a",
                      color: "#fef3c7",
                      display: "grid",
                      placeItems: "center",
                      fontFamily: "ui-monospace, monospace",
                      fontWeight: 700,
                      fontSize: 11,
                    }}
                  >
                    {s.ticker.split("-")[0].slice(0, 2)}
                  </div>
                  <div>
                    <div style={{ fontSize: 14, fontWeight: 600, color: "#0f172a" }}>
                      {s.name}
                    </div>
                    <div
                      style={{
                        fontSize: 11.5,
                        color: "#64748b",
                        fontFamily: "ui-monospace, monospace",
                      }}
                    >
                      {s.ticker}.ST
                    </div>
                  </div>
                </div>
                <div style={{ textAlign: "right" }}>
                  <div
                    data-vc-stockprice
                    data-target={s.price}
                    style={{
                      fontSize: 13.5,
                      fontWeight: 600,
                      color: "#0f172a",
                      fontFamily: "ui-monospace, monospace",
                    }}
                  >
                    {s.price.toFixed(2)} kr
                  </div>
                  <div
                    style={{
                      fontSize: 11.5,
                      color: s.color,
                      fontFamily: "ui-monospace, monospace",
                    }}
                  >
                    {s.change > 0 ? "▲" : "▼"} {Math.abs(s.change).toFixed(1)} %
                  </div>
                </div>
              </button>
            ))}
          </div>

          <div style={{ padding: 26, background: "#fafaf9" }}>
            <div className={theme.eyebrow} style={{ marginBottom: 8 }}>
              Köp · Marknadsorder
            </div>
            <h3
              style={{
                fontSize: 22,
                fontWeight: 600,
                letterSpacing: -0.4,
                margin: "0 0 6px",
              }}
            >
              {cur.name}
            </h3>
            <div
              style={{
                fontSize: 26,
                fontFamily: "ui-monospace, monospace",
                fontWeight: 700,
                color: "#0f172a",
                marginBottom: 4,
              }}
            >
              {cur.price.toFixed(2)}{" "}
              <span style={{ fontSize: 14, color: "#64748b" }}>kr</span>
            </div>
            <div
              style={{
                fontSize: 12,
                color: cur.color,
                fontFamily: "ui-monospace, monospace",
                marginBottom: 22,
              }}
            >
              {cur.change > 0 ? "▲" : "▼"} {Math.abs(cur.change).toFixed(1)} %
              senaste timmen
            </div>

            <div
              style={{
                background: "#fff",
                border: `1px solid ${theme.rule}`,
                borderRadius: 8,
                padding: 16,
                fontFamily: "ui-monospace, monospace",
                fontSize: 13,
                lineHeight: 1.9,
              }}
            >
              <div style={{ display: "flex", justifyContent: "space-between", color: "#475569" }}>
                <span>Antal</span>
                <strong style={{ color: "#0f172a" }}>{tradeAmount} st</strong>
              </div>
              <div style={{ display: "flex", justifyContent: "space-between", color: "#475569" }}>
                <span>Affärsbelopp</span>
                <strong style={{ color: "#0f172a" }}>{tradeValue.toFixed(2)} kr</strong>
              </div>
              <div style={{ display: "flex", justifyContent: "space-between", color: "#475569" }}>
                <span>Courtage (Mini · 0,25 %)</span>
                <strong style={{ color: "#0f172a" }}>{courtage.toFixed(2)} kr</strong>
              </div>
              <div
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  marginTop: 8,
                  paddingTop: 8,
                  borderTop: `1px solid ${theme.rule}`,
                  color: "#0f172a",
                }}
              >
                <span>Totalt</span>
                <strong style={{ color: theme.accent }}>{total.toFixed(2)} kr</strong>
              </div>
            </div>

            <div
              style={{
                marginTop: 14,
                padding: "10px 14px",
                background: "#fef3c7",
                border: "1px solid rgba(120,53,15,.2)",
                borderRadius: 8,
                fontSize: 12,
                color: "#78350f",
                lineHeight: 1.5,
              }}
            >
              <strong>Innan eleven klickar:</strong> hen skriver en kort
              motivering. "Q4-rapporten såg bra ut." Den sparas i ledgern —
              läraren kan fråga om den senare.
            </div>
          </div>
        </div>
      </div>

      {/* Loss aversion */}
      <div
        style={{
          background: "#0f172a",
          color: "#fff",
          borderRadius: 14,
          padding: "32px 36px",
          marginBottom: 28,
        }}
      >
        <div
          className="vc-stocks-loss-grid"
          style={{
            display: "grid",
            gridTemplateColumns: "1fr 1fr",
            gap: 48,
            alignItems: "center",
          }}
        >
          <div>
            <div
              style={{
                fontFamily: "ui-monospace, monospace",
                fontSize: 11,
                letterSpacing: 1.2,
                color: "#fbbf24",
                textTransform: "uppercase",
                marginBottom: 12,
              }}
            >
              Loss aversion · Kahneman/Tversky
            </div>
            <h3
              style={{
                fontSize: 26,
                fontWeight: 600,
                letterSpacing: -0.4,
                lineHeight: 1.25,
                margin: "0 0 14px",
                fontFamily: theme.serifFont,
              }}
            >
              En förlust på 1 % gör{" "}
              <em style={{ color: "#fbbf24" }}>dubbelt så ont</em> som en vinst
              på 1 % känns bra.
            </h3>
            <p
              style={{
                fontSize: 14.5,
                lineHeight: 1.6,
                color: "#cbd5e1",
                margin: "0 0 18px",
              }}
            >
              Wellbeing-Trygghet räknar in portföljens 24h-rörelse med λ ≈ 2.0.
              Om eleven inte känner smärtan av en förlust — i siffror, på sin
              egen mätare — kan hen aldrig lära sig att skilja känsloreaktion
              från klokt beslut.
            </p>
            <div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>
              <button
                type="button"
                onClick={() => setScenario("loss")}
                style={{
                  padding: "9px 16px",
                  borderRadius: 8,
                  cursor: "pointer",
                  background: scenario === "loss" ? "#dc4c2b" : "transparent",
                  border:
                    scenario === "loss"
                      ? "1px solid #dc4c2b"
                      : "1px solid rgba(255,255,255,0.2)",
                  color: "#fff",
                  fontSize: 13,
                  fontWeight: 500,
                  fontFamily: "inherit",
                }}
              >
                Portföljen ner 3,2 %
              </button>
              <button
                type="button"
                onClick={() => setScenario("gain")}
                style={{
                  padding: "9px 16px",
                  borderRadius: 8,
                  cursor: "pointer",
                  background: scenario === "gain" ? "#10b981" : "transparent",
                  border:
                    scenario === "gain"
                      ? "1px solid #10b981"
                      : "1px solid rgba(255,255,255,0.2)",
                  color: "#fff",
                  fontSize: 13,
                  fontWeight: 500,
                  fontFamily: "inherit",
                }}
              >
                Portföljen upp 3,2 %
              </button>
            </div>
          </div>

          <div
            style={{
              background: "rgba(255,255,255,0.03)",
              border: "1px solid rgba(255,255,255,0.08)",
              borderRadius: 12,
              padding: 24,
            }}
          >
            <div
              style={{
                fontFamily: "ui-monospace, monospace",
                fontSize: 10.5,
                letterSpacing: 1,
                color: "#94a3b8",
                textTransform: "uppercase",
                marginBottom: 14,
              }}
            >
              Wellbeing · Trygghet
            </div>
            <div
              style={{
                display: "flex",
                alignItems: "baseline",
                gap: 12,
                marginBottom: 14,
              }}
            >
              <span
                style={{
                  fontSize: 56,
                  fontWeight: 700,
                  letterSpacing: -1.5,
                  color: scenario === "loss" ? "#dc4c2b" : "#10b981",
                  transition: "color .3s",
                  fontFamily: "ui-monospace, monospace",
                }}
              >
                {newTrygghet}
              </span>
              <span
                style={{
                  fontSize: 18,
                  color: "#64748b",
                  fontFamily: "ui-monospace, monospace",
                }}
              >
                / 100
              </span>
              <span
                style={{
                  fontSize: 13,
                  marginLeft: "auto",
                  color: scenario === "loss" ? "#dc4c2b" : "#10b981",
                  fontFamily: "ui-monospace, monospace",
                  fontWeight: 600,
                }}
              >
                {trygghetImpact > 0 ? "+" : ""}
                {trygghetImpact}
              </span>
            </div>
            <div
              style={{
                height: 6,
                background: "rgba(255,255,255,0.08)",
                borderRadius: 3,
                overflow: "hidden",
                marginBottom: 16,
              }}
            >
              <div
                style={{
                  width: `${newTrygghet}%`,
                  height: "100%",
                  background: scenario === "loss" ? "#dc4c2b" : "#10b981",
                  transition: "all .4s cubic-bezier(.2,.7,.3,1)",
                }}
              />
            </div>
            <div
              style={{
                fontSize: 12.5,
                lineHeight: 1.55,
                color: "#cbd5e1",
                fontFamily: theme.serifFont,
                fontStyle: "italic",
              }}
            >
              {scenario === "loss"
                ? '"AAPL och Volvo B drog ner portföljen med 784 kr. Det kostade dig 4 Trygghet-poäng — dubbelt så mycket som en lika stor vinst hade gett."'
                : '"Portföljen upp 784 kr. Trygghet steg 2 poäng. En lika stor förlust hade kostat 4 — det är loss aversion i en mätare."'}
            </div>
          </div>
        </div>
      </div>

      {/* Månadsrapport — Aktie-eftertanke */}
      <div
        style={{
          background: "#fff",
          border: `1px solid ${theme.rule}`,
          borderRadius: 14,
          padding: "32px 36px",
        }}
      >
        <div
          style={{
            display: "flex",
            alignItems: "flex-start",
            justifyContent: "space-between",
            marginBottom: 24,
            flexWrap: "wrap",
            gap: 16,
          }}
        >
          <div>
            <div className={theme.eyebrow} style={{ marginBottom: 8 }}>
              Månadsrapport · Aktie-eftertanke
            </div>
            <h3
              style={{
                fontSize: 24,
                fontWeight: 600,
                letterSpacing: -0.4,
                lineHeight: 1.25,
                margin: 0,
                maxWidth: 540,
              }}
            >
              60 dagar senare — den brutala spegeln som{" "}
              <em style={{ color: theme.accent, fontStyle: "italic" }}>
                driver lärande.
              </em>
            </h3>
          </div>
          <span
            style={{
              padding: "6px 12px",
              background: "#fef3c7",
              border: "1px solid rgba(120,53,15,.2)",
              borderRadius: 100,
              fontSize: 11,
              fontFamily: "ui-monospace, monospace",
              color: "#78350f",
              letterSpacing: 0.5,
            }}
          >
            OKTOBER 2026
          </span>
        </div>

        <div
          className="vc-stocks-mreport-grid"
          style={{
            display: "grid",
            gridTemplateColumns: "1fr 1fr",
            gap: 14,
            marginBottom: 14,
          }}
        >
          <div
            style={{
              background: "rgba(16,185,129,0.06)",
              border: "1px solid rgba(16,185,129,0.25)",
              borderRadius: 10,
              padding: 20,
            }}
          >
            <div
              style={{
                fontFamily: "ui-monospace, monospace",
                fontSize: 10.5,
                letterSpacing: 1,
                color: "#10b981",
                textTransform: "uppercase",
                marginBottom: 8,
                fontWeight: 600,
              }}
            >
              ● Bästa beslut
            </div>
            <div style={{ fontSize: 16, fontWeight: 600, marginBottom: 4, color: "#0f172a" }}>
              Sålde Investor B på topp
            </div>
            <div
              style={{
                fontSize: 13,
                color: "#475569",
                fontFamily: "ui-monospace, monospace",
                marginBottom: 12,
              }}
            >
              5 st @ 285,00 kr · realiserat{" "}
              <strong style={{ color: "#10b981" }}>+ 412 kr</strong>
            </div>
            <div
              style={{
                fontSize: 13.5,
                lineHeight: 1.55,
                color: "#065f46",
                fontStyle: "italic",
                fontFamily: theme.serifFont,
              }}
            >
              "Idag står den i 268 kr. Om du väntat hade du förlorat 85 kr. Bra
              läsning av rapporten."
            </div>
          </div>

          <div
            style={{
              background: "rgba(220,76,43,0.06)",
              border: "1px solid rgba(220,76,43,0.25)",
              borderRadius: 10,
              padding: 20,
            }}
          >
            <div
              style={{
                fontFamily: "ui-monospace, monospace",
                fontSize: 10.5,
                letterSpacing: 1,
                color: "#dc4c2b",
                textTransform: "uppercase",
                marginBottom: 8,
                fontWeight: 600,
              }}
            >
              ● Sämsta beslut
            </div>
            <div style={{ fontSize: 16, fontWeight: 600, marginBottom: 4, color: "#0f172a" }}>
              Sålde Volvo B i panik
            </div>
            <div
              style={{
                fontSize: 13,
                color: "#475569",
                fontFamily: "ui-monospace, monospace",
                marginBottom: 12,
              }}
            >
              10 st @ 267,00 kr · realiserat{" "}
              <strong style={{ color: "#dc4c2b" }}>− 148 kr</strong>
            </div>
            <div
              style={{
                fontSize: 13.5,
                lineHeight: 1.55,
                color: "#7f1d1d",
                fontStyle: "italic",
                fontFamily: theme.serifFont,
              }}
            >
              "Idag står den i 312 kr. Om du väntat hade du haft + 450 kr. Din
              förlust var marknaden — eller var det?"
            </div>
          </div>
        </div>

        <div
          className="vc-stocks-laq-grid"
          style={{
            background: "#0f172a",
            color: "#fff",
            borderRadius: 10,
            padding: "22px 26px",
            display: "grid",
            gridTemplateColumns: "auto 1fr auto",
            gap: 28,
            alignItems: "center",
          }}
        >
          <div
            style={{
              width: 72,
              height: 72,
              borderRadius: "50%",
              background: "rgba(251,191,36,0.12)",
              border: "2px solid #fbbf24",
              display: "grid",
              placeItems: "center",
              fontFamily: "ui-monospace, monospace",
              fontSize: 24,
              fontWeight: 700,
              color: "#fbbf24",
            }}
          >
            1.8×
          </div>
          <div>
            <div
              style={{
                fontFamily: "ui-monospace, monospace",
                fontSize: 10.5,
                letterSpacing: 1,
                color: "#fbbf24",
                textTransform: "uppercase",
                marginBottom: 4,
              }}
            >
              Din loss-aversion-quotient
            </div>
            <div style={{ fontSize: 15, lineHeight: 1.55, color: "#e2e8f0" }}>
              Du säljer 1,8× oftare i förlust än i vinst. Du säljer för snabbt
              när det går ner, för långsamt när det går upp. Klassiskt
              nybörjarmönster — och fixbart.
            </div>
          </div>
          <div
            style={{
              fontFamily: "ui-monospace, monospace",
              fontSize: 11,
              color: "#94a3b8",
              letterSpacing: 0.5,
              textAlign: "right",
            }}
          >
            4 sälj i förlust
            <br />2 sälj i vinst
          </div>
        </div>

        <p
          style={{
            marginTop: 22,
            fontSize: 13.5,
            lineHeight: 1.6,
            color: "#475569",
            fontStyle: "italic",
            maxWidth: 720,
          }}
        >
          Inget facit. Bara en spegel som visar mönstren — så att eleven nästa
          månad kan se om hen rör sig mot kvoten 1.0, eller djupare in i
          mönstret. Det är livslära, inte räknelära.
        </p>
      </div>
    </section>
  );
}

// ---------- CreditTriggerSection (v5) — val under press ----------

function CreditTriggerSection({ theme }: { theme: Theme }) {
  const [choice, setChoice] = useState<"priv" | "sms" | "skip">("priv");
  type Tone = "safe" | "warn" | "danger";
  const choices: Record<
    "priv" | "sms" | "skip",
    {
      label: string;
      kicker: string;
      tone: Tone;
      borrow: string;
      apr: string;
      term: string;
      monthly: string;
      total: string;
      tag: string;
      note: string;
      meta: string[];
    }
  > = {
    priv: {
      label: "Privatlån",
      kicker: "Förstavalet",
      tone: "safe",
      borrow: "15 000 kr",
      apr: "6,4 %",
      term: "36 mån",
      monthly: "460 kr/mån",
      total: "16 560 kr",
      tag: "Bankens process · kreditupplysning",
      note: "Banken kollar din inkomst, dina lån och din buffert. Bättre ekonomi ger bättre ränta. Du läser villkoren innan du klickar.",
      meta: [
        "Kreditupplysning körs",
        "Ränta beror på din score",
        "Lånet hamnar i huvudboken",
      ],
    },
    sms: {
      label: "SMS-lån",
      kicker: "Sista utvägen",
      tone: "danger",
      borrow: "5 000 kr",
      apr: "117 %",
      term: "30 dagar",
      monthly: "5 950 kr i en klumpsumma",
      total: "5 950 kr",
      tag: "Snabbt · dyrt · sällan rätt",
      note: "Inget kollas. Pengarna är inne på minuter — och försvinner med ränta och avgifter på 30 dagar. När det inte räcker tas ett nytt lån för att betala det första.",
      meta: [
        "Ingen kreditupplysning",
        "Effektiv ränta 89–200 %",
        "Skuldspiralen börjar här",
      ],
    },
    skip: {
      label: "Skjut upp räkningen",
      kicker: 'Det "gratis" valet',
      tone: "warn",
      borrow: "0 kr",
      apr: "—",
      term: "tills den går till inkasso",
      monthly: "60 kr påminnelse → 180 kr inkasso",
      total: "+ ev. betalningsanmärkning",
      tag: "Konsekvensen syns senare",
      note: "Räkningen försvinner inte. Påminnelse, inkasso, och i värsta fall en betalningsanmärkning som följer dig i tre år — när du senare ska teckna abonnemang eller hyra lägenhet.",
      meta: [
        "Påminnelseavgift 60 kr",
        "Inkasso efter 14 dagar",
        "Betalningsanmärkning 3 år",
      ],
    },
  };
  const tones: Record<
    Tone,
    { fg: string; bg: string; border: string; accent: string; soft: string }
  > = {
    safe: {
      fg: "#d1fae5",
      bg: "rgba(16,185,129,0.08)",
      border: "rgba(16,185,129,0.35)",
      accent: "#10b981",
      soft: "rgba(16,185,129,0.14)",
    },
    warn: {
      fg: "#fef3c7",
      bg: "rgba(251,191,36,0.08)",
      border: "rgba(251,191,36,0.35)",
      accent: "#fbbf24",
      soft: "rgba(251,191,36,0.14)",
    },
    danger: {
      fg: "#fee2e2",
      bg: "rgba(220,76,43,0.08)",
      border: "rgba(220,76,43,0.4)",
      accent: "#dc4c2b",
      soft: "rgba(220,76,43,0.14)",
    },
  };
  const curC = choices[choice];
  const tone = tones[curC.tone];

  return (
    <section
      style={{
        padding: "96px 24px",
        borderTop: `1px solid ${theme.rule}`,
        background: "#0f172a",
        color: "#fff",
      }}
    >
      <SectionHeader
        cell={{ sym: "Kr", n: "05", label: "Kredit" }}
        eyebrow="Val under press"
        theme={theme}
        dark
      >
        När ekonomin inte går ihop —{" "}
        <em style={{ color: "#fbbf24", fontStyle: "italic" }}>
          vad väljer eleven?
        </em>
      </SectionHeader>
      <p
        style={{
          maxWidth: 720,
          marginBottom: 36,
          fontSize: 15.5,
          lineHeight: 1.55,
          color: "#94a3b8",
        }}
      >
        Pengarna räcker inte. Hyran är på väg, autogirot går idag, och saldot
        är 1 200 kr för lågt. Systemet pausar — och tvingar fram ett beslut.
        Tre vägar finns. Alla tre kostar något. Den som är billigast på fredag
        kan vara dyrast om ett år.
      </p>

      <div
        style={{
          background: "rgba(255,255,255,0.03)",
          border: "1px solid rgba(255,255,255,0.08)",
          borderRadius: 14,
          padding: "32px 36px",
          marginBottom: 28,
          color: "#fff",
          position: "relative",
          overflow: "hidden",
        }}
      >
        <div
          className="vc-credit-trigger"
          style={{
            display: "grid",
            gridTemplateColumns: "1fr auto",
            gap: 32,
            alignItems: "center",
          }}
        >
          <style>{`
            @media (max-width: 768px) {
              .vc-credit-trigger { grid-template-columns: 1fr !important; gap: 18px !important; }
              .vc-credit-grid { grid-template-columns: 1fr !important; }
              .vc-credit-detail { grid-template-columns: 1fr !important; gap: 18px !important; }
            }
          `}</style>
          <div>
            <div
              style={{
                fontFamily: "ui-monospace, monospace",
                fontSize: 11,
                letterSpacing: 1.2,
                color: "#fbbf24",
                textTransform: "uppercase",
                marginBottom: 10,
              }}
            >
              ● Systemet pausar transaktionen
            </div>
            <h3
              style={{
                fontSize: 28,
                fontWeight: 600,
                letterSpacing: -0.5,
                lineHeight: 1.2,
                margin: "0 0 12px",
                fontFamily: theme.serifFont,
              }}
            >
              "Din ekonomi går inte ihop."
            </h3>
            <p
              style={{
                fontSize: 14.5,
                lineHeight: 1.55,
                color: "#cbd5e1",
                margin: 0,
                maxWidth: 540,
              }}
            >
              Hyran på 8 500 kr ska dras imorgon. Saldot är 7 300 kr. Du saknar
              <strong style={{ color: "#fff" }}> 1 200 kr</strong>. Vad gör du?
            </p>
          </div>
          <div
            style={{
              fontFamily: "ui-monospace, monospace",
              fontSize: 13,
              lineHeight: 1.85,
              background: "rgba(0,0,0,0.3)",
              border: "1px solid rgba(255,255,255,0.1)",
              borderRadius: 10,
              padding: "16px 20px",
              minWidth: 220,
            }}
          >
            <div
              style={{
                color: "#94a3b8",
                marginBottom: 6,
                fontSize: 11,
                letterSpacing: 1,
              }}
            >
              LÖNEKONTO
            </div>
            <div style={{ color: "#e2e8f0" }}>
              Saldo: <strong style={{ color: "#fff" }}>+ 7 300 kr</strong>
            </div>
            <div style={{ color: "#e2e8f0" }}>
              Hyra: <span style={{ color: "#fbbf24" }}>− 8 500 kr</span>
            </div>
            <div
              style={{
                marginTop: 6,
                paddingTop: 6,
                borderTop: "1px solid rgba(255,255,255,.1)",
                color: "#e2e8f0",
              }}
            >
              Saknas: <strong style={{ color: "#dc4c2b" }}>− 1 200 kr</strong>
            </div>
          </div>
        </div>
      </div>

      <div
        className="vc-credit-grid"
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(3, 1fr)",
          gap: 14,
          marginBottom: 28,
        }}
      >
        {(Object.entries(choices) as Array<[
          "priv" | "sms" | "skip",
          (typeof choices)["priv"],
        ]>).map(([key, c]) => {
          const t = tones[c.tone];
          const active = choice === key;
          return (
            <button
              key={key}
              type="button"
              onClick={() => setChoice(key)}
              style={{
                textAlign: "left",
                cursor: "pointer",
                padding: 22,
                background: active ? t.bg : "rgba(255,255,255,0.03)",
                border: active
                  ? `2px solid ${t.accent}`
                  : "1px solid rgba(255,255,255,0.08)",
                borderRadius: 12,
                transition: "all .15s",
                color: "#fff",
                fontFamily: "inherit",
              }}
            >
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                  marginBottom: 14,
                }}
              >
                <span
                  style={{
                    fontFamily: "ui-monospace, monospace",
                    fontSize: 10.5,
                    letterSpacing: 1,
                    color: t.accent,
                    textTransform: "uppercase",
                    fontWeight: 600,
                  }}
                >
                  {c.kicker}
                </span>
                <span
                  style={{
                    width: 8,
                    height: 8,
                    borderRadius: "50%",
                    background: t.accent,
                    boxShadow: active ? `0 0 0 4px ${t.soft}` : "none",
                  }}
                />
              </div>
              <h4
                style={{
                  fontSize: 19,
                  fontWeight: 600,
                  letterSpacing: -0.3,
                  margin: "0 0 6px",
                  color: "#fff",
                }}
              >
                {c.label}
              </h4>
              <div
                style={{
                  fontSize: 12,
                  color: "#94a3b8",
                  fontFamily: "ui-monospace, monospace",
                  marginBottom: 14,
                }}
              >
                {c.tag}
              </div>
              <div
                style={{
                  display: "grid",
                  gridTemplateColumns: "1fr 1fr",
                  gap: 10,
                  fontFamily: "ui-monospace, monospace",
                  fontSize: 12.5,
                }}
              >
                <div>
                  <div style={{ color: "#64748b", fontSize: 10.5, letterSpacing: 0.5 }}>
                    RÄNTA
                  </div>
                  <strong style={{ color: "#e2e8f0" }}>{c.apr}</strong>
                </div>
                <div>
                  <div style={{ color: "#64748b", fontSize: 10.5, letterSpacing: 0.5 }}>
                    LÖPTID
                  </div>
                  <strong style={{ color: "#e2e8f0" }}>{c.term}</strong>
                </div>
              </div>
            </button>
          );
        })}
      </div>

      <div
        className="vc-credit-detail"
        style={{
          background: tone.bg,
          border: `1px solid ${tone.border}`,
          borderRadius: 14,
          padding: "28px 32px",
          display: "grid",
          gridTemplateColumns: "1.4fr 1fr",
          gap: 36,
          alignItems: "start",
        }}
      >
        <div>
          <div
            style={{
              fontFamily: "ui-monospace, monospace",
              fontSize: 11,
              letterSpacing: 1.2,
              color: tone.accent,
              textTransform: "uppercase",
              marginBottom: 10,
              fontWeight: 600,
            }}
          >
            Vald väg · {curC.label}
          </div>
          <h3
            style={{
              fontSize: 24,
              fontWeight: 600,
              letterSpacing: -0.4,
              lineHeight: 1.3,
              margin: "0 0 14px",
              color: "#fff",
              fontFamily: theme.serifFont,
            }}
          >
            {curC.note}
          </h3>
          <ul
            style={{
              listStyle: "none",
              padding: 0,
              margin: 0,
              display: "flex",
              flexDirection: "column",
              gap: 8,
            }}
          >
            {curC.meta.map((m, i) => (
              <li
                key={i}
                style={{
                  display: "flex",
                  gap: 12,
                  alignItems: "center",
                  fontSize: 13.5,
                  color: tone.fg,
                  fontFamily: "ui-monospace, monospace",
                }}
              >
                <span
                  style={{
                    width: 18,
                    height: 18,
                    borderRadius: "50%",
                    background: "rgba(0,0,0,0.3)",
                    border: `1px solid ${tone.border}`,
                    color: tone.accent,
                    display: "grid",
                    placeItems: "center",
                    fontSize: 10,
                    fontWeight: 700,
                  }}
                >
                  {i + 1}
                </span>
                {m}
              </li>
            ))}
          </ul>
        </div>
        <div
          style={{
            background: "rgba(0,0,0,0.3)",
            borderRadius: 10,
            padding: 22,
            fontFamily: "ui-monospace, monospace",
            fontSize: 13,
            lineHeight: 1.9,
            border: `1px solid ${tone.border}`,
            color: "#e2e8f0",
          }}
        >
          <div
            style={{
              fontSize: 10.5,
              letterSpacing: 1,
              color: "#94a3b8",
              marginBottom: 10,
              textTransform: "uppercase",
            }}
          >
            Vad det kostar
          </div>
          <div>
            Lånat: <strong style={{ color: "#fff" }}>{curC.borrow}</strong>
          </div>
          <div>
            Att betala: <strong style={{ color: "#fff" }}>{curC.monthly}</strong>
          </div>
          <div>
            Total kostnad:{" "}
            <strong style={{ color: tone.accent }}>{curC.total}</strong>
          </div>
          <div
            style={{
              marginTop: 10,
              paddingTop: 10,
              borderTop: `1px solid ${tone.border}`,
              fontStyle: "italic",
              color: tone.fg,
              fontFamily: theme.serifFont,
              fontSize: 13.5,
            }}
          >
            {curC.tone === "safe" && "Lugnt val. Ränta i normalsegmentet."}
            {curC.tone === "danger" &&
              "Pengarna är inne på minuter. Skulden växer lika snabbt."}
            {curC.tone === "warn" && "Räkningen försvinner inte. Den blir bara dyrare."}
          </div>
        </div>
      </div>

      <div
        style={{
          marginTop: 32,
          paddingTop: 32,
          borderTop: "1px solid rgba(255,255,255,0.08)",
          display: "flex",
          alignItems: "flex-start",
          justifyContent: "space-between",
          gap: 32,
        }}
      >
        <div style={{ flex: 1 }}>
          <div
            style={{
              fontFamily: "ui-monospace, monospace",
              fontSize: 11,
              letterSpacing: 1.2,
              color: "#fbbf24",
              textTransform: "uppercase",
              marginBottom: 8,
            }}
          >
            Konsekvenserna kvarstår
          </div>
          <p
            style={{
              fontSize: 15,
              lineHeight: 1.55,
              margin: 0,
              color: "#cbd5e1",
              maxWidth: 760,
            }}
          >
            Lånet blir en rad i huvudboken med ett amorteringsschema.
            Påminnelseavgiften blir en transaktion. SMS-lånet blir en månadsavi
            i 30 dagar — och en följdfråga från AI-coachen:{" "}
            <em style={{ color: "#fbbf24" }}>
              "Hur hamnade du här? Vad kunde du gjort annorlunda?"
            </em>
          </p>
        </div>
      </div>
    </section>
  );
}

// ---------- LifeSimSection (v5) — livssimulator + Swish-skuld-spotlight ----------

function LifeSimSection({ theme }: { theme: Theme }) {
  const events = [
    {
      cat: "Socialt",
      symbol: "Bg",
      title: "Bio på Filmstaden",
      cost: "195 kr",
      wb: "+ Sociala · + Fritid",
      detail:
        "Vänskap kostar pengar. Säger eleven nej blir Wellbeing 60 — säger hen ja på allt brister bufferten.",
    },
    {
      cat: "Hälsa",
      symbol: "Tn",
      title: "Tandläkare akut",
      cost: "2 400 kr",
      wb: "− Trygghet om buffert saknas",
      detail:
        "Oväntad utgift. Nu märker eleven varför reservfonden är sex månadshyror, inte två.",
    },
    {
      cat: "Fest",
      symbol: "Kj",
      title: "Kalas hos Jonna",
      cost: "450 kr present + uber",
      wb: "+ Sociala · − Ekonomi",
      detail: "Eleven måste välja: avstå eller ompröva budgeten denna vecka.",
    },
    {
      cat: "Vardag",
      symbol: "Lh",
      title: "Löning till sparkonto",
      cost: "+ 4 000 kr",
      wb: "+ Ekonomi · + Trygghet",
      detail:
        "Automatiserat sparande. 25 % till buffert, 5 % till långsiktigt — innan eleven hinner spendera.",
    },
    {
      cat: "Större",
      symbol: "Mt",
      title: "Marathon-anmälan",
      cost: "795 kr",
      wb: "+ Hälsa · + Fritid",
      detail:
        "En investering i sig själv. Värt det? Beror på vad det tränger ut.",
    },
    {
      cat: "Tvång",
      symbol: "Sl",
      title: "Sl-böter — glömt biljett",
      cost: "− 1 500 kr",
      wb: "− Ekonomi · − Trygghet",
      detail:
        "Konsekvens. Inte abstrakt straff — riktig hål i bufferten som tar två månader att fylla.",
    },
  ];
  return (
    <section
      style={{
        padding: "96px 24px",
        borderTop: `1px solid ${theme.rule}`,
        background: "#fafaf9",
      }}
    >
      <div
        style={{
          display: "flex",
          alignItems: "flex-start",
          justifyContent: "space-between",
          marginBottom: 12,
          flexWrap: "wrap",
          gap: 12,
        }}
      >
        <SectionHeader
          cell={{ sym: "Lv", n: "06", label: "Livet" }}
          eyebrow="Livssimulatorn"
          theme={theme}
        >
          Igenkännbara situationer
          <br />
          <em style={{ color: theme.accent, fontStyle: "italic" }}>
            från svensk vardag.
          </em>
        </SectionHeader>
        <span
          style={{
            padding: "6px 12px",
            background: "#fff",
            border: `1px solid ${theme.rule}`,
            borderRadius: 100,
            fontSize: 12,
            fontFamily: "ui-monospace, monospace",
            color: "#475569",
            letterSpacing: 0.5,
            marginTop: 12,
          }}
        >
          URVAL · 6 KORT
        </span>
      </div>
      <p
        style={{
          maxWidth: 720,
          marginBottom: 36,
          fontSize: 15.5,
          lineHeight: 1.55,
          color: "#475569",
        }}
      >
        Bio på Filmstaden, julbord på Operaterrassen, akut tandläkare, SL-böter,
        kalas-presenter, marathon-anmälan. Inga abstrakta lärobokssituationer
        — situationer eleven faktiskt möter, eller kommer att möta. Varje val
        syns i bokföringen — och i Wellbeing-poängen.
      </p>
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))",
          gap: 14,
        }}
      >
        {events.map((e, i) => (
          <div
            key={i}
            style={{
              background: "#fff",
              border: `1px solid ${theme.rule}`,
              borderRadius: 10,
              padding: 18,
              transition: "all .14s",
            }}
          >
            <div
              style={{
                display: "flex",
                alignItems: "flex-start",
                justifyContent: "space-between",
                marginBottom: 14,
              }}
            >
              <div
                style={{
                  width: 38,
                  height: 38,
                  borderRadius: 7,
                  background: "#fef3c7",
                  color: "#78350f",
                  border: "1px solid rgba(120,53,15,.2)",
                  display: "grid",
                  placeItems: "center",
                  fontFamily: "ui-monospace, monospace",
                  fontWeight: 700,
                  fontSize: 13,
                }}
              >
                {e.symbol}
              </div>
              <span
                style={{
                  fontSize: 10.5,
                  padding: "3px 8px",
                  borderRadius: 100,
                  background: "#f1f5f9",
                  color: "#475569",
                  fontFamily: "ui-monospace, monospace",
                  letterSpacing: 0.5,
                  textTransform: "uppercase",
                }}
              >
                {e.cat}
              </span>
            </div>
            <h4 style={{ fontSize: 15, fontWeight: 600, marginBottom: 4 }}>
              {e.title}
            </h4>
            <div
              style={{
                fontSize: 12.5,
                fontFamily: "ui-monospace, monospace",
                color: theme.accent,
                marginBottom: 10,
              }}
            >
              {e.cost} · {e.wb}
            </div>
            <p
              style={{
                fontSize: 13,
                lineHeight: 1.5,
                color: "#64748b",
                margin: 0,
              }}
            >
              {e.detail}
            </p>
          </div>
        ))}
      </div>

      {/* Social opportunity cost — feature spotlight */}
      <div
        style={{
          marginTop: 56,
          padding: 0,
          background: "#fff",
          border: `1px solid ${theme.rule}`,
          borderRadius: 14,
          overflow: "hidden",
        }}
      >
        <div
          className="vc-lifesim-spotlight"
          style={{
            display: "grid",
            gridTemplateColumns: "1fr 1fr",
            alignItems: "stretch",
          }}
        >
          <style>{`
            @media (max-width: 768px) {
              .vc-lifesim-spotlight { grid-template-columns: 1fr !important; }
            }
          `}</style>
          <div style={{ padding: "36px 36px 36px 40px" }}>
            <div className={theme.eyebrow} style={{ marginBottom: 12 }}>
              Mitt favoritmoment
            </div>
            <h3
              style={{
                fontSize: 24,
                fontWeight: 600,
                letterSpacing: -0.4,
                lineHeight: 1.25,
                marginBottom: 14,
                color: "#0f172a",
                maxWidth: 480,
              }}
            >
              "Att bjuda en kompis" är en av de vanligaste anledningarna till
              att en budget spricker — som vuxen.
            </h3>
            <p
              style={{
                fontSize: 14.5,
                lineHeight: 1.6,
                color: "#475569",
                marginBottom: 18,
                maxWidth: 480,
              }}
            >
              Eleven känner det innan hen är 20. Bjuder hen på middagen denna
              vecka, kan hen inte gå på konserten nästa vecka. Det är opportunity
              cost — fast social, vardaglig, igenkännbar. Och eleven ser det i
              samma vy som saldot.
            </p>
            <ul
              style={{
                listStyle: "none",
                padding: 0,
                margin: 0,
                display: "flex",
                flexDirection: "column",
                gap: 12,
              }}
            >
              <li
                style={{
                  display: "flex",
                  gap: 12,
                  alignItems: "flex-start",
                  fontSize: 14,
                  lineHeight: 1.55,
                  color: "#0f172a",
                }}
              >
                <span
                  style={{
                    color: theme.accent,
                    fontFamily: "ui-monospace, monospace",
                    fontWeight: 700,
                    flexShrink: 0,
                  }}
                >
                  01
                </span>
                <span>
                  <strong>Sociala band sjunker</strong> om eleven nekar
                  konsekvent. "Spara pengar" på bekostnad av kompisar är inte
                  gratis.
                </span>
              </li>
              <li
                style={{
                  display: "flex",
                  gap: 12,
                  alignItems: "flex-start",
                  fontSize: 14,
                  lineHeight: 1.55,
                  color: "#0f172a",
                }}
              >
                <span
                  style={{
                    color: theme.accent,
                    fontFamily: "ui-monospace, monospace",
                    fontWeight: 700,
                    flexShrink: 0,
                  }}
                >
                  02
                </span>
                <span>
                  <strong>Ekonomin spricker</strong> om eleven bjuder på allt
                  utan buffert. Generositet utan ramar blir SMS-lån.
                </span>
              </li>
              <li
                style={{
                  display: "flex",
                  gap: 12,
                  alignItems: "flex-start",
                  fontSize: 14,
                  lineHeight: 1.55,
                  color: "#0f172a",
                }}
              >
                <span
                  style={{
                    color: theme.accent,
                    fontFamily: "ui-monospace, monospace",
                    fontWeight: 700,
                    flexShrink: 0,
                  }}
                >
                  03
                </span>
                <span>
                  <strong>Swish-skulden</strong> blir riktig. En obetald 80-lapp
                  till en klasskompis är en finansiell belastning som minskar
                  handlingsutrymmet på riktigt.
                </span>
              </li>
            </ul>
          </div>

          <div
            style={{
              background: "#0f172a",
              padding: 40,
              display: "grid",
              placeItems: "center",
              position: "relative",
            }}
          >
            <div
              style={{
                width: "100%",
                maxWidth: 320,
                background: "#fff",
                borderRadius: 18,
                padding: 18,
                boxShadow: "0 20px 60px -10px rgba(0,0,0,0.5)",
                fontFamily: '"Inter", system-ui, sans-serif',
              }}
            >
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                  marginBottom: 16,
                }}
              >
                <span
                  style={{
                    fontSize: 11,
                    fontFamily: "ui-monospace, monospace",
                    letterSpacing: 1,
                    color: "#64748b",
                  }}
                >
                  SOCIALA SKULDER
                </span>
                <span style={{ fontSize: 11, color: "#dc4c2b", fontWeight: 600 }}>
                  3 öppna
                </span>
              </div>
              {[
                { name: "Linnea · pizza på fredag", amt: "85 kr", age: "sedan 6 dagar", urgent: true },
                { name: "Adam · biobiljett", amt: "140 kr", age: "sedan 2 veckor", urgent: true },
                { name: "Maja · Spotify-delning", amt: "40 kr", age: "sedan 4 dagar", urgent: false },
              ].map((d, i) => (
                <div
                  key={i}
                  style={{
                    padding: "12px 0",
                    borderBottom: i < 2 ? "1px solid #f1f5f9" : "none",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "space-between",
                    gap: 10,
                  }}
                >
                  <div style={{ minWidth: 0, flex: 1 }}>
                    <div style={{ fontSize: 13.5, fontWeight: 500, color: "#0f172a", marginBottom: 2 }}>
                      {d.name}
                    </div>
                    <div style={{ fontSize: 11.5, color: d.urgent ? "#dc4c2b" : "#64748b" }}>
                      {d.age}
                    </div>
                  </div>
                  <div
                    style={{
                      fontFamily: "ui-monospace, monospace",
                      fontSize: 13,
                      fontWeight: 600,
                      color: "#0f172a",
                      flexShrink: 0,
                    }}
                  >
                    {d.amt}
                  </div>
                </div>
              ))}
              <div
                style={{
                  marginTop: 14,
                  padding: 12,
                  background: "#fef3c7",
                  borderRadius: 8,
                  fontSize: 12.5,
                  lineHeight: 1.45,
                  color: "#78350f",
                }}
              >
                <span style={{ fontWeight: 600 }}>Påverkan på handlingsutrymmet:</span>{" "}
                265 kr fast — det är drygt en bio nästa vecka.
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}

// ---------- EmployerSection (v5) — Linda · IT-konsult, satisfaction + 17 yrken ----------

function EmployerSection({ theme }: { theme: Theme }) {
  const [hoveredP, setHoveredP] = useState(1);

  const professions: Array<{
    sym: string;
    name: string;
    agreement: string;
    short: string;
    alt?: boolean;
  }> = [
    { sym: "Us", name: "Undersköterska", agreement: "HÖK Kommunal", short: "Kommunal" },
    { sym: "Lf", name: "Lärare F-3", agreement: "HÖK Lärarna", short: "SKR" },
    { sym: "It", name: "IT-konsult", agreement: "Tjänstemanna IT", short: "Unionen" },
    { sym: "Sj", name: "Sjuksköterska", agreement: "HÖK Vård", short: "Vårdförb." },
    { sym: "Sn", name: "Snickare", agreement: "Byggavtalet", short: "Byggnads" },
    { sym: "Fr", name: "Frisör", agreement: "Frisöravtalet", short: "Handels", alt: true },
    { sym: "Bm", name: "Bilmekaniker", agreement: "Motorbranschen", short: "IF Metall" },
    { sym: "Bu", name: "Butiksmedarb.", agreement: "Detaljhandelsavt.", short: "Handels" },
    { sym: "El", name: "Elektriker", agreement: "Installationsavt.", short: "Elektrikerna" },
    { sym: "Ea", name: "Ekonomiass.", agreement: "Tjänstemanna", short: "Unionen" },
    { sym: "Pl", name: "Projektledare", agreement: "Tjänstemanna", short: "Unionen" },
    { sym: "Ma", name: "Marknadsass.", agreement: "Tjänstemanna", short: "Unionen" },
    { sym: "Sä", name: "Säljare", agreement: "Tjänstemanna", short: "Unionen" },
    { sym: "Ko", name: "Kock", agreement: "Gröna Riks (HRF)", short: "HRF", alt: true },
    { sym: "Bk", name: "Barnskötare", agreement: "HÖK Kommunal", short: "Kommunal" },
    { sym: "Ba", name: "Barista", agreement: "Gröna Riks (HRF)", short: "HRF", alt: true },
    { sym: "Fö", name: "Förskollärare", agreement: "HÖK Lärarna", short: "Lärarförb." },
  ];

  const events = [
    { ts: "Idag · 14:32", kind: "fråga", delta: "+4", text: "Bra svar på \"Kollegan glömmer pass — täcker du?\"", color: "#10b981" },
    { ts: "I går", kind: "sjuk", delta: "0", text: "Sjukanmälan dag 1 — inom avtalets ram", color: "#64748b" },
    { ts: "mån 18 jan", kind: "fråga", delta: "−3", text: "Vagt svar på \"Hur hanterar du missnöjd kund?\"", color: "#dc4c2b" },
    { ts: "fre 15 jan", kind: "vab", delta: "0", text: "VAB 1 dag (av 60 årligen)", color: "#64748b" },
    { ts: "tis 12 jan", kind: "lärare", delta: "+2", text: "Manuell justering — initiativ på arbetsplatsmöte", color: "#10b981" },
  ];

  const score = 72;
  const curP = professions[hoveredP];

  return (
    <section
      style={{
        padding: "96px 24px",
        borderTop: `1px solid ${theme.rule}`,
        background: "#faf7f2",
      }}
    >
      <NewSectionHeader
        cell={{ sym: "Ag", n: "09", label: "Arbetsgiv." }}
        eyebrow="Arbetsgivar-relationen"
        theme={theme}
      >
        Arbetslivet är inte ett vakuum.
        <br />
        <em style={{ color: theme.accent, fontStyle: "italic" }}>Chefen ser dig.</em>
      </NewSectionHeader>
      <p
        style={{
          maxWidth: 720,
          marginBottom: 48,
          fontSize: 15.5,
          lineHeight: 1.55,
          color: "#475569",
        }}
      >
        Eleven får en faktisk arbetsgivare med en faktisk relation. Sjukdagar,
        VAB, ärlighet i slumpade arbetsplats-frågor — varje val flyttar
        nöjdhetsfaktorn 0–100. Och bakom relationen finns ett kollektivavtal:
        17 yrken får riktiga avtal med riktiga regler.
      </p>

      <div
        className="vc-emp-grid"
        style={{
          display: "grid",
          gridTemplateColumns: "1.05fr 1fr",
          gap: 18,
          marginBottom: 18,
        }}
      >
        <style>{`
          @media (max-width: 900px) {
            .vc-emp-grid { grid-template-columns: 1fr !important; }
            .vc-emp-radial { grid-template-columns: 1fr !important; gap: 18px !important; }
            .vc-emp-detail { grid-template-columns: auto 1fr !important; gap: 18px !important; }
            .vc-emp-detail > div:nth-child(n+3) { grid-column: span 2; }
            .vc-emp-prof-grid { grid-template-columns: repeat(5, 1fr) !important; }
            .vc-emp-influence { grid-template-columns: repeat(2, 1fr) !important; }
          }
          @media (max-width: 540px) {
            .vc-emp-prof-grid { grid-template-columns: repeat(4, 1fr) !important; }
            .vc-emp-influence { grid-template-columns: 1fr !important; }
          }
        `}</style>

        {/* LEFT: Satisfaction dashboard */}
        <div
          style={{
            background: "#fff",
            border: `1px solid ${theme.rule}`,
            borderRadius: 14,
            padding: 28,
            position: "relative",
            overflow: "hidden",
          }}
        >
          <div
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              marginBottom: 22,
              flexWrap: "wrap",
              gap: 8,
            }}
          >
            <div>
              <div className={theme.eyebrow} style={{ marginBottom: 6 }}>
                /arbetsgivare · översikt
              </div>
              <div style={{ fontSize: 18, fontWeight: 600, color: "#0f172a" }}>
                Linda · IT-konsult · Visma
              </div>
              <div
                style={{
                  fontSize: 12.5,
                  color: "#64748b",
                  fontFamily: "ui-monospace, monospace",
                  marginTop: 2,
                }}
              >
                anställd 2024-08-15 · 1 år 5 mån
              </div>
            </div>
            <span
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: 6,
                fontSize: 11,
                padding: "4px 10px",
                borderRadius: 100,
                background: "#dcfce7",
                color: "#166534",
                fontFamily: "ui-monospace, monospace",
                fontWeight: 600,
                letterSpacing: 0.5,
              }}
            >
              <span style={{ width: 5, height: 5, borderRadius: "50%", background: "#16a34a" }} />
              STIGER
            </span>
          </div>

          <div
            className="vc-emp-radial"
            style={{
              display: "grid",
              gridTemplateColumns: "170px 1fr",
              gap: 28,
              alignItems: "center",
              marginBottom: 24,
            }}
          >
            <div style={{ position: "relative", width: 170, height: 170 }}>
              <svg viewBox="0 0 170 170" style={{ position: "absolute", inset: 0 }}>
                <circle cx="85" cy="85" r="72" fill="none" stroke="#f1f5f9" strokeWidth="14" />
                <circle
                  cx="85"
                  cy="85"
                  r="72"
                  fill="none"
                  stroke="#10b981"
                  strokeWidth="14"
                  strokeDasharray={`${(score / 100) * 452.4} 452.4`}
                  strokeLinecap="round"
                  transform="rotate(-90 85 85)"
                />
              </svg>
              <div
                style={{
                  position: "absolute",
                  inset: 0,
                  display: "flex",
                  flexDirection: "column",
                  alignItems: "center",
                  justifyContent: "center",
                }}
              >
                <div
                  style={{
                    fontSize: 44,
                    fontWeight: 700,
                    letterSpacing: -1,
                    color: "#0f172a",
                    fontFamily: "ui-monospace, monospace",
                    lineHeight: 1,
                  }}
                >
                  {score}
                </div>
                <div
                  style={{
                    fontSize: 10,
                    color: "#64748b",
                    fontFamily: "ui-monospace, monospace",
                    letterSpacing: 1,
                    marginTop: 4,
                    textTransform: "uppercase",
                  }}
                >
                  satisfaction
                </div>
              </div>
            </div>

            <div>
              <div
                style={{
                  fontSize: 11,
                  fontFamily: "ui-monospace, monospace",
                  color: "#64748b",
                  letterSpacing: 1,
                  textTransform: "uppercase",
                  marginBottom: 12,
                }}
              >
                Senaste 30 dagar
              </div>
              <svg viewBox="0 0 240 60" style={{ width: "100%", height: 60, display: "block" }}>
                <polyline
                  points="0,38 24,42 48,40 72,46 96,44 120,38 144,32 168,30 192,28 216,24 240,22"
                  fill="none"
                  stroke="#10b981"
                  strokeWidth="2"
                />
                <polyline
                  points="0,38 24,42 48,40 72,46 96,44 120,38 144,32 168,30 192,28 216,24 240,22 240,60 0,60"
                  fill="rgba(16,185,129,0.08)"
                  stroke="none"
                />
                <circle cx="240" cy="22" r="3.5" fill="#10b981" />
              </svg>
              <div
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  marginTop: 12,
                  fontSize: 11,
                  fontFamily: "ui-monospace, monospace",
                  color: "#64748b",
                }}
              >
                <span>62 → 72</span>
                <span style={{ color: "#10b981" }}>+10 över 30d</span>
              </div>
            </div>
          </div>

          <div style={{ borderTop: `1px solid ${theme.rule}`, paddingTop: 18 }}>
            <div
              style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                marginBottom: 12,
              }}
            >
              <span className={theme.eyebrow}>Eventlogg · 5 senaste</span>
              <span
                style={{
                  fontSize: 11,
                  color: "#64748b",
                  fontFamily: "ui-monospace, monospace",
                }}
              >
                visa alla →
              </span>
            </div>
            {events.map((e, i) => (
              <div
                key={i}
                style={{
                  display: "grid",
                  gridTemplateColumns: "auto auto 1fr auto",
                  gap: 14,
                  alignItems: "baseline",
                  padding: "8px 0",
                  borderBottom: i < events.length - 1 ? "1px dashed #e2e8f0" : "none",
                  fontSize: 13,
                  fontFamily: "ui-monospace, monospace",
                }}
              >
                <span style={{ color: "#94a3b8", fontSize: 11, minWidth: 92 }}>
                  {e.ts}
                </span>
                <span
                  style={{
                    fontSize: 10,
                    padding: "2px 7px",
                    borderRadius: 100,
                    background: "#f1f5f9",
                    color: "#475569",
                    textTransform: "uppercase",
                    letterSpacing: 0.5,
                  }}
                >
                  {e.kind}
                </span>
                <span
                  style={{
                    color: "#0f172a",
                    fontFamily: "inherit",
                    fontSize: 13,
                    lineHeight: 1.4,
                  }}
                >
                  {e.text}
                </span>
                <span style={{ color: e.color, fontWeight: 600, fontSize: 13 }}>
                  {e.delta}
                </span>
              </div>
            ))}
          </div>
        </div>

        {/* RIGHT: Workplace question popup */}
        <div
          style={{
            background: "#0f172a",
            borderRadius: 14,
            padding: 28,
            color: "#fff",
            display: "flex",
            flexDirection: "column",
            justifyContent: "space-between",
          }}
        >
          <div>
            <div
              style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                marginBottom: 18,
                flexWrap: "wrap",
                gap: 8,
              }}
            >
              <span
                style={{
                  display: "inline-flex",
                  alignItems: "center",
                  gap: 6,
                  fontSize: 11,
                  padding: "4px 10px",
                  borderRadius: 100,
                  background: "rgba(251,191,36,0.12)",
                  color: "#fbbf24",
                  fontFamily: "ui-monospace, monospace",
                  fontWeight: 600,
                  letterSpacing: 0.5,
                }}
              >
                <span style={{ width: 5, height: 5, borderRadius: "50%", background: "#fbbf24" }} />
                ARBETSPLATS-FRÅGA · TIS 14:30
              </span>
              <span
                style={{
                  fontSize: 11,
                  color: "#64748b",
                  fontFamily: "ui-monospace, monospace",
                }}
              >
                kan skjutas upp 1 ggn
              </span>
            </div>
            <p
              style={{
                fontFamily: theme.serifFont,
                fontSize: 22,
                lineHeight: 1.35,
                color: "#fff",
                fontStyle: "italic",
                margin: "0 0 22px",
                letterSpacing: -0.2,
              }}
            >
              "Din kollega Maria har glömt sitt passerkort hemma och ringer kl
              06.45 — kan du köra och hämta henne? Ert pass startar 07.00."
            </p>
            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              {[
                { label: "Ja, jag kör direkt — vi täcker varandra.", delta: "+4", good: true as boolean | null, ghost: false },
                { label: "Be henne ta taxi och ersätta dig.", delta: "+1", good: null as boolean | null, ghost: false },
                { label: "Säg till chefen att hon är sen — hennes problem.", delta: "−5", good: false as boolean | null, ghost: false },
                { label: "Skjut upp frågan.", delta: "−1", good: false as boolean | null, ghost: true },
              ].map((opt, i) => (
                <div
                  key={i}
                  style={{
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "space-between",
                    padding: "12px 14px",
                    background: opt.ghost ? "transparent" : "rgba(255,255,255,0.04)",
                    border: opt.ghost
                      ? "1px dashed rgba(255,255,255,0.15)"
                      : "1px solid rgba(255,255,255,0.08)",
                    borderRadius: 8,
                    fontSize: 13.5,
                    color: opt.ghost ? "#64748b" : "#e2e8f0",
                  }}
                >
                  <span style={{ paddingRight: 12 }}>{opt.label}</span>
                  <span
                    style={{
                      fontSize: 11.5,
                      fontFamily: "ui-monospace, monospace",
                      fontWeight: 700,
                      color:
                        opt.good === true
                          ? "#10b981"
                          : opt.good === false
                          ? "#dc4c2b"
                          : "#94a3b8",
                      flexShrink: 0,
                    }}
                  >
                    {opt.delta}
                  </span>
                </div>
              ))}
            </div>
          </div>
          <div
            style={{
              marginTop: 20,
              paddingTop: 16,
              borderTop: "1px solid rgba(255,255,255,0.08)",
              fontSize: 12.5,
              color: "#94a3b8",
              lineHeight: 1.55,
              fontStyle: "italic",
              fontFamily: theme.serifFont,
            }}
          >
            Max 1 fråga per dygn. Eleven kan skjuta upp en gång — ignoreras
            frågan helt räknas det som "−1, visat lite engagemang".
          </div>
        </div>
      </div>

      {/* Collective agreements grid */}
      <div
        style={{
          background: "#fff",
          border: `1px solid ${theme.rule}`,
          borderRadius: 14,
          padding: 28,
          marginBottom: 18,
        }}
      >
        <div
          style={{
            display: "flex",
            alignItems: "flex-start",
            justifyContent: "space-between",
            marginBottom: 22,
            flexWrap: "wrap",
            gap: 12,
          }}
        >
          <div>
            <div className={theme.eyebrow} style={{ marginBottom: 8 }}>
              Kollektivavtal · 17 av 17 yrken täckta
            </div>
            <h3
              style={{
                fontSize: 22,
                fontWeight: 600,
                letterSpacing: -0.3,
                margin: "0 0 6px",
                color: "#0f172a",
              }}
            >
              Varje yrke kopplat till sitt avtal — eller markerat "småföretag,
              fri lönesättning".
            </h3>
            <p
              style={{
                fontSize: 13.5,
                color: "#64748b",
                margin: 0,
                maxWidth: 580,
                lineHeight: 1.5,
              }}
            >
              Hovra över ett yrke för att se avtalet. Klick öppnar en ~300-ords
              pedagogisk summary med revisionsökning, semesterdagar,
              sjuklön-trappa och tjänstepension.
            </p>
          </div>
          <span
            style={{
              padding: "6px 12px",
              background: "#fef3c7",
              border: "1px solid rgba(120,53,15,.2)",
              borderRadius: 100,
              fontSize: 11,
              fontFamily: "ui-monospace, monospace",
              color: "#78350f",
              letterSpacing: 0.5,
            }}
          >
            SCB 2024 + 5 % FÖR 2026
          </span>
        </div>

        <div
          className="vc-emp-prof-grid"
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(9, 1fr)",
            gap: 8,
            marginBottom: 22,
          }}
        >
          {professions.map((p, i) => {
            const active = hoveredP === i;
            return (
              <button
                key={i}
                type="button"
                onMouseEnter={() => setHoveredP(i)}
                onClick={() => setHoveredP(i)}
                style={{
                  aspectRatio: "1 / 1",
                  padding: 6,
                  background: active ? "#0f172a" : p.alt ? "#fef3c7" : "#fff",
                  color: active ? "#fbbf24" : p.alt ? "#78350f" : "#0f172a",
                  border: active
                    ? "1px solid #0f172a"
                    : `1px solid ${p.alt ? "rgba(120,53,15,.2)" : "#e2e8f0"}`,
                  borderRadius: 7,
                  cursor: "pointer",
                  transition: "all .12s",
                  fontFamily: "ui-monospace, monospace",
                  display: "flex",
                  flexDirection: "column",
                  justifyContent: "space-between",
                  textAlign: "left",
                }}
              >
                <span style={{ fontSize: 9, opacity: 0.6 }}>
                  {String(i + 1).padStart(2, "0")}
                </span>
                <span style={{ fontSize: 16, fontWeight: 700, letterSpacing: -0.3, lineHeight: 1 }}>
                  {p.sym}
                </span>
                <span
                  style={{
                    fontSize: 8,
                    opacity: 0.65,
                    letterSpacing: 0.3,
                    textTransform: "uppercase",
                    lineHeight: 1.1,
                  }}
                >
                  {p.short}
                </span>
              </button>
            );
          })}
        </div>

        <div
          className="vc-emp-detail"
          style={{
            background: "#0f172a",
            color: "#fff",
            borderRadius: 10,
            padding: "20px 24px",
            display: "grid",
            gridTemplateColumns: "auto 1fr auto auto auto",
            gap: 28,
            alignItems: "center",
          }}
        >
          <div
            style={{
              width: 52,
              height: 52,
              borderRadius: 8,
              background: "#fbbf24",
              color: "#0f172a",
              display: "grid",
              placeItems: "center",
              fontFamily: "ui-monospace, monospace",
              fontWeight: 700,
              fontSize: 18,
            }}
          >
            {curP.sym}
          </div>
          <div>
            <div
              style={{
                fontSize: 11,
                fontFamily: "ui-monospace, monospace",
                color: "#94a3b8",
                letterSpacing: 1,
                marginBottom: 4,
              }}
            >
              YRKE
            </div>
            <div style={{ fontSize: 16, fontWeight: 600 }}>{curP.name}</div>
          </div>
          <div>
            <div
              style={{
                fontSize: 11,
                fontFamily: "ui-monospace, monospace",
                color: "#94a3b8",
                letterSpacing: 1,
                marginBottom: 4,
              }}
            >
              AVTAL
            </div>
            <div style={{ fontSize: 14, fontFamily: "ui-monospace, monospace", color: "#fff" }}>
              {curP.agreement}
            </div>
          </div>
          <div>
            <div
              style={{
                fontSize: 11,
                fontFamily: "ui-monospace, monospace",
                color: "#94a3b8",
                letterSpacing: 1,
                marginBottom: 4,
              }}
            >
              REVISION 2026
            </div>
            <div
              style={{
                fontSize: 14,
                fontFamily: "ui-monospace, monospace",
                color: "#10b981",
                fontWeight: 600,
              }}
            >
              {curP.alt ? "fri sättning" : "+ 2,5 %"}
            </div>
          </div>
          <div>
            <div
              style={{
                fontSize: 11,
                fontFamily: "ui-monospace, monospace",
                color: "#94a3b8",
                letterSpacing: 1,
                marginBottom: 4,
              }}
            >
              TJÄNSTEPENSION
            </div>
            <div style={{ fontSize: 14, fontFamily: "ui-monospace, monospace", color: "#fff" }}>
              {curP.alt ? "lagstadgat golv" : "ITP1 · 4,5 %"}
            </div>
          </div>
        </div>
      </div>

      {/* Influence sources */}
      <div
        className="vc-emp-influence"
        style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 14 }}
      >
        {[
          {
            title: "Sjukanmälan dag 8+",
            delta: "−5",
            tone: "neg",
            note: "Utan läkarintyg — avtal kräver det",
          },
          {
            title: "VAB ≤ 60 dagar/år",
            delta: "0",
            tone: "neutral",
            note: "Lagstadgad rätt — ingen påverkan",
          },
          {
            title: "Bra svar på fråga",
            delta: "+2 till +5",
            tone: "pos",
            note: "Visar engagemang och omdöme",
          },
          {
            title: "För sen ankomst",
            delta: "−2",
            tone: "neg",
            note: "Slumpas — chefen noterar",
          },
        ].map((src, i) => (
          <div
            key={i}
            style={{
              background: "#fff",
              border: `1px solid ${theme.rule}`,
              borderRadius: 10,
              padding: 18,
            }}
          >
            <div
              style={{
                fontSize: 18,
                fontFamily: "ui-monospace, monospace",
                fontWeight: 700,
                marginBottom: 6,
                color:
                  src.tone === "pos"
                    ? "#10b981"
                    : src.tone === "neg"
                    ? "#dc4c2b"
                    : "#64748b",
              }}
            >
              {src.delta}
            </div>
            <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 4, color: "#0f172a" }}>
              {src.title}
            </div>
            <div style={{ fontSize: 12.5, color: "#64748b", lineHeight: 1.45 }}>
              {src.note}
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}

// ---------- SalaryTalkSection (v5) — 5-rond förhandling + Marias faktagrund ----------

function SalaryTalkSection({ theme }: { theme: Theme }) {
  const [round, setRound] = useState(2);

  const rounds: Array<{
    no: number;
    student: string;
    employer: string;
    pct: string;
    kr: string;
    highlight?: boolean;
    future?: boolean;
  }> = [
    {
      no: 1,
      student:
        '"Jag vill diskutera min lön. Jag har varit här i 1,5 år och tagit på mig leadrollen för Acme-projektet utan tillägg."',
      employer:
        "Tack för att du tar upp det. Berätta — vad har du i tankarna konkret? Och vad bygger du det på?",
      pct: "2,5 %",
      kr: "+ 925 kr",
    },
    {
      no: 2,
      student:
        '"Marknadslönen för min roll ligger på 39 500 kr enligt Akavia 2026. Jag ligger 1 500 kr under. Jag vill upp till 39 500 kr — det är 4,5 %."',
      employer:
        "Marknadsdata är ett bra argument. Akaviaa siffran stämmer för seniora konsulter — du är på väg dit. Avtalet ger 2,5 %, jag kan sträcka mig till 3,2 % i år och titta igen i juli.",
      pct: "3,2 %",
      kr: "+ 1 184 kr",
      highlight: true,
    },
    {
      no: 3,
      student:
        '"Jag uppskattar det. Men leadrollen var inget jag valde — jag hoppade in när Erik slutade. Det är ett skäl för 4 %."',
      employer:
        "Det stämmer, och du gjorde det bra. Jag kan gå upp till 3,5 %. Mer än så kräver att vi formaliserar leadrollen — det gör vi i juli.",
      pct: "3,5 %",
      kr: "+ 1 295 kr",
    },
    { no: 4, student: "…", employer: "…", pct: "—", kr: "—", future: true },
    { no: 5, student: "…", employer: "…", pct: "—", kr: "—", future: true },
  ];

  const curR = rounds[round - 1];

  return (
    <section
      style={{
        padding: "96px 24px",
        borderTop: `1px solid ${theme.rule}`,
        background: "#0f172a",
        color: "#fff",
      }}
    >
      <NewSectionHeader
        cell={{ sym: "Ls", n: "10", label: "Lönesamtal" }}
        eyebrow="Det enda samtalet på året"
        theme={theme}
        dark
      >
        Förhandling är inte konflikt.
        <br />
        Det är samtalet som{" "}
        <em style={{ color: "#fbbf24", fontStyle: "italic" }}>flyttar din lön.</em>
      </NewSectionHeader>
      <p
        style={{
          maxWidth: 720,
          marginBottom: 48,
          fontSize: 15.5,
          lineHeight: 1.55,
          color: "#94a3b8",
        }}
      >
        En gång om året möter eleven Maria — HR-chef, AI-driven, känner
        kollektivavtalet, elevens nöjdhetsfaktor och lönehistorik. Fem ronder.
        Eleven argumenterar, Maria svarar balanserat. Slutbudet jämförs mot
        avtalets revisionsutrymme. Och syns i{" "}
        <em style={{ color: "#fff", fontStyle: "normal", fontWeight: 500 }}>
          nästa månads
        </em>{" "}
        lönespec — inte direkt.
      </p>

      <div
        style={{
          background: "rgba(255,255,255,0.03)",
          border: "1px solid rgba(255,255,255,0.08)",
          borderRadius: 14,
          padding: "20px 24px",
          marginBottom: 18,
        }}
      >
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            marginBottom: 14,
            flexWrap: "wrap",
            gap: 8,
          }}
        >
          <span
            style={{
              fontSize: 11,
              fontFamily: "ui-monospace, monospace",
              letterSpacing: 1.2,
              color: "#fbbf24",
              textTransform: "uppercase",
            }}
          >
            Lönesamtalet 2026 · 5 ronder
          </span>
          <span
            style={{
              fontSize: 11,
              fontFamily: "ui-monospace, monospace",
              color: "#64748b",
            }}
          >
            modell: claude-haiku-4-5 · kostnad/session ≈ $0.015
          </span>
        </div>
        <div
          className="vc-salary-rounds"
          style={{ display: "grid", gridTemplateColumns: "repeat(5, 1fr)", gap: 8 }}
        >
          <style>{`
            @media (max-width: 768px) {
              .vc-salary-rounds { grid-template-columns: repeat(2, 1fr) !important; }
              .vc-salary-conv { grid-template-columns: 1fr !important; }
              .vc-salary-outcome { grid-template-columns: 1fr !important; gap: 18px !important; text-align: center; }
            }
          `}</style>
          {rounds.map((r, i) => {
            const active = round === r.no;
            const past = round > r.no;
            return (
              <button
                key={i}
                type="button"
                onClick={() => !r.future && setRound(r.no)}
                style={{
                  textAlign: "left",
                  padding: 14,
                  cursor: r.future ? "default" : "pointer",
                  background: active
                    ? "rgba(251,191,36,0.12)"
                    : past
                    ? "rgba(255,255,255,0.05)"
                    : "transparent",
                  border: active
                    ? "2px solid #fbbf24"
                    : past
                    ? "1px solid rgba(255,255,255,0.1)"
                    : "1px dashed rgba(255,255,255,0.08)",
                  borderRadius: 10,
                  transition: "all .15s",
                  opacity: r.future ? 0.5 : 1,
                  fontFamily: "inherit",
                  color: "#fff",
                }}
              >
                <div
                  style={{
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "space-between",
                    marginBottom: 6,
                  }}
                >
                  <span
                    style={{
                      fontSize: 10.5,
                      fontFamily: "ui-monospace, monospace",
                      color: active ? "#fbbf24" : "#64748b",
                      letterSpacing: 1,
                      fontWeight: 600,
                    }}
                  >
                    ROND {String(r.no).padStart(2, "0")}
                  </span>
                  {past && !active && (
                    <span style={{ color: "#10b981", fontSize: 11 }}>✓</span>
                  )}
                </div>
                <div
                  style={{
                    fontSize: 18,
                    fontWeight: 700,
                    fontFamily: "ui-monospace, monospace",
                    color: r.future ? "#475569" : "#fff",
                    letterSpacing: -0.3,
                  }}
                >
                  {r.pct}
                </div>
                <div
                  style={{
                    fontSize: 11,
                    fontFamily: "ui-monospace, monospace",
                    color: r.future ? "#475569" : "#94a3b8",
                    marginTop: 2,
                  }}
                >
                  {r.kr}
                </div>
              </button>
            );
          })}
        </div>
      </div>

      <div
        className="vc-salary-conv"
        style={{
          display: "grid",
          gridTemplateColumns: "1.4fr 1fr",
          gap: 18,
          marginBottom: 18,
        }}
      >
        {/* Conversation */}
        <div
          style={{
            background: "rgba(255,255,255,0.03)",
            border: "1px solid rgba(255,255,255,0.08)",
            borderRadius: 14,
            padding: 28,
          }}
        >
          <div style={{ marginBottom: 22 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 10 }}>
              <div
                style={{
                  width: 32,
                  height: 32,
                  borderRadius: "50%",
                  background: "#dc4c2b",
                  color: "#fff",
                  display: "grid",
                  placeItems: "center",
                  fontFamily: "ui-monospace, monospace",
                  fontSize: 12,
                  fontWeight: 700,
                }}
              >
                L
              </div>
              <div>
                <div style={{ fontSize: 13, fontWeight: 600, color: "#fff" }}>
                  Linda · IT-konsult
                </div>
                <div
                  style={{
                    fontSize: 10.5,
                    fontFamily: "ui-monospace, monospace",
                    color: "#64748b",
                    letterSpacing: 0.5,
                  }}
                >
                  ROND {String(curR.no).padStart(2, "0")} · DU
                </div>
              </div>
            </div>
            <p
              style={{
                fontFamily: theme.serifFont,
                fontSize: 17,
                lineHeight: 1.5,
                color: curR.future ? "#475569" : "#fbbf24",
                fontStyle: "italic",
                margin: 0,
                paddingLeft: 42,
              }}
            >
              {curR.student}
            </p>
          </div>

          <div>
            <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 10 }}>
              <div
                style={{
                  width: 32,
                  height: 32,
                  borderRadius: "50%",
                  background: "rgba(251,191,36,0.15)",
                  color: "#fbbf24",
                  display: "grid",
                  placeItems: "center",
                  fontFamily: "ui-monospace, monospace",
                  fontSize: 12,
                  fontWeight: 700,
                  border: "1px solid rgba(251,191,36,0.3)",
                }}
              >
                M
              </div>
              <div>
                <div style={{ fontSize: 13, fontWeight: 600, color: "#fff" }}>
                  Maria · HR-chef, Visma
                </div>
                <div
                  style={{
                    fontSize: 10.5,
                    fontFamily: "ui-monospace, monospace",
                    color: "#64748b",
                    letterSpacing: 0.5,
                  }}
                >
                  AI-PERSONA · CLAUDE HAIKU 4.5
                </div>
              </div>
            </div>
            <p
              style={{
                fontFamily: theme.serifFont,
                fontSize: 17,
                lineHeight: 1.55,
                color: curR.future ? "#475569" : "#e2e8f0",
                margin: 0,
                paddingLeft: 42,
              }}
            >
              {curR.future ? (
                <span style={{ fontStyle: "italic" }}>Maria väntar på ditt svar…</span>
              ) : (
                <>
                  <span
                    style={{
                      color: "#dc4c2b",
                      fontFamily: "ui-monospace, monospace",
                      fontSize: 11,
                      marginRight: 8,
                    }}
                  >
                    AI →
                  </span>
                  {curR.employer}
                </>
              )}
            </p>

            {!curR.future && (
              <div
                style={{
                  marginTop: 18,
                  marginLeft: 42,
                  display: "inline-flex",
                  alignItems: "center",
                  gap: 8,
                  padding: "6px 12px",
                  background: curR.highlight
                    ? "rgba(251,191,36,0.12)"
                    : "rgba(255,255,255,0.05)",
                  border: `1px solid ${
                    curR.highlight ? "rgba(251,191,36,0.3)" : "rgba(255,255,255,0.1)"
                  }`,
                  borderRadius: 8,
                  fontSize: 12,
                  fontFamily: "ui-monospace, monospace",
                  color: curR.highlight ? "#fbbf24" : "#94a3b8",
                }}
              >
                <span>NUVARANDE BUD:</span>
                <strong style={{ color: "#fff" }}>{curR.pct}</strong>
                <span style={{ color: "#94a3b8" }}>·</span>
                <span>{curR.kr}/mån</span>
              </div>
            )}
          </div>
        </div>

        {/* Marias faktagrund */}
        <div
          style={{
            background: "#fbbf24",
            color: "#78350f",
            borderRadius: 14,
            padding: 24,
            display: "flex",
            flexDirection: "column",
            justifyContent: "space-between",
          }}
        >
          <div>
            <div
              style={{
                fontSize: 11,
                fontFamily: "ui-monospace, monospace",
                letterSpacing: 1.2,
                textTransform: "uppercase",
                marginBottom: 14,
                color: "#92400e",
                display: "flex",
                alignItems: "center",
                gap: 8,
              }}
            >
              <span style={{ width: 6, height: 6, background: "#92400e", borderRadius: "50%" }} />
              Marias faktagrund
              <span style={{ marginLeft: "auto", fontSize: 10, opacity: 0.7 }}>
                cachad i system-prompt
              </span>
            </div>
            <h4
              style={{
                fontSize: 16,
                fontWeight: 700,
                margin: "0 0 18px",
                color: "#0f172a",
                fontFamily: theme.serifFont,
                fontStyle: "italic",
              }}
            >
              "Eleven ser inte detta. Maria balanserar avtal, satisfaction och
              budget — utgår från det här."
            </h4>
            <ul
              style={{
                listStyle: "none",
                padding: 0,
                margin: 0,
                fontSize: 13,
                lineHeight: 1.85,
                fontFamily: "ui-monospace, monospace",
              }}
            >
              <li>Aktuell lön: <strong>37 000 kr/mån</strong></li>
              <li>Anställd: <strong>1 år 5 mån</strong></li>
              <li>Avtal: Tjänstemanna IT</li>
              <li>Revisionsutrymme: <strong>2,5 %</strong></li>
              <li>Satisfaction: <strong>72 / 100 ↗</strong></li>
              <li
                style={{
                  paddingTop: 6,
                  marginTop: 6,
                  borderTop: "1px dashed rgba(120,53,15,.3)",
                }}
              >
                Förhandlingsutrymme:{" "}
                <strong style={{ color: "#0f172a" }}>+2,5 % till +4,0 %</strong>
              </li>
              <li style={{ fontStyle: "italic", color: "#92400e" }}>
                (hög satisf. = +1,5 pp över norm)
              </li>
            </ul>
          </div>
          <div
            style={{
              marginTop: 18,
              paddingTop: 14,
              borderTop: "1px dashed rgba(120,53,15,.3)",
              fontSize: 12,
              lineHeight: 1.55,
              fontStyle: "italic",
              fontFamily: theme.serifFont,
            }}
          >
            Marias principer: bemöter argument, inte personen. Säger aldrig vad
            avtalet ger — eleven måste själv hänvisa.
          </div>
        </div>
      </div>

      {/* Outcome strip */}
      <div
        className="vc-salary-outcome"
        style={{
          background: "rgba(16,185,129,0.06)",
          border: "1px solid rgba(16,185,129,0.25)",
          borderRadius: 14,
          padding: "24px 28px",
          display: "grid",
          gridTemplateColumns: "auto 1fr auto",
          gap: 28,
          alignItems: "center",
        }}
      >
        <div
          style={{
            width: 56,
            height: 56,
            borderRadius: 12,
            background: "rgba(16,185,129,0.15)",
            border: "1px solid rgba(16,185,129,0.3)",
            display: "grid",
            placeItems: "center",
            fontFamily: "ui-monospace, monospace",
            fontSize: 22,
            color: "#10b981",
            fontWeight: 700,
          }}
        >
          ↑
        </div>
        <div>
          <div
            style={{
              fontSize: 11,
              fontFamily: "ui-monospace, monospace",
              letterSpacing: 1.2,
              color: "#10b981",
              textTransform: "uppercase",
              marginBottom: 6,
            }}
          >
            ● Resultat · 3,5 % över avtalets 2,5 %
          </div>
          <h3
            style={{
              fontSize: 22,
              fontWeight: 600,
              letterSpacing: -0.3,
              margin: "0 0 8px",
              color: "#fff",
            }}
          >
            Ny lön 38 295 kr — gäller från{" "}
            <em style={{ color: "#fbbf24", fontStyle: "italic" }}>1 maj 2026.</em>
          </h3>
          <p
            style={{
              fontSize: 13.5,
              color: "#cbd5e1",
              margin: 0,
              lineHeight: 1.55,
              maxWidth: 640,
            }}
          >
            Lönehöjningen verkar nästa månad. Mellan idag och första nya
            utbetalning visar /arbetsgivare-översikten "Ny lön (gäller från
            2026-05-01)" — pedagogiskt synkat med verkligheten där samtalet
            sker i januari men utbetalningen kommer i februari.
          </p>
        </div>
        <div
          style={{
            fontFamily: "ui-monospace, monospace",
            fontSize: 13,
            lineHeight: 1.7,
            color: "#e2e8f0",
            background: "rgba(0,0,0,0.3)",
            border: "1px solid rgba(255,255,255,0.1)",
            borderRadius: 10,
            padding: "14px 18px",
            minWidth: 200,
          }}
        >
          <div style={{ color: "#64748b", fontSize: 10.5, letterSpacing: 1, marginBottom: 4 }}>
            FÖRE → EFTER
          </div>
          <div>
            37 000 → <strong style={{ color: "#10b981" }}>38 295</strong>
          </div>
          <div style={{ color: "#94a3b8" }}>+ 1 295 kr/mån</div>
        </div>
      </div>
    </section>
  );
}

// ---------- BankSection (v5) — flow + EkonomilabbetID + EkonomiSkalan + konsekvenskedja ----------

function BankSection({ theme }: { theme: Theme }) {
  const [bScore, setBScore] = useState(680);

  return (
    <section
      style={{
        padding: "96px 24px",
        borderTop: `1px solid ${theme.rule}`,
        background: "#fafaf9",
      }}
    >
      <NewSectionHeader
        cell={{ sym: "Bk", n: "11", label: "Banken" }}
        eyebrow="Banken som ett eget rum"
        theme={theme}
      >
        Pengar flyttas inte i en budget-app.
        <br />
        De flyttas i{" "}
        <em style={{ color: theme.accent, fontStyle: "italic" }}>banken.</em>
      </NewSectionHeader>
      <p
        style={{
          maxWidth: 760,
          marginBottom: 48,
          fontSize: 15.5,
          lineHeight: 1.55,
          color: "#475569",
        }}
      >
        Banken är inte redovisningssystemet. I verkligheten laddar du ner ett
        kontoutdrag från banken, sparar PDF:en, och importerar sedan till
        bokföringen. Vi simulerar precis det flödet — med EkonomilabbetID,
        signering av kommande betalningar, saldokontroll och konsekvenser som
        syns i EkonomiSkalan.
      </p>

      {/* Flödesschemat */}
      <div
        style={{
          background: "#fff",
          border: `1px solid ${theme.rule}`,
          borderRadius: 14,
          padding: "28px 32px",
          marginBottom: 18,
        }}
      >
        <div className={theme.eyebrow} style={{ marginBottom: 18 }}>
          Det stora flödesschemat · tre platser, en kedja
        </div>
        <style>{`
          @media (max-width: 768px) {
            .vc-bank-flow { grid-template-columns: 1fr !important; }
            .vc-bank-flow > div:nth-child(2),
            .vc-bank-flow > div:nth-child(4) {
              transform: rotate(90deg);
              margin: 0 auto;
            }
            .vc-bank-features { grid-template-columns: 1fr !important; }
            .vc-bank-cqgrid { grid-template-columns: repeat(2, 1fr) !important; }
          }
          @media (max-width: 540px) {
            .vc-bank-cqgrid { grid-template-columns: 1fr !important; }
          }
        `}</style>
        <div
          className="vc-bank-flow"
          style={{
            display: "grid",
            gridTemplateColumns: "1fr auto 1fr auto 1fr",
            gap: 18,
            alignItems: "stretch",
          }}
        >
          <div style={{ background: "#0f172a", color: "#fff", borderRadius: 12, padding: 22 }}>
            <div
              style={{
                fontSize: 11,
                fontFamily: "ui-monospace, monospace",
                letterSpacing: 1,
                color: "#fbbf24",
                marginBottom: 12,
                textTransform: "uppercase",
              }}
            >
              ● /bank
            </div>
            <h4 style={{ fontSize: 17, fontWeight: 600, margin: "0 0 12px", color: "#fff" }}>
              Banken genererar
            </h4>
            <ul
              style={{
                listStyle: "none",
                padding: 0,
                margin: 0,
                fontSize: 12.5,
                lineHeight: 1.85,
                color: "#cbd5e1",
                fontFamily: "ui-monospace, monospace",
              }}
            >
              <li>· Kontoutdrag (PDF)</li>
              <li>· Kreditkortsfaktura</li>
              <li>· Lånebesked</li>
              <li>· Påminnelser</li>
            </ul>
          </div>

          <div style={{ display: "flex", alignItems: "center", justifyContent: "center", minWidth: 64 }}>
            <div style={{ textAlign: "center" }}>
              <svg width="40" height="40" viewBox="0 0 40 40" fill="none">
                <path
                  d="M8 20 H32 M26 14 L32 20 L26 26"
                  stroke="#0f172a"
                  strokeWidth="1.6"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              </svg>
              <div
                style={{
                  fontSize: 9.5,
                  fontFamily: "ui-monospace, monospace",
                  color: "#64748b",
                  letterSpacing: 0.8,
                  marginTop: 4,
                }}
              >
                EXPORTERA
              </div>
            </div>
          </div>

          <div
            style={{
              background: "#fef3c7",
              borderRadius: 12,
              padding: 22,
              border: "1px solid rgba(120,53,15,.2)",
            }}
          >
            <div
              style={{
                fontSize: 11,
                fontFamily: "ui-monospace, monospace",
                letterSpacing: 1,
                color: "#92400e",
                marginBottom: 12,
                textTransform: "uppercase",
              }}
            >
              ● /my-batches
            </div>
            <h4 style={{ fontSize: 17, fontWeight: 600, margin: "0 0 12px", color: "#0f172a" }}>
              Mellanlager
            </h4>
            <p
              style={{
                fontSize: 12.5,
                lineHeight: 1.55,
                color: "#78350f",
                margin: 0,
                fontFamily: "ui-monospace, monospace",
              }}
            >
              Eleven förhandsgranskar PDF:en innan import. Lönespec hör inte
              hit — den landar på /arbetsgivare.
            </p>
          </div>

          <div style={{ display: "flex", alignItems: "center", justifyContent: "center", minWidth: 64 }}>
            <div style={{ textAlign: "center" }}>
              <svg width="40" height="40" viewBox="0 0 40 40" fill="none">
                <path
                  d="M8 20 H32 M26 14 L32 20 L26 26"
                  stroke="#0f172a"
                  strokeWidth="1.6"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              </svg>
              <div
                style={{
                  fontSize: 9.5,
                  fontFamily: "ui-monospace, monospace",
                  color: "#64748b",
                  letterSpacing: 0.8,
                  marginTop: 4,
                }}
              >
                IMPORTERA
              </div>
            </div>
          </div>

          <div
            style={{
              background: "#fff",
              border: `1px solid ${theme.rule}`,
              borderRadius: 12,
              padding: 22,
            }}
          >
            <div
              style={{
                fontSize: 11,
                fontFamily: "ui-monospace, monospace",
                letterSpacing: 1,
                color: theme.accent,
                marginBottom: 12,
                textTransform: "uppercase",
              }}
            >
              ● /transactions
            </div>
            <h4 style={{ fontSize: 17, fontWeight: 600, margin: "0 0 12px", color: "#0f172a" }}>
              Bokföringen
            </h4>
            <ul
              style={{
                listStyle: "none",
                padding: 0,
                margin: 0,
                fontSize: 12.5,
                lineHeight: 1.85,
                color: "#475569",
                fontFamily: "ui-monospace, monospace",
              }}
            >
              <li>· Huvudbok</li>
              <li>· Kontoplan</li>
              <li>· Balansräkning</li>
              <li>· Avstämning</li>
            </ul>
          </div>
        </div>
      </div>

      {/* 3 feature-kort */}
      <div
        className="vc-bank-features"
        style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 14, marginBottom: 18 }}
      >
        {/* EkonomilabbetID */}
        <div
          style={{
            background: "#0f172a",
            color: "#fff",
            borderRadius: 14,
            padding: 24,
            display: "flex",
            flexDirection: "column",
          }}
        >
          <div
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              marginBottom: 16,
              flexWrap: "wrap",
              gap: 6,
            }}
          >
            <span
              style={{
                fontSize: 11,
                fontFamily: "ui-monospace, monospace",
                letterSpacing: 1.2,
                color: "#fbbf24",
                textTransform: "uppercase",
              }}
            >
              EkonomilabbetID-flödet
            </span>
            <span
              style={{
                fontSize: 10.5,
                fontFamily: "ui-monospace, monospace",
                color: "#64748b",
              }}
            >
              session 14:32 → exp. 14:47
            </span>
          </div>
          <h4 style={{ fontSize: 18, fontWeight: 600, margin: "0 0 16px", color: "#fff" }}>
            QR på desktop, PIN på mobil.
          </h4>

          <div
            style={{
              background: "#fff",
              borderRadius: 10,
              padding: 14,
              marginBottom: 14,
              position: "relative",
              display: "grid",
              gridTemplateColumns: "1fr 1fr",
              gap: 12,
              alignItems: "center",
            }}
          >
            <div
              style={{
                width: "100%",
                aspectRatio: "1 / 1",
                background: "#fff",
                backgroundImage:
                  "radial-gradient(#0f172a 35%, transparent 36%), radial-gradient(#0f172a 35%, transparent 36%)",
                backgroundSize: "12px 12px, 12px 12px",
                backgroundPosition: "0 0, 6px 6px",
                border: "6px solid #fff",
                boxShadow: "0 0 0 1px #cbd5e1",
                borderRadius: 4,
                position: "relative",
              }}
            >
              <div
                style={{
                  position: "absolute",
                  inset: "40% 40%",
                  background: "#fbbf24",
                  border: "2px solid #0f172a",
                  borderRadius: 4,
                }}
              />
            </div>
            <div
              style={{
                fontSize: 11,
                fontFamily: "ui-monospace, monospace",
                color: "#0f172a",
                lineHeight: 1.6,
              }}
            >
              <div style={{ color: "#64748b", marginBottom: 4 }}>SCANNA</div>
              <div>Eklabb-app</div>
              <div style={{ marginTop: 8, color: "#10b981" }}>● väntar på telefon</div>
            </div>
          </div>

          <div
            style={{
              fontSize: 12.5,
              lineHeight: 1.55,
              color: "#94a3b8",
              fontStyle: "italic",
              fontFamily: theme.serifFont,
              marginTop: "auto",
            }}
          >
            "Något du har" (telefon) + "något du vet" (4-siffrig PIN).
            Pedagogiskt speglar vi den riktiga säkerhetslogiken — minus
            produktionssäkerheten.
          </div>
        </div>

        {/* Scheduled payments */}
        <div
          style={{
            background: "#fff",
            border: `1px solid ${theme.rule}`,
            borderRadius: 14,
            padding: 24,
          }}
        >
          <div
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              marginBottom: 16,
            }}
          >
            <span className={theme.eyebrow}>Signera kommande</span>
            <span
              style={{
                fontSize: 10.5,
                padding: "3px 8px",
                borderRadius: 100,
                background: "#fef3c7",
                color: "#78350f",
                fontFamily: "ui-monospace, monospace",
                letterSpacing: 0.5,
              }}
            >
              3 OBETALDA
            </span>
          </div>
          <h4 style={{ fontSize: 18, fontWeight: 600, margin: "0 0 18px", color: "#0f172a" }}>
            Saldokontroll vid signering.
          </h4>

          <div style={{ display: "flex", flexDirection: "column", gap: 8, marginBottom: 14 }}>
            {[
              { name: "Hyran · Stockholmshem", amt: "8 500 kr", due: "fredag · 1 feb", ok: true },
              { name: "El · Vattenfall", amt: "690 kr", due: "mån · 4 feb", ok: true },
              { name: "Tre · mobil", amt: "299 kr", due: "tor · 7 feb", ok: false },
            ].map((p, i) => (
              <div
                key={i}
                style={{
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                  padding: "10px 12px",
                  background: "#fafaf9",
                  border: `1px solid ${theme.rule}`,
                  borderRadius: 8,
                }}
              >
                <div style={{ minWidth: 0, flex: 1 }}>
                  <div style={{ fontSize: 13, fontWeight: 500, color: "#0f172a", marginBottom: 2 }}>
                    {p.name}
                  </div>
                  <div
                    style={{
                      fontSize: 11,
                      color: "#64748b",
                      fontFamily: "ui-monospace, monospace",
                    }}
                  >
                    {p.due}
                  </div>
                </div>
                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <span
                    style={{
                      fontSize: 13,
                      fontFamily: "ui-monospace, monospace",
                      fontWeight: 600,
                      color: "#0f172a",
                    }}
                  >
                    {p.amt}
                  </span>
                  <span
                    style={{
                      width: 14,
                      height: 14,
                      borderRadius: 4,
                      border: "1.5px solid",
                      borderColor: p.ok ? "#10b981" : "#cbd5e1",
                      background: p.ok ? "#10b981" : "#fff",
                      display: "grid",
                      placeItems: "center",
                      fontSize: 9,
                      color: "#fff",
                    }}
                  >
                    {p.ok ? "✓" : ""}
                  </span>
                </div>
              </div>
            ))}
          </div>

          <div
            style={{
              background: "rgba(220,76,43,0.06)",
              border: "1px solid rgba(220,76,43,0.2)",
              borderRadius: 8,
              padding: "10px 12px",
              marginBottom: 14,
              fontSize: 12,
              color: "#7f1d1d",
              lineHeight: 1.5,
            }}
          >
            <strong>OBS — du har 800 kr kvar efter dessa.</strong> Om något
            oväntat händer innan 7 feb kan signeringen failas.
          </div>

          <button
            type="button"
            style={{
              width: "100%",
              padding: "11px 14px",
              borderRadius: 8,
              background: "#0f172a",
              color: "#fff",
              border: "none",
              cursor: "pointer",
              fontSize: 13.5,
              fontWeight: 500,
              fontFamily: "inherit",
            }}
          >
            Signera 2 markerade · EklabbID →
          </button>
        </div>

        {/* EkonomiSkalan */}
        <div
          style={{
            background: "linear-gradient(180deg, #fff 0%, #fef3c7 100%)",
            border: `1px solid ${theme.rule}`,
            borderRadius: 14,
            padding: 24,
          }}
        >
          <div
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              marginBottom: 16,
            }}
          >
            <span className={theme.eyebrow}>EkonomiSkalan</span>
            <span
              style={{
                fontSize: 10.5,
                padding: "3px 8px",
                borderRadius: 100,
                background: "#fff",
                color: "#475569",
                border: "1px solid #cbd5e1",
                fontFamily: "ui-monospace, monospace",
                letterSpacing: 0.5,
              }}
            >
              300–850
            </span>
          </div>
          <h4 style={{ fontSize: 18, fontWeight: 600, margin: "0 0 14px", color: "#0f172a" }}>
            Betyg som rör sig med vanorna.
          </h4>

          <div style={{ position: "relative", marginBottom: 14 }}>
            <svg viewBox="0 0 240 130" style={{ width: "100%", display: "block" }}>
              <defs>
                <linearGradient id="vc-ek-scale" x1="0" y1="0" x2="1" y2="0">
                  <stop offset="0%" stopColor="#dc4c2b" />
                  <stop offset="40%" stopColor="#fbbf24" />
                  <stop offset="100%" stopColor="#10b981" />
                </linearGradient>
              </defs>
              <path
                d="M 30 110 A 90 90 0 0 1 210 110"
                fill="none"
                stroke="#f1f5f9"
                strokeWidth="14"
                strokeLinecap="round"
              />
              <path
                d="M 30 110 A 90 90 0 0 1 210 110"
                fill="none"
                stroke="url(#vc-ek-scale)"
                strokeWidth="14"
                strokeLinecap="round"
                strokeDasharray={`${((bScore - 300) / 550) * 282} 282`}
              />
              <text
                x="120"
                y="92"
                textAnchor="middle"
                fontSize="36"
                fontWeight="700"
                fill="#0f172a"
                fontFamily="ui-monospace, monospace"
              >
                {bScore}
              </text>
              <text
                x="120"
                y="112"
                textAnchor="middle"
                fontSize="10"
                fill="#64748b"
                fontFamily="ui-monospace, monospace"
                letterSpacing="1.5"
              >
                GRAD B+
              </text>
            </svg>
          </div>

          <div style={{ display: "flex", flexDirection: "column", gap: 6, marginBottom: 14 }}>
            {[
              { label: "Inga sena betalningar", sign: "+", val: "32", color: "#10b981" },
              { label: "Buffert: 1,5 mån", sign: "+", val: "12", color: "#10b981" },
              { label: "Skuldkvot 0,4", sign: "−", val: "8", color: "#dc4c2b" },
            ].map((f, i) => (
              <div
                key={i}
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  fontSize: 12,
                  fontFamily: "ui-monospace, monospace",
                  color: "#475569",
                }}
              >
                <span>{f.label}</span>
                <span style={{ color: f.color, fontWeight: 600 }}>
                  {f.sign}
                  {f.val}
                </span>
              </div>
            ))}
          </div>

          <div
            style={{
              paddingTop: 14,
              borderTop: "1px dashed rgba(120,53,15,.25)",
              display: "flex",
              gap: 6,
              fontSize: 11.5,
            }}
          >
            <button
              type="button"
              onClick={() => setBScore(Math.max(420, bScore - 35))}
              style={{
                flex: 1,
                padding: "7px 10px",
                borderRadius: 6,
                cursor: "pointer",
                background: "#fff",
                border: "1px solid rgba(120,53,15,.25)",
                color: "#7f1d1d",
                fontFamily: "ui-monospace, monospace",
              }}
            >
              Sen betalning
            </button>
            <button
              type="button"
              onClick={() => setBScore(Math.min(800, bScore + 22))}
              style={{
                flex: 1,
                padding: "7px 10px",
                borderRadius: 6,
                cursor: "pointer",
                background: "#fff",
                border: "1px solid rgba(120,53,15,.25)",
                color: "#065f46",
                fontFamily: "ui-monospace, monospace",
              }}
            >
              Bygg buffert
            </button>
          </div>
        </div>
      </div>

      {/* Konsekvenskedjan */}
      <div
        style={{
          background: "#0f172a",
          color: "#fff",
          borderRadius: 14,
          padding: "28px 32px",
        }}
      >
        <div className={theme.eyebrow} style={{ marginBottom: 14, color: "#94a3b8" }}>
          Konsekvenskedjan · obetald faktura över tid
        </div>
        <h3
          style={{
            fontSize: 22,
            fontWeight: 600,
            letterSpacing: -0.3,
            margin: "0 0 22px",
            color: "#fff",
            maxWidth: 760,
            lineHeight: 1.3,
          }}
        >
          En glömd faktura idag är en betalningsanmärkning om{" "}
          <em style={{ color: "#fbbf24", fontStyle: "italic" }}>tre år.</em>
        </h3>

        <div
          className="vc-bank-cqgrid"
          style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 12 }}
        >
          {[
            {
              day: "DAG 0",
              title: "Förfallodatum + 5 dagar",
              cost: "+ 60 kr",
              delta: "−5",
              tone: "#fbbf24",
              desc: "Påminnelse 1 genereras som PDF i dina dokument.",
            },
            {
              day: "DAG 14",
              title: "Påminnelse 2",
              cost: "+ 120 kr",
              delta: "−12",
              tone: "#f59e0b",
              desc: "Avgift adderas som ny UpcomingTransaction.",
            },
            {
              day: "DAG 30",
              title: "Inkasso",
              cost: "+ 180 kr",
              delta: "−25",
              tone: "#dc4c2b",
              desc: '"Ärendet kan skickas till inkasso" — eleven får brev.',
            },
            {
              day: "DAG 45",
              title: "Kronofogden",
              cost: "BETALN.ANMÄRKN.",
              delta: "−95",
              tone: "#7f1d1d",
              desc: "EkonomiSkalan rasar. Anmärkningen följer eleven i 3 år.",
            },
          ].map((s, i) => (
            <div
              key={i}
              style={{
                background: "rgba(255,255,255,0.04)",
                border: `1px solid ${s.tone}33`,
                borderRadius: 10,
                padding: 18,
                position: "relative",
              }}
            >
              <div
                style={{
                  fontSize: 10.5,
                  fontFamily: "ui-monospace, monospace",
                  letterSpacing: 1,
                  color: s.tone,
                  marginBottom: 8,
                  fontWeight: 600,
                }}
              >
                ● {s.day}
              </div>
              <h5 style={{ fontSize: 14, fontWeight: 600, margin: "0 0 4px", color: "#fff" }}>
                {s.title}
              </h5>
              <div
                style={{
                  fontSize: 12,
                  fontFamily: "ui-monospace, monospace",
                  color: s.tone,
                  marginBottom: 10,
                }}
              >
                {s.cost} · EkonomiSkalan {s.delta}
              </div>
              <p style={{ fontSize: 11.5, lineHeight: 1.5, color: "#94a3b8", margin: 0 }}>
                {s.desc}
              </p>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

// ---------- SocraticAISection (v5) — AI:n frågar mer än den svarar ----------

function SocraticAISection({ theme }: { theme: Theme }) {
  const exchanges = [
    {
      q: '"Är det dumt att jag spenderade 1200 kr på sneakers?"',
      a: "Vad var ditt mål med sparandet den här månaden? Och hur känns det nu i efterhand — bra, neutralt, tomt?",
    },
    {
      q: '"Kan AI:n säga om jag har råd med konsertbiljetten?"',
      a: "Vi kan kolla tillsammans. Vad är din buffert just nu? Och vad är det som gör konserten viktig — vänskapen, musiken, något annat?",
    },
    {
      q: '"Borde jag ha kreditkort?"',
      a: "Vad skulle du vilja kunna göra med ett kreditkort som du inte kan idag? Och vad händer om du inte kan betala hela summan en månad?",
    },
  ];
  return (
    <section
      style={{
        padding: "96px 24px",
        borderTop: `1px solid ${theme.rule}`,
        background: "#0f172a",
        color: "#fff",
      }}
    >
      <SectionHeader
        cell={{ sym: "Ai", n: "07", label: "Sokrates" }}
        eyebrow="Sokratisk AI"
        theme={theme}
        dark
      >
        AI:n <em style={{ color: "#fbbf24", fontStyle: "italic" }}>frågar</em>{" "}
        mer än den svarar.
      </SectionHeader>
      <p
        style={{
          maxWidth: 680,
          marginBottom: 48,
          fontSize: 15.5,
          lineHeight: 1.55,
          color: "#94a3b8",
        }}
      >
        Den rekommenderar aldrig — den hjälper eleven se mönster. Inspirerad av
        Sokrates och John Rawls "veil of ignorance": bedöm beslutet utan att
        veta din egen position.
      </p>
      <div
        style={{
          display: "flex",
          flexDirection: "column",
          gap: 18,
          maxWidth: 820,
        }}
      >
        {exchanges.map((e, i) => (
          <div
            key={i}
            style={{
              display: "grid",
              gridTemplateColumns: "auto 1fr",
              gap: 28,
              padding: 24,
              background: "rgba(255,255,255,0.03)",
              border: "1px solid rgba(255,255,255,0.08)",
              borderRadius: 12,
            }}
          >
            <div
              style={{
                fontFamily: "ui-monospace, monospace",
                fontSize: 11,
                color: "#64748b",
                letterSpacing: 1,
                writingMode: "vertical-rl",
                transform: "rotate(180deg)",
              }}
            >
              EX · {String(i + 1).padStart(2, "0")}
            </div>
            <div>
              <div
                style={{
                  fontSize: 16,
                  color: "#fbbf24",
                  fontStyle: "italic",
                  marginBottom: 12,
                  fontFamily: theme.serifFont,
                }}
              >
                {e.q}
              </div>
              <div
                style={{
                  fontSize: 15.5,
                  color: "#e2e8f0",
                  lineHeight: 1.55,
                  fontFamily: theme.serifFont,
                }}
              >
                <span
                  style={{
                    color: "#dc4c2b",
                    marginRight: 8,
                    fontFamily: "ui-monospace, monospace",
                    fontSize: 11,
                  }}
                >
                  AI →
                </span>
                {e.a}
              </div>
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}

// ---------- MyCompanySection (v5) — Mitt företag · entreprenörskap ----------

function MyCompanySection({ theme }: { theme: Theme }) {
  return (
    <section
      style={{
        padding: "96px 24px",
        borderTop: `1px solid ${theme.rule}`,
        background: "#fff",
      }}
    >
      <div
        style={{
          background: "#fef3c7",
          border: `1px dashed ${theme.fg}`,
          borderRadius: 16,
          padding: "48px 44px",
          position: "relative",
        }}
      >
        <span
          style={{
            position: "absolute",
            top: -12,
            left: 24,
            background: theme.fg,
            color: "#fef3c7",
            padding: "4px 12px",
            borderRadius: 100,
            fontSize: 11,
            fontWeight: 600,
            letterSpacing: 0.8,
            fontFamily: "ui-monospace, monospace",
            textTransform: "uppercase",
          }}
        >
          ● Kommer Q3 2026
        </span>
        <div
          className="vc-mc-hero"
          style={{
            display: "grid",
            gridTemplateColumns: "1.2fr 1fr",
            gap: 64,
            alignItems: "center",
          }}
        >
          <style>{`
            @media (max-width: 900px) {
              .vc-mc-hero { grid-template-columns: 1fr !important; gap: 32px !important; }
              .vc-mc-ledger { grid-template-columns: 1fr !important; gap: 14px !important; }
              .vc-mc-ledger > div:nth-child(2) { transform: rotate(90deg); margin: 0 auto; }
              .vc-mc-cf { grid-template-columns: 1fr !important; }
            }
          `}</style>
          <div>
            <SectionHeader
              cell={{ sym: "Co", n: "08", label: "Företag" }}
              eyebrow="Mitt företag · entreprenörskaps-modul"
              theme={theme}
            >
              Driv ett{" "}
              <em style={{ color: theme.accent, fontStyle: "italic" }}>
                eget företag
              </em>
              <br />i 8–16 veckor.
            </SectionHeader>
            <p
              style={{
                fontSize: 16,
                lineHeight: 1.55,
                color: "#78350f",
                marginBottom: 22,
                maxWidth: 520,
              }}
            >
              För FE1 / FE2 (företagsekonomi gymnasiet). Eleven driver eget
              företag genom hela terminen — säljer, fakturerar, hanterar moms,
              möter AI-genererade kunder, skriver årsredovisning. Allt inom
              samma redovisningssystem som privatekonomin.
            </p>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
              {[
                "Egen kontoplan (BAS)",
                "Moms 25/12/6",
                "AI-genererade kunder",
                "Resultatrapport",
                "Årsredovisning",
                "Likviditetsplan",
              ].map((t, i) => (
                <span
                  key={i}
                  style={{
                    fontSize: 12,
                    padding: "5px 11px",
                    borderRadius: 100,
                    background: "#fff",
                    border: "1px solid rgba(120,53,15,.25)",
                    color: "#78350f",
                    fontFamily: "ui-monospace, monospace",
                  }}
                >
                  {t}
                </span>
              ))}
            </div>
          </div>
          <div
            style={{
              background: "#0f172a",
              color: "#fbbf24",
              padding: 24,
              borderRadius: 12,
              fontFamily: "ui-monospace, monospace",
              fontSize: 12,
              lineHeight: 1.7,
            }}
          >
            <div style={{ color: "#64748b", marginBottom: 10 }}>// vecka 6 · saldo</div>
            <div>
              Försäljning: <span style={{ color: "#fff" }}>+ 14 200 kr</span>
            </div>
            <div>
              Moms ut: <span style={{ color: "#fff" }}>− 2 840 kr</span>
            </div>
            <div>
              Kostnader: <span style={{ color: "#fff" }}>− 6 100 kr</span>
            </div>
            <div
              style={{
                marginTop: 8,
                paddingTop: 8,
                borderTop: "1px solid rgba(255,255,255,.15)",
              }}
            >
              Resultat: <span style={{ color: "#10b981" }}>+ 5 260 kr</span>
            </div>
            <div style={{ marginTop: 18, color: "#64748b", fontStyle: "italic" }}>
              "Tre nya kunder den här veckan — varav en är skeptisk till priset."
            </div>
          </div>
        </div>

        {/* Privatekonomi ↔ företag */}
        <div
          style={{
            marginTop: 44,
            paddingTop: 36,
            borderTop: "1px dashed rgba(120,53,15,.3)",
          }}
        >
          <div className={theme.eyebrow} style={{ marginBottom: 14, color: "#78350f" }}>
            Företaget och privatekonomin är kopplade
          </div>
          <h3
            style={{
              fontSize: 26,
              fontWeight: 600,
              letterSpacing: -0.4,
              lineHeight: 1.2,
              marginBottom: 16,
              color: "#0f172a",
              maxWidth: 720,
            }}
          >
            Eleven driver företaget och lever sitt liv samtidigt. En högre lön
            gör privatekonomin starkare — och tär på företagets kassa. En lägre
            lön ger företaget luft att växa — och kräver mer av elevens buffert
            hemma.
          </h3>
          <p
            style={{
              fontSize: 15,
              lineHeight: 1.6,
              color: "#78350f",
              maxWidth: 720,
              marginBottom: 28,
            }}
          >
            Eleven balanserar två huvudböcker som faktiskt påverkar varandra.
            Lön, utdelning, kostnader, kapitalinsats — varje transaktion mellan
            företag och privat syns på <strong> båda</strong> sidor. Och
            Wellbeing räknar på <em>helheten</em>, inte på den ena.
          </p>

          <div
            className="vc-mc-ledger"
            style={{
              display: "grid",
              gridTemplateColumns: "1fr auto 1fr",
              gap: 18,
              alignItems: "stretch",
            }}
          >
            <div
              style={{
                background: "#fff",
                border: "1px solid rgba(120,53,15,.2)",
                borderRadius: 10,
                padding: 22,
              }}
            >
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                  marginBottom: 14,
                }}
              >
                <span
                  style={{
                    fontSize: 11,
                    fontFamily: "ui-monospace, monospace",
                    letterSpacing: 1,
                    color: "#78350f",
                  }}
                >
                  PRIVAT
                </span>
                <span
                  style={{
                    fontSize: 11,
                    fontFamily: "ui-monospace, monospace",
                    color: "#10b981",
                  }}
                >
                  Wellbeing 78
                </span>
              </div>
              <ul
                style={{
                  listStyle: "none",
                  padding: 0,
                  margin: 0,
                  fontSize: 13,
                  fontFamily: "ui-monospace, monospace",
                  lineHeight: 1.9,
                  color: "#0f172a",
                }}
              >
                <li>
                  Lön in: <strong style={{ color: "#10b981" }}>+ 22 000 kr</strong>
                </li>
                <li>
                  Hyra: <span style={{ color: "#dc4c2b" }}>− 8 500 kr</span>
                </li>
                <li>
                  Sparkvot: <strong>18 %</strong>
                </li>
                <li style={{ color: "#64748b", fontStyle: "italic", marginTop: 8 }}>
                  "Bra månad. Buffert växer."
                </li>
              </ul>
            </div>

            <div
              style={{
                display: "flex",
                flexDirection: "column",
                alignItems: "center",
                justifyContent: "center",
                minWidth: 64,
              }}
            >
              <svg width="40" height="40" viewBox="0 0 40 40" fill="none">
                <path
                  d="M8 14 H32 M28 10 L32 14 L28 18"
                  stroke="#78350f"
                  strokeWidth="1.6"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
                <path
                  d="M32 26 H8 M12 22 L8 26 L12 30"
                  stroke="#78350f"
                  strokeWidth="1.6"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              </svg>
              <span
                style={{
                  fontSize: 10,
                  fontFamily: "ui-monospace, monospace",
                  color: "#78350f",
                  letterSpacing: 1,
                  marginTop: 8,
                  textAlign: "center",
                }}
              >
                LÖN
                <br />
                UTDELNING
                <br />
                INSATS
              </span>
            </div>

            <div
              style={{
                background: "#0f172a",
                color: "#fbbf24",
                borderRadius: 10,
                padding: 22,
              }}
            >
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                  marginBottom: 14,
                }}
              >
                <span
                  style={{
                    fontSize: 11,
                    fontFamily: "ui-monospace, monospace",
                    letterSpacing: 1,
                    color: "#94a3b8",
                  }}
                >
                  FÖRETAG
                </span>
                <span
                  style={{
                    fontSize: 11,
                    fontFamily: "ui-monospace, monospace",
                    color: "#dc4c2b",
                  }}
                >
                  Likviditet låg
                </span>
              </div>
              <ul
                style={{
                  listStyle: "none",
                  padding: 0,
                  margin: 0,
                  fontSize: 13,
                  fontFamily: "ui-monospace, monospace",
                  lineHeight: 1.9,
                  color: "#e2e8f0",
                }}
              >
                <li>
                  Lön ut: <span style={{ color: "#dc4c2b" }}>− 22 000 kr</span>
                </li>
                <li>
                  Försäljning:{" "}
                  <strong style={{ color: "#10b981" }}>+ 18 400 kr</strong>
                </li>
                <li>
                  Resultat: <strong style={{ color: "#dc4c2b" }}>− 3 600 kr</strong>
                </li>
                <li style={{ color: "#94a3b8", fontStyle: "italic", marginTop: 8 }}>
                  "Måste sänka lönen — eller sälja mer."
                </li>
              </ul>
            </div>
          </div>

          <p
            style={{
              marginTop: 24,
              fontSize: 13.5,
              color: "#78350f",
              fontStyle: "italic",
              maxWidth: 720,
            }}
          >
            Det är inte ett quiz. Det är en balansgång där eleven känner
            skillnaden mellan att optimera för sig själv, för företaget eller
            för helheten.
          </p>
        </div>

        {/* Likviditet ≠ Lönsamhet */}
        <div
          style={{
            marginTop: 44,
            paddingTop: 36,
            borderTop: "1px dashed rgba(120,53,15,.3)",
          }}
        >
          <div className={theme.eyebrow} style={{ marginBottom: 14, color: "#78350f" }}>
            Advanced · Likviditet ≠ Lönsamhet
          </div>
          <h3
            style={{
              fontSize: 26,
              fontWeight: 600,
              letterSpacing: -0.4,
              lineHeight: 1.25,
              marginBottom: 16,
              color: "#0f172a",
              maxWidth: 760,
            }}
          >
            Lönsamt på pappret, konkurs på torsdag.
          </h3>
          <p
            style={{
              fontSize: 15,
              lineHeight: 1.6,
              color: "#78350f",
              maxWidth: 720,
              marginBottom: 24,
            }}
          >
            Den enskilt viktigaste lärdomen i företagande, som de flesta
            läroböcker missar: ett lönsamt företag kan gå i konkurs när kunderna
            betalar sent. Eleven får uppleva glappet mellan kassaflöde och
            resultat på sin egen dashboard — inte som teori, som plötslig
            verklighet.
          </p>
          <div
            className="vc-mc-cf"
            style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}
          >
            <div
              style={{
                background: "#fff",
                border: "1px solid rgba(120,53,15,.2)",
                borderRadius: 10,
                padding: 22,
              }}
            >
              <div
                style={{
                  fontSize: 11,
                  fontFamily: "ui-monospace, monospace",
                  letterSpacing: 1,
                  color: "#78350f",
                  marginBottom: 12,
                }}
              >
                RESULTATRÄKNING
              </div>
              <ul
                style={{
                  listStyle: "none",
                  padding: 0,
                  margin: 0,
                  fontSize: 13,
                  fontFamily: "ui-monospace, monospace",
                  lineHeight: 1.9,
                  color: "#0f172a",
                }}
              >
                <li>
                  Fakturerat:{" "}
                  <strong style={{ color: "#10b981" }}>+ 48 000 kr</strong>
                </li>
                <li>
                  Kostnader: <span style={{ color: "#dc4c2b" }}>− 32 000 kr</span>
                </li>
                <li
                  style={{
                    marginTop: 8,
                    paddingTop: 8,
                    borderTop: "1px solid rgba(120,53,15,.15)",
                  }}
                >
                  Resultat:{" "}
                  <strong style={{ color: "#10b981" }}>+ 16 000 kr ✓</strong>
                </li>
              </ul>
              <div
                style={{
                  marginTop: 14,
                  fontSize: 12.5,
                  color: "#10b981",
                  fontStyle: "italic",
                }}
              >
                "Lönsamt!"
              </div>
            </div>
            <div
              style={{
                background: "#fff",
                border: "2px solid #dc4c2b",
                borderRadius: 10,
                padding: 22,
              }}
            >
              <div
                style={{
                  fontSize: 11,
                  fontFamily: "ui-monospace, monospace",
                  letterSpacing: 1,
                  color: "#dc4c2b",
                  marginBottom: 12,
                }}
              >
                KASSAFLÖDE
              </div>
              <ul
                style={{
                  listStyle: "none",
                  padding: 0,
                  margin: 0,
                  fontSize: 13,
                  fontFamily: "ui-monospace, monospace",
                  lineHeight: 1.9,
                  color: "#0f172a",
                }}
              >
                <li>
                  Faktiskt inbetalt:{" "}
                  <strong style={{ color: "#10b981" }}>+ 18 000 kr</strong>
                </li>
                <li>
                  Hyra + lön:{" "}
                  <span style={{ color: "#dc4c2b" }}>− 24 000 kr</span>
                </li>
                <li
                  style={{
                    marginTop: 8,
                    paddingTop: 8,
                    borderTop: "1px solid rgba(120,53,15,.15)",
                  }}
                >
                  Kassa:{" "}
                  <strong style={{ color: "#dc4c2b" }}>− 6 000 kr ✗</strong>
                </li>
              </ul>
              <div
                style={{
                  marginTop: 14,
                  fontSize: 12.5,
                  color: "#dc4c2b",
                  fontStyle: "italic",
                }}
              >
                "Kunderna betalar 30 dagar för sent. Hyran kan inte vänta."
              </div>
            </div>
          </div>
          <p
            style={{
              marginTop: 22,
              fontSize: 13.5,
              color: "#78350f",
              fontStyle: "italic",
              maxWidth: 720,
            }}
          >
            Eleven kommer i kontakt med påminnelser, dröjsmålsränta, kortsiktiga
            lån — och ser i siffror varför likviditetsplanering är skillnaden
            mellan ett företag som överlever och ett som inte gör det.
          </p>
        </div>
      </div>
    </section>
  );
}

// ---------- PriceSection (v5) — pilot 2026 + från 2027 ----------

function PriceSection({ theme }: { theme: Theme }) {
  return (
    <section
      id="pris"
      style={{ padding: "64px 24px", borderTop: `1px solid ${theme.rule}` }}
    >
      <div className={theme.eyebrow} style={{ textAlign: "center", marginBottom: 12 }}>
        Pris
      </div>
      <h2 className={theme.h2} style={{ textAlign: "center" }}>
        Enkel prismodell.
      </h2>
      <p
        style={{
          fontSize: 15,
          color: "#475569",
          marginTop: 14,
          marginBottom: 32,
          maxWidth: 640,
          marginLeft: "auto",
          marginRight: "auto",
          textAlign: "center",
          lineHeight: 1.6,
        }}
      >
        Gratis under pilotåret 2026 — för skolor och familjer. Ingen
        bindningstid, inga dolda kostnader. Från 2027 sätts en avgift per
        användare i dialog med pilotkunderna.
      </p>
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))",
          gap: 18,
          maxWidth: 1000,
          margin: "0 auto",
        }}
      >
        <div
          style={{
            background: theme.cardBg,
            border: `2px solid ${theme.fg}`,
            borderRadius: theme.radius,
            padding: 28,
          }}
        >
          <div className={theme.eyebrow} style={{ marginBottom: 12 }}>
            Pilot 2026
          </div>
          <div
            style={{
              fontSize: 56,
              fontWeight: 700,
              letterSpacing: -2,
              lineHeight: 1,
              marginBottom: 6,
            }}
          >
            0 kr
          </div>
          <div style={{ marginBottom: 18, color: "#475569" }}>
            Hela plattformen, utan tak.
          </div>
          <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
            {[
              "Obegränsat antal elever/barn",
              "AI-funktioner (Claude Sonnet)",
              "Portfolio-PDF + ZIP-export",
              "Support via mail",
            ].map((t, i) => (
              <li key={i} style={{ marginBottom: 6, color: "#475569" }}>
                · {t}
              </li>
            ))}
          </ul>
        </div>
        <div
          style={{
            background: theme.cardBg,
            border: `1px solid ${theme.rule}`,
            borderRadius: theme.radius,
            padding: 28,
          }}
        >
          <div className={theme.eyebrow} style={{ marginBottom: 12 }}>
            Från 2027
          </div>
          <div
            style={{
              fontSize: 36,
              fontWeight: 600,
              letterSpacing: -1,
              lineHeight: 1.05,
              marginBottom: 14,
            }}
          >
            Per-användare
          </div>
          <div style={{ marginBottom: 18, color: "#475569" }}>
            Nivå sätts tillsammans med pilotkunderna — troligen 50–100
            kr/användare/år. Familjer får ett enskilt pris/abonn.
          </div>
          <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
            {[
              "Samma plattform, ingen funktionsnedskärning",
              "Tak för AI-användning",
              "Dedicerad support",
            ].map((t, i) => (
              <li key={i} style={{ marginBottom: 6, color: "#475569" }}>
                · {t}
              </li>
            ))}
          </ul>
        </div>
      </div>
    </section>
  );
}

// ---------- FoundersQuoteSection (v5) — Robin Fröjd · Ekonomilabbet ----------

function FoundersQuoteSection({ theme }: { theme: Theme }) {
  const sectionRef = useRef<HTMLElement | null>(null);
  const quoteRef = useRef<HTMLParagraphElement | null>(null);
  const supportRef = useRef<HTMLDivElement | null>(null);
  const reduced = useReducedMotion();

  // Text-reveal: huvudcitatet maskeras vänster→höger med clip-path,
  // sedan fade:ar de stödjande paragraferna in med stagger.
  useEffect(() => {
    if (reduced || !sectionRef.current) return;
    registerScrollTrigger();
    const ctx = gsap.context(() => {
      const tl = gsap.timeline({
        scrollTrigger: { trigger: sectionRef.current, start: "top 70%", once: true },
      });
      if (quoteRef.current) {
        tl.fromTo(
          quoteRef.current,
          { clipPath: "inset(0 100% 0 0)" },
          { clipPath: "inset(0 0% 0 0)", duration: 2.0, ease: "power2.inOut" },
        );
      }
      if (supportRef.current) {
        tl.from(
          supportRef.current.querySelectorAll("p"),
          { opacity: 0, y: 16, duration: 0.7, stagger: 0.2, ease: "power2.out" },
          "-=0.5",
        );
      }
    }, sectionRef);
    return () => ctx.revert();
  }, [reduced]);

  return (
    <section
      ref={sectionRef}
      style={{
        padding: "120px 24px",
        borderTop: `1px solid ${theme.rule}`,
        background: "#0f172a",
        color: "#fff",
      }}
    >
      <blockquote
        style={{
          margin: "0 auto",
          maxWidth: 820,
          textAlign: "center",
          padding: 0,
        }}
      >
        <p
          ref={quoteRef}
          style={{
            fontFamily: theme.serifFont,
            fontSize: 32,
            lineHeight: 1.25,
            color: "#fff",
            fontStyle: "italic",
            margin: 0,
            letterSpacing: -0.5,
            textWrap: "balance",
            fontWeight: 500,
          }}
        >
          "Vi simulerar inte bara ekonomi — vi tränar förmågan att{" "}
          <em style={{ color: "#fbbf24" }}>leva ett balanserat liv.</em>"
        </p>

        <div
          ref={supportRef}
          style={{
            marginTop: 36,
            fontSize: 15.5,
            lineHeight: 1.7,
            color: "#94a3b8",
            maxWidth: 640,
            marginLeft: "auto",
            marginRight: "auto",
            fontFamily: theme.serifFont,
          }}
        >
          <p style={{ margin: "0 0 14px" }}>
            Ekonomi är inte ett abstrakt kapitel i en lärobok — det är balansen
            mellan våra val idag och våra möjligheter imorgon.
          </p>
          <p style={{ margin: "0 0 14px" }}>
            Genom att bygga kunskap genom konsekvenser snarare än teori, ger vi
            nästa generation verktygen att navigera livets dalar med insikt
            istället för osäkerhet.
          </p>
          <p style={{ margin: 0 }}>
            Genom att koppla ekonomisk trygghet till personligt välmående, lär
            vi eleverna att hantera verklighetens stress och fatta beslut som
            håller över tid.
          </p>
        </div>

        <footer
          style={{
            marginTop: 36,
            fontSize: 12,
            color: "#64748b",
            fontFamily: "ui-monospace, monospace",
            letterSpacing: 1,
            textTransform: "uppercase",
          }}
        >
          — Robin Fröjd · Ekonomilabbet
        </footer>
      </blockquote>
    </section>
  );
}

function PeriodicGrid({
  hovered,
  setHovered,
  onPick,
}: {
  hovered: number | null;
  setHovered: (n: number | null) => void;
  onPick?: (cell: CellInfo) => void;
}) {
  // Map nummer → CellInfo så vi kan slå upp tip/long/example/trains
  // utan att förändra PERIODIC_CELLS-strukturen.
  const infoByN = new Map<number, CellInfo>(CELL_INFO.map((c) => [c.n, c]));
  return (
    <div className="vc-periodic-grid">
      {PERIODIC_CELLS.map((c) => {
        const p = PALETTE[c.cat];
        const isH = hovered === c.n;
        const info = infoByN.get(c.n);
        return (
          <button
            key={c.n}
            type="button"
            onMouseEnter={() => setHovered(c.n)}
            onMouseLeave={() => setHovered(null)}
            onClick={() => info && onPick?.(info)}
            aria-label={`${c.name} — ${info?.tip ?? c.desc}`}
            title={info?.tip}
            style={{
              aspectRatio: "1",
              padding: 4,
              borderRadius: 5,
              background: p.bg,
              color: p.fg,
              border: `1px solid ${p.border}`,
              display: "flex",
              flexDirection: "column",
              justifyContent: "space-between",
              transform: isH ? "translateY(-2px)" : "none",
              boxShadow: isH ? "0 4px 10px rgba(15,23,42,.1)" : "none",
              transition: "all .12s",
              cursor: onPick ? "pointer" : "default",
              minHeight: 0,
              fontFamily: "inherit",
              textAlign: "inherit",
            }}
          >
            <div
              className="vc-mono"
              style={{ fontSize: 8, opacity: 0.6, lineHeight: 1 }}
            >
              {c.n.toString().padStart(2, "0")}
            </div>
            <div
              className="vc-mono"
              style={{
                fontSize: 13,
                fontWeight: 700,
                lineHeight: 1,
                textAlign: "center",
              }}
            >
              {c.sym}
            </div>
            <div
              style={{
                fontSize: 8,
                lineHeight: 1.1,
                textAlign: "center",
                overflow: "hidden",
                textOverflow: "ellipsis",
                whiteSpace: "nowrap",
              }}
            >
              {c.name}
            </div>
          </button>
        );
      })}
    </div>
  );
}

// ---------- Cell-modal (SaaS-stil) ----------

function CellModal({
  cell,
  onClose,
}: {
  cell: CellInfo;
  onClose: () => void;
}) {
  // Esc stänger; lås body-scroll medan modalen är öppen.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      window.removeEventListener("keydown", onKey);
      document.body.style.overflow = prevOverflow;
    };
  }, [onClose]);

  const p = PALETTE[cell.cat];
  const meta = CATEGORY_META[cell.cat];

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="cell-modal-title"
      onClick={onClose}
      style={{
        position: "fixed",
        inset: 0,
        background: "rgba(15,23,42,.55)",
        backdropFilter: "blur(2px)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        padding: 16,
        zIndex: 50,
        animation: "vc-modal-fade .15s ease-out",
      }}
    >
      <style>{`
        @keyframes vc-modal-fade {
          from { opacity: 0; }
          to { opacity: 1; }
        }
        @keyframes vc-modal-pop {
          from { opacity: 0; transform: translateY(8px) scale(.98); }
          to { opacity: 1; transform: none; }
        }
      `}</style>
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          background: "#fff",
          border: "1px solid #e2e8f0",
          borderRadius: 14,
          maxWidth: 540,
          width: "100%",
          maxHeight: "85vh",
          overflowY: "auto",
          boxShadow: "0 24px 64px rgba(15,23,42,.18), 0 6px 18px rgba(15,23,42,.08)",
          animation: "vc-modal-pop .18s ease-out",
        }}
      >
        {/* Färgband i kategori-pastell */}
        <div
          style={{
            height: 6,
            background: p.bg,
            borderTopLeftRadius: 14,
            borderTopRightRadius: 14,
          }}
        />
        <div style={{ padding: "22px 26px 26px" }}>
          {/* Header: cell-pill + namn + kategori */}
          <div style={{ display: "flex", alignItems: "flex-start", gap: 16 }}>
            <div
              style={{
                width: 56,
                height: 56,
                borderRadius: 10,
                background: p.bg,
                color: p.fg,
                border: `1px solid ${p.border}`,
                display: "flex",
                flexDirection: "column",
                alignItems: "center",
                justifyContent: "center",
                flexShrink: 0,
              }}
            >
              <span
                className="vc-mono"
                style={{ fontSize: 9, opacity: 0.7, lineHeight: 1 }}
              >
                {String(cell.n).padStart(2, "0")}
              </span>
              <span
                className="vc-mono"
                style={{ fontSize: 18, fontWeight: 700, lineHeight: 1 }}
              >
                {cell.sym}
              </span>
            </div>
            <div style={{ flex: 1, minWidth: 0 }}>
              <h2
                id="cell-modal-title"
                style={{
                  fontSize: 22,
                  fontWeight: 700,
                  letterSpacing: -0.4,
                  lineHeight: 1.2,
                  margin: 0,
                }}
              >
                {cell.name}
              </h2>
              <div
                className="vc-eyebrow"
                style={{ marginTop: 4, color: "#64748b" }}
              >
                {meta.label} · #{cell.n}
              </div>
            </div>
            <button
              onClick={onClose}
              aria-label="Stäng"
              style={{
                background: "transparent",
                border: 0,
                cursor: "pointer",
                color: "#64748b",
                fontSize: 22,
                lineHeight: 1,
                padding: 4,
              }}
            >
              ×
            </button>
          </div>

          {/* TIP-banner */}
          <div
            style={{
              marginTop: 18,
              padding: "10px 14px",
              background: "#f8fafc",
              border: "1px solid #e2e8f0",
              borderRadius: 8,
              fontSize: 13.5,
              color: "#0f172a",
              fontStyle: "italic",
            }}
          >
            {cell.tip}
          </div>

          {/* LONG */}
          <p
            style={{
              marginTop: 18,
              fontSize: 14.5,
              lineHeight: 1.6,
              color: "#334155",
            }}
          >
            {cell.long}
          </p>

          {/* EXAMPLE */}
          <div
            style={{
              marginTop: 18,
              borderLeft: "3px solid #0f172a",
              paddingLeft: 14,
              paddingTop: 2,
              paddingBottom: 2,
            }}
          >
            <div className="vc-eyebrow" style={{ marginBottom: 4 }}>
              Exempel
            </div>
            <p
              style={{
                fontSize: 14,
                lineHeight: 1.55,
                color: "#475569",
                margin: 0,
              }}
            >
              {cell.example}
            </p>
          </div>

          {/* TRAINS-IN */}
          <div
            style={{
              marginTop: 20,
              paddingTop: 16,
              borderTop: "1px solid #e2e8f0",
            }}
          >
            <div className="vc-eyebrow" style={{ marginBottom: 4 }}>
              Tränas i
            </div>
            <p
              style={{
                fontSize: 13.5,
                lineHeight: 1.55,
                color: "#475569",
                margin: 0,
              }}
            >
              {cell.trains}
            </p>
          </div>

          {/* Footer */}
          <div
            style={{
              marginTop: 22,
              display: "flex",
              justifyContent: "flex-end",
              gap: 8,
            }}
          >
            <button
              onClick={onClose}
              className="vc-btn vc-btn-primary"
              style={{ padding: "9px 16px" }}
            >
              Stäng
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

// ---------- Search palette (B1) ----------

function SearchPalette({
  onClose,
  onPick,
}: {
  onClose: () => void;
  onPick: (cell: CellInfo) => void;
}) {
  const [q, setQ] = useState("");
  const [activeIdx, setActiveIdx] = useState(0);

  // Filtrera på namn, sym eller tip — case-insensitivt.
  const ql = q.toLowerCase().trim();
  const results = ql
    ? CELL_INFO.filter(
        (c) =>
          c.name.toLowerCase().includes(ql) ||
          c.sym.toLowerCase().includes(ql) ||
          c.tip.toLowerCase().includes(ql),
      )
    : CELL_INFO;

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
      else if (e.key === "ArrowDown") {
        e.preventDefault();
        setActiveIdx((i) => Math.min(i + 1, results.length - 1));
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        setActiveIdx((i) => Math.max(i - 1, 0));
      } else if (e.key === "Enter") {
        e.preventDefault();
        const cell = results[activeIdx];
        if (cell) onPick(cell);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose, onPick, results, activeIdx]);

  // Reset activeIdx när query ändras så vi inte hamnar utanför listan.
  useEffect(() => {
    setActiveIdx(0);
  }, [q]);

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="Sök i kursplanen"
      onClick={onClose}
      style={{
        position: "fixed",
        inset: 0,
        background: "rgba(15,23,42,.45)",
        display: "flex",
        alignItems: "flex-start",
        justifyContent: "center",
        paddingTop: "12vh",
        zIndex: 60,
      }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          background: "#fff",
          border: "1px solid #e2e8f0",
          borderRadius: 12,
          width: "min(560px, 92vw)",
          maxHeight: "70vh",
          display: "flex",
          flexDirection: "column",
          boxShadow: "0 24px 64px rgba(15,23,42,.2)",
          overflow: "hidden",
        }}
      >
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 10,
            padding: "12px 16px",
            borderBottom: "1px solid #e2e8f0",
          }}
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#64748b" strokeWidth="2">
            <circle cx="11" cy="11" r="7" />
            <path d="m20 20-3.5-3.5" />
          </svg>
          <input
            autoFocus
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Sök bland 32 grundbegrepp…"
            style={{
              flex: 1,
              border: 0,
              outline: 0,
              fontSize: 15,
              fontFamily: "inherit",
              background: "transparent",
            }}
          />
          <span className="vc-kbd">Esc</span>
        </div>
        <div style={{ overflowY: "auto", padding: "6px 0" }}>
          {results.length === 0 && (
            <div
              style={{
                padding: "24px 16px",
                color: "#64748b",
                fontSize: 14,
                textAlign: "center",
              }}
            >
              Inget begrepp matchar &quot;{q}&quot;.
            </div>
          )}
          {results.map((c, i) => {
            const p = PALETTE[c.cat];
            const active = i === activeIdx;
            return (
              <button
                key={c.n}
                type="button"
                onMouseEnter={() => setActiveIdx(i)}
                onClick={() => onPick(c)}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 12,
                  width: "100%",
                  padding: "9px 16px",
                  background: active ? "#f1f5f9" : "transparent",
                  border: 0,
                  textAlign: "left",
                  cursor: "pointer",
                  fontFamily: "inherit",
                }}
              >
                <span
                  className="vc-mono"
                  style={{
                    width: 32,
                    height: 32,
                    borderRadius: 6,
                    background: p.bg,
                    color: p.fg,
                    border: `1px solid ${p.border}`,
                    display: "inline-flex",
                    alignItems: "center",
                    justifyContent: "center",
                    fontWeight: 700,
                    fontSize: 12,
                    flexShrink: 0,
                  }}
                >
                  {c.sym}
                </span>
                <span style={{ flex: 1, minWidth: 0 }}>
                  <span style={{ fontSize: 14, fontWeight: 500, color: "#0f172a" }}>
                    {c.name}
                  </span>
                  <span
                    style={{
                      display: "block",
                      fontSize: 12,
                      color: "#64748b",
                      whiteSpace: "nowrap",
                      overflow: "hidden",
                      textOverflow: "ellipsis",
                    }}
                  >
                    {c.tip}
                  </span>
                </span>
                <span className="vc-mono" style={{ fontSize: 11, color: "#94a3b8" }}>
                  #{c.n}
                </span>
              </button>
            );
          })}
        </div>
        <div
          style={{
            padding: "8px 16px",
            borderTop: "1px solid #e2e8f0",
            background: "#f8fafc",
            fontSize: 11.5,
            color: "#64748b",
            display: "flex",
            gap: 16,
          }}
        >
          <span><span className="vc-kbd">↑↓</span> bläddra</span>
          <span><span className="vc-kbd">↵</span> öppna</span>
          <span><span className="vc-kbd">Esc</span> stäng</span>
        </div>
      </div>
    </div>
  );
}
