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
import { useEffect, useState } from "react";
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
  { n: 31, sym: "Ba", name: "BankID", desc: "PIN-scen.", cat: "risk" },
  { n: 32, sym: "Mo", name: "Modul", desc: "7 steg", cat: "prof" },
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
  grund: { label: "Grundkompetens", count: 8 },
  fordj: { label: "Fördjupning", count: 8 },
  expert: { label: "Expert", count: 4 },
  konto: { label: "Konto & flöde", count: 4 },
  risk: { label: "Riskgrupp", count: 4 },
  prof: { label: "Professorns tillskott", count: 4 },
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
];

// ---------- Root ----------

export default function LandingVariantC() {
  return (
    <div
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
      @media (max-width: 768px) {
        .vc-h1 { font-size: 36px; letter-spacing: -1.2px; }
        .vc-h2 { font-size: 28px; }
      }
    `}</style>
  );
}

// ---------- Header ----------

function Header() {
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
        </Link>
        <nav style={{ display: "flex", gap: 4 }} className="vc-nav">
          {["Översikt", "Funktioner", "Pris", "FAQ"].map((t, i) => (
            <a
              key={t}
              href={`#${t.toLowerCase()}`}
              className={`vc-tab ${i === 0 ? "vc-tab-on" : "vc-tab-off"}`}
              style={{ textDecoration: "none" }}
            >
              {t}
            </a>
          ))}
        </nav>
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
        <Link
          to="/login"
          className="vc-btn vc-btn-ghost"
          style={{ textDecoration: "none" }}
        >
          Logga in
        </Link>
        <Link
          to="/signup/teacher"
          className="vc-btn vc-btn-primary"
          style={{ textDecoration: "none" }}
        >
          Kom igång →
        </Link>
      </div>
    </header>
  );
}

// ---------- Hero ----------

function Hero() {
  const [hovered, setHovered] = useState<number | null>(null);
  const [openCell, setOpenCell] = useState<CellInfo | null>(null);

  return (
    <section style={{ padding: "32px 24px 16px" }}>
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
            EKONOMILABBET / UTGÅVA 2026
          </span>
          <h1 className="vc-h1">
            Hushållsekonomi
            <br />
            <span style={{ color: "#dc4c2b" }}>på riktigt</span> —<br />
            för 13–19 år.
          </h1>
          <p
            style={{
              fontSize: 16,
              lineHeight: 1.55,
              marginTop: 22,
              color: "#475569",
              maxWidth: 460,
            }}
          >
            Ett verktyg för lärare, föräldrar, elever och barn. 32
            grundbegrepp, simulerade kontoutdrag, riktiga räntor, oväntade
            utgifter — eleven övar genom att göra, inte genom att läsa
            om det.
          </p>

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
        </div>

        <div className="vc-card" style={{ padding: 22 }}>
          <div style={{ marginBottom: 18 }}>
            <div className="vc-eyebrow" style={{ marginBottom: 4 }}>
              KURSPLAN-KARTA
            </div>
            <div style={{ fontSize: 16, fontWeight: 600 }}>
              Det periodiska systemet för pengar
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
    <div
      style={{
        display: "grid",
        gridTemplateColumns: "repeat(8, 1fr)",
        gap: 4,
      }}
    >
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

// ---------- Cell-modal (stub, fylls i fas A3) ----------

function CellModal({
  cell,
  onClose,
}: {
  cell: CellInfo;
  onClose: () => void;
}) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div
      role="dialog"
      aria-modal="true"
      onClick={onClose}
      style={{
        position: "fixed",
        inset: 0,
        background: "rgba(15,23,42,.55)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        padding: 16,
        zIndex: 50,
      }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          background: "#fff",
          border: "1px solid #e2e8f0",
          borderRadius: 12,
          padding: 24,
          maxWidth: 480,
          width: "100%",
        }}
      >
        <div style={{ fontSize: 20, fontWeight: 600 }}>{cell.name}</div>
        <p style={{ marginTop: 12, fontSize: 14, color: "#475569" }}>{cell.long}</p>
        <button
          onClick={onClose}
          className="vc-btn vc-btn-primary"
          style={{ marginTop: 16 }}
        >
          Stäng
        </button>
      </div>
    </div>
  );
}
