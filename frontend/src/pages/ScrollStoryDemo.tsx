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

type WeekData = {
  number: 1 | 2 | 3;
  theme: string;
  startWb: WBScores;
  chapters: Chapter[];
};

const START: WBScores = { ek: 50, hl: 62, sb: 50, fr: 50, tr: 60 };

const WEEKS: WeekData[] = [
  // ─── Vecka 1 — Optimism ───
  {
    number: 1,
    theme: "Första lönen, första valen",
    startWb: START,
    chapters: [
      {
        id: "v1-mon",
        range: "Vecka 1 · måndag 09:14",
        title: "Lönesamtalet",
        body:
          "Du börjar med ett lönesamtal. Marknadslönen ligger 1 500 kr över dig — du argumenterar och Maria höjer 3,2 %. Trygghet stiger.",
        delta: "+3,2 % lön · Trygghet ↗",
        wb: { ek: 58, hl: 62, sb: 50, fr: 50, tr: 68 },
      },
      {
        id: "v1-wed",
        range: "Vecka 1 · onsdag",
        title: "5 000 kr till ISK",
        body:
          "Nytt sparmål: 25 % av lönen direkt till ISK. Du köper Volvo B (10 st) och Ericsson B (15 st). Bufferten blir två månadshyror.",
        delta: "+5 000 kr till ISK · Ekonomi ↗",
        wb: { ek: 70, hl: 62, sb: 50, fr: 50, tr: 70 },
      },
      {
        id: "v1-fri",
        range: "Vecka 1 · fredag 17:33",
        title: 'Du säger ja till bion',
        body:
          'Kompisen pingar — 180 kr för biobiljett + popcorn. Du säger ja. Sociala band stiger 4, fritiden plus 3. Saldot är fortfarande grönt.',
        delta: "−180 kr · Sociala +4 · Fritid +3",
        wb: { ek: 67, hl: 62, sb: 64, fr: 58, tr: 70 },
      },
    ],
  },

  // ─── Vecka 2 — Det oväntade ───
  {
    number: 2,
    theme: "Det oväntade",
    startWb: { ek: 67, hl: 62, sb: 64, fr: 58, tr: 70 },
    chapters: [
      {
        id: "v2-mon",
        range: "Vecka 2 · måndag 06:48",
        title: "Maria har glömt passerkortet",
        body:
          'Slumpad arbetsplats-fråga: "Din kollega ringer 06:45 — kan du hämta henne?" Du svarar ja, vi täcker varandra. Chefen noterar +4 satisfaction.',
        delta: "Satisfaction 62 → 72",
        wb: { ek: 67, hl: 62, sb: 64, fr: 58, tr: 72 },
      },
      {
        id: "v2-wed",
        range: "Vecka 2 · onsdag 14:02",
        title: "Tandläkare akut — 2 400 kr",
        body:
          'Oväntad utgift. Bufferten dippar med en månads sparande. Nu märker du varför reservfonden inte ska vara tre veckors hyra.',
        delta: "−2 400 kr · Trygghet ↘",
        wb: { ek: 60, hl: 60, sb: 64, fr: 58, tr: 60 },
      },
      {
        id: "v2-fri",
        range: "Vecka 2 · fredag 17:31",
        title: "Aktiemarknaden ner 3,2 %",
        body:
          'Volvo B och en H&M-position drar ner portföljen 784 kr. Wellbeing-Trygghet räknar med λ ≈ 2,0 — förlusten gör dubbelt så ont som motsvarande vinst hade gett.',
        delta: "Trygghet rasar 2× hårdare",
        wb: { ek: 55, hl: 58, sb: 64, fr: 55, tr: 45 },
      },
    ],
  },

  // ─── Vecka 3 — Krisen och insikten ───
  {
    number: 3,
    theme: "Krisen och insikten",
    startWb: { ek: 55, hl: 58, sb: 64, fr: 55, tr: 45 },
    chapters: [
      {
        id: "v3-mon",
        range: "Vecka 3 · måndag 19:18",
        title: "Hyran går inte ihop",
        body:
          'Hyran 8 500 kr ska dras imorgon. Saldot är 7 300 kr. Du saknar 1 200 kr. Systemet pausar transaktionen och tvingar fram ett beslut.',
        delta: "Saknas: −1 200 kr",
        wb: { ek: 42, hl: 56, sb: 64, fr: 52, tr: 40 },
      },
      {
        id: "v3-wed",
        range: "Vecka 3 · onsdag 09:34",
        title: "Privatlån via banken",
        body:
          'Du väljer privatlån 6,4 % över 36 mån istället för SMS-lån (117 % APR). Banken kör kreditupplysning, du signerar med EkonomilabbetID. Lugnt val — ränta i normalsegmentet.',
        delta: "Lånar 1 500 kr · EkonomiSkalan 700 → 680",
        wb: { ek: 50, hl: 58, sb: 64, fr: 55, tr: 52 },
      },
      {
        id: "v3-fri",
        range: "Vecka 3 · fredag · Aktie-eftertanke",
        title: "Loss-aversion-quotient: 1,8×",
        body:
          'Spegeln 60 dagar senare: du säljer 1,8× oftare i förlust än i vinst. Du säljer för snabbt när det går ner, för långsamt när det går upp. Klassiskt nybörjarmönster — och fixbart.',
        delta: "Insikt → Wellbeing stabiliseras",
        wb: { ek: 56, hl: 62, sb: 66, fr: 60, tr: 62 },
      },
    ],
  },
];

