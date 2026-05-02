/**
 * Aktör 10 · Arbetsförmedlingen — elev-vy.
 *
 * Spec: dev/game-motor/05-arbetsformedlingen.md
 *
 * Tre kolumner:
 *   1. Mats-välkomst + jobblista (sorterad på match_score)
 *   2. Mina pågående/avslutade ansökningar
 *   3. Aktiv ansökan: 5-rond state-machine med val per rond
 *
 * Återanvänder lan.css för konsekvent design (samma som
 * BoendemarknadV2).
 */
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  v2Api,
  type V2ArbetsformedlingenApplication,
  type V2ArbetsformedlingenJob,
  type V2ArbetsformedlingenJobsResponse,
} from "./api";
import { V2Banner } from "./V2Banner";
import "./lan.css";

const SEK = (n: number) =>
  new Intl.NumberFormat("sv-SE", { maximumFractionDigits: 0 }).format(n);

const CURRENT_YM = (() => {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
})();

const STATUS_LABEL: Record<V2ArbetsformedlingenApplication["status"], string> = {
  round_1: "Rond 1 · CV",
  round_2: "Rond 2 · Telefon",
  round_3: "Rond 3 · Case",
  round_4: "Rond 4 · Intervju",
  round_5: "Rond 5 · Erbjudande",
  offer_pending: "Erbjudande väntar",
  accepted: "Accepterat",
  rejected: "Avslag",
  declined: "Tackat nej",
  abandoned: "Avbrutet",
};

const STATUS_COLOR: Record<V2ArbetsformedlingenApplication["status"], string> = {
  round_1: "#7dd3fc",
  round_2: "#7dd3fc",
  round_3: "#7dd3fc",
  round_4: "#7dd3fc",
  round_5: "#fbbf24",
  offer_pending: "#fbbf24",
  accepted: "#34d399",
  rejected: "#f87171",
  declined: "#9ca3af",
  abandoned: "#9ca3af",
};


