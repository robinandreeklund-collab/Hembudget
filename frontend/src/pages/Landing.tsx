/**
 * Landing.tsx — paper-design migrerat från demo3-periodic.html.
 *
 * Strukturen följer exakt demo3:
 *   Header → Hero (text + grid + prof) → Funktioner → Flow → Stats →
 *   Logiken-strip → Why → Social proof → Vyer → Pricing → FAQ →
 *   Founder-citat → CTA → Kontakt → Footer
 *
 * Alla 32 cellerna i hero-griden, eye-tracking, heatmap-toggle,
 * cell-modal och drift-partiklar är React-portade från standalone-HTML:en.
 */
import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "@/api/client";

// ---------- Cell-data (32 begrepp) ----------

type CellColor = "grund" | "fordj" | "expert" | "konto" | "risk" | "special";

type Cell = {
  num: number;
  sym: string;
  name: string;
  val: string;
  tip: string;
  color: CellColor;
};

const CELLS: Cell[] = [
  { num: 1, sym: "Lö", name: "Lön", val: "brutto · netto", tip: "Lön = bruttolön minus skatt = det du faktiskt får", color: "grund" },
  { num: 2, sym: "Sk", name: "Skatt", val: "kommun · stat", tip: "Skatt = din andel av samhället", color: "grund" },
  { num: 3, sym: "Bu", name: "Budget", val: "in − ut", tip: "Budget = planen innan pengarna försvinner", color: "grund" },
  { num: 4, sym: "Ku", name: "Kontoutdrag", val: "rörelser", tip: "Kontoutdrag = bankens dagbok över dig", color: "konto" },
  { num: 5, sym: "Ka", name: "Kategori", val: "mat · hyra", tip: "Kategorisering = första steget till förståelse", color: "grund" },
  { num: 6, sym: "Sa", name: "Saldo", val: "kontot nu", tip: "Saldo = sanningen just nu", color: "konto" },
  { num: 7, sym: "Sp", name: "Sparande", val: "buffert", tip: "Sparande = framtida du tackar nuvarande du", color: "fordj" },
  { num: 8, sym: "Hu", name: "Hushållskost.", val: "Konsumentv.", tip: "Hushållskostnader = vad det faktiskt kostar att leva", color: "fordj" },
  { num: 9, sym: "Bl", name: "Bolån", val: "räntebärande", tip: "Bolån = ditt största ekonomiska beslut", color: "fordj" },
  { num: 10, sym: "Am", name: "Amortering", val: "betala av", tip: "Amortering = att krympa skulden, inte bara räntan", color: "fordj" },
  { num: 11, sym: "Ov", name: "Oväntat", val: "buffert", tip: "Oväntat = tandläkare, kyl som går sönder, en tisdag", color: "risk" },
  { num: 12, sym: "Kk", name: "Kreditkort", val: "kostar om...", tip: "Kreditkort = bra verktyg, dålig vana", color: "risk" },
  { num: 13, sym: "Lp", name: "Långsiktig plan", val: "3–5 år", tip: "Långsiktig plan = du vet vart du är på väg", color: "expert" },
  { num: 14, sym: "Rb", name: "Räntebindning", val: "rörlig/bunden", tip: "Räntebindning = risk vs. förutsägbarhet", color: "expert" },
  { num: 15, sym: "AI", name: "Fråga Ekon", val: "Claude Sonnet", tip: "AI-coach som kan hela kursplanen", color: "special" },
  { num: 16, sym: "Pf", name: "Portfolio", val: "PDF-export", tip: "Portfolio-PDF = lärarens betygsunderlag", color: "special" },
  { num: 17, sym: "In", name: "Inkomst", val: "lön · bidrag", tip: "Inkomst = allt som kommer in", color: "konto" },
  { num: 18, sym: "Ut", name: "Utgift", val: "fast · rörlig", tip: "Utgift = allt som går ut", color: "konto" },
  { num: 19, sym: "Öv", name: "Överskott", val: "sparat", tip: "Överskott = pengar kvar i slutet av månaden", color: "konto" },
  { num: 20, sym: "Un", name: "Underskott", val: "varning", tip: "Underskott = du spenderade mer än du fick in", color: "risk" },
  { num: 21, sym: "Rä", name: "Ränta", val: "% per år", tip: "Ränta = priset för att låna pengar", color: "fordj" },
  { num: 22, sym: "Ef", name: "Effektiv ränta", val: "verkligt", tip: "Effektiv ränta = den ränta du faktiskt betalar inkl. avgifter", color: "fordj" },
  { num: 23, sym: "Rp", name: "Rubric", val: "bedömning", tip: "Rubric = lärarens betygskriterier per kompetens", color: "special" },
  { num: 24, sym: "Qr", name: "QR-kod", val: "login", tip: "QR-login = elev loggar in genom att skanna en kod", color: "special" },
  { num: 25, sym: "Pe", name: "Pension", val: "premie", tip: "Pension = lön du får utan att jobba — så småningom", color: "grund" },
  { num: 26, sym: "Fs", name: "Försäkring", val: "trygghet", tip: "Försäkring = du betalar lite varje månad för att slippa krasch", color: "grund" },
  { num: 27, sym: "Fo", name: "Fondspar.", val: "index", tip: "Fondsparande = långsiktigt ägande av flera bolag samtidigt", color: "fordj" },
  { num: 28, sym: "Ak", name: "Aktie", val: "ägarskap", tip: "Aktie = en liten del av ett bolag", color: "expert" },
  { num: 29, sym: "Sn", name: "SMS-lån", val: "undvik", tip: "SMS-lån = den dyraste formen av kredit", color: "risk" },
  { num: 30, sym: "Bg", name: "Bankgiro", val: "fakturor", tip: "Bankgiro = systemet svenska företag använder för räkningar", color: "konto" },
  { num: 31, sym: "Ba", name: "Batch-PDF", val: "scenarier", tip: "Batch = lärare genererar månadens dokument till hela klassen", color: "special" },
  { num: 32, sym: "Mo", name: "Modul", val: "7 steg", tip: "Modul = en kursvecka med läs/titta/reflektera/quiz/uppdrag", color: "special" },
];

