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
  const [detailJob, setDetailJob] = useState<V2ArbetsformedlingenJob | null>(null);
  const [applyBusy, setApplyBusy] = useState(false);

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
    setApplyBusy(true);
    try {
      const app = await v2Api.arbetsformedlingenApply(job);
      setConfirmMsg(`Ansökan startad till ${job.employer_name}!`);
      setSelectedAppId(app.id);
      setDetailJob(null);
      refresh(ym);
    } catch (e) {
      setConfirmMsg(`Fel: ${String((e as Error).message || e)}`);
    } finally {
      setApplyBusy(false);
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
              {jobsData?.jobs.map((j) => {
                const tier = j.match_score >= 80 ? "good"
                          : j.match_score >= 60 ? "ok" : "low";
                const tierColor = tier === "good" ? "#34d399"
                                : tier === "ok" ? "#fbbf24" : "#f87171";
                return (
                  <article
                    key={j.listing_id}
                    onClick={() => setDetailJob(j)}
                    style={{
                      border: "1px solid var(--line)",
                      borderLeft: `3px solid ${tierColor}`,
                      borderRadius: 8,
                      padding: "16px 20px",
                      background: "rgba(15,21,37,0.6)",
                      color: "var(--text)",
                      cursor: "pointer",
                      transition: "background 0.15s, border-color 0.15s",
                    }}
                    onMouseEnter={(e) => {
                      (e.currentTarget as HTMLElement).style.background = "rgba(15,21,37,0.85)";
                    }}
                    onMouseLeave={(e) => {
                      (e.currentTarget as HTMLElement).style.background = "rgba(15,21,37,0.6)";
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
                      <div style={{ minWidth: 0, flex: 1 }}>
                        <div
                          style={{
                            fontFamily: "var(--mono)",
                            fontSize: 9,
                            letterSpacing: "1.4px",
                            textTransform: "uppercase",
                            color: tierColor,
                            marginBottom: 4,
                          }}
                        >
                          {j.employer_name}
                        </div>
                        <div
                          style={{
                            fontFamily: "var(--serif)",
                            fontSize: 18,
                            fontWeight: 700,
                            color: "#fff",
                            letterSpacing: "-0.2px",
                          }}
                        >
                          {j.yrke_display}
                        </div>
                        <div
                          style={{
                            fontFamily: "var(--mono)",
                            fontSize: 10,
                            color: "var(--text-mid)",
                            marginTop: 6,
                            letterSpacing: "0.3px",
                          }}
                        >
                          {j.city_display} · {j.employment_type}
                        </div>
                      </div>
                      <MatchPill score={j.match_score} />
                    </div>
                    <div
                      style={{
                        marginTop: 14,
                        paddingTop: 12,
                        borderTop: "1px solid var(--line)",
                        display: "flex",
                        justifyContent: "space-between",
                        alignItems: "center",
                        flexWrap: "wrap",
                        gap: 10,
                        fontFamily: "var(--mono)",
                        fontSize: 11,
                      }}
                    >
                      <div style={{ color: "var(--text-mid)" }}>
                        <strong style={{ color: "#fff" }}>
                          {SEK(j.monthly_gross_min)}–{SEK(j.monthly_gross_max)}
                        </strong>{" "}
                        kr/mån
                      </div>
                      <div style={{ color: "var(--text-dim)", fontSize: 10 }}>
                        Sista ans. {j.application_deadline} →
                      </div>
                    </div>
                  </article>
                );
              })}
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

      {/* Detaljvy-modal · klick på jobb-card */}
      {detailJob && (
        <JobDetailModal
          job={detailJob}
          onClose={() => setDetailJob(null)}
          onApply={() => handleApply(detailJob)}
          applyBusy={applyBusy}
        />
      )}
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
        border: "1px solid var(--accent)",
        borderRadius: 8,
        padding: "20px 24px",
        background: "rgba(15,21,37,0.7)",
        color: "var(--text)",
      }}
    >
      <header
        style={{
          marginBottom: 14,
          display: "flex",
          justifyContent: "space-between",
          alignItems: "flex-start",
          gap: 14,
        }}
      >
        <div>
          <div
            style={{
              fontFamily: "var(--mono)",
              fontSize: 9.5,
              letterSpacing: "1.2px",
              textTransform: "uppercase",
              color: "var(--accent)",
              marginBottom: 6,
            }}
          >
            ● Aktiv intervju
          </div>
          <h2
            style={{
              margin: 0,
              fontFamily: "var(--serif)",
              fontSize: 18,
              color: "#fff",
              fontWeight: 700,
            }}
          >
            {app.yrke_display} <em style={{ color: "var(--text-mid)" }}>@</em>{" "}
            {app.employer_name}
          </h2>
          <div
            style={{
              fontFamily: "var(--mono)",
              fontSize: 10.5,
              color: "var(--text-mid)",
              marginTop: 6,
              letterSpacing: "0.6px",
            }}
          >
            {STATUS_LABEL[app.status]} · {app.current_round}/5 ronder · match{" "}
            {app.match_score}/100
          </div>
        </div>
        {app.status !== "offer_pending" && app.status !== "accepted" && (
          <button
            type="button"
            onClick={handleAbandon}
            className="cta-btn ghost"
            style={{ padding: "6px 12px", fontSize: 9.5 }}
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
                    ? "rgba(220,76,43,0.4)"
                    : "var(--line-strong)",
              borderRadius: 3,
            }}
          />
        ))}
      </div>

      {feedback && (
        <div
          style={{
            padding: "12px 16px",
            borderRadius: 6,
            marginBottom: 16,
            background: "rgba(110,231,183,0.06)",
            border: "1px solid rgba(110,231,183,0.4)",
            whiteSpace: "pre-wrap",
            fontSize: 13,
            fontFamily: "var(--serif)",
            lineHeight: 1.5,
            color: "var(--text)",
          }}
        >
          {feedback}
        </div>
      )}

      {app.status === "round_1" && (
        <CoverLetterEditor
          app={app}
          submitting={submitting}
          onSubmit={(text) => submit({ cover_letter_text: text })}
        />
      )}

      {app.status === "round_2" && (
        <div>
          <h3 style={ronH3Style}>Rond 2 · Telefonintervju</h3>
          <label style={ronLabelStyle}>
            Ton:&nbsp;
            <select
              value={tone}
              onChange={(e) => setTone(e.target.value as typeof tone)}
              style={ronSelectStyle}
            >
              <option value="saker">Säker</option>
              <option value="reflekterande">Reflekterande</option>
              <option value="ansprakvol">Anspråksfull</option>
              <option value="arlig">Ärlig</option>
            </select>
          </label>
          <p
            style={{
              color: "var(--text-mid)",
              fontSize: 12,
              fontFamily: "var(--serif)",
              marginTop: 12,
            }}
          >
            Svara på 4 frågor (kortfattat går bra):
          </p>
          {[
            "Berätta om en gång du hanterat en konflikt",
            "Vad är dina svaga sidor?",
            "Varför vill du byta jobb?",
            "Vad förväntar du dig för lön?",
          ].map((q, i) => (
            <div key={i} style={{ marginBottom: 10 }}>
              <div
                style={{
                  fontFamily: "var(--serif)",
                  fontSize: 13,
                  color: "#fff",
                  marginBottom: 4,
                }}
              >
                {q}
              </div>
              <textarea
                rows={2}
                style={ronTextareaStyle}
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
            type="button"
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
          <h3 style={ronH3Style}>Rond 3 · Case</h3>
          <label style={ronLabelStyle}>
            Effort:&nbsp;
            <select
              value={effort}
              onChange={(e) => setEffort(e.target.value as typeof effort)}
              style={ronSelectStyle}
            >
              <option value="lat">Lat (mindre tid)</option>
              <option value="normal">Normal</option>
              <option value="djup">Djup (kostar fritid)</option>
            </select>
          </label>
          <textarea
            rows={6}
            style={{ ...ronTextareaStyle, marginTop: 10 }}
            placeholder="Skriv ditt case-svar här..."
            value={caseAnswer}
            onChange={(e) => setCaseAnswer(e.target.value)}
          />
          <button
            type="button"
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
          <h3 style={ronH3Style}>Rond 4 · Intervju på plats</h3>
          <label style={ronLabelStyle}>
            Klädsel:&nbsp;
            <select
              value={dress}
              onChange={(e) => setDress(e.target.value as typeof dress)}
              style={ronSelectStyle}
            >
              <option value="vardag">Vardags</option>
              <option value="business_casual">Business casual</option>
              <option value="formell">Formell</option>
            </select>
          </label>
          <div
            style={{
              marginTop: 10,
              fontFamily: "var(--mono)",
              fontSize: 11,
              color: "#fff",
            }}
          >
            Företagsforskning: {research} h
            <input
              type="range" min="0" max="2" step="0.5" value={research}
              onChange={(e) => setResearch(parseFloat(e.target.value))}
              style={{ width: "100%", marginTop: 4 }}
            />
          </div>
          <button
            type="button"
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
          <h3 style={ronH3Style}>Erbjudande mottaget!</h3>
          <p
            style={{
              fontFamily: "var(--serif)",
              fontSize: 14,
              color: "var(--text)",
            }}
          >
            Lön:{" "}
            <strong style={{ color: "#6ee7b7" }}>
              {SEK(app.monthly_gross_offered || 0)} kr/mån
            </strong>{" "}
            brutto. Slutpoäng:{" "}
            <strong style={{ color: "var(--warm)" }}>
              {app.final_score}/100
            </strong>.
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
    marginTop: 14,
    padding: "10px 18px",
    background: opts.bg || "var(--accent)",
    color: "#fff",
    border: 0,
    borderRadius: 100,
    cursor: "pointer",
    fontFamily: "var(--mono)",
    fontSize: 10,
    fontWeight: 700,
    letterSpacing: "1.2px",
    textTransform: "uppercase",
  };
}

const ronTextareaStyle: React.CSSProperties = {
  background: "rgba(255,255,255,0.04)",
  border: "1px solid var(--line-strong)",
  color: "#fff",
  padding: "8px 10px",
  borderRadius: 6,
  fontFamily: "Inter, sans-serif",
  fontSize: 13,
  width: "100%",
  resize: "vertical",
};

const ronSelectStyle: React.CSSProperties = {
  background: "rgba(255,255,255,0.04)",
  border: "1px solid var(--line-strong)",
  color: "#fff",
  padding: "6px 10px",
  borderRadius: 6,
  fontFamily: "var(--mono)",
  fontSize: 12,
};

const ronH3Style: React.CSSProperties = {
  fontFamily: "var(--serif)",
  fontSize: 16,
  fontWeight: 700,
  color: "#fff",
  margin: "0 0 8px 0",
};

const ronLabelStyle: React.CSSProperties = {
  fontFamily: "var(--mono)",
  fontSize: 10,
  letterSpacing: "0.8px",
  color: "var(--text-mid)",
  display: "inline-block",
  marginBottom: 6,
};


// === Sprint 7 · Personligt brev-editor med AI-feedback ===

function CoverLetterEditor({
  app, submitting, onSubmit,
}: {
  app: V2ArbetsformedlingenApplication;
  submitting: boolean;
  onSubmit: (text: string) => void;
}) {
  const [text, setText] = useState("");
  const [feedback, setFeedback] = useState<{
    score: number; feedback_md: string; highlights: string[];
  } | null>(null);
  const [feedbackBusy, setFeedbackBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const wordCount = text.trim().split(/\s+/).filter(Boolean).length;
  const tooShort = wordCount < 30;
  const tooLong = wordCount > 600;

  async function getFeedback() {
    if (tooShort) {
      setError("Skriv minst 30 ord för att få feedback.");
      return;
    }
    setFeedbackBusy(true);
    setError(null);
    try {
      const res = await v2Api.arbetsformedlingenCoverLetterPreview({
        text,
        yrke_display: app.yrke_display,
        employer_name: app.employer_name,
      });
      setFeedback(res);
    } catch (e) {
      const msg = String((e as Error)?.message || e);
      if (msg.includes("503")) setError("AI-funktioner är inte aktiverade.");
      else if (msg.includes("502")) setError("AI-tjänsten gick inte att nå.");
      else setError(msg);
    } finally {
      setFeedbackBusy(false);
    }
  }

  return (
    <div>
      <h3 style={ronH3Style}>Rond 1 · Personligt brev</h3>
      <p
        style={{
          color: "var(--text-mid)",
          fontFamily: "var(--serif)",
          fontSize: 13.5,
          lineHeight: 1.5,
          marginBottom: 12,
        }}
      >
        Skriv ett personligt brev till{" "}
        <strong style={{ color: "var(--warm)" }}>{app.employer_name}</strong>.
        Berätta varför just <em>detta</em> jobbet och ge konkreta exempel
        från din erfarenhet. Sikta på 200–400 ord. Du kan be om AI-feedback
        innan du skickar in — den kostar inget extra rond.
      </p>
      <textarea
        value={text}
        onChange={(e) => setText(e.target.value)}
        rows={14}
        placeholder="Hej,&#10;&#10;Jag söker jobbet som ... eftersom ..."
        style={{
          width: "100%",
          background: "rgba(255,255,255,0.04)",
          border: "1px solid var(--line-strong)",
          borderRadius: 6,
          color: "#fff",
          fontFamily: "var(--serif)",
          fontSize: 14,
          lineHeight: 1.5,
          padding: "12px 14px",
          boxSizing: "border-box",
          resize: "vertical",
        }}
      />
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          marginTop: 6,
          fontFamily: "var(--mono)",
          fontSize: 10,
          color: tooShort ? "#fca5a5" : tooLong ? "#fca5a5" : "var(--text-dim)",
        }}
      >
        <span>
          {wordCount} ord
          {tooShort && " · för kort (min 30)"}
          {tooLong && " · för långt (max 600)"}
        </span>
        <span style={{ color: "var(--text-dim)" }}>
          Tips: 200–400 ord brukar landa bäst
        </span>
      </div>

      {error && (
        <div
          style={{
            marginTop: 12,
            padding: "8px 12px",
            background: "rgba(220,38,38,0.08)",
            color: "#fca5a5",
            borderRadius: 4,
            fontFamily: "var(--mono)",
            fontSize: 11,
          }}
        >
          {error}
        </div>
      )}

      {feedback && (
        <div
          style={{
            marginTop: 14,
            padding: "14px 16px",
            background: "rgba(139, 92, 246, 0.06)",
            borderLeft: "3px solid #a78bfa",
            borderRadius: 4,
          }}
        >
          <div
            style={{
              fontFamily: "var(--mono)",
              fontSize: 9,
              letterSpacing: "1.4px",
              textTransform: "uppercase",
              color: "#a78bfa",
              marginBottom: 6,
            }}
          >
            ✦ AI-feedback · {feedback.score}/25 poäng
          </div>
          <div
            style={{
              fontFamily: "var(--serif)",
              fontSize: 13.5,
              color: "rgba(255,255,255,0.85)",
              lineHeight: 1.55,
              whiteSpace: "pre-wrap",
            }}
          >
            {feedback.feedback_md}
          </div>
          {feedback.highlights.length > 0 && (
            <div style={{ marginTop: 12 }}>
              <div
                style={{
                  fontFamily: "var(--mono)",
                  fontSize: 9.5,
                  letterSpacing: "1.2px",
                  textTransform: "uppercase",
                  color: "#6ee7b7",
                  marginBottom: 6,
                }}
              >
                ✓ Det här gör du bra
              </div>
              {feedback.highlights.map((h, i) => (
                <div
                  key={i}
                  style={{
                    fontSize: 13,
                    color: "rgba(255,255,255,0.78)",
                    fontFamily: "var(--serif)",
                    marginTop: 4,
                  }}
                >
                  • {h}
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      <div style={{ marginTop: 16, display: "flex", gap: 10, flexWrap: "wrap" }}>
        <button
          type="button"
          disabled={feedbackBusy || tooShort || tooLong}
          onClick={getFeedback}
          style={{
            ...btnStyle(),
            background: "transparent",
            border: "1px solid #a78bfa",
            color: "#a78bfa",
          }}
        >
          {feedbackBusy ? "AI-bedömer..." : "✦ Be om AI-feedback"}
        </button>
        <button
          type="button"
          disabled={submitting || tooShort || tooLong}
          onClick={() => onSubmit(text)}
          style={btnStyle()}
        >
          {submitting ? "Skickar..." : "Skicka in →"}
        </button>
      </div>
    </div>
  );
}

// === Sprint 7 · Job-detaljvy modal ===

export function JobDetailModal({
  job, onClose, onApply, applyBusy,
}: {
  job: V2ArbetsformedlingenJob;
  onClose: () => void;
  onApply: () => void;
  applyBusy: boolean;
}) {
  return (
    <div
      onClick={onClose}
      style={{
        position: "fixed", inset: 0, zIndex: 100,
        background: "rgba(0,0,0,0.7)",
        display: "flex", alignItems: "center", justifyContent: "center",
        padding: 20,
      }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          background: "#14131a",
          border: "1px solid var(--line-strong)",
          borderRadius: 10,
          maxWidth: 720, width: "100%",
          maxHeight: "90vh", overflowY: "auto",
          padding: "26px 30px",
        }}
      >
        <div style={{
          display: "flex", justifyContent: "space-between",
          alignItems: "start", marginBottom: 14,
        }}>
          <div>
            <div
              style={{
                fontFamily: "var(--mono)",
                fontSize: 9.5,
                letterSpacing: "1.4px",
                textTransform: "uppercase",
                color: "var(--accent)",
                marginBottom: 4,
              }}
            >
              ● Jobbannons
            </div>
            <h2 style={{
              fontFamily: "var(--serif)", fontSize: 26,
              fontWeight: 700, letterSpacing: "-0.5px",
              margin: 0,
            }}>
              {job.yrke_display}
            </h2>
            <div style={{
              fontFamily: "var(--serif)", fontSize: 16, marginTop: 4,
              color: "var(--warm)", fontStyle: "italic",
            }}>
              {job.employer_name} · {job.city_display}
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            style={{
              ...btnStyle(),
              background: "transparent",
              border: "1px solid var(--line-strong)",
              color: "var(--text-mid)",
            }}
          >
            Stäng
          </button>
        </div>

        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fit, minmax(140px, 1fr))",
            gap: 0,
            margin: "16px -30px",
            borderTop: "1px solid var(--line)",
            borderBottom: "1px solid var(--line)",
          }}
        >
          {[
            { label: "Lön/mån", value: `${SEK(job.monthly_gross_min)}–${SEK(job.monthly_gross_max)}` },
            { label: "Anställning", value: job.employment_type },
            { label: "Arbetstid", value: job.work_hours },
            { label: "Tillträde", value: job.start_date.replace("Tillträde ", "") },
            { label: "Sista ans.", value: job.application_deadline },
          ].map((c) => (
            <div key={c.label} style={{
              padding: "14px 18px",
              borderRight: "1px solid var(--line)",
              background: "rgba(255,255,255,0.02)",
            }}>
              <div style={{
                fontFamily: "var(--mono)", fontSize: 9,
                letterSpacing: "1.4px", textTransform: "uppercase",
                color: "var(--text-dim)", marginBottom: 4,
              }}>
                {c.label}
              </div>
              <div style={{
                fontFamily: "var(--serif)", fontSize: 13,
                color: "#fff",
              }}>
                {c.value}
              </div>
            </div>
          ))}
        </div>

        <Section title="Om företaget">
          <p style={{
            fontFamily: "var(--serif)", fontSize: 14.5, lineHeight: 1.6,
            color: "rgba(255,255,255,0.8)",
          }}>
            {job.company_blurb.replace("{employer}", job.employer_name)}
          </p>
        </Section>

        <Section title="Vad du kommer göra">
          <ul style={listStyle}>
            {job.job_description.map((d, i) => <li key={i}>{d}</li>)}
          </ul>
        </Section>

        <Section title="Krav">
          <ul style={listStyle}>
            {job.requirements.map((r, i) => <li key={i}>{r}</li>)}
          </ul>
        </Section>

        {job.meriter.length > 0 && (
          <Section title="Meriter">
            <ul style={listStyle}>
              {job.meriter.map((m, i) => <li key={i}>{m}</li>)}
            </ul>
          </Section>
        )}

        <Section title="Förmåner">
          <ul style={listStyle}>
            {job.benefits.map((b, i) => <li key={i}>{b}</li>)}
          </ul>
        </Section>

        <div style={{
          marginTop: 26, display: "flex", gap: 10,
          paddingTop: 18, borderTop: "1px solid var(--line)",
        }}>
          <button
            type="button"
            disabled={applyBusy}
            onClick={onApply}
            style={btnStyle()}
          >
            {applyBusy ? "Söker..." : "Sök jobbet →"}
          </button>
          <button
            type="button"
            onClick={onClose}
            style={{
              ...btnStyle(),
              background: "transparent",
              border: "1px solid var(--line-strong)",
              color: "var(--text-mid)",
            }}
          >
            Avbryt
          </button>
        </div>
      </div>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div style={{ marginTop: 22 }}>
      <div style={{
        fontFamily: "var(--mono)", fontSize: 9.5,
        letterSpacing: "1.4px", textTransform: "uppercase",
        color: "var(--accent)", marginBottom: 8,
      }}>
        {title}
      </div>
      {children}
    </div>
  );
}

const listStyle: React.CSSProperties = {
  listStyle: "none", padding: 0, margin: 0,
  display: "flex", flexDirection: "column", gap: 6,
  fontFamily: "var(--serif)", fontSize: 14,
  color: "rgba(255,255,255,0.8)", lineHeight: 1.5,
};