export function ArbetsformedlingenV2() {
  const [ym, setYm] = useState(CURRENT_YM);
  const [jobsData, setJobsData] = useState<V2ArbetsformedlingenJobsResponse | null>(null);
  const [apps, setApps] = useState<V2ArbetsformedlingenApplication[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedAppId, setSelectedAppId] = useState<number | null>(null);
  const [confirmMsg, setConfirmMsg] = useState<string | null>(null);

  const refresh = (targetYm: string) => {
    setLoading(true);
    Promise.all([
      v2Api.arbetsformedlingenJobs(targetYm, 6),
      v2Api.arbetsformedlingenApplications(),
    ])
      .then(([j, a]) => {
        setJobsData(j);
        setApps(a);
      })
      .catch((e) => setError(String(e?.message || e)))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    refresh(ym);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ym]);

  const handleApply = async (job: V2ArbetsformedlingenJob) => {
    try {
      const app = await v2Api.arbetsformedlingenApply(job);
      setConfirmMsg(`Ansökan startad till ${job.employer_name}!`);
      setSelectedAppId(app.id);
      refresh(ym);
    } catch (e) {
      setConfirmMsg(`Fel: ${String((e as Error).message || e)}`);
    }
  };

  const activeApp = apps.find((a) => a.id === selectedAppId)
    || apps.find((a) => ["round_1", "round_2", "round_3", "round_4", "offer_pending"].includes(a.status));

  return (
    <div className="v2-lan-root">
      <V2Banner status={{ role: "student", is_super_admin: false }} />

      <div className="shell">
        <Link className="actor-back" to="/v2/hub">
          Tillbaka till pentagonen
        </Link>

        <header className="actor-head" style={{ marginBottom: 18 }}>
          <div>
            <span className="pill warm">Aktör 10 · Arbetsförmedlingen</span>
            <h1 className="actor-name" style={{ marginTop: 14 }}>
              Arbetsförmedlingen — <em>byt jobb</em>.
            </h1>
            <p className="actor-sub" style={{ maxWidth: 720 }}>
              {jobsData?.mats_message ||
                "Mats hjälper dig hitta nytt jobb genom 5 ronder."}
            </p>
          </div>
        </header>

        <div
          style={{
            display: "flex",
            gap: 12,
            marginBottom: 16,
            alignItems: "center",
            fontFamily: "var(--mono)",
            fontSize: 11,
            color: "var(--text-mid)",
            letterSpacing: "0.6px",
          }}
        >
          <label>
            Spelmånad:&nbsp;
            <input
              type="month"
              value={ym}
              onChange={(e) => setYm(e.target.value || CURRENT_YM)}
              style={{
                background: "rgba(255,255,255,0.04)",
                border: "1px solid var(--line-strong)",
                color: "#fff",
                padding: "6px 10px",
                borderRadius: 6,
                fontFamily: "var(--mono)",
                fontSize: 11,
              }}
            />
          </label>
        </div>

        {confirmMsg && (
          <div
            style={{
              background: "rgba(110,231,183,0.06)",
              padding: "10px 16px",
              borderRadius: 6,
              marginBottom: 16,
              border: "1px solid rgba(110,231,183,0.4)",
              fontFamily: "var(--mono)",
              fontSize: 11,
              color: "#6ee7b7",
              letterSpacing: "0.5px",
            }}
          >
            ● {confirmMsg}
          </div>
        )}

        {error && (
          <div
            style={{
              color: "#fca5a5",
              fontFamily: "var(--mono)",
              fontSize: 11,
              marginBottom: 12,
            }}
          >
            Fel: {error}
          </div>
        )}

        <div
          style={{
            display: "grid",
            gridTemplateColumns: "1fr 1fr",
            gap: 24,
            marginBottom: 32,
          }}
        >
          {/* JOBBLISTA */}
          <section>
            <h2 style={{ fontSize: "1.1rem", marginBottom: 12 }}>
              Lediga jobb i {jobsData?.jobs[0]?.city_display || "din stad"}
            </h2>
            {loading && <div>Laddar jobb…</div>}
            <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              {jobsData?.jobs.map((j) => (
                <article
                  key={j.listing_id}
                  style={{
                    border: "1px solid var(--line)",
                    borderRadius: 8,
                    padding: 18,
                    background: "rgba(15,21,37,0.7)",
                    color: "var(--text)",
                  }}
                >
                  <div
                    style={{
                      display: "flex",
                      justifyContent: "space-between",
                      alignItems: "flex-start",
                      gap: 12,
                    }}
                  >
                    <div>
                      <div
                        style={{
                          fontFamily: "var(--serif)",
                          fontSize: 16,
                          fontWeight: 700,
                          color: "#fff",
                        }}
                      >
                        {j.yrke_display}
                      </div>
                      <div
                        style={{
                          fontFamily: "var(--mono)",
                          fontSize: 10.5,
                          color: "var(--text-mid)",
                          marginTop: 4,
                          letterSpacing: "0.4px",
                        }}
                      >
                        {j.employer_name} · {j.city_display}
                      </div>
                    </div>
                    <MatchPill score={j.match_score} />
                  </div>
                  <div
                    style={{
                      marginTop: 12,
                      display: "grid",
                      gridTemplateColumns: "1fr 1fr",
                      gap: 8,
                      fontFamily: "var(--mono)",
                      fontSize: 11,
                      color: "var(--text-mid)",
                    }}
                  >
                    <div>
                      Median:{" "}
                      <strong style={{ color: "#fff" }}>
                        {SEK(j.monthly_gross_median)} kr
                      </strong>
                    </div>
                    <div>
                      Utbildning:{" "}
                      <strong style={{ color: "#fff" }}>
                        {j.education_level}
                      </strong>
                    </div>
                    <div style={{ gridColumn: "1 / -1" }}>
                      Spann: {SEK(j.monthly_gross_min)}–
                      {SEK(j.monthly_gross_max)} kr/mån brutto
                    </div>
                  </div>
                  {j.description && (
                    <p
                      style={{
                        marginTop: 12,
                        fontFamily: "var(--serif)",
                        fontSize: 13.5,
                        lineHeight: 1.5,
                        color: "var(--text)",
                      }}
                    >
                      {j.description}
                    </p>
                  )}
                  <button
                    type="button"
                    onClick={() => handleApply(j)}
                    style={{
                      marginTop: 14,
                      width: "100%",
                      padding: "10px",
                      background: "var(--accent)",
                      color: "#fff",
                      border: 0,
                      borderRadius: 6,
                      cursor: "pointer",
                      fontFamily: "var(--mono)",
                      fontSize: 11,
                      fontWeight: 700,
                      letterSpacing: "1.2px",
                      textTransform: "uppercase",
                    }}
                  >
                    Sök jobbet →
                  </button>
                </article>
              ))}
            </div>
          </section>

          {/* MINA ANSÖKNINGAR */}
          <section>
            <h2 style={{ fontSize: "1.1rem", marginBottom: 12 }}>
              Mina ansökningar ({apps.length})
            </h2>
            {apps.length === 0 && (
              <div style={{ color: "var(--text-mid)" }}>
                Inga ansökningar än. Sök ett jobb från listan!
              </div>
            )}
            <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              {apps.map((a) => (
                <article
                  key={a.id}
                  onClick={() => setSelectedAppId(a.id)}
                  style={{
                    border: "1px solid",
                    borderColor:
                      selectedAppId === a.id
                        ? "var(--accent)"
                        : "var(--line)",
                    borderRadius: 8,
                    padding: 14,
                    cursor: "pointer",
                    background:
                      selectedAppId === a.id
                        ? "rgba(220,76,43,0.08)"
                        : "rgba(15,21,37,0.7)",
                    color: "var(--text)",
                  }}
                >
                  <div
                    style={{
                      display: "flex",
                      justifyContent: "space-between",
                      gap: 12,
                    }}
                  >
                    <strong
                      style={{
                        fontFamily: "var(--serif)",
                        fontSize: 14.5,
                        color: "#fff",
                      }}
                    >
                      {a.yrke_display}
                    </strong>
                    <span
                      style={{
                        fontFamily: "var(--mono)",
                        fontSize: 9.5,
                        color: STATUS_COLOR[a.status],
                        fontWeight: 700,
                        letterSpacing: "1.2px",
                        textTransform: "uppercase",
                      }}
                    >
                      {STATUS_LABEL[a.status]}
                    </span>
                  </div>
                  <div
                    style={{
                      fontFamily: "var(--mono)",
                      fontSize: 10.5,
                      color: "var(--text-mid)",
                      marginTop: 4,
                    }}
                  >
                    {a.employer_name} · startade {a.started_on}
                  </div>
                  {a.final_score !== null && (
                    <div
                      style={{
                        fontFamily: "var(--serif)",
                        fontSize: 12.5,
                        marginTop: 6,
                      }}
                    >
                      Slutpoäng:{" "}
                      <strong style={{ color: "var(--warm)" }}>
                        {a.final_score}/100
                      </strong>
                      {a.monthly_gross_offered != null &&
                        ` · erbjudande ${SEK(a.monthly_gross_offered)} kr/mån`}
                    </div>
                  )}
                </article>
              ))}
            </div>
          </section>
        </div>

        {/* AKTIV INTERVJU */}
        {activeApp && (
          <ActiveInterviewPanel
            app={activeApp}
            onUpdate={() => refresh(ym)}
            onMessage={setConfirmMsg}
          />
        )}
      </div>
    </div>
  );
}