// Bekvämlighet — alla kapitel i ordning (om vi behöver lista all-in-one t.ex.
// i reduced-motion-fallbacken).
const ALL_CHAPTERS: Chapter[] = WEEKS.flatMap((w) => w.chapters);

const REDUCED_THEME = {
  bg: "linear-gradient(180deg, #f0f9ff 0%, #fafaf9 50%, #ffffff 100%)",
  fg: "#0f172a",
  accent: "#dc4c2b",
  amber: "#fbbf24",
};

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
      {reduced ? (
        <ReducedMotionStory />
      ) : (
        <>
          <WeekStory week={WEEKS[0]} />
          <HorizontalGallery
            label="Vecka 1 i bilder"
            intro="Snabb återblick på det du gjorde — lönen, ISK-köpet, bio-eventet. Skärmar du skulle se i din egen elev-vy."
          >
            <PayslipCard />
            <PortfolioCard />
            <WellbeingMiniCard
              score={wellbeingScore(WEEKS[0].chapters[2].wb)}
              wb={WEEKS[0].chapters[2].wb}
              label="efter vecka 1"
            />
            <EventLogCard
              rows={[
                { ts: "mån 09:14", text: "Lönesamtal — 3,2 % höjning", delta: "+ 1 184 kr/mån", tone: "good" },
                { ts: "ons 12:30", text: "Överföring till ISK", delta: "− 5 000 kr", tone: "neutral" },
                { ts: "ons 12:31", text: "Köpte Volvo B + Ericsson B", delta: "− 4 290 kr", tone: "neutral" },
                { ts: "fre 17:33", text: "Bio på Filmstaden — ja", delta: "− 180 kr", tone: "good" },
              ]}
            />
            <EchoCard
              quote='"Du sa ja till bion. Vad var viktigast — vänskapen eller filmen?"'
              response="Notera vad som triggade beslutet. Var det FOMO eller en genuin lust att se folk?"
            />
          </HorizontalGallery>

          <WeekStory week={WEEKS[1]} />
          <HorizontalGallery
            label="Vecka 2 i bilder"
            intro="Det oväntade träffar tre gånger på en vecka. Så här ser konsekvenserna ut i systemet."
          >
            <SatisfactionCard from={62} to={72} />
            <BankDocCard
              title="Faktura · Tandläkare"
              issuer="Folktandvården Stockholm"
              amount="2 400 kr"
              due="14 nov 2026"
              warning="Bufferten räcker — knappt. En månad till och vi hade trillat under."
            />
            <LossAversionCard />
            <WellbeingMiniCard
              score={wellbeingScore(WEEKS[1].chapters[2].wb)}
              wb={WEEKS[1].chapters[2].wb}
              label="efter vecka 2"
            />
            <EchoCard
              quote='"Aktierna föll 3,2 %. Hur kändes det?"'
              response="Förlusten gör dubbelt så ont som motsvarande vinst hade gett. Det är inte i ditt huvud — det är i din kropp. Och i din mätare."
            />
          </HorizontalGallery>

          <WeekStory week={WEEKS[2]} />
        </>
      )}
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
// WeekStory — pinnad scroll-storytelling per vecka. Tar en WeekData
// som driver kapitellistan och Wellbeing-pentagonens startpunkt.
// Återanvänds 3 gånger (vecka 1/2/3) i master-flödet.
// ─────────────────────────────────────────────────────────────
function WeekStory({ week }: { week: WeekData }) {
  const sectionRef = useRef<HTMLDivElement | null>(null);
  const polyRef = useRef<SVGPolygonElement | null>(null);
  const dotsRef = useRef<SVGGElement | null>(null);
  const scoreRef = useRef<SVGTextElement | null>(null);
  const stepRefs = useRef<(HTMLDivElement | null)[]>([]);
  const progressBarRef = useRef<HTMLDivElement | null>(null);
  const counterRef = useRef<HTMLDivElement | null>(null);

  const chapters = week.chapters;

  useEffect(() => {
    if (!sectionRef.current || !polyRef.current) return;
    registerScrollTrigger();
    const el = sectionRef.current;

    const ctx = gsap.context(() => {
      // Wellbeing-state — startar där föregående vecka slutade (eller på
      // veckans egen startpunkt om det är vecka 1). Animeras genom
      // kapitlens målvärden via gsap.to + onUpdate.
      const wb = { ...week.startWb };
      const updatePoly = () => {
        if (polyRef.current) {
          polyRef.current.setAttribute("points", polyFor(wb));
        }
        if (dotsRef.current) {
          DIMS.forEach((d, i) => {
            const [x, y] = point(i, wb[d.key]);
            const c = dotsRef.current!.children[i] as SVGCircleElement | undefined;
            if (c) {
              c.setAttribute("cx", String(x));
              c.setAttribute("cy", String(y));
            }
          });
        }
        if (scoreRef.current) {
          scoreRef.current.textContent = String(wellbeingScore(wb));
        }
      };
      updatePoly();

      // Master-tidslinje pinnad mot sektionen. End=400% ger ~4 viewport-höjder
      // av scroll, scrub=1.2 → filmisk smoothness.
      const tl = gsap.timeline({
        scrollTrigger: {
          trigger: el,
          start: "top top",
          end: "+=200%",
          pin: true,
          scrub: 1.2,
          anticipatePin: 1,
          onUpdate: (self) => {
            if (progressBarRef.current) {
              progressBarRef.current.style.width = `${self.progress * 100}%`;
            }
            if (counterRef.current) {
              const idx = Math.min(
                chapters.length - 1,
                Math.floor(self.progress * chapters.length),
              );
              counterRef.current.textContent =
                `Vecka ${week.number} · ${idx + 1} / ${chapters.length}`;
            }
          },
        },
      });

      // Varje kapitel pågår ~1 enhet på tidslinjen → 3 kapitel/vecka = 3 enheter.
      // Före varje kapitel: bleknar föregående ut, nästa in. Wellbeing morphar
      // till kapitlets målvärden.
      chapters.forEach((c, i) => {
        const stepEl = stepRefs.current[i];
        if (!stepEl) return;
        const t = i;
        // Fade in current step
        tl.fromTo(
          stepEl,
          { autoAlpha: 0, y: 24 },
          { autoAlpha: 1, y: 0, duration: 0.4, ease: "power2.out" },
          t,
        );
        // Wellbeing morph mot kapitel-mål
        tl.to(
          wb,
          {
            ek: c.wb.ek,
            hl: c.wb.hl,
            sb: c.wb.sb,
            fr: c.wb.fr,
            tr: c.wb.tr,
            duration: 0.8,
            ease: "power2.inOut",
            onUpdate: updatePoly,
          },
          t,
        );
        // Fade out before next chapter (utom sista)
        if (i < chapters.length - 1) {
          tl.to(
            stepEl,
            { autoAlpha: 0, y: -24, duration: 0.4, ease: "power2.in" },
            t + 0.7,
          );
        }
      });
    }, sectionRef);

    return () => ctx.revert();
  }, [chapters, week.number, week.startWb]);

  return (
    <section
      ref={sectionRef}
      style={{
        height: "100vh",
        background:
          "radial-gradient(ellipse at top, #1e293b 0%, #0f172a 50%, #020617 100%)",
        color: "#fff",
        position: "relative",
        overflow: "hidden",
      }}
    >
      {/* Progress-stripe i toppen */}
      <div
        style={{
          position: "absolute",
          top: 0,
          left: 0,
          right: 0,
          height: 3,
          background: "rgba(255,255,255,0.08)",
          zIndex: 5,
        }}
      >
        <div
          ref={progressBarRef}
          style={{
            height: "100%",
            width: "0%",
            background:
              "linear-gradient(90deg, #fbbf24 0%, #dc4c2b 100%)",
            transition: "width .1s linear",
          }}
        />
      </div>

      {/* Vecka + kapitelräknare (övre vänstra) */}
      <div
        style={{
          position: "absolute",
          top: 24,
          left: 24,
          fontFamily: "ui-monospace, monospace",
          fontSize: 11,
          letterSpacing: 1.4,
          color: "#94a3b8",
          textTransform: "uppercase",
          zIndex: 5,
          maxWidth: "min(360px, 60vw)",
        }}
      >
        <div ref={counterRef} style={{ color: "#fbbf24", marginBottom: 4 }}>
          Vecka {week.number} · 1 / {chapters.length}
        </div>
        <div style={{ fontSize: 10.5, letterSpacing: 1, color: "#64748b" }}>
          Akt {week.number} · {week.theme}
        </div>
      </div>

      {/* Bakgrundsavatar — student vid skrivbord (subtilt) */}
      <DeskScene />

      {/* Centrum: Wellbeing-pentagon */}
      <div
        style={{
          position: "absolute",
          top: "50%",
          left: "50%",
          transform: "translate(-50%, -50%)",
          width: "min(420px, 60vw)",
          aspectRatio: "1 / 1",
          opacity: 0.95,
        }}
      >
        <svg viewBox="0 0 400 400" style={{ width: "100%", height: "100%" }}>
          {/* Koncentriska ringar */}
          {[0.25, 0.5, 0.75, 1].map((r, i) => (
            <polygon
              key={i}
              points={DIMS.map((_, j) => {
                const a = angleAt(j);
                return `${CX + Math.cos(a) * R * r},${CY + Math.sin(a) * R * r}`;
              }).join(" ")}
              fill="none"
              stroke="rgba(255,255,255,0.08)"
              strokeWidth="1"
            />
          ))}
          {/* Axlar */}
          {DIMS.map((_, i) => {
            const [x, y] = point(i, 100);
            return (
              <line
                key={i}
                x1={CX}
                y1={CY}
                x2={x}
                y2={y}
                stroke="rgba(255,255,255,0.06)"
                strokeWidth="1"
              />
            );
          })}
          {/* Data-polygon (animeras) */}
          <polygon
            ref={polyRef}
            points={polyFor(week.startWb)}
            fill="rgba(251,191,36,0.18)"
            stroke="#fbbf24"
            strokeWidth="2.4"
          />
          {/* Hörn-dots (animeras) */}
          <g ref={dotsRef}>
            {DIMS.map((d, i) => {
              const [x, y] = point(i, week.startWb[d.key]);
              return (
                <circle key={i} cx={x} cy={y} r="5" fill="#fbbf24" />
              );
            })}
          </g>
          {/* Etiketter */}
          {DIMS.map((d, i) => {
            const a = angleAt(i);
            const lr = R + 30;
            const lx = CX + Math.cos(a) * lr;
            const ly = CY + Math.sin(a) * lr + 4;
            return (
              <text
                key={i}
                x={lx}
                y={ly}
                textAnchor="middle"
                fontSize="11"
                fontWeight="600"
                fill="#cbd5e1"
                fontFamily="ui-monospace, monospace"
              >
                {d.label}
              </text>
            );
          })}
          {/* Score i mitten (animeras) */}
          <text
            ref={scoreRef}
            x={CX}
            y={CY - 4}
            textAnchor="middle"
            fontSize="56"
            fontWeight="700"
            fill="#fff"
          >
            {wellbeingScore(week.startWb)}
          </text>
          <text
            x={CX}
            y={CY + 22}
            textAnchor="middle"
            fontSize="11"
            fill="#94a3b8"
            fontFamily="ui-monospace, monospace"
            letterSpacing="2"
          >
            WELLBEING
          </text>
        </svg>
      </div>

      {/* Kapitelkort — alla renderas, GSAP fade:ar mellan dem */}
      <div
        style={{
          position: "absolute",
          left: "min(56px, 5vw)",
          bottom: "min(72px, 7vh)",
          maxWidth: "min(440px, 80vw)",
          zIndex: 4,
        }}
      >
        {chapters.map((c, i) => (
          <div
            key={c.id}
            ref={(el) => (stepRefs.current[i] = el)}
            style={{
              position: i === 0 ? "relative" : "absolute",
              top: i === 0 ? "auto" : 0,
              left: i === 0 ? "auto" : 0,
              opacity: i === 0 ? 1 : 0,
              background: "rgba(15,23,42,0.85)",
              backdropFilter: "blur(8px)",
              border: "1px solid rgba(251,191,36,0.25)",
              borderRadius: 14,
              padding: "20px 22px",
              maxWidth: 440,
            }}
          >
            <div
              style={{
                fontFamily: "ui-monospace, monospace",
                fontSize: 11,
                letterSpacing: 1.2,
                color: "#fbbf24",
                marginBottom: 8,
                textTransform: "uppercase",
                fontWeight: 600,
              }}
            >
              ● {c.range}
            </div>
            <h3
              style={{
                fontSize: 22,
                fontWeight: 600,
                letterSpacing: -0.4,
                margin: "0 0 10px",
                color: "#fff",
                lineHeight: 1.2,
              }}
            >
              {c.title}
            </h3>
            <p
              style={{
                fontSize: 14.5,
                lineHeight: 1.55,
                color: "#cbd5e1",
                margin: 0,
              }}
            >
              {c.body}
            </p>
            {c.delta && (
              <div
                style={{
                  marginTop: 12,
                  paddingTop: 12,
                  borderTop: "1px dashed rgba(255,255,255,0.1)",
                  fontFamily: "ui-monospace, monospace",
                  fontSize: 12.5,
                  color: "#10b981",
                  letterSpacing: 0.4,
                }}
              >
                → {c.delta}
              </div>
            )}
          </div>
        ))}
      </div>

    </section>
  );
}