// ---------- Default export ----------

export default function Landing() {
  return (
    <div className="bg-paper text-ink min-h-screen">
      <Header />
      <Hero />
      {/* TODO A2.2-A2.8: resterande sektioner */}
      <div className="max-w-7xl mx-auto px-6 py-20 text-center text-sm text-[#888] serif-italic">
        Landningssidan migreras till paper-stil — fler sektioner kommer i nästa commit.
      </div>
    </div>
  );
}

// ---------- Header ----------

function Header() {
  return (
    <header className="border-b border-rule">
      <div className="max-w-7xl mx-auto px-6 h-16 flex items-center justify-between">
        <Link to="/" className="flex items-center gap-3">
          <svg width="28" height="28" viewBox="0 0 40 40" aria-hidden="true">
            <circle cx="20" cy="20" r="18" fill="none" stroke="#111217" strokeWidth="2" />
            <text x="20" y="26" textAnchor="middle" fontFamily="Spectral" fontWeight="800" fontSize="18">Ek</text>
          </svg>
          <span className="serif text-xl">Ekonomilabbet</span>
        </Link>
        <nav className="hidden md:flex items-center gap-7 text-sm">
          <a href="#funktioner" className="nav-link">Funktioner</a>
          <a href="#flow" className="nav-link">Så funkar det</a>
          <a href="#pricing" className="nav-link">Pris</a>
          <a href="#faq" className="nav-link">FAQ</a>
          <a href="#kontakt" className="nav-link">Kontakt</a>
        </nav>
        <div className="flex gap-2">
          <Link to="/login/student" className="btn-outline text-sm px-4 py-2 rounded-md">
            Elevlogin
          </Link>
          <Link to="/login/teacher" className="btn-dark text-sm px-4 py-2 rounded-md">
            Lärarkonto
          </Link>
        </div>
      </div>
    </header>
  );
}

// ---------- Hero (text + grid + professor) ----------