function MatchPill({ score }: { score: number }) {
  const color =
    score >= 80 ? "#34d399" : score >= 60 ? "#fbbf24" : score >= 40 ? "#fb923c" : "#f87171";
  return (
    <span
      style={{
        background: color,
        color: "white",
        padding: "2px 8px",
        borderRadius: 12,
        fontSize: "0.75rem",
        fontWeight: 600,
      }}
    >
      Match {score}/100
    </span>
  );
}


function ActiveInterviewPanel({
  app, onUpdate, onMessage,
}: {
  app: V2ArbetsformedlingenApplication;
  onUpdate: () => void;
  onMessage: (msg: string) => void;
}) {
  const [submitting, setSubmitting] = useState(false);
  const [feedback, setFeedback] = useState<string | null>(null);

  // Round 1
  const [coverHours, setCoverHours] = useState(1.5);
  // Round 2
  const [tone, setTone] = useState<"saker" | "reflekterande" | "ansprakvol" | "arlig">("reflekterande");
  const [answers, setAnswers] = useState<string[]>(["", "", "", ""]);
  // Round 3
  const [effort, setEffort] = useState<"lat" | "normal" | "djup">("normal");
  const [caseAnswer, setCaseAnswer] = useState("");
  // Round 4
  const [dress, setDress] = useState<"vardag" | "business_casual" | "formell">("business_casual");
  const [research, setResearch] = useState(0.5);

  const submit = async (payload: Record<string, unknown>) => {
    setSubmitting(true);
    setFeedback(null);
    try {
      const r = await v2Api.arbetsformedlingenSubmitRound(app.id, payload);
      setFeedback(r.feedback_md);
      onUpdate();
    } catch (e) {
      onMessage(`Fel: ${String((e as Error).message || e)}`);
    } finally {
      setSubmitting(false);
    }
  };

  const handleAccept = async () => {
    try {
      await v2Api.arbetsformedlingenAccept(app.id);
      onMessage("Du tog jobbet! Pentagon-effekt: +3 safety, +1 economy.");
      onUpdate();
    } catch (e) {
      onMessage(`Fel: ${String((e as Error).message || e)}`);
    }
  };

  const handleDecline = async () => {
    try {
      await v2Api.arbetsformedlingenDecline(app.id);
      onMessage("Du tackade nej till erbjudandet.");
      onUpdate();
    } catch (e) {
      onMessage(`Fel: ${String((e as Error).message || e)}`);
    }
  };

  const handleAbandon = async () => {
    if (!confirm("Avbryta hela ansökan? Pentagon-effekt: -1 safety, -1 health.")) return;
    try {
      await v2Api.arbetsformedlingenAbandon(app.id);
      onMessage("Ansökan avbruten.");
      onUpdate();
    } catch (e) {
      onMessage(`Fel: ${String((e as Error).message || e)}`);
    }
  };

  return (
    <section
      style={{
        border: "2px solid var(--accent, #0066cc)",
        borderRadius: 12,
        padding: 18,
        background: "var(--surface, #fff)",
      }}
    >
      <header style={{ marginBottom: 14, display: "flex", justifyContent: "space-between" }}>
        <div>
          <h2 style={{ margin: 0, fontSize: "1.15rem" }}>
            Aktiv intervju · {app.yrke_display} @ {app.employer_name}
          </h2>
          <div style={{ color: "var(--text-mid)", fontSize: "0.9rem", marginTop: 4 }}>
            {STATUS_LABEL[app.status]} ·{" "}
            {app.current_round}/5 ronder · match {app.match_score}/100
          </div>
        </div>
        {app.status !== "offer_pending" && app.status !== "accepted" && (
          <button
            onClick={handleAbandon}
            style={{
              background: "transparent", border: "1px solid var(--border)",
              padding: "6px 12px", borderRadius: 6, cursor: "pointer",
              color: "var(--text-mid)",
            }}
          >
            Avbryt
          </button>
        )}
      </header>

      {/* Progress bar */}
      <div style={{ display: "flex", gap: 4, marginBottom: 18 }}>
        {[1, 2, 3, 4, 5].map((n) => (
          <div
            key={n}
            style={{
              flex: 1,
              height: 6,
              background:
                n < app.current_round || app.status === "offer_pending" || app.status === "accepted"
                  ? "var(--accent)"
                  : n === app.current_round
                    ? "rgba(0, 102, 204, 0.4)"
                    : "var(--border)",
              borderRadius: 3,
            }}
          />
        ))}
      </div>

      {feedback && (
        <div
          style={{
            padding: 12, borderRadius: 8, marginBottom: 16,
            background: "rgba(0, 102, 204, 0.06)",
            whiteSpace: "pre-wrap",
            fontSize: "0.9rem",
          }}
        >
          {feedback}
        </div>
      )}

      {app.status === "round_1" && (
        <div>
          <h3>Rond 1 · CV + personligt brev</h3>
          <p style={{ color: "var(--text-mid)" }}>
            Hur lång tid vill du lägga på personligt brev? Mer tid = bättre intryck men kostar fritid + relation.
          </p>
          <input
            type="range" min="0.5" max="4" step="0.5" value={coverHours}
            onChange={(e) => setCoverHours(parseFloat(e.target.value))}
          />
          <div>{coverHours} timmar</div>
          <button
            disabled={submitting}
            onClick={() => submit({ cover_letter_hours: coverHours })}
            style={btnStyle()}
          >
            Skicka in
          </button>
        </div>
      )}

      {app.status === "round_2" && (
        <div>
          <h3>Rond 2 · Telefonintervju</h3>
          <label>Ton:&nbsp;
            <select value={tone} onChange={(e) => setTone(e.target.value as typeof tone)}>
              <option value="saker">Säker</option>
              <option value="reflekterande">Reflekterande</option>
              <option value="ansprakvol">Anspråksfull</option>
              <option value="arlig">Ärlig</option>
            </select>
          </label>
          <p style={{ color: "var(--text-mid)", fontSize: "0.85rem" }}>
            Svara på 4 frågor (kortfattat går bra):
          </p>
          {[
            "Berätta om en gång du hanterat en konflikt",
            "Vad är dina svaga sidor?",
            "Varför vill du byta jobb?",
            "Vad förväntar du dig för lön?",
          ].map((q, i) => (
            <div key={i} style={{ marginBottom: 8 }}>
              <div style={{ fontSize: "0.85rem", marginBottom: 2 }}>{q}</div>
              <textarea
                rows={2}
                style={{ width: "100%" }}
                value={answers[i] || ""}
                onChange={(e) => {
                  const next = [...answers];
                  next[i] = e.target.value;
                  setAnswers(next);
                }}
              />
            </div>
          ))}
          <button
            disabled={submitting}
            onClick={() => submit({ tone, answers })}
            style={btnStyle()}
          >
            Skicka in
          </button>
        </div>
      )}

      {app.status === "round_3" && (
        <div>
          <h3>Rond 3 · Case</h3>
          <label>Effort:&nbsp;
            <select value={effort} onChange={(e) => setEffort(e.target.value as typeof effort)}>
              <option value="lat">Lat (mindre tid)</option>
              <option value="normal">Normal</option>
              <option value="djup">Djup (kostar fritid)</option>
            </select>
          </label>
          <textarea
            rows={6}
            style={{ width: "100%", marginTop: 8 }}
            placeholder="Skriv ditt case-svar här..."
            value={caseAnswer}
            onChange={(e) => setCaseAnswer(e.target.value)}
          />
          <button
            disabled={submitting}
            onClick={() => submit({ effort_level: effort, case_answer: caseAnswer })}
            style={btnStyle()}
          >
            Skicka in
          </button>
        </div>
      )}

      {app.status === "round_4" && (
        <div>
          <h3>Rond 4 · Intervju på plats</h3>
          <label>Klädsel:&nbsp;
            <select value={dress} onChange={(e) => setDress(e.target.value as typeof dress)}>
              <option value="vardag">Vardags</option>
              <option value="business_casual">Business casual</option>
              <option value="formell">Formell</option>
            </select>
          </label>
          <div style={{ marginTop: 8 }}>
            Företagsforskning: {research} h
            <input
              type="range" min="0" max="2" step="0.5" value={research}
              onChange={(e) => setResearch(parseFloat(e.target.value))}
            />
          </div>
          <button
            disabled={submitting}
            onClick={() => submit({ dress, research_hours: research })}
            style={btnStyle()}
          >
            Skicka in
          </button>
        </div>
      )}

      {app.status === "offer_pending" && (
        <div>
          <h3>Erbjudande mottaget!</h3>
          <p>
            Lön: <strong>{SEK(app.monthly_gross_offered || 0)} kr/mån</strong> brutto.
            Final score: <strong>{app.final_score}/100</strong>.
          </p>
          <div style={{ display: "flex", gap: 10 }}>
            <button onClick={handleAccept} style={btnStyle({ bg: "#34d399" })}>
              Acceptera
            </button>
            <button onClick={handleDecline} style={btnStyle({ bg: "#9ca3af" })}>
              Tacka nej
            </button>
          </div>
        </div>
      )}

      {(app.status === "accepted" || app.status === "rejected" ||
        app.status === "declined" || app.status === "abandoned") && (
        <div style={{ padding: 16, background: "rgba(0,0,0,0.03)", borderRadius: 8 }}>
          <strong>{STATUS_LABEL[app.status]}</strong> ·{" "}
          {app.completed_on && `slutdatum ${app.completed_on}`}
          {app.feedback_md && (
            <div style={{ marginTop: 8, fontSize: "0.85rem", whiteSpace: "pre-wrap" }}>
              {app.feedback_md}
            </div>
          )}
        </div>
      )}
    </section>
  );
}

function btnStyle(opts: { bg?: string } = {}): React.CSSProperties {
  return {
    marginTop: 12,
    padding: "10px 20px",
    background: opts.bg || "var(--accent, #0066cc)",
    color: "white",
    border: "none",
    borderRadius: 6,
    cursor: "pointer",
    fontSize: "0.95rem",
  };
}
