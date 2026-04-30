/**
 * V2 Onboarding · 8 steg som EXAKT matchar /proposals/vol-7/elev.html.
 *
 * Inga genvägar — varje steg har samma copy, samma layout, samma
 * pedagogik-block som i prototypen. CSS lever i ./onboarding.css.
 *
 * Flöde:
 *   1. Välkommen + 3 principer
 *   2. Möt karaktären (Sara A.)
 *   3. Nivå & spenderprofil (3 nivåer som progression)
 *   4. Pentagonen är hjärtat
 *   5. Postlådan är källan
 *   6. Echo är spegeln
 *   7. Sambo-frågan (3 partner-modeller + 3 värderingsval)
 *   8. Klar — Vol. 18 är laddad
 */
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { v2Api, type FairnessChoice } from "./api";
import "./onboarding.css";

const TOTAL = 8;
const NEXT_LABELS = [
  "",
  "Möt din karaktär →",
  "Välj din nivå →",
  "Visa pentagonen →",
  "Visa postlådan →",
  "Visa Echo →",
  "En fråga om värderingar →",
  "Sista regeln →",
  "Starta Vol. 18 ↗",
];

export function OnboardingV2() {
  const [step, setStep] = useState(1);
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
      setSaving(false);
    }
  }

  function next() {
    if (step < TOTAL) setStep(step + 1);
    else complete();
  }
  function back() {
    if (step > 1) setStep(step - 1);
  }

  return (
    <div className="v2-onboarding-root">
      <div className="onb-shell">
        <div className="onb-stage">
          <div className="onb-progress">
            {Array.from({ length: TOTAL }).map((_, i) => (
              <span
                key={i}
                className={
                  i + 1 < step ? "done" : i + 1 === step ? "now" : ""
                }
              />
            ))}
          </div>

          {step === 1 && <Step1 />}
          {step === 2 && <Step2 />}
          {step === 3 && <Step3 />}
          {step === 4 && <Step4 />}
          {step === 5 && <Step5 />}
          {step === 6 && <Step6 />}
          {step === 7 && (
            <Step7 fairness={fairness} setFairness={setFairness} />
          )}
          {step === 8 && <Step8 />}

          <div className="onb-foot">
            <span className="onb-step-num">
              Steg <strong>{step}</strong> av {TOTAL}
            </span>
            {error && (
              <span style={{ color: "#fca5a5", fontSize: 12 }}>{error}</span>
            )}
            <div className="onb-actions">
              <button
                className="onb-btn"
                onClick={back}
                disabled={step === 1 || saving}
              >
                ← Tillbaka
              </button>
              <button
                className="onb-btn solid"
                onClick={next}
                disabled={
                  saving ||
                  (step === 7 && !fairness) /* sambo-svar krävs */
                }
              >
                {saving && step === TOTAL ? "Sparar..." : NEXT_LABELS[step]}
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

/* === STEG 1 — Välkommen + 3 principer + pedagogik === */
function Step1() {
  return (
    <div className="onb-step">
      <div className="onb-eye">Onboarding · steg 1 av 8</div>
      <h1 className="onb-h">
        Välkommen till <em>Ekonomilabbet</em>.
      </h1>
      <p className="onb-lead">
        Det här är inte ett spel. Det är en{" "}
        <em>simulator av det vuxna ekonomiska livet</em> — där du får möta
        riktiga aktörer (banken, arbetsgivaren, Skatteverket), riktiga flöden
        (BankID-signering, lönesamtal, kreditprövning) och fatta riktiga
        beslut.
      </p>
      <p className="onb-lead">
        Du driver din ekonomi i <em>realtid</em> mellan inloggningar.
        Räkningar kommer i postlådan. Lönen ramlar in den 25:e. Beslut du
        fattar nu får konsekvenser nästa månad. Hela poängen är att{" "}
        <strong>känna</strong> det innan det händer på riktigt.
      </p>

      <div className="onb-rules">
        <div className="onb-rule">
          <div className="onb-rule-eye">Princip 01</div>
          <div className="onb-rule-h">
            Inga <em>genvägar</em>
          </div>
          <div className="onb-rule-prose">
            BankID-signering tar 6 steg som i verkligheten. Lönesamtal har 5
            rundor. Friktionen är meningen.
          </div>
        </div>
        <div className="onb-rule">
          <div className="onb-rule-eye">Princip 02</div>
          <div className="onb-rule-h">
            Inget <em>betyg</em>
          </div>
          <div className="onb-rule-prose">
            Det finns inga "rätta svar". Echo ställer frågor — du fattar
            besluten. Läraren bedömer din portfolio, inte enskilda val.
          </div>
        </div>
        <div className="onb-rule">
          <div className="onb-rule-eye">Princip 03</div>
          <div className="onb-rule-h">
            AI är <em>spegel</em>
          </div>
          <div className="onb-rule-prose">
            Echo, Maria och Anna är inte orakel. De ställer frågor, jämför med
            data — du tänker själv.
          </div>
        </div>
      </div>

      <div className="onb-rules">
        <div
          className="onb-rule"
          style={{
            gridColumn: "1 / -1",
            background: "rgba(99,102,241,0.05)",
            borderColor: "rgba(99,102,241,0.2)",
          }}
        >
          <div className="onb-rule-eye" style={{ color: "#a5b4fc" }}>
            Pedagogik
          </div>
          <div className="onb-rule-h">
            Vad du <em>lär dig</em> i Vol. 18
          </div>
          <div className="onb-rule-prose">
            14 systemkompetenser: bokföring, budget, sparande, lån, ränta,
            skatt, lön, kollektivavtal, pension, försäkring, kreditförståelse,
            investering, konsumenträtt, ekonomisk reflektion. Du växer från{" "}
            <em>basis</em> till <em>grund</em> till <em>fördjupning</em> i
            takt med vad du gör.
          </div>
        </div>
      </div>
    </div>
  );
}

/* === STEG 2 — Möt karaktären === */
function Step2() {
  return (
    <div className="onb-step">
      <div className="onb-eye">Onboarding · steg 2 av 8 · karaktär</div>
      <h1 className="onb-h">
        Möt <em>Sara A.</em>
      </h1>
      <p className="onb-lead">
        Du spelar inte dig själv — du spelar <em>Sara</em>. Hon är 16, går
        gymnasium, jobbar 80 % som undersköterskelev på Sthlm Sjukhus AB, bor
        i en 2 r o k i Hökarängen. Hennes karaktär är genererad av din lärare
        med specifika förutsättningar du kommer behöva förstå innan du fattar
        beslut åt henne.
      </p>

      <div className="onb-char">
        <div className="onb-char-avatar">SA</div>
        <div>
          <div className="onb-char-name">Sara Andersson</div>
          <div className="onb-char-meta">
            16 år · gymnasium åk 1 · stockholm · solo · klass 9C
          </div>
          <div className="onb-char-prose">
            Tjänar <em>22 400 kr/mån</em> netto efter skatt + studiebidrag
            1 250. Hyran är 7 240 kr. Har <em>38 200 kr</em> i CSN-skuld,
            8 460 kr på Avanza-ISK, 1 800 kr i buffert. Tar <em>laxsim</em>{" "}
            två kvällar/v och får ofta för sig att äta på Max efteråt — ett
            vanligt budgetdilemma.
          </div>
        </div>
      </div>

      <div className="onb-rules">
        <div className="onb-rule">
          <div className="onb-rule-eye">Karaktär · arbete</div>
          <div className="onb-rule-h">Sthlm Sjukhus AB</div>
          <div className="onb-rule-prose">
            80 % tjänst · kollektivavtal Akavia/Vårdförbundet · ITP1-pension ·
            friskvårdsbidrag 5 000/år
          </div>
        </div>
        <div className="onb-rule">
          <div className="onb-rule-eye">Karaktär · boende</div>
          <div className="onb-rule-h">Stockholmshem</div>
          <div className="onb-rule-prose">
            2 r o k Hökarängen · första-handskontrakt · 7 240 kr/mån inkl. el
            via Tibber
          </div>
        </div>
        <div className="onb-rule">
          <div className="onb-rule-eye">Karaktär · skuld &amp; spar</div>
          <div className="onb-rule-h">Måttligt skuldsatt</div>
          <div className="onb-rule-prose">
            CSN 38 200 (1,7 % ränta) · Sparar 600 kr/mån i ISK · Bufferten på
            1 800 är under riktvärdet 0,5 mån
          </div>
        </div>
      </div>

      <div
        className="onb-rule"
        style={{
          background: "rgba(99,102,241,0.05)",
          borderColor: "rgba(99,102,241,0.2)",
        }}
      >
        <div className="onb-rule-eye" style={{ color: "#a5b4fc" }}>
          Pedagogik · varför just Sara
        </div>
        <div className="onb-rule-prose">
          Sara är medvetet vald som{" "}
          <em style={{ color: "var(--warm)" }}>representativ ung vuxen</em> —
          inte rik, inte fattig, har anställning men inte trygghet, sparar
          lite men inte för pension, har en buffert under riktvärdet. Det
          skapar{" "}
          <em style={{ color: "var(--warm)" }}>realistiska dilemman</em> där
          alla val har tradeoffs. Inget rätt svar.
        </div>
      </div>
    </div>
  );
}

/* === STEG 3 — Nivå & spenderprofil (3 nivåer som progression) === */
function Step3() {
  return (
    <div className="onb-step">
      <div className="onb-eye">Onboarding · steg 3 av 8 · nivå &amp; profil</div>
      <h1 className="onb-h">
        Du börjar på <em>Nivå 1 · Sparsam</em>.
      </h1>
      <p className="onb-lead">
        Plattformen har <em>tre nivåer</em>. Du börjar på Nivå 1 och din
        spenderprofil är <strong>låst till Sparsam</strong> som start. När du
        klarat Nivå 1 öppnar <strong>Anders Lind</strong> Nivå 2 åt dig — då
        blir samma karaktär (Sara) balanserad och utmaningen ökar.
      </p>

      <div className="onb-profiles">
        <div
          className="onb-profile selected"
          style={{
            borderColor: "#6ee7b7",
            background: "rgba(110,231,183,0.06)",
          }}
        >
          <div className="onb-profile-icon" style={{ color: "#6ee7b7" }}>
            ▰▱▱
          </div>
          <div className="onb-profile-name">
            Nivå 1 · Sparsam{" "}
            <em
              style={{
                color: "#6ee7b7",
                fontSize: 9,
                verticalAlign: "middle",
                fontFamily: "var(--mono)",
                marginLeft: 6,
              }}
            >
              DU ÄR HÄR
            </em>
          </div>
          <div className="onb-profile-desc">
            Lättare att hålla ordning. Sara lagar mat hemma, få överraskningar.{" "}
            <em style={{ color: "var(--warm)" }}>Men friktion finns</em> —
            tandläkaren ringer ändå.
          </div>
          <div className="onb-profile-stat">
            ~ <strong>10</strong> brev/mån · CC-faktura ~{" "}
            <strong>2 800 kr</strong> · sparkvot 18 %
          </div>
        </div>
        <div className="onb-profile" style={{ opacity: 0.55 }}>
          <div className="onb-profile-icon" style={{ color: "var(--warm)" }}>
            ▰▰▱
          </div>
          <div className="onb-profile-name">
            Nivå 2 · Balanserad{" "}
            <em
              style={{
                color: "var(--text-dim)",
                fontSize: 9,
                verticalAlign: "middle",
                fontFamily: "var(--mono)",
                marginLeft: 6,
              }}
            >
              LÅST · LÄRAREN AKTIVERAR
            </em>
          </div>
          <div className="onb-profile-desc">
            Konsumentverkets schablon. Lite restaurang, Foodora, fler
            impulser. Mer att jonglera med.
          </div>
          <div className="onb-profile-stat">
            ~ <strong>14</strong> brev/mån · CC-faktura ~{" "}
            <strong>4 800 kr</strong> · sparkvot 14 %
          </div>
        </div>
        <div className="onb-profile" style={{ opacity: 0.4 }}>
          <div
            className="onb-profile-icon"
            style={{ color: "var(--accent)" }}
          >
            ▰▰▰
          </div>
          <div className="onb-profile-name">
            Nivå 3 · Slösa{" "}
            <em
              style={{
                color: "var(--text-dim)",
                fontSize: 9,
                verticalAlign: "middle",
                fontFamily: "var(--mono)",
                marginLeft: 6,
              }}
            >
              LÅST · EFTER NIVÅ 2
            </em>
          </div>
          <div className="onb-profile-desc">
            Många abonnemang, impulsköp, push-betalningar. Påminnelser kommer.
            Skuldfälla möjlig.
          </div>
          <div className="onb-profile-stat">
            ~ <strong>18</strong> brev/mån · CC-faktura ~{" "}
            <strong>7 200 kr</strong> · sparkvot 4 %
          </div>
        </div>
      </div>

      <div
        className="onb-rule"
        style={{
          background: "rgba(99,102,241,0.05)",
          borderColor: "rgba(99,102,241,0.2)",
        }}
      >
        <div className="onb-rule-eye" style={{ color: "#a5b4fc" }}>
          Pedagogik · varför nivåer
        </div>
        <div className="onb-rule-prose">
          Samma karaktär (Sara A.) genom alla tre nivåer — bara den{" "}
          <em style={{ color: "var(--warm)" }}>ekonomiska komplexiteten</em>{" "}
          ökar. På Nivå 1 lär du dig grunden i en relativt vänlig miljö. På
          Nivå 2 möter du fler oväntade brev, fler impulsköp, restaurang som
          börjar gå över budget. På Nivå 3 är skuldfälla, sms-lån och
          betalningsanmärkningar reella risker. Du{" "}
          <strong style={{ color: "var(--accent)" }}>jobbar dig</strong> uppåt
          — Anders öppnar nästa nivå när hen ser att du klarar den.
        </div>
      </div>
    </div>
  );
}

/* === STEG 4 — Pentagonen är hjärtat === */
function Step4() {
  return (
    <div className="onb-step">
      <div className="onb-eye">Onboarding · steg 4 av 8 · pentagonen</div>
      <h1 className="onb-h">
        Pentagonen är <em>hjärtat</em>.
      </h1>
      <p className="onb-lead">
        All ekonomi är inte siffror — det är <em>balans</em>. Pentagonen
        visar fem axlar:{" "}
        <em>ekonomi, karriär, hälsa, relation, fritid</em>. När tandläkaren
        ringer (4 200 kr akut) tippar den. När du höjer din lön tippar den åt
        andra hållet. Du ser konsekvensen <strong>direkt</strong> i bilden.
      </p>

      <div className="onb-pent-row">
        <svg
          viewBox="0 0 200 200"
          style={{ width: 200, height: 200 }}
        >
          <g transform="translate(100,100)">
            <polygon
              points="0,-86 82,-27 51,69 -51,69 -82,-27"
              fill="none"
              stroke="rgba(255,255,255,0.18)"
              strokeWidth="0.8"
              strokeDasharray="2 3"
            />
            <polygon
              points="0,-65 62,-20 38,53 -38,53 -62,-20"
              fill="none"
              stroke="rgba(255,255,255,0.15)"
              strokeWidth="0.8"
              strokeDasharray="2 3"
            />
            <polygon
              points="0,-43 41,-13 25,35 -25,35 -41,-13"
              fill="none"
              stroke="rgba(255,255,255,0.12)"
              strokeWidth="0.8"
              strokeDasharray="2 3"
            />
            <line x1="0" y1="0" x2="0" y2="-86" stroke="rgba(255,255,255,0.12)" strokeDasharray="2 3" />
            <line x1="0" y1="0" x2="82" y2="-27" stroke="rgba(255,255,255,0.12)" strokeDasharray="2 3" />
            <line x1="0" y1="0" x2="51" y2="69" stroke="rgba(255,255,255,0.12)" strokeDasharray="2 3" />
            <line x1="0" y1="0" x2="-51" y2="69" stroke="rgba(255,255,255,0.12)" strokeDasharray="2 3" />
            <line x1="0" y1="0" x2="-82" y2="-27" stroke="rgba(255,255,255,0.12)" strokeDasharray="2 3" />
            <polygon
              points="0,-65 70,-22 42,55 -45,53 -68,-23"
              fill="rgba(220,76,43,0.22)"
              stroke="#dc4c2b"
              strokeWidth="2"
              filter="drop-shadow(0 0 12px rgba(220,76,43,0.4))"
            />
            <text
              x="0"
              y="6"
              textAnchor="middle"
              fontFamily="Source Serif 4"
              fontStyle="italic"
              fontWeight="700"
              fontSize="32"
              fill="#fbbf24"
            >
              76
            </text>
          </g>
        </svg>
        <ul className="onb-axes-list">
          <li>
            <strong>Ekonomi</strong>
            <span>Saldon, skulder, sparkvot, bufferthöjd</span>
          </li>
          <li>
            <strong>Karriär</strong>
            <span>Lön, lönesamtal, anställning, utbildning</span>
          </li>
          <li>
            <strong>Hälsa</strong>
            <span>Försäkring, läkare, sömn (via Echo-frågor)</span>
          </li>
          <li>
            <strong>Relation</strong>
            <span>Familj-batches, klass-aktivitet, peer-review</span>
          </li>
          <li>
            <strong>Fritid</strong>
            <span>Restaurang-budget, prenumerationer, semester-mål</span>
          </li>
        </ul>
      </div>

      <div
        className="onb-rule"
        style={{
          background: "rgba(99,102,241,0.05)",
          borderColor: "rgba(99,102,241,0.2)",
        }}
      >
        <div className="onb-rule-eye" style={{ color: "#a5b4fc" }}>
          Pedagogik · varför pentagon
        </div>
        <div className="onb-rule-prose">
          Pengar är aldrig bara pengar. Att betala tandläkaren kostar{" "}
          <em style={{ color: "var(--warm)" }}>ekonomi</em> men ger{" "}
          <em style={{ color: "var(--warm)" }}>hälsa</em>. Att skjuta upp ger
          ekonomi men kostar hälsa. Pentagonen tvingar dig att se{" "}
          <strong style={{ color: "var(--accent)" }}>hela utbytet</strong> —
          inte bara siffran på kontot. Det är vad WHO &amp; OECD kallar{" "}
          <em style={{ color: "var(--warm)" }}>finansiell wellbeing</em>.
        </div>
      </div>
    </div>
  );
}
/* === STEG 5 — Postlådan är källan === */
function Step5() {
  return (
    <div className="onb-step">
      <div className="onb-eye">Onboarding · steg 5 av 8 · postlådan</div>
      <h1 className="onb-h">
        Allt landar i <em>postlådan</em>.
      </h1>
      <p className="onb-lead">
        Detta är skillnaden från andra appar: <em>ingen räkning är "redan
        betald"</em> bara för att månaden börjat. Brev <strong>kommer in</strong>
        över dagar och veckor — fakturor, lönespecar, myndighetspost,
        kreditkortsfakturor från förra månadens spend. Du måste{" "}
        <strong>granska</strong>, <strong>klassa</strong>,{" "}
        <strong>exportera</strong> dem till banken. Annars händer ingenting.
      </p>

      <div className="onb-mail-mock">
        <div className="onb-mail-mock-row">
          <span>●</span>
          <span>SEB Visa</span>
          <span>April-spend · 47 köp att granska</span>
          <span>4 822 kr</span>
          <span>Ohanterad</span>
        </div>
        <div className="onb-mail-mock-row">
          <span>●</span>
          <span>Skatteverket</span>
          <span>Deklaration 2025 · 1 förslag</span>
          <span>+ 1 240 kr</span>
          <span>Ohanterad</span>
        </div>
        <div className="onb-mail-mock-row">
          <span>●</span>
          <span>Folktandvården</span>
          <span>Cariesfyllning · faktura idag</span>
          <span>4 200 kr</span>
          <span>Ohanterad</span>
        </div>
        <div className="onb-mail-mock-row">
          <span>●</span>
          <span>Stockholmshem</span>
          <span>Hyra maj · vana · auto-exporterad</span>
          <span>7 240 kr</span>
          <span
            style={{
              background: "rgba(99,102,241,0.16)",
              color: "#a5b4fc",
            }}
          >
            Exporterad
          </span>
        </div>
      </div>

      <div className="onb-rules">
        <div className="onb-rule">
          <div className="onb-rule-eye">Hantering · 5 status</div>
          <div className="onb-rule-prose">
            Ohanterad → Granskad → Exporterad → Betald → Arkiv. Vana brev
            (hyra, el, mobil) kan auto-exporteras med din bekräftelse. Nya
            brev kräver alltid din blick.
          </div>
        </div>
        <div className="onb-rule">
          <div className="onb-rule-eye">Påminnelser</div>
          <div className="onb-rule-prose">
            Ohanterad räkning efter <em>14 dagar</em> → påminnelse. Efter{" "}
            <em>30 dagar</em> → inkasso-varning. Bygger upp i{" "}
            <em>kreditprövning</em> hos lånegivaren.
          </div>
        </div>
        <div className="onb-rule">
          <div className="onb-rule-eye">Konsekvenser i pentagon</div>
          <div className="onb-rule-prose">
            Inkasso → ekonomi-axeln dyker. Ignorerade brev → relation-axeln
            dyker (du missar saker som rör dig). Allt återspeglas.
          </div>
        </div>
      </div>

      <div
        className="onb-rule"
        style={{
          background: "rgba(99,102,241,0.05)",
          borderColor: "rgba(99,102,241,0.2)",
        }}
      >
        <div className="onb-rule-eye" style={{ color: "#a5b4fc" }}>
          Pedagogik · varför friktion
        </div>
        <div className="onb-rule-prose">
          Vuxna missar fakturor inte för att de inte vill betala — utan för
          att de <em style={{ color: "var(--warm)" }}>inte sett dem</em>.
          Postlådan tränar dig på att{" "}
          <strong style={{ color: "var(--accent)" }}>se</strong>. Att klicka,
          läsa, klassa, exportera är{" "}
          <em style={{ color: "var(--warm)" }}>kognitiv friktion med syfte</em>{" "}
          — det skapar vana att inte ignorera ekonomin. Det är samma muskel
          man behöver hela vuxenlivet.
        </div>
      </div>
    </div>
  );
}

/* === STEG 6 — Echo är spegeln === */
function Step6() {
  return (
    <div className="onb-step">
      <div className="onb-eye">Onboarding · steg 6 av 8 · Echo</div>
      <h1 className="onb-h">
        Echo är din <em>spegel</em>.
      </h1>
      <p className="onb-lead">
        Echo (Claude Haiku 4.5) är inte ett orakel. Hen ger inte råd som
        "spara mer i ISK". Hen <em>ställer frågor</em>,{" "}
        <em>jämför med dina data</em>, <em>påminner om mönster</em>. Du
        fattar besluten — Echo visar dig <em>vad du redan vet</em>.
      </p>

      <div className="onb-echo">
        <div className="onb-echo-bubble">
          "Du har <em>12 transaktioner</em> från Coop, Ica och Hemköp
          ovettade. <em>Vill du gå igenom dem nu</em> — eller efter att du
          tittat på din mat-kategori i budgeten?"
        </div>
        <div className="onb-echo-attr">
          Echo · sokratisk · 47 tokens · vet vad du tittar på
        </div>
      </div>

      <div className="onb-rules">
        <div className="onb-rule">
          <div className="onb-rule-eye">Förbjudet</div>
          <div className="onb-rule-h">
            Inga <em>imperativ</em>
          </div>
          <div className="onb-rule-prose">
            Echo får inte säga "du borde", "du måste". System-prompten
            förbjuder rekommendationer.
          </div>
        </div>
        <div className="onb-rule">
          <div className="onb-rule-eye">Tillåtet</div>
          <div className="onb-rule-h">
            Mönster &amp; <em>frågor</em>
          </div>
          <div className="onb-rule-prose">
            "Du har stått här förut — vad gjorde du då?" "Mars var 1 940,
            april blev 2 100 — vad hände den 17:e?"
          </div>
        </div>
        <div className="onb-rule">
          <div className="onb-rule-eye">Initiativ</div>
          <div className="onb-rule-h">
            Bara på <em>förfrågan</em>
          </div>
          <div className="onb-rule-prose">
            Echo dyker inte upp om hen inte är öppnad. Inga
            push-notifikationer. Du bestämmer när du vill prata.
          </div>
        </div>
      </div>

      <div
        className="onb-rule"
        style={{
          background: "rgba(99,102,241,0.05)",
          borderColor: "rgba(99,102,241,0.2)",
        }}
      >
        <div className="onb-rule-eye" style={{ color: "#a5b4fc" }}>
          Pedagogik · sokratisk metod
        </div>
        <div className="onb-rule-prose">
          <em style={{ color: "var(--warm)" }}>"Den ovärderliga frågan"</em>{" "}
          — Sokrates kallade det. Bra ekonomilärande händer när eleven ser
          sitt eget mönster, inte när läraren talar om det. Echo är teknikens
          version av{" "}
          <strong style={{ color: "var(--accent)" }}>
            tystnaden i klassrummet
          </strong>{" "}
          — pausen som tvingar fram tanken.
        </div>
      </div>
    </div>
  );
}
/* === STEG 7 — Sambo-fråga (3 partner-modeller + 3 värderingsval) === */
function Step7({
  fairness,
  setFairness,
}: {
  fairness: FairnessChoice | null;
  setFairness: (v: FairnessChoice) => void;
}) {
  const fairOpts: { v: FairnessChoice; nameJsx: React.ReactNode; desc: string }[] = [
    {
      v: "50_50",
      nameJsx: (
        <>
          <em>50/50</em> — vi delar lika
        </>
      ),
      desc: "Båda betalar exakt halva varje gemensam kostnad.",
    },
    {
      v: "proportionellt",
      nameJsx: (
        <>
          <em>Proportionellt</em> — den som tjänar mer betalar mer
        </>
      ),
      desc:
        "Var och en betalar samma andel av sin egen lön — så ni har ungefär samma marginal kvar.",
    },
    {
      v: "pool",
      nameJsx: (
        <>
          <em>Allt delas</em> — gemensam ekonomi
        </>
      ),
      desc:
        'Båda löner går in på ett gemensamt konto. Inga "mina pengar" eller "dina pengar".',
    },
  ];

  return (
    <div className="onb-step">
      <div className="onb-eye">
        Onboarding · steg 7 av 8 · värderingar
      </div>
      <h1 className="onb-h">
        Innan vi avslöjar din <em>partners ekonomi</em> — en fråga.
      </h1>
      <p className="onb-lead">
        Sara har fått en <em>AI-genererad sambo</em> — Linus B. Inte alla
        elever får det; vissa karaktärer är solo, en del par. Innan vi visar
        vad Linus tjänar svarar du på en fråga om <em>dig själv</em>.
      </p>

      {/* Partner-modeller: 3 varianter */}
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(3, 1fr)",
          gap: 10,
          marginBottom: 22,
        }}
      >
        <div
          style={{
            background: "rgba(255,255,255,0.04)",
            border: "1px solid var(--line)",
            borderRadius: 6,
            padding: "12px 14px",
          }}
        >
          <div
            style={{
              fontFamily: "var(--mono)",
              fontSize: 9,
              fontWeight: 700,
              letterSpacing: "1.2px",
              textTransform: "uppercase",
              color: "var(--text-mid)",
              marginBottom: 4,
            }}
          >
            Modell A · Solo
          </div>
          <div
            style={{
              fontFamily: "var(--serif)",
              fontSize: 13,
              color: "#fff",
              fontWeight: 700,
              marginBottom: 3,
            }}
          >
            Ingen partner
          </div>
          <div
            style={{
              fontFamily: "var(--serif)",
              fontSize: 12,
              color: "var(--text-mid)",
              lineHeight: 1.4,
            }}
          >
            ~ 60 % av karaktärer. Eget hushåll, egen ekonomi. Sambo-frågor
            hoppar.
          </div>
        </div>
        <div
          style={{
            background: "rgba(99,102,241,0.06)",
            border: "1px solid rgba(99,102,241,0.30)",
            borderRadius: 6,
            padding: "12px 14px",
          }}
        >
          <div
            style={{
              fontFamily: "var(--mono)",
              fontSize: 9,
              fontWeight: 700,
              letterSpacing: "1.2px",
              textTransform: "uppercase",
              color: "#c7d2fe",
              marginBottom: 4,
            }}
          >
            Modell B · AI-partner{" "}
            <em
              style={{
                color: "var(--warm)",
                fontSize: 10,
                verticalAlign: "middle",
                fontFamily: "var(--mono)",
                marginLeft: 4,
              }}
            >
              DU ÄR HÄR
            </em>
          </div>
          <div
            style={{
              fontFamily: "var(--serif)",
              fontSize: 13,
              color: "#fff",
              fontWeight: 700,
              marginBottom: 3,
            }}
          >
            Linus B. (auto-genererad)
          </div>
          <div
            style={{
              fontFamily: "var(--serif)",
              fontSize: 12,
              color: "var(--text-mid)",
              lineHeight: 1.4,
            }}
          >
            ~ 35 %. Plattformen skapar partnern med egen lön, värdering och
            bakgrund. Realistiska sambo-konflikter.
          </div>
        </div>
        <div
          style={{
            background: "rgba(110,231,183,0.05)",
            border: "1px solid rgba(110,231,183,0.25)",
            borderRadius: 6,
            padding: "12px 14px",
          }}
        >
          <div
            style={{
              fontFamily: "var(--mono)",
              fontSize: 9,
              fontWeight: 700,
              letterSpacing: "1.2px",
              textTransform: "uppercase",
              color: "#6ee7b7",
              marginBottom: 4,
            }}
          >
            Modell C · Klasskompis
          </div>
          <div
            style={{
              fontFamily: "var(--serif)",
              fontSize: 13,
              color: "#fff",
              fontWeight: 700,
              marginBottom: 3,
            }}
          >
            Annan elev (riktig person)
          </div>
          <div
            style={{
              fontFamily: "var(--serif)",
              fontSize: 12,
              color: "var(--text-mid)",
              lineHeight: 1.4,
            }}
          >
            ~ 5 %.{" "}
            <em style={{ color: "var(--warm)" }}>
              Aktiveras endast av läraren.
            </em>{" "}
            Två elever pairas och delar gemensam ekonomi-modell.
          </div>
        </div>
      </div>

      <div className="onb-partner-card">
        <div className="onb-partner-eye">
          Värderingsfråga · sparas i din portfolio
        </div>
        <h2 className="onb-partner-h">
          Hur tycker du att <em>gemensamma kostnader</em> ska fördelas i ett
          hushåll?
        </h2>
        <p className="onb-partner-prose">
          <strong>Hyra · el · mat hemma · försäkringar.</strong> Du vet inte
          än om du eller din partner tjänar mer. Svara utifrån vad du{" "}
          <em>tycker är rätt</em> — inte vad som gynnar dig själv. Det är en
          fråga om värderingar, inte matematik.
        </p>

        <div className="onb-fairness">
          {fairOpts.map((opt) => (
            <div
              key={opt.v}
              className={
                "onb-fair-option" +
                (fairness === opt.v ? " selected" : "")
              }
              onClick={() => setFairness(opt.v)}
              role="button"
              tabIndex={0}
            >
              <span className="onb-fair-radio" />
              <div>
                <div className="onb-fair-name">{opt.nameJsx}</div>
                <div className="onb-fair-desc">{opt.desc}</div>
              </div>
            </div>
          ))}
        </div>

        <div className="onb-fair-foot">
          Ditt svar låses till profilen.{" "}
          <strong>
            Linus svarar samma fråga separat (deterministiskt baserat på hans
            karaktär).
          </strong>{" "}
          Sen jämförs era svar och du kan se skillnaderna i partner-vyn.
        </div>
      </div>

      <div
        className="onb-rule"
        style={{
          background: "rgba(99,102,241,0.05)",
          borderColor: "rgba(99,102,241,0.2)",
        }}
      >
        <div className="onb-rule-eye" style={{ color: "#a5b4fc" }}>
          Pedagogik · varför fråga innan vi visar siffror
        </div>
        <div className="onb-rule-prose">
          Det finns inget rätt svar — men det finns ett{" "}
          <em style={{ color: "var(--warm)" }}>rationaliserat</em> svar. Om du
          redan vet att din partner tjänar 38 000 och du tjänar 22 000,
          kommer du gärna säga{" "}
          <em style={{ color: "var(--warm)" }}>proportionellt</em>. Men frågar
          du <em style={{ color: "var(--warm)" }}>innan</em>, baseras svaret
          på din värdering — vilket är pedagogiskt det viktiga. Att svara
          före data är hela poängen.
        </div>
      </div>
    </div>
  );
}