function Hero() {
  // Hålls i Landing-state och drillas ner till PeriodicGrid + button.
  const [heatmapOn, setHeatmapOn] = useState(false);
  const [openCell, setOpenCell] = useState<Cell | null>(null);

  // Sätter body-klassen för heatmap-overlay (CSS triggar via .heatmap-on)
  useEffect(() => {
    document.body.classList.toggle("heatmap-on", heatmapOn);
    return () => {
      document.body.classList.remove("heatmap-on");
    };
  }, [heatmapOn]);

  return (
    <section className="relative max-w-7xl mx-auto px-6 pt-16 pb-12 grid md:grid-cols-[1fr_1.4fr] gap-12 items-start">
      <DriftParticles />
      <div className="relative z-[1]">
        <div className="eyebrow mb-5">Ekonomilabbet · utgåva 2026</div>
        <h1 className="serif text-5xl md:text-6xl leading-[1.02]">
          Det periodiska<br />systemet för pengar.
        </h1>
        <p className="mt-6 lead max-w-md">
          Från <span className="kbd">Lö</span> (lön) till <span className="kbd">Rb</span> (räntebindning) —
          32 grundbegrepp som en 16-åring behöver för att inte krocka med vuxenlivet.
          Hovra över en cell. Klassen ser resten.
        </p>
        <div className="mt-8 flex flex-wrap gap-3">
          <Link to="/login/teacher" className="btn-dark px-5 py-3 rounded-md">
            Prova experimentet
          </Link>
          <a href="#flow" className="btn-outline px-5 py-3 rounded-md">
            Se hur det funkar
          </a>
          <button
            type="button"
            onClick={() => setHeatmapOn((v) => !v)}
            aria-pressed={heatmapOn}
            className="btn-outline px-5 py-3 rounded-md"
          >
            {heatmapOn ? "Ta bort klassens värmekarta" : "Lägg på klassens värmekarta"}
          </button>
        </div>

        <ul className="mt-10 text-sm space-y-3">
          <li className="flex items-center gap-3"><LegendDot bg="#eef3ff" />Grundkompetens (5)</li>
          <li className="flex items-center gap-3"><LegendDot bg="#fff3e6" />Fördjupning (5)</li>
          <li className="flex items-center gap-3"><LegendDot bg="#f3eaff" />Expert (2)</li>
          <li className="flex items-center gap-3"><LegendDot bg="#e8f7ef" />Konto &amp; flöde</li>
          <li className="flex items-center gap-3"><LegendDot bg="#fdecec" />Riskgrupp</li>
          <li className="flex items-center gap-3"><LegendDot bg="#111217" />Professorns tillskott</li>
        </ul>
      </div>

      <div className="relative z-[1]">
        <ProfessorWithBubble />
        <PeriodicGrid onPick={setOpenCell} />
        <p className="mt-4 text-xs text-[#777] serif-italic">
          Prototyp · 32 celler motsvarar 12 kompetenser + 20 stödbegrepp i kursplan 2026.
        </p>
      </div>

      {openCell && <CellModal cell={openCell} onClose={() => setOpenCell(null)} />}
    </section>
  );
}

function LegendDot({ bg }: { bg: string }) {
  return (
    <span
      className="inline-block w-2.5 h-2.5 border border-ink"
      style={{ background: bg }}
    />
  );
}

// ---------- Periodic-grid (32 celler) ----------

function PeriodicGrid({ onPick }: { onPick: (c: Cell) => void }) {
  // Deterministiska heatmap-värden per cellposition (0-1)
  const heat = [
    0.92, 0.74, 0.88, 0.82, 0.71, 0.66, 0.54, 0.48,
    0.38, 0.32, 0.64, 0.58, 0.22, 0.18, 0.41, 0.36,
    0.52, 0.46, 0.42, 0.28, 0.26, 0.14, 0.50, 0.71,
    0.67, 0.55, 0.34, 0.12, 0.08, 0.44, 0.62, 0.58,
  ];

  // Pilar mellan celler (8-kolumn grid)
  function onKeyDown(e: React.KeyboardEvent<HTMLDivElement>) {
    const focused = document.activeElement as HTMLElement | null;
    if (!focused?.classList.contains("elem")) return;
    const cells = Array.from(
      e.currentTarget.querySelectorAll<HTMLElement>(".elem")
    );
    const idx = cells.indexOf(focused);
    if (idx < 0) return;
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      const cell = CELLS[idx];
      if (cell) onPick(cell);
      return;
    }
    const dx = e.key === "ArrowRight" ? 1 : e.key === "ArrowLeft" ? -1 : 0;
    const dy = e.key === "ArrowDown" ? 1 : e.key === "ArrowUp" ? -1 : 0;
    if (dx === 0 && dy === 0) return;
    e.preventDefault();
    const cols = window.innerWidth >= 768 ? 8 : 4;
    const next = idx + dx + dy * cols;
    if (cells[next]) cells[next].focus();
  }

  return (
    <div
      className="grid grid-cols-4 md:grid-cols-8 gap-1.5"
      role="grid"
      aria-label="Periodiska systemet för pengar — 32 begrepp"
      onKeyDown={onKeyDown}
    >
      {CELLS.map((c, i) => (
        <button
          key={c.num}
          type="button"
          role="gridcell"
          tabIndex={0}
          onClick={() => onPick(c)}
          className={`elem ${c.color}`}
          aria-label={`${c.name}, ${c.val}. ${c.tip}`}
          style={{ ["--h" as never]: String(heat[i] ?? 0) }}
        >
          <span className="num">{c.num}</span>
          <span>
            <span className="sym block">{c.sym}</span>
            <span className="name block">{c.name}</span>
          </span>
          <span className="val">{c.val}</span>
          <span className="elem-tooltip">{c.tip}</span>
          <span className="heatmap" />
        </button>
      ))}
    </div>
  );
}

// ---------- Cell-modal ----------

