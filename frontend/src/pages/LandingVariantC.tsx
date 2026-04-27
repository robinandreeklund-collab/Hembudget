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
import { useEffect, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { CELL_INFO, type CellInfo } from "@/data/landingCells";

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
  return (
    <div
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
      <Moments />
      <Logic />
      <Problem />
      <ThreeWays />
      <Pricing />
      <Faq />
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

const PROBLEM_STATS = [
  { num: "4 av 10", label: "unga klarar inte en oväntad räkning på 2 000 kr." },
  { num: "60 %", label: "av unga har aldrig läst en lönespecifikation." },
  { num: "1 h", label: "räcker för att prova grunderna i Ekonomilabbet." },
];

// 5 nyckelmoment — språkfix från originalbundlen:
// 'kortfaktur' → 'kortfakturor', 'din barn' → 'dina barn'.
const MOMENTS = [
  {
    n: 1,
    title: "En egen vardag",
    desc: "Yrke, lön, bostad, lån — allt slumpas unikt per användare. Dashboarden visar nettolön, utgifter, sparande och budget mot verkligheten i realtid.",
  },
  {
    n: 2,
    title: "Riktiga dokument att jobba med",
    desc: "Du trycker \"generera\" — eleven får kontoutdrag, lönespec, lånebesked och kortfakturor som PDF:er och importerar själv.",
  },
  {
    n: 3,
    title: "Budget möter verklighet",
    desc: "Eleven sätter månadsbudget enligt Konsumentverkets 2026-siffror. När en trasig diskmaskin slår till syns följderna direkt.",
  },
  {
    n: 4,
    title: "Verkliga ekonomiska val",
    desc: "Bolåne-beslut baserat på Riksbankens historiska räntor. Eleven binder eller kör rörlig — systemet visar facit efter perioden.",
  },
  {
    n: 5,
    title: "Du ser hela bilden",
    desc: "Översiktsmatris över alla användare och uppdrag. Kategoriseringsfacit per transaktion. Chatt för feedback. Samma översikt vare sig du följer en klass eller dina barn.",
  },
];

const LOGIC = [
  {
    n: "01",
    title: "En cell, en kompetens",
    desc: "Varje element är kopplat till en eller flera moduler. När eleven klarar stegen fylls cellen — precis som mastery-grafen redan gör.",
  },
  {
    n: "02",
    title: "Du rättar i rader",
    desc: "Reflektioner samlas per kolumn. Claude föreslår rubric-betyg; du skriver under eller ändrar på två klick — som lärare eller förälder.",
  },
  {
    n: "03",
    title: "Hela gruppen i en bild",
    desc: "Översikten lägger användarnas mastery som ett värmekarta-lager ovanpå systemet. Funkar för en klass eller ett syskonpar.",
  },
];

// Live-statistik visar siffror i nollläge tills pilotskolan startar.
const STATS_LIVE: Array<{ num: string; label: string }> = [
  { num: "0", label: "Lärare" },
  { num: "5", label: "Elever" },
  { num: "0", label: "Avklarade moduler" },
  { num: "0", label: "Reflektioner" },
];

// Sex koncept-skärmar lärare och elever rör sig i.
const SCREENS: Array<{ sym: string; title: string; desc: string }> = [
  { sym: "Lä", title: "Lärarens dashboard", desc: "Alla elever, inbox, uppdrag och AI-lägesbilder på en skärm." },
  { sym: "Mo", title: "Elevens kursplan", desc: "Moduler steg för steg, klar, reflektera, quiz och uppdrag." },
  { sym: "Ms", title: "Mastery-grafen", desc: "Per-kompetens mastery, milstolpar och nästa-steg-hint." },
  { sym: "Pf", title: "Portfolio-PDF", desc: "Exporteras per elev eller som ZIP för hela klassen." },
  { sym: "AI", title: "Echo", desc: "Multi-turn AI-coach som anpassar svaren till elevens nivå." },
  { sym: "Tt", title: "Time on task", desc: "Se vilka steg som fastnar för eleverna i din klass." },
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

// NewSectionCell/Header — separat namn för v5:s tre nya sektioner
// (Employer/SalaryTalk/Bank). Identiskt utseende, behåller separation
// så att v5-källkoden mappar 1:1.
const NewSectionCell = SectionCell;
const NewSectionHeader = SectionHeader;

// Tillfällig referens — håller resterande atomer/konstanter "använda"
// under fas 3 (konsumeras av sektionerna som byggs i fas 5–18). Tas
// bort senast i fas 4 när Features renderar THEME.
const __VC_PHASE1_SCAFFOLD = {
  SectionCell,
  SectionHeader,
  NewSectionCell,
  NewSectionHeader,
  THEME,
  STATS_LIVE,
  SCREENS,
};
void __VC_PHASE1_SCAFFOLD;

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

  return (
    <section id="oversikt" className="vc-hero-section">
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

          {/* Stats-rad enligt v5 */}
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
              { num: "32", label: "grundbegrepp" },
              { num: "80+", label: "mikrouppgifter" },
              { num: "6", label: "kategorier" },
            ].map((s) => (
              <div
                key={s.label}
                style={{ display: "flex", flexDirection: "column", alignItems: "flex-start", gap: 6 }}
              >
                <span style={{ fontSize: 26, fontWeight: 700, letterSpacing: -0.5, color: "#0f172a" }}>
                  {s.num}
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

        <div className="vc-card" style={{ padding: 22 }}>
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

// ---------- Problem ----------

function Problem() {
  return (
    <section
      style={{
        padding: "64px 24px",
        borderTop: "1px solid #e2e8f0",
        maxWidth: 1200,
        margin: "0 auto",
      }}
    >
      <div className="vc-eyebrow" style={{ marginBottom: 12 }}>
        Problemet
      </div>
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "minmax(0,1.1fr) minmax(0,1.4fr)",
          gap: 56,
          alignItems: "start",
        }}
        className="vc-problem-grid"
      >
        <style>{`
          @media (max-width: 768px) {
            .vc-problem-grid { grid-template-columns: 1fr !important; gap: 24px !important; }
          }
        `}</style>
        <div>
          <h2 className="vc-h2">
            Ekonomi är ett livskunskapsämne.{" "}
            <em style={{ color: "#dc4c2b", fontStyle: "normal" }}>
              Och det saknas
            </em>{" "}
            — både i skolan och hemma.
          </h2>
          <p
            style={{
              fontSize: 15,
              lineHeight: 1.65,
              color: "#475569",
              marginTop: 20,
              maxWidth: 440,
            }}
          >
            Svenska unga lämnar gymnasiet utan grundläggande kunskaper om
            skatt, sparande, lån och budget. Verkligheten möter dem först
            när de flyttar hemifrån — ofta för sent. Skolan har sällan
            tid, och föräldrar har sällan ett verktyg att luta sig mot.
          </p>
          <p
            style={{
              fontSize: 17,
              marginTop: 22,
              fontStyle: "italic",
              maxWidth: 440,
              color: "#0f172a",
            }}
          >
            Lär genom att göra — inte genom att läsa om det.
          </p>
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>
          {PROBLEM_STATS.map((s, i) => (
            <div
              key={i}
              className="vc-card"
              style={{
                padding: 24,
                display: "flex",
                alignItems: "center",
                gap: 24,
                flexWrap: "wrap",
              }}
            >
              <div
                style={{
                  fontSize: 40,
                  fontWeight: 700,
                  letterSpacing: -1.2,
                  color: "#0f172a",
                  minWidth: 120,
                }}
              >
                {s.num}
              </div>
              <div style={{ flex: 1, minWidth: 180, color: "#475569" }}>
                {s.label}
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

// ---------- Three ways to use ----------

function ThreeWays() {
  type Way = {
    kicker: string;
    title: string;
    items: string[];
    cta: string;
    href: string;
    soon?: boolean;
    lead?: string;
  };
  const ways: Way[] = [
    {
      kicker: "För skolan",
      title: "Ett labb i klassrummet",
      items: [
        "Bjud in en hel klass via 6-tecken-koder — ingen e-post per elev krävs.",
        "Tilldela samma modul till alla, eller skräddarsy per elev. Mastery-grafen visar var klassen fastnar.",
        "Portfolio-PDF per elev eller hela klassen som ZIP — perfekt som bedömningsunderlag.",
        "AI-coachen anpassar sig efter elevens nivå utan att läraren behöver konfigurera något.",
      ],
      cta: "Skapa lärarkonto →",
      href: "/signup/teacher",
    },
    {
      kicker: "För hemmet",
      title: "Samtalet om pengar — i lugnt format",
      items: [
        "Skapa konton för dina barn på två minuter. Varje barn får en egen sandlåda — riktiga pengar är aldrig inblandade.",
        "Du följer med i samma vy som läraren har: vad har barnet gjort, vad har det fastnat på, vad har det frågat AI:n.",
        "Modulerna täcker kontoutdrag, bolån, kreditkort, sparande och familjebudget — bygg upp ett gemensamt språk hemma.",
        'AI-coachen svarar på "varför betalar man skatt?" utan att vänta på er nästa middag.',
      ],
      cta: "Skapa familjekonto →",
      href: "/signup/parent",
    },
    {
      kicker: "Kommer 2026",
      title: "Hela familjens riktiga ekonomi — på ett ställe",
      lead: "Inspirerat av riktiga bokföringssystem — men enklare, roligare och faktiskt begripligt. Tänk Visma eller Fortnox, fast för köksbordet.",
      items: [
        "Anslut bankkonton, kreditkort och lån via Tink (PSD2). Vi kategoriserar varje transaktion automatiskt — inga manuella Excel-kolumner.",
        "Ladda upp era fakturor — el, vatten, hyra, försäkringar. Vi läser av förbrukning, datum och belopp och knyter dem till rätt kategori.",
        "Bygg månadsbudget för kommande period på minuter. Varje månad balanseras automatiskt i en huvudbok — debet och kredit på riktigt.",
        'Fråga AI-coachen direkt: "Vad spenderade vi mest på i mars?", "Hur mycket går till prenumerationer?" — den läser hela familjens ekonomi och svarar i klartext.',
        "Barnet ser sina sparmål bredvid familjens budget — utan beloppen om ni inte vill. Ni bestämmer vad som syns.",
        "Bank-grade kryptering, svensk personuppgiftsbehandling. Datan stannar hos er och raderas på en knapptryckning.",
      ],
      cta: "Sätt upp på väntelistan →",
      href: "mailto:info@ekonomilabbet.org?subject=V%C3%A4ntelista%20Ekonomilabbet%202026",
      soon: true,
    },
  ];
  return (
    <section
      id="malgrupper"
      style={{
        padding: "64px 24px",
        borderTop: "1px solid #e2e8f0",
        maxWidth: 1200,
        margin: "0 auto",
      }}
    >
      <div className="vc-eyebrow" style={{ marginBottom: 12 }}>
        Tre sätt att använda
      </div>
      <h2 className="vc-h2">
        Klassrummet, köksbordet — och snart{" "}
        <em style={{ color: "#dc4c2b", fontStyle: "normal" }}>
          er riktiga ekonomi.
        </em>
      </h2>
      <p
        style={{
          fontSize: 15,
          color: "#475569",
          marginTop: 16,
          marginBottom: 36,
          maxWidth: 680,
          lineHeight: 1.6,
        }}
      >
        Ekonomilabbet är byggt så att en lärare kan följa en hel klass och
        en förälder kan följa sina egna barn — i samma verktyg, med samma
        moduler och samma trygga sandlåda. 2026 öppnar vi en tredje vy:
        er riktiga familjeekonomi, säkert kopplad och visualiserad i
        samma karta.
      </p>
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))",
          gap: 18,
        }}
      >
        {ways.map((c, i) => (
          <article
            key={i}
            style={{
              background: c.soon ? "linear-gradient(180deg, #fff 0%, #fef3c7 100%)" : "#fff",
              border: c.soon ? "1px dashed #0f172a" : "1px solid #e2e8f0",
              borderRadius: 10,
              padding: 28,
              position: "relative",
            }}
          >
            {c.soon && (
              <span
                style={{
                  position: "absolute",
                  top: -10,
                  right: 18,
                  background: "#0f172a",
                  color: "#fff",
                  padding: "3px 9px",
                  borderRadius: 100,
                  fontSize: 10.5,
                  fontWeight: 600,
                  letterSpacing: 0.6,
                  fontFamily: 'ui-monospace, "SF Mono", monospace',
                  textTransform: "uppercase",
                }}
              >
                ● Kommer snart
              </span>
            )}
            <div className="vc-eyebrow" style={{ marginBottom: 8 }}>
              {c.kicker}
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
              {c.title}.
            </h3>
            {c.lead && (
              <p
                style={{
                  fontSize: 14,
                  lineHeight: 1.5,
                  color: "#64748b",
                  marginBottom: 18,
                  fontStyle: "italic",
                }}
              >
                {c.lead}
              </p>
            )}
            <ul style={{ listStyle: "none", padding: 0, margin: "0 0 24px 0" }}>
              {c.items.map((it, j) => (
                <li
                  key={j}
                  style={{
                    paddingLeft: 18,
                    position: "relative",
                    marginBottom: 10,
                    fontSize: 14,
                    lineHeight: 1.5,
                    color: "#475569",
                  }}
                >
                  <span
                    style={{ position: "absolute", left: 0, color: "#dc4c2b" }}
                  >
                    —
                  </span>
                  {it}
                </li>
              ))}
            </ul>
            {c.soon ? (
              <a
                href={c.href}
                className="vc-btn vc-btn-outline"
                style={{ borderColor: "#0f172a", textDecoration: "none" }}
              >
                {c.cta}
              </a>
            ) : (
              <Link
                to={c.href}
                className="vc-btn vc-btn-primary"
                style={{ textDecoration: "none" }}
              >
                {c.cta}
              </Link>
            )}
          </article>
        ))}
      </div>
    </section>
  );
}

// ---------- Pricing ----------

function Pricing() {
  return (
    <section
      id="pris"
      style={{
        padding: "64px 24px",
        borderTop: "1px solid #e2e8f0",
        maxWidth: 1100,
        margin: "0 auto",
      }}
    >
      <div className="vc-eyebrow" style={{ textAlign: "center", marginBottom: 12 }}>
        Pris
      </div>
      <h2 className="vc-h2" style={{ textAlign: "center" }}>
        Enkel prismodell.
      </h2>
      <p
        style={{
          fontSize: 15,
          color: "#475569",
          marginTop: 14,
          marginBottom: 32,
          maxWidth: 640,
          margin: "14px auto 32px",
          textAlign: "center",
        }}
      >
        Gratis under pilotåret 2026 — för skolor och familjer. Ingen
        bindningstid, inga dolda kostnader. Från 2027 sätts en avgift per
        användare i dialog med pilotkunderna.
      </p>
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))",
          gap: 18,
        }}
      >
        <div
          style={{
            background: "#fff",
            border: "2px solid #0f172a",
            borderRadius: 10,
            padding: 28,
          }}
        >
          <div className="vc-eyebrow" style={{ marginBottom: 12 }}>
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
              <li
                key={i}
                style={{ marginBottom: 6, color: "#475569", fontSize: 14 }}
              >
                · {t}
              </li>
            ))}
          </ul>
        </div>
        <div
          style={{
            background: "#fff",
            border: "1px solid #e2e8f0",
            borderRadius: 10,
            padding: 28,
          }}
        >
          <div className="vc-eyebrow" style={{ marginBottom: 12 }}>
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
            Per användare
          </div>
          <div style={{ marginBottom: 18, color: "#475569", fontSize: 14 }}>
            Nivå sätts tillsammans med pilotkunderna — troligen 50–100
            kr/användare/år. Familjer får ett enklare paketpris.
          </div>
          <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
            {[
              "Samma plattform, ingen funktionsnedskärning",
              "Tak för AI-användning",
              "Dedikerad support",
            ].map((t, i) => (
              <li
                key={i}
                style={{ marginBottom: 6, color: "#475569", fontSize: 14 }}
              >
                · {t}
              </li>
            ))}
          </ul>
        </div>
      </div>
    </section>
  );
}