// ─────────────────────────────────────────────────────────────
// DeskScene — abstrakt SVG-bakgrund med skrivbord + laptop
// ─────────────────────────────────────────────────────────────
function DeskScene() {
  return (
    <svg
      viewBox="0 0 1200 800"
      preserveAspectRatio="xMidYMid slice"
      style={{
        position: "absolute",
        inset: 0,
        width: "100%",
        height: "100%",
        opacity: 0.08,
        zIndex: 1,
      }}
    >
      {/* Skrivbord */}
      <line
        x1="0"
        y1="620"
        x2="1200"
        y2="620"
        stroke="#fbbf24"
        strokeWidth="1.5"
      />
      {/* Laptop */}
      <rect
        x="540"
        y="540"
        width="160"
        height="100"
        rx="6"
        fill="none"
        stroke="#fbbf24"
        strokeWidth="1.5"
      />
      <line x1="540" y1="640" x2="700" y2="640" stroke="#fbbf24" strokeWidth="1.5" />
      <line x1="510" y1="650" x2="730" y2="650" stroke="#fbbf24" strokeWidth="1.5" />
      {/* Telefon */}
      <rect
        x="730"
        y="595"
        width="40"
        height="60"
        rx="6"
        fill="none"
        stroke="#fbbf24"
        strokeWidth="1.5"
      />
      {/* Mugg */}
      <rect
        x="450"
        y="600"
        width="50"
        height="40"
        rx="2"
        fill="none"
        stroke="#fbbf24"
        strokeWidth="1.5"
      />
      <path
        d="M500 615 Q510 615 510 625 Q510 635 500 635"
        fill="none"
        stroke="#fbbf24"
        strokeWidth="1.5"
      />
      {/* Skrivbordslampa */}
      <line x1="380" y1="620" x2="380" y2="540" stroke="#fbbf24" strokeWidth="1.5" />
      <path d="M360 540 L400 540 L390 510 L370 510 Z" fill="none" stroke="#fbbf24" strokeWidth="1.5" />
      {/* Avatar — siluett av en person */}
      <circle cx="620" cy="430" r="32" fill="none" stroke="#fbbf24" strokeWidth="1.5" />
      <path
        d="M580 540 Q580 470 620 470 Q660 470 660 540"
        fill="none"
        stroke="#fbbf24"
        strokeWidth="1.5"
      />
    </svg>
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
          Tre veckor i nio kapitel
        </div>
        <h2 className="ssd-h2" style={{ marginBottom: 24, color: "#fff" }}>
          Du har valt minskad rörelse — så här ser kapitlen ut.
        </h2>
        <ol style={{ listStyle: "none", padding: 0, margin: 0, display: "flex", flexDirection: "column", gap: 18 }}>
          {ALL_CHAPTERS.map((c, i) => (
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
// HorizontalGallery — interlude mellan veckor.
// Pinnad sektion med horisontellt scroll-track som scrubbas vänster
// → höger när användaren scrollar vertikalt. GSAP-mönster:
// translateX:as från 0 till -(track.scrollWidth - viewportWidth).
// ─────────────────────────────────────────────────────────────
function HorizontalGallery({
  label,
  intro,
  children,
}: {
  label: string;
  intro: string;
  children: React.ReactNode;
}) {
  const sectionRef = useRef<HTMLDivElement | null>(null);
  const trackRef = useRef<HTMLDivElement | null>(null);
  const reduced = useReducedMotion();

  useEffect(() => {
    if (reduced || !sectionRef.current || !trackRef.current) return;
    registerScrollTrigger();
    const track = trackRef.current;
    const ctx = gsap.context(() => {
      gsap.to(track, {
        x: () => -(track.scrollWidth - window.innerWidth),
        ease: "none",
        scrollTrigger: {
          trigger: sectionRef.current,
          start: "top top",
          end: () => `+=${Math.max(track.scrollWidth - window.innerWidth, 1)}`,
          pin: true,
          scrub: 1,
          invalidateOnRefresh: true,
          anticipatePin: 1,
        },
      });
    }, sectionRef);
    return () => ctx.revert();
  }, [reduced]);

  // Reduced-motion: bara vertikal lista med samma kort.
  if (reduced) {
    return (
      <section
        style={{
          padding: "48px 24px",
          background: "#fafaf9",
          color: "#0f172a",
        }}
      >
        <div style={{ maxWidth: 720, margin: "0 auto" }}>
          <div className="ssd-eyebrow" style={{ marginBottom: 8 }}>
            {label}
          </div>
          <p style={{ fontSize: 15, color: "#475569", marginBottom: 24, maxWidth: 540 }}>
            {intro}
          </p>
          <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>
            {children}
          </div>
        </div>
      </section>
    );
  }

  return (
    <section
      ref={sectionRef}
      style={{
        height: "100vh",
        background: "linear-gradient(180deg, #fafaf9 0%, #fef3c7 100%)",
        color: "#0f172a",
        position: "relative",
        overflow: "hidden",
      }}
    >
      {/* Vänster panel — fixed label medan tracket scrubbar */}
      <div
        style={{
          position: "absolute",
          top: "50%",
          left: "min(48px, 4vw)",
          transform: "translateY(-50%)",
          maxWidth: "min(280px, 28vw)",
          zIndex: 5,
        }}
      >
        <div
          className="ssd-mono"
          style={{
            fontSize: 11,
            letterSpacing: 1.6,
            color: "#dc4c2b",
            textTransform: "uppercase",
            marginBottom: 12,
            fontWeight: 600,
          }}
        >
          ● Mellanakt
        </div>
        <h3
          style={{
            fontSize: "clamp(22px, 2.6vw, 30px)",
            fontWeight: 600,
            letterSpacing: -0.4,
            lineHeight: 1.15,
            margin: "0 0 12px",
            color: "#0f172a",
          }}
        >
          {label}
        </h3>
        <p
          style={{
            fontSize: 13.5,
            lineHeight: 1.55,
            color: "#475569",
            margin: 0,
          }}
        >
          {intro}
        </p>
        <div
          className="ssd-mono ssd-bounce"
          style={{
            marginTop: 24,
            fontSize: 11,
            letterSpacing: 1.4,
            color: "#94a3b8",
            textTransform: "uppercase",
          }}
        >
          ↓ scrolla — bilderna flyttar sig
        </div>
      </div>

      {/* Horisontell track */}
      <div
        ref={trackRef}
        style={{
          display: "flex",
          alignItems: "center",
          height: "100%",
          gap: 24,
          paddingLeft: "min(380px, 35vw)",
          paddingRight: "8vw",
          willChange: "transform",
        }}
      >
        {children}
      </div>
    </section>
  );
}

// ─── Card-komponenter — varje kort är en mockup av en plattformsskärm ───
//
// Alla kort är 360-440px breda, har samma korthus-stil (vit kort, mjuk
// skugga, runda hörn) och en eyebrow + titel + visual + meta-rad.

const CARD_BASE: React.CSSProperties = {
  flex: "0 0 420px",
  height: "min(540px, 70vh)",
  background: "#fff",
  border: "1px solid #e2e8f0",
  borderRadius: 14,
  padding: 22,
  display: "flex",
  flexDirection: "column",
  boxShadow: "0 4px 14px rgba(15,23,42,0.06)",
};

function CardEyebrow({ children }: { children: React.ReactNode }) {
  return (
    <div
      className="ssd-mono"
      style={{
        fontSize: 10.5,
        letterSpacing: 1.4,
        color: "#64748b",
        textTransform: "uppercase",
        marginBottom: 8,
      }}
    >
      {children}
    </div>
  );
}

function PayslipCard() {
  return (
    <div style={CARD_BASE}>
      <CardEyebrow>Lönespec · november</CardEyebrow>
      <h4 style={{ fontSize: 19, fontWeight: 600, margin: "0 0 4px", color: "#0f172a" }}>
        Visma · IT-konsult
      </h4>
      <div style={{ fontSize: 12, color: "#64748b", marginBottom: 16 }}>
        Linda · pay-date 25 nov
      </div>
      <ul
        style={{
          listStyle: "none",
          padding: 0,
          margin: 0,
          fontFamily: "ui-monospace, monospace",
          fontSize: 13,
          lineHeight: 2,
          color: "#0f172a",
        }}
      >
        <li style={{ display: "flex", justifyContent: "space-between" }}>
          <span style={{ color: "#475569" }}>Bruttolön</span>
          <strong>38 295 kr</strong>
        </li>
        <li style={{ display: "flex", justifyContent: "space-between" }}>
          <span style={{ color: "#475569" }}>Kommunalskatt 32 %</span>
          <span style={{ color: "#dc4c2b" }}>− 12 254 kr</span>
        </li>
        <li style={{ display: "flex", justifyContent: "space-between" }}>
          <span style={{ color: "#475569" }}>ITP1 (4,5 %)</span>
          <span style={{ color: "#dc4c2b" }}>− 1 723 kr</span>
        </li>
        <li
          style={{
            display: "flex",
            justifyContent: "space-between",
            paddingTop: 10,
            marginTop: 10,
            borderTop: "1px solid #e2e8f0",
          }}
        >
          <strong>Nettolön</strong>
          <strong style={{ color: "#10b981" }}>24 318 kr</strong>
        </li>
      </ul>
      <div
        style={{
          marginTop: "auto",
          paddingTop: 16,
          fontSize: 12,
          color: "#78350f",
          background: "#fef3c7",
          padding: "8px 12px",
          borderRadius: 8,
          fontStyle: "italic",
        }}
      >
        Förhandlade upp 3,2 % från Maria. Syns från november-lönen.
      </div>
    </div>
  );
}

function PortfolioCard() {
  const stocks = [
    { ticker: "VOLV-B", name: "Volvo B", qty: 10, price: 312.4, change: -2.1 },
    { ticker: "ERIC-B", name: "Ericsson B", qty: 15, price: 78.65, change: 1.8 },
    { ticker: "INVE-B", name: "Investor B", qty: 5, price: 285.0, change: 0.4 },
  ];
  const total = stocks.reduce((s, x) => s + x.qty * x.price, 0);
  return (
    <div style={CARD_BASE}>
      <CardEyebrow>ISK · innehav</CardEyebrow>
      <h4 style={{ fontSize: 19, fontWeight: 600, margin: "0 0 4px", color: "#0f172a" }}>
        Aktiekonto
      </h4>
      <div style={{ fontSize: 12, color: "#64748b", marginBottom: 16 }}>
        3 innehav · totalt {total.toFixed(0)} kr
      </div>
      <ul
        style={{
          listStyle: "none",
          padding: 0,
          margin: 0,
          display: "flex",
          flexDirection: "column",
          gap: 10,
          flex: 1,
        }}
      >
        {stocks.map((s) => (
          <li
            key={s.ticker}
            style={{
              display: "flex",
              alignItems: "center",
              gap: 10,
              padding: "10px 12px",
              background: "#fafaf9",
              border: "1px solid #e2e8f0",
              borderRadius: 8,
            }}
          >
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
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontSize: 13.5, fontWeight: 600, color: "#0f172a" }}>{s.name}</div>
              <div
                style={{
                  fontSize: 11.5,
                  color: "#64748b",
                  fontFamily: "ui-monospace, monospace",
                }}
              >
                {s.qty} st · {s.price.toFixed(2)} kr
              </div>
            </div>
            <span
              style={{
                fontSize: 12,
                fontFamily: "ui-monospace, monospace",
                color: s.change > 0 ? "#10b981" : "#dc4c2b",
                fontWeight: 600,
              }}
            >
              {s.change > 0 ? "▲" : "▼"} {Math.abs(s.change).toFixed(1)} %
            </span>
          </li>
        ))}
      </ul>
      <div
        style={{
          marginTop: 16,
          paddingTop: 14,
          borderTop: "1px solid #e2e8f0",
          fontSize: 12,
          color: "#475569",
          fontStyle: "italic",
        }}
      >
        Du köpte med 25 % av lönen. Bufferten är fortfarande två månadshyror.
      </div>
    </div>
  );
}

function WellbeingMiniCard({ score, wb, label }: { score: number; wb: WBScores; label: string }) {
  return (
    <div style={CARD_BASE}>
      <CardEyebrow>Wellbeing · {label}</CardEyebrow>
      <h4 style={{ fontSize: 19, fontWeight: 600, margin: "0 0 16px", color: "#0f172a" }}>
        Snapshot {score} / 100
      </h4>
      <div style={{ flex: 1, display: "grid", placeItems: "center" }}>
        <svg viewBox="0 0 400 400" style={{ width: "100%", maxWidth: 280 }}>
          {[0.25, 0.5, 0.75, 1].map((r, i) => (
            <polygon
              key={i}
              points={DIMS.map((_, j) => {
                const a = angleAt(j);
                return `${CX + Math.cos(a) * R * r},${CY + Math.sin(a) * R * r}`;
              }).join(" ")}
              fill="none"
              stroke="#e2e8f0"
              strokeWidth="1"
            />
          ))}
          <polygon
            points={polyFor(wb)}
            fill="rgba(251,191,36,0.20)"
            stroke="#fbbf24"
            strokeWidth="2.4"
          />
          {DIMS.map((d, i) => {
            const [x, y] = point(i, wb[d.key]);
            return <circle key={i} cx={x} cy={y} r="4.5" fill="#fbbf24" />;
          })}
          {DIMS.map((d, i) => {
            const a = angleAt(i);
            const lr = R + 28;
            return (
              <text
                key={i}
                x={CX + Math.cos(a) * lr}
                y={CY + Math.sin(a) * lr + 4}
                textAnchor="middle"
                fontSize="10"
                fontWeight="600"
                fill="#475569"
                fontFamily="ui-monospace, monospace"
              >
                {d.label}
              </text>
            );
          })}
          <text x={CX} y={CY - 4} textAnchor="middle" fontSize="46" fontWeight="700" fill="#0f172a">
            {score}
          </text>
        </svg>
      </div>
    </div>
  );
}

function EventLogCard({
  rows,
}: {
  rows: { ts: string; text: string; delta: string; tone: "good" | "bad" | "neutral" }[];
}) {
  const toneColor = { good: "#10b981", bad: "#dc4c2b", neutral: "#64748b" };
  return (
    <div style={CARD_BASE}>
      <CardEyebrow>Eventlogg · senaste 5</CardEyebrow>
      <h4 style={{ fontSize: 19, fontWeight: 600, margin: "0 0 16px", color: "#0f172a" }}>
        Vad hände den här veckan
      </h4>
      <ul style={{ listStyle: "none", padding: 0, margin: 0, flex: 1, display: "flex", flexDirection: "column", gap: 6 }}>
        {rows.map((r, i) => (
          <li
            key={i}
            style={{
              display: "grid",
              gridTemplateColumns: "auto 1fr auto",
              gap: 12,
              alignItems: "baseline",
              padding: "8px 0",
              borderBottom: i < rows.length - 1 ? "1px dashed #e2e8f0" : "none",
              fontFamily: "ui-monospace, monospace",
              fontSize: 12.5,
            }}
          >
            <span style={{ color: "#94a3b8", minWidth: 80 }}>{r.ts}</span>
            <span style={{ color: "#0f172a", fontFamily: "inherit" }}>{r.text}</span>
            <span style={{ color: toneColor[r.tone], fontWeight: 600 }}>{r.delta}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function EchoCard({ quote, response }: { quote: string; response: string }) {
  return (
    <div
      style={{
        ...CARD_BASE,
        background: "#0f172a",
        color: "#fff",
        border: "1px solid rgba(251,191,36,0.25)",
      }}
    >
      <CardEyebrow>
        <span style={{ color: "#fbbf24" }}>● Echo · sokratisk AI</span>
      </CardEyebrow>
      <h4 style={{ fontSize: 19, fontWeight: 600, margin: "0 0 18px", color: "#fff" }}>
        AI:n frågar mer än den svarar
      </h4>
      <div
        style={{
          fontSize: 16,
          lineHeight: 1.5,
          color: "#fbbf24",
          fontStyle: "italic",
          fontFamily: '"Source Serif 4", Georgia, serif',
          marginBottom: 16,
        }}
      >
        {quote}
      </div>
      <div
        style={{
          fontSize: 14.5,
          lineHeight: 1.55,
          color: "#e2e8f0",
          fontFamily: '"Source Serif 4", Georgia, serif',
          marginTop: "auto",
        }}
      >
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
        {response}
      </div>
    </div>
  );
}

function SatisfactionCard({ from, to }: { from: number; to: number }) {
  return (
    <div style={CARD_BASE}>
      <CardEyebrow>Arbetsgivare · satisfaction</CardEyebrow>
      <h4 style={{ fontSize: 19, fontWeight: 600, margin: "0 0 16px", color: "#0f172a" }}>
        {from} → {to}
      </h4>
      <div style={{ flex: 1, display: "grid", placeItems: "center" }}>
        <svg viewBox="0 0 200 200" style={{ width: "100%", maxWidth: 200 }}>
          <circle cx="100" cy="100" r="80" fill="none" stroke="#f1f5f9" strokeWidth="14" />
          <circle
            cx="100"
            cy="100"
            r="80"
            fill="none"
            stroke="#10b981"
            strokeWidth="14"
            strokeDasharray={`${(to / 100) * 502.4} 502.4`}
            strokeLinecap="round"
            transform="rotate(-90 100 100)"
          />
          <text x="100" y="106" textAnchor="middle" fontSize="44" fontWeight="700" fill="#0f172a">
            {to}
          </text>
        </svg>
      </div>
      <div
        style={{
          marginTop: 14,
          fontSize: 12,
          color: "#475569",
          fontStyle: "italic",
        }}
      >
        Bra svar på "Maria glömt passerkort". Chefen noterade.
      </div>
    </div>
  );
}

function BankDocCard({
  title,
  amount,
  issuer,
  due,
  warning,
}: {
  title: string;
  amount: string;
  issuer: string;
  due: string;
  warning?: string;
}) {
  return (
    <div style={CARD_BASE}>
      <CardEyebrow>Bank-dokument</CardEyebrow>
      <h4 style={{ fontSize: 19, fontWeight: 600, margin: "0 0 4px", color: "#0f172a" }}>
        {title}
      </h4>
      <div style={{ fontSize: 12, color: "#64748b", marginBottom: 16 }}>
        Från {issuer}
      </div>
      <div
        style={{
          background: "#fafaf9",
          border: "1px dashed #cbd5e1",
          borderRadius: 8,
          padding: "20px 18px",
          fontFamily: "ui-monospace, monospace",
          fontSize: 13,
          lineHeight: 1.9,
          color: "#0f172a",
          flex: 1,
        }}
      >
        <div style={{ display: "flex", justifyContent: "space-between" }}>
          <span style={{ color: "#475569" }}>Belopp</span>
          <strong style={{ color: "#dc4c2b", fontSize: 17 }}>{amount}</strong>
        </div>
        <div style={{ display: "flex", justifyContent: "space-between" }}>
          <span style={{ color: "#475569" }}>Förfallodag</span>
          <strong>{due}</strong>
        </div>
      </div>
      {warning && (
        <div
          style={{
            marginTop: 14,
            fontSize: 12,
            color: "#7f1d1d",
            background: "rgba(220,76,43,.06)",
            border: "1px solid rgba(220,76,43,.2)",
            padding: "8px 12px",
            borderRadius: 8,
          }}
        >
          {warning}
        </div>
      )}
    </div>
  );
}

function LossAversionCard() {
  return (
    <div style={CARD_BASE}>
      <CardEyebrow>Loss aversion · λ ≈ 2,0</CardEyebrow>
      <h4 style={{ fontSize: 19, fontWeight: 600, margin: "0 0 16px", color: "#0f172a" }}>
        En förlust gör dubbelt så ont
      </h4>
      <div style={{ display: "flex", flexDirection: "column", gap: 14, flex: 1, justifyContent: "center" }}>
        <div>
          <div style={{ fontSize: 11, color: "#64748b", marginBottom: 6, fontFamily: "ui-monospace, monospace", letterSpacing: 1 }}>
            VINST +3,2 %
          </div>
          <div style={{ height: 18, background: "#f1f5f9", borderRadius: 4, overflow: "hidden" }}>
            <div style={{ height: "100%", width: "32%", background: "#10b981" }} />
          </div>
          <div style={{ fontSize: 12, color: "#10b981", fontFamily: "ui-monospace, monospace", marginTop: 4 }}>
            Trygghet +2 poäng
          </div>
        </div>
        <div>
          <div style={{ fontSize: 11, color: "#64748b", marginBottom: 6, fontFamily: "ui-monospace, monospace", letterSpacing: 1 }}>
            FÖRLUST −3,2 %
          </div>
          <div style={{ height: 18, background: "#f1f5f9", borderRadius: 4, overflow: "hidden" }}>
            <div style={{ height: "100%", width: "64%", background: "#dc4c2b" }} />
          </div>
          <div style={{ fontSize: 12, color: "#dc4c2b", fontFamily: "ui-monospace, monospace", marginTop: 4 }}>
            Trygghet −4 poäng (2× hårdare)
          </div>
        </div>
      </div>
      <div
        style={{
          marginTop: 16,
          paddingTop: 14,
          borderTop: "1px solid #e2e8f0",
          fontSize: 12,
          color: "#475569",
          fontStyle: "italic",
        }}
      >
        Wellbeing räknar in portföljens 24h-rörelse asymmetriskt — exakt
        som Kahneman/Tversky beskrev.
      </div>
    </div>
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