function CellModal({ cell, onClose }: { cell: Cell; onClose: () => void }) {
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
      className="fixed inset-0 z-40 bg-ink/55 flex items-center justify-center p-4"
    >
      <div
        onClick={(e) => e.stopPropagation()}
        className="bg-white rounded-xl p-7 max-w-md w-full shadow-2xl"
      >
        <div className="serif text-4xl">{cell.sym}</div>
        <div className="text-lg font-semibold mt-1">{cell.name}</div>
        <div className="text-sm text-[#666] mt-0.5">{cell.val}</div>
        <p className="mt-3 text-[#333]">{cell.tip}</p>
        <div className="mt-4 text-xs text-[#888]">
          Tränas i modulen "Din första månad" · steg 1–7
        </div>
        <button
          onClick={onClose}
          className="btn-dark mt-5 px-4 py-2 rounded text-sm"
        >
          Stäng
        </button>
      </div>
    </div>
  );
}

// ---------- Professor + speech-bubble ----------

function ProfessorWithBubble() {
  const eyeLRef = useRef<SVGCircleElement | null>(null);
  const eyeRRef = useRef<SVGCircleElement | null>(null);
  const svgRef = useRef<SVGSVGElement | null>(null);

  useEffect(() => {
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (reduce) return;
    const onMove = (e: MouseEvent) => {
      const svg = svgRef.current;
      if (!svg || !eyeLRef.current || !eyeRRef.current) return;
      const r = svg.getBoundingClientRect();
      const cx = r.left + r.width / 2;
      const cy = r.top + r.height / 2;
      const dx = Math.max(-1, Math.min(1, (e.clientX - cx) / 200));
      const dy = Math.max(-1, Math.min(1, (e.clientY - cy) / 200));
      eyeLRef.current.setAttribute("cx", String(48 + dx * 2));
      eyeLRef.current.setAttribute("cy", String(68 + dy * 2));
      eyeRRef.current.setAttribute("cx", String(72 + dx * 2));
      eyeRRef.current.setAttribute("cy", String(68 + dy * 2));
    };
    window.addEventListener("mousemove", onMove);
    return () => window.removeEventListener("mousemove", onMove);
  }, []);

  return (
    <div className="prof-wrap" aria-hidden="true">
      <div className="prof-bubble">
        Hovra över en cell — eleven ser samma karta som du.
      </div>
      <svg ref={svgRef} className="prof-svg" viewBox="0 0 120 120">
        <ellipse cx="60" cy="70" rx="36" ry="38" fill="#ffd7b0" stroke="#111" strokeWidth="3" />
        <path
          d="M24 50 Q10 10 40 30 Q30 -5 60 20 Q90 -5 80 30 Q110 10 96 50 Q105 70 80 60 L40 60 Q15 70 24 50Z"
          fill="#fff" stroke="#111" strokeWidth="3"
        />
        <circle cx="48" cy="68" r="8" fill="#fff" stroke="#111" strokeWidth="2.5" />
        <circle cx="72" cy="68" r="8" fill="#fff" stroke="#111" strokeWidth="2.5" />
        <circle ref={eyeLRef} cx="48" cy="68" r="3" fill="#111" />
        <circle ref={eyeRRef} cx="72" cy="68" r="3" fill="#111" />
        <path d="M48 88 Q60 96 72 88" stroke="#111" strokeWidth="2.5" fill="none" />
        <path d="M30 58 L40 50 M90 58 L80 50" stroke="#111" strokeWidth="2.5" />
      </svg>
    </div>
  );
}

// ---------- Drift-partiklar bakom hero ----------

function DriftParticles() {
  const [particles] = useState(() => {
    const arr: { top: number; left: number; dx: number; dy: number; dur: number }[] = [];
    for (let i = 0; i < 18; i++) {
      arr.push({
        top: Math.random() * 100,
        left: Math.random() * 100,
        dx: (Math.random() - 0.5) * 120,
        dy: (Math.random() - 0.5) * 120,
        dur: 6 + Math.random() * 8,
      });
    }
    return arr;
  });
  return (
    <div className="absolute inset-0 overflow-hidden pointer-events-none z-0" aria-hidden="true">
      {particles.map((p, i) => (
        <span
          key={i}
          className="particle drifting"
          style={{
            top: `${p.top}%`,
            left: `${p.left}%`,
            ["--dx" as never]: `${p.dx}px`,
            ["--dy" as never]: `${p.dy}px`,
            ["--dur" as never]: `${p.dur}s`,
          }}
        />
      ))}
    </div>
  );
}

// Notera: api är importerad ovan men används inte än —
// kommer in i A2.5 (stats-fetch). Förhindrar tsc-fel.
void api;