/* === STEG 8 — Klar / Vol. 18 är laddad === */
function Step8() {
  return (
    <div className="onb-step">
      <div className="onb-eye">Onboarding · steg 8 av 8 · klar</div>
      <h1 className="onb-h">
        Vol. 18 är <em>laddad</em>.
      </h1>
      <p className="onb-lead">
        Det är onsdag 29 april 2026. Sara har <em>14 282 kr</em> på
        lönekontot. Hyran kommer på fredag (7 240). Lönen den 25:e (22 880
        brutto, 22 400 netto). Tandläkaren ringer <em>klockan 14:22</em>.
        Postlådan har <strong>4 ohanterade</strong>. Anders Lind (din lärare)
        har skickat ett uppdrag: <em>räkna KALP för en 2:a på 2,4 Mkr</em>.
      </p>

      <div className="onb-rules">
        <div className="onb-rule">
          <div className="onb-rule-eye">Aktörer</div>
          <div className="onb-rule-h">8 + meta</div>
          <div className="onb-rule-prose">
            Banken, arbetsgivaren, Avanza, lånegivaren, försäkringar,
            förbrukning, Skatteverket, pension, hyresvärden, postlådan
          </div>
        </div>
        <div className="onb-rule">
          <div className="onb-rule-eye">Verktyg</div>
          <div className="onb-rule-h">10 stycken</div>
          <div className="onb-rule-prose">
            Bokföring, budget, mål, simulator, lånekalkyl, pension,
            deklaration, kvitton, moduler, reflektioner
          </div>
        </div>
        <div className="onb-rule">
          <div className="onb-rule-eye">Modul i bakgrunden</div>
          <div className="onb-rule-h">Bolån-modulen</div>
          <div className="onb-rule-prose">
            Steg 4 av 12 · KALP · 14 min kvar att räkna · uppdrag från Anders
            Lind förfaller 5 maj
          </div>
        </div>
      </div>

      <div
        className="onb-rule"
        style={{
          background: "rgba(220,76,43,0.06)",
          borderColor: "rgba(220,76,43,0.3)",
        }}
      >
        <div className="onb-rule-eye" style={{ color: "var(--accent)" }}>
          Sista regeln · ingen ångerknapp
        </div>
        <div className="onb-rule-h">
          <em>Beslut räknas</em>.
        </div>
        <div className="onb-rule-prose">
          När du betalat tandläkaren går det inte att "ångra" — pengarna är
          borta. När du valt att skjuta upp en räkning räknas <em>14 dagar</em>{" "}
          till påminnelsen. Det är samma{" "}
          <strong style={{ color: "var(--accent)" }}>irreversibilitet</strong>{" "}
          som i verkligheten. Det är hela poängen. Du kan reflektera efteråt
          — men inte spola tillbaka.{" "}
          <em style={{ color: "var(--warm)" }}>Klar?</em>
        </div>
      </div>
    </div>
  );
}
