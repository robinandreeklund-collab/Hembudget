import { useEffect, useState } from "react";
import { api } from "@/api/client";
import { useAuth } from "@/hooks/useAuth";
import { EditorialAuthShell } from "@/components/editorial/EditorialAuthShell";
import { AuthAwareTopLinks } from "@/components/editorial/AuthAwareTopLinks";
import { LiveTime } from "@/components/editorial/LiveClock";

type DemoStatus = {
  demo_available: boolean;
  teacher_email?: string;
  student_codes?: Array<{ name: string; code: string; class: string | null }>;
  next_reset_at?: string | null;
  reason?: string;
};

/** Aktörer i simuleringen — de "yttre parter" eleven möter inne i
 *  plattformen. Visas som ett ekosystem så besökaren förstår omfånget
 *  innan de loggar in. */
type Actor = {
  group: "bank" | "myndighet" | "arbetsliv" | "ai" | "skola";
  short: string;
  name: string;
  role: string;
  body: string;
};

const ACTORS: Actor[] = [
  // Banker / penninghantering
  { group: "bank", short: "SE", name: "SEB · Lönekonto", role: "Bank · primärbank",
    body: "Lönen kommer in den 25:e. Räntefri vardags. Eleven ser saldo, OCR-rörelser, autogiron i realtid." },
  { group: "bank", short: "ND", name: "Nordea · Sparkonto", role: "Bank · buffert",
    body: "2,0 % årsränta. Sparmål per månad. Buffert testas när tandläkaren ringer eller bilen kraschar." },
  { group: "bank", short: "AV", name: "Avanza · ISK-broker", role: "Investeringar",
    body: "Schablonbeskattning på basen. Globalfond / svensk index / räntefond. Krasch-fredagar och 30-årsprognoser." },
  { group: "bank", short: "BG", name: "Bankgirot", role: "Autogiro · OCR",
    body: "Hyra, el, försäkring, mobil — 18 av 23 fakturor signeras kollektivt med EkonomilabbetID. 5 manuella." },

  // Myndigheter
  { group: "myndighet", short: "SK", name: "Skatteverket", role: "Skatt · deklaration",
    body: "A-skatt-tabell, kommunalskatt, K4-blankett, ISK-schablonintäkt. Allt synligt på lönespecen." },
  { group: "myndighet", short: "PM", name: "Pensionsmyndigheten", role: "Allmän pension",
    body: "7 % av varje lön. Premiepension. AP-fonderna. Eleven ser sin 67-årig-prognos automatiskt." },
  { group: "myndighet", short: "KV", name: "Konsumentverket", role: "Hushållsbudget-data",
    body: "Kategoribudgetar 2026 — mat, boende, kläder, fritid. Plattformens budget-baseline för varje typhushåll." },

  // Arbetsliv
  { group: "arbetsliv", short: "Vi", name: "Visma AB", role: "Arbetsgivare · Linda",
    body: "Lindas faktiska arbetsgivare. Genererar lönespec, kollektivavtal Akavia ITP1, tjänstepension 4,5 %." },
  { group: "arbetsliv", short: "AK", name: "Akavia · facket", role: "Lönedata · avtal",
    body: "Akavia 2026 medianlön per roll och region. Kollektivavtal som levande dokument — eleven ser värdet." },
  { group: "arbetsliv", short: "Fo", name: "Folksam", role: "Försäkring",
    body: "Hem · bil · person · ansvar. Premier auto-importeras. Försäkringsärende-flöden i akuta scenarier." },

  // AI / coachning
  { group: "ai", short: "Ec", name: "Echo", role: "Sokratisk AI-coach",
    body: "Claude Haiku 4.5. Ger frågor — inte råd. Triggar reflektioner efter val och vid kris." },
  { group: "ai", short: "Ma", name: "Maria · HR-chef", role: "Lönesamtals-förhandling",
    body: "AI-driven motpart i Lindas lönesamtal. Fem ronder, deterministisk förhandlingsmotor styrd av Akavia-data." },

  // Skola / lärarvy
  { group: "skola", short: "An", name: "Anna · samhällslärare", role: "Lärarvy · klassdashboard",
    body: "Annas dashboard visar 28 elever på en yta. WB-index, senaste val, vem som inte loggat in på 5 dagar." },
];

const GROUP_LABELS: Record<Actor["group"], string> = {
  bank: "Banker · pengaflöde",
  myndighet: "Myndigheter · regelverk",
  arbetsliv: "Arbetsliv · avtal",
  ai: "AI-coachning",
  skola: "Skola · lärarvy",
};