// ---------- Moments ----------

function Moments() {
  return (
    <section
      style={{
        padding: "40px 24px 80px",
        maxWidth: 1100,
        margin: "0 auto",
      }}
    >
      <h2 className="vc-h2">
        Fem <em style={{ color: "#dc4c2b", fontStyle: "normal" }}>nyckelmoment.</em>
      </h2>
      <p
        style={{
          fontSize: 15,
          color: "#475569",
          marginTop: 16,
          marginBottom: 48,
          maxWidth: 540,
        }}
      >
        Det är vad den unga och den vuxna faktiskt gör — i ordning, månad
        för månad. Samma flöde i klassrummet som hemma.
      </p>
      <div style={{ display: "flex", flexDirection: "column", gap: 36 }}>
        {MOMENTS.map((m, i) => (
          <div
            key={m.n}
            style={{
              display: "grid",
              gridTemplateColumns: "minmax(0,1fr) minmax(0,1.2fr)",
              gap: 56,
              paddingTop: i === 0 ? 0 : 28,
              borderTop: i === 0 ? "none" : "1px solid #e2e8f0",
            }}
            className="vc-moment-row"
          >
            <style>{`
              @media (max-width: 768px) {
                .vc-moment-row { grid-template-columns: 1fr !important; gap: 20px !important; }
              }
            `}</style>
            <div>
              <div
                style={{
                  display: "inline-flex",
                  alignItems: "center",
                  justifyContent: "center",
                  width: 30,
                  height: 30,
                  borderRadius: "50%",
                  border: "1.5px solid #0f172a",
                  fontSize: 13,
                  fontWeight: 600,
                  marginBottom: 14,
                }}
              >
                {m.n}
              </div>
              <h3
                style={{
                  fontSize: 26,
                  fontWeight: 600,
                  letterSpacing: -0.6,
                  lineHeight: 1.15,
                  marginBottom: 12,
                }}
              >
                {m.title}.
              </h3>
              <p
                style={{
                  fontSize: 14,
                  lineHeight: 1.6,
                  color: "#475569",
                  maxWidth: 380,
                }}
              >
                {m.desc}
              </p>
            </div>
            <div
              className="vc-card"
              style={{
                padding: 16,
                minHeight: 180,
                fontFamily: 'ui-monospace, "SF Mono", monospace',
                fontSize: 11,
                color: "#64748b",
              }}
            >
              <MomentMock variant={m.n} />
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}

function MomentMock({ variant }: { variant: number }) {
  if (variant === 1) {
    return (
      <div>
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            borderBottom: "1px solid #e2e8f0",
            paddingBottom: 8,
            marginBottom: 12,
          }}
        >
          <span style={{ fontWeight: 600, color: "#0f172a" }}>
            Anna · Barista · Stockholm
          </span>
        </div>
        {[
          ["Nettolön nov", "23 450 kr"],
          ["Hyra", "−9 200 kr"],
          ["Mat & dryck", "−3 870 kr"],
          ["Sparande", "−1 500 kr"],
          ["Saldo idag", "8 880 kr"],
        ].map(([k, v]) => (
          <div
            key={k}
            style={{
              display: "flex",
              justifyContent: "space-between",
              padding: "5px 0",
            }}
          >
            <span>{k}</span>
            <span style={{ color: "#0f172a" }}>{v}</span>
          </div>
        ))}
      </div>
    );
  }
  if (variant === 2) {
    return (
      <div>
        <div style={{ marginBottom: 8 }}>Generering 2026-11</div>
        {[
          ["Kontoutdrag", "33 transaktioner"],
          ["Lönespec", "november"],
          ["Lånebesked", "1 år bunden"],
          ["Kortfaktura", "−7 240 kr"],
        ].map(([t, d], i) => (
          <div
            key={i}
            style={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              padding: "6px 0",
              borderBottom: "1px solid #e2e8f0",
            }}
          >
            <div>
              <div style={{ color: "#0f172a", fontWeight: 500 }}>{t}</div>
              <div style={{ fontSize: 10 }}>{d}</div>
            </div>
            <span
              style={{
                padding: "2px 8px",
                border: "1px solid #e2e8f0",
                borderRadius: 3,
              }}
            >
              PDF
            </span>
          </div>
        ))}
      </div>
    );
  }
  if (variant === 3) {
    return (
      <div>
        <div style={{ marginBottom: 10 }}>Budget vs faktiskt · november</div>
        {[
          ["Mat (planerat 4 000)", "3 870", 0.97],
          ["Nöje (planerat 1 500)", "2 410", 1.6],
          ["Hushåll (planerat 800)", "1 290", 1.6],
        ].map(([k, v, r], i) => (
          <div key={i} style={{ marginBottom: 8 }}>
            <div
              style={{
                display: "flex",
                justifyContent: "space-between",
                fontSize: 10,
                color: "#0f172a",
              }}
            >
              <span>{k as string}</span>
              <span>{v as string}</span>
            </div>
            <div
              style={{
                height: 4,
                background: "#e2e8f0",
                borderRadius: 2,
                overflow: "hidden",
                marginTop: 3,
              }}
            >
              <div
                style={{
                  height: "100%",
                  width: `${Math.min((r as number) * 60, 100)}%`,
                  background: (r as number) > 1 ? "#dc4c2b" : "#0f172a",
                }}
              />
            </div>
          </div>
        ))}
      </div>
    );
  }
  if (variant === 4) {
    return (
      <div>
        <div style={{ marginBottom: 8 }}>Bolåne-uppdrag · 36 mån horisont</div>
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "1fr 1fr",
            gap: 8,
            marginBottom: 10,
          }}
        >
          <div
            style={{
              padding: 10,
              border: "1.5px solid #0f172a",
              borderRadius: 4,
            }}
          >
            <div style={{ fontSize: 10 }}>Rörlig (slutvärde)</div>
            <div style={{ fontSize: 16, fontWeight: 700, color: "#0f172a" }}>
              3,25 %
            </div>
          </div>
          <div
            style={{
              padding: 10,
              border: "1px solid #e2e8f0",
              borderRadius: 4,
            }}
          >
            <div style={{ fontSize: 10 }}>3 år bunden</div>
            <div style={{ fontSize: 16, fontWeight: 700, color: "#0f172a" }}>
              3,90 %
            </div>
          </div>
        </div>
        <div style={{ fontSize: 10 }}>
          Snittränta över perioden: 3,5 % · Bunden hela perioden
        </div>
        <div
          style={{
            marginTop: 8,
            padding: 6,
            background: "#fef3c7",
            borderRadius: 3,
            fontSize: 10,
            color: "#0f172a",
          }}
        >
          Rörlig vann — 19 240 kr lägre kostnad
        </div>
      </div>
    );
  }
  return (
    <div>
      <div style={{ marginBottom: 8 }}>Klass 9A · 5 elever</div>
      <table style={{ width: "100%", fontSize: 10, borderCollapse: "collapse" }}>
        <thead style={{ color: "#64748b" }}>
          <tr>
            <th align="left">Elev</th>
            <th>Budget</th>
            <th>Bolån</th>
            <th align="right">Mastery</th>
          </tr>
        </thead>
        <tbody>
          {[
            ["Anna", "klar", "klar", "83%"],
            ["Edvard", "klar", "pågår", "71%"],
            ["Cassi", "pågår", "väntar", "54%"],
            ["Maja", "klar", "klar", "90%"],
            ["Erik", "pågår", "klar", "67%"],
          ].map((r, i) => (
            <tr key={i} style={{ borderTop: "1px solid #e2e8f0" }}>
              <td style={{ color: "#0f172a", padding: "5px 0" }}>{r[0]}</td>
              <td align="center">
                <span
                  style={{
                    padding: "1px 6px",
                    background: r[1] === "klar" ? "#d1fae5" : "#fef3c7",
                    borderRadius: 3,
                  }}
                >
                  {r[1]}
                </span>
              </td>
              <td align="center">
                <span
                  style={{
                    padding: "1px 6px",
                    background:
                      r[2] === "klar"
                        ? "#d1fae5"
                        : r[2] === "pågår"
                        ? "#fef3c7"
                        : "#fee2e2",
                    borderRadius: 3,
                  }}
                >
                  {r[2]}
                </span>
              </td>
              <td
                align="right"
                style={{ color: "#0f172a", fontWeight: 600 }}
              >
                {r[3]}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ---------- Logic ----------

function Logic() {
  return (
    <section
      style={{
        padding: "56px 24px",
        maxWidth: 1100,
        margin: "0 auto",
        borderTop: "1px solid #e2e8f0",
      }}
    >
      <div
        className="vc-eyebrow"
        style={{ textAlign: "center", marginBottom: 32 }}
      >
        Logiken
      </div>
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))",
          gap: 32,
        }}
      >
        {LOGIC.map((l) => (
          <div key={l.n}>
            <div
              className="vc-mono"
              style={{ fontSize: 11, color: "#64748b", marginBottom: 8 }}
            >
              {l.n}
            </div>
            <h3
              style={{
                fontSize: 22,
                fontWeight: 600,
                letterSpacing: -0.4,
                marginBottom: 10,
              }}
            >
              {l.title}.
            </h3>
            <p style={{ fontSize: 14, lineHeight: 1.6, color: "#475569" }}>
              {l.desc}
            </p>
          </div>
        ))}
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
          <span className="vc-eyebrow">FUNKTIONER · 09 / 09</span>
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