export default function DemoChoice() {
  const { demoTeacherLogin, demoStudentLogin } = useAuth();
  const [status, setStatus] = useState<DemoStatus | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    api<DemoStatus>("/demo/status")
      .then(setStatus)
      .catch((e) => setErr(e instanceof Error ? e.message : String(e)));
  }, []);

  async function loginAsTeacher() {
    setBusy(true); setErr(null);
    try {
      await demoTeacherLogin();
      window.location.href = "/teacher";
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally { setBusy(false); }
  }
  async function loginAsStudent(code: string) {
    setBusy(true); setErr(null);
    try {
      await demoStudentLogin(code);
      window.location.href = "/dashboard";
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally { setBusy(false); }
  }

  // Gruppera aktörer per group
  const grouped = (Object.keys(GROUP_LABELS) as Actor["group"][]).map((g) => ({
    g, label: GROUP_LABELS[g], items: ACTORS.filter((a) => a.group === g),
  }));

  return (
    <EditorialAuthShell topNavRight={<AuthAwareTopLinks />}>
      <div className="ed-eyebrow">Demoläge · Vol. 00 · Tour</div>

      <div className="ed-clock">
        <div className="ed-clock-time">
          Klockan är <LiveTime />.
        </div>
        <span className="ed-clock-countdown">
          Demon nollställs <em>var 10:e minut</em>.
        </span>
      </div>

      <p className="ed-subhead">
        Du står just utanför ett ekosystem av <em>tretton simulerade
        parter</em>. Banken, Skatteverket, Visma, Avanza, Folksam, Akavia,
        Konsumentverket — plus AI-coacherna Echo och Maria, plus lärarvyn
        Anna. Allt riggat med svenska 2026-data.
      </p>

      {err && <div className="ed-error">{err}</div>}

      {/* Aktör-grid: visa alla simulerade parter */}
      <div className="demo-actors">
        <div className="demo-actors-title">
          <span className="demo-actors-eye">● Inuti plattformen</span>
          <h3>Tretton parter, en simulering.</h3>
          <p>
            Varje aktör är en levande del av elevens vecka. Klicka in
            som lärare eller elev så möter du dem i flödet.
          </p>
        </div>

        {grouped.map(({ g, label, items }) => (
          <div key={g} className="demo-actor-group">
            <div className="demo-actor-group-eye">{label}</div>
            <div className="demo-actor-row">
              {items.map((a) => (
                <div key={a.name} className={"demo-actor demo-actor-" + a.group}>
                  <div className="demo-actor-chip">{a.short}</div>
                  <div className="demo-actor-body">
                    <div className="demo-actor-name">{a.name}</div>
                    <div className="demo-actor-role">{a.role}</div>
                    <p className="demo-actor-text">{a.body}</p>
                  </div>
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>

      {/* Auth-flow */}
      <div className="demo-enter">
        <div className="demo-enter-eye">● Kliv in i ekosystemet</div>
        <h3>Två sätt att börja.</h3>

        {!status ? (
          <p style={{ color: "rgba(255,255,255,0.55)", fontStyle: "italic" }}>
            Laddar demo-status…
          </p>
        ) : !status.demo_available ? (
          <p style={{ color: "rgba(255,255,255,0.7)" }}>
            Demomiljön är inte tillgänglig just nu
            {status.reason ? `: ${status.reason}` : "."}. Testa igen
            om en minut.
          </p>
        ) : (
          <>
            <button
              onClick={loginAsTeacher}
              disabled={busy}
              className="demo-enter-tile is-teacher"
              aria-label="Logga in som demo-lärare"
            >
              <span className="demo-enter-icon">⚡</span>
              <div>
                <div className="demo-enter-title">Som lärare</div>
                <div className="demo-enter-body">
                  Annas perspektiv. Skapa elever, skicka dokument, se
                  klassens dashboard. Du ser hela ekosystemet uppifrån.
                </div>
              </div>
              <span className="demo-enter-arrow">→</span>
            </button>

            {(status.student_codes ?? []).length > 0 && (
              <>
                <div className="demo-enter-or">eller — som en av eleverna</div>
                <div className="demo-enter-grid">
                  {(status.student_codes ?? []).map((s) => (
                    <button
                      key={s.code}
                      onClick={() => loginAsStudent(s.code)}
                      disabled={busy}
                      className="demo-enter-tile is-student"
                    >
                      <span className="demo-enter-code">{s.code}</span>
                      <div>
                        <div className="demo-enter-title">{s.name}</div>
                        <div className="demo-enter-body">
                          {s.class ?? "Demo-elev"} — möt banken, Visma,
                          Skatteverket inifrån.
                        </div>
                      </div>
                      <span className="demo-enter-arrow">→</span>
                    </button>
                  ))}
                </div>
              </>
            )}

            {status.next_reset_at && <ResetCountdown iso={status.next_reset_at} />}
          </>
        )}
      </div>

      <style>{`
        .demo-actors { margin-top: 8px; }
        .demo-actors-title { margin-bottom: 22px; }
        .demo-actors-eye {
          font-family: var(--ed-mono); font-size: 10px; font-weight: 700;
          letter-spacing: 1.6px; text-transform: uppercase;
          color: var(--ed-accent);
        }
        .demo-actors-title h3 {
          font-family: var(--ed-serif); font-size: 28px; font-weight: 700;
          letter-spacing: -0.6px; line-height: 1.1;
          color: #fff; margin-top: 6px;
        }
        .demo-actors-title p {
          font-family: var(--ed-serif); font-style: italic;
          font-size: 15px; line-height: 1.5;
          color: rgba(255,255,255,0.7);
          margin-top: 10px; max-width: 56ch;
        }
        .demo-actor-group { margin-top: 22px; }
        .demo-actor-group-eye {
          font-family: var(--ed-mono); font-size: 9.5px; font-weight: 700;
          letter-spacing: 1.6px; text-transform: uppercase;
          color: rgba(255,255,255,0.55);
          margin-bottom: 10px;
        }
        .demo-actor-row {
          display: grid;
          grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
          gap: 10px;
        }
        .demo-actor {
          display: grid;
          grid-template-columns: 44px 1fr;
          gap: 12px;
          padding: 14px 14px 16px;
          background: rgba(255,255,255,0.04);
          border: 1px solid rgba(255,255,255,0.10);
          border-radius: 4px;
          transition: border-color .25s var(--ed-ease), background .25s var(--ed-ease);
        }
        .demo-actor:hover {
          border-color: var(--ed-gold);
          background: rgba(255,255,255,0.07);
        }
        .demo-actor-chip {
          width: 44px; height: 44px;
          border-radius: 6px;
          display: grid; place-items: center;
          font-family: var(--ed-mono); font-size: 13px; font-weight: 700;
          letter-spacing: 0.4px;
          background: rgba(220, 76, 43, 0.12);
          color: var(--ed-accent);
          border: 1px solid rgba(220, 76, 43, 0.3);
        }
        .demo-actor-bank .demo-actor-chip   { background: rgba(220, 76, 43, 0.12);  color: var(--ed-accent); border-color: rgba(220, 76, 43, 0.3); }
        .demo-actor-myndighet .demo-actor-chip { background: rgba(15, 23, 42, 0.6); color: #fff; border-color: rgba(255,255,255,0.18); }
        .demo-actor-arbetsliv .demo-actor-chip { background: rgba(251, 191, 36, 0.14); color: var(--ed-gold); border-color: rgba(251, 191, 36, 0.32); }
        .demo-actor-ai .demo-actor-chip   { background: rgba(99, 102, 241, 0.16); color: #a5b4fc; border-color: rgba(99, 102, 241, 0.4); }
        .demo-actor-skola .demo-actor-chip { background: rgba(16, 185, 129, 0.14); color: #6ee7b7; border-color: rgba(16, 185, 129, 0.35); }
        .demo-actor-name {
          font-family: var(--ed-serif); font-size: 16px; font-weight: 700;
          letter-spacing: -0.3px; color: #fff;
        }
        .demo-actor-role {
          font-family: var(--ed-mono); font-size: 9.5px;
          letter-spacing: 1.4px; text-transform: uppercase;
          color: rgba(255,255,255,0.55);
          margin-top: 2px;
        }
        .demo-actor-text {
          font-size: 12.5px; line-height: 1.5;
          color: rgba(255,255,255,0.78);
          margin-top: 8px;
        }

        .demo-enter {
          margin-top: 32px;
          padding-top: 32px;
          border-top: 1px solid rgba(255,255,255,0.12);
        }
        .demo-enter-eye {
          font-family: var(--ed-mono); font-size: 10px; font-weight: 700;
          letter-spacing: 1.6px; text-transform: uppercase;
          color: var(--ed-gold);
        }
        .demo-enter h3 {
          font-family: var(--ed-serif); font-size: 28px; font-weight: 700;
          letter-spacing: -0.6px; line-height: 1.1;
          color: #fff; margin-top: 6px;
        }
        .demo-enter h3::after {
          content: ""; display: block;
          width: 36px; height: 2px; background: var(--ed-gold);
          margin-top: 12px;
        }
        .demo-enter-tile {
          display: grid;
          grid-template-columns: 56px 1fr auto;
          gap: 18px; align-items: center;
          width: 100%;
          padding: 18px 22px;
          margin-top: 18px;
          border-radius: 6px;
          font: inherit;
          color: #fff;
          text-align: left;
          cursor: pointer;
          transition: transform .25s var(--ed-ease), border-color .25s var(--ed-ease);
        }
        .demo-enter-tile:disabled { opacity: 0.5; cursor: not-allowed; }
        .demo-enter-tile:not(:disabled):hover { transform: translateY(-2px); }
        .demo-enter-tile.is-teacher {
          background: linear-gradient(135deg, rgba(251, 191, 36, 0.10) 0%, rgba(220, 76, 43, 0.10) 100%);
          border: 1px solid rgba(251, 191, 36, 0.32);
        }
        .demo-enter-tile.is-teacher:hover { border-color: var(--ed-gold); }
        .demo-enter-tile.is-student {
          background: rgba(255,255,255,0.04);
          border: 1px solid rgba(255,255,255,0.12);
        }
        .demo-enter-tile.is-student:hover { border-color: var(--ed-accent); }
        .demo-enter-icon {
          width: 56px; height: 56px;
          border-radius: 8px;
          background: rgba(251,191,36,0.14);
          display: grid; place-items: center;
          font-size: 24px;
        }
        .demo-enter-code {
          width: 56px; height: 56px;
          border-radius: 8px;
          background: rgba(220,76,43,0.16);
          color: var(--ed-accent);
          display: grid; place-items: center;
          font-family: var(--ed-mono); font-size: 13px; font-weight: 700;
          letter-spacing: 1.4px;
          border: 1px solid rgba(220,76,43,0.32);
        }
        .demo-enter-title {
          font-family: var(--ed-serif); font-size: 19px; font-weight: 700;
          letter-spacing: -0.4px;
        }
        .demo-enter-body {
          font-size: 13.5px; line-height: 1.5;
          color: rgba(255,255,255,0.7);
          margin-top: 4px;
          max-width: 52ch;
        }
        .demo-enter-arrow {
          font-family: var(--ed-mono); font-weight: 400; font-size: 18px;
          color: rgba(255,255,255,0.5);
        }
        .demo-enter-or {
          font-family: var(--ed-mono); font-size: 10px; font-weight: 700;
          letter-spacing: 1.6px; text-transform: uppercase;
          color: rgba(255,255,255,0.45);
          margin: 22px 0 6px;
          text-align: center;
        }
        .demo-enter-or::before, .demo-enter-or::after {
          content: ""; display: inline-block;
          width: 40px; height: 1px;
          background: rgba(255,255,255,0.2);
          vertical-align: middle;
          margin: 0 12px;
        }
        .demo-enter-grid {
          display: grid;
          grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
          gap: 10px;
        }
        .demo-enter-grid .demo-enter-tile {
          margin-top: 0;
        }

        @media (max-width: 600px) {
          .demo-actor { grid-template-columns: 1fr; }
          .demo-actor-chip { width: 36px; height: 36px; font-size: 11px; }
        }
      `}</style>
    </EditorialAuthShell>
  );
}

function ResetCountdown({ iso }: { iso: string }) {
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 5000);
    return () => clearInterval(t);
  }, []);
  const diffMs = new Date(iso).getTime() - now;
  const mins = Math.max(0, Math.floor(diffMs / 60000));
  const secs = Math.max(0, Math.floor((diffMs % 60000) / 1000));
  return (
    <div
      style={{
        textAlign: "center",
        fontFamily: '"JetBrains Mono", ui-monospace, monospace',
        fontSize: "11px",
        letterSpacing: "1.6px",
        textTransform: "uppercase",
        color: "rgba(255, 255, 255, 0.5)",
        marginTop: "18px",
      }}
    >
      Nästa reset · {mins} min {secs.toString().padStart(2, "0")} s
    </div>
  );
}
