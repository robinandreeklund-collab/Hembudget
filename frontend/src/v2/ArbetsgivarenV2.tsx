/**
 * V2 Arbetsgivaren · matchar /proposals/vol-7/elev.html#p-arbg EXAKT.
 *
 * Layout (samma som prototypen):
 *   1. .actor-back tillbaka-länk → /v2/hub
 *   2. .actor-head · "Aktör 02 · Arbetsgivaren"-pill + actor-name
 *      (employer + tjänst) + actor-meta (Anställd sedan / Lönerevision /
 *      Avtalsvillkor)
 *   3. .act-grid (1.4fr 1fr):
 *      MAIN:
 *        - .cta-card · "Pågående lönesamtal · Maria" (om aktiv) eller
 *          "Starta lönesamtal" (om ingen)
 *        - .section-eye + .tx-list · senaste 4 lönespecar
 *        - .section-eye + .tx-list · kollektivavtalet (4 rader: ITP1,
 *          friskvård, OB, lönerevision)
 *        - .section-eye + .sat-card + .biz-table · arbetsgivar-frågor +
 *          nöjdhets-meter
 *        - .peda · pedagogik-block
 *      ASIDE:
 *        - .side-card · Marknadssnitt
 *        - .side-card · Wellbeing-konsekvens
 *        - .side-card · Modul-länk
 *
 * All data hämtas via /v2/arbetsgivaren — riktig data från master + scope.
 */
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { v2Api, type EmployerData } from "./api";
import { V2Banner } from "./V2Banner";
import "./arbetsgivaren.css";

const SEK = (n: number) =>
  new Intl.NumberFormat("sv-SE", { maximumFractionDigits: 0 }).format(n);

const SHORT_DATE = (iso: string | null): string => {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleDateString("sv-SE", { day: "numeric", month: "short" });
};

const MONTH_DATE = (iso: string | null): string => {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleDateString("sv-SE", { month: "short", year: "numeric" });
};

const DIFFICULTY_LABEL: Record<string, string> = {
  easy: "▰▱▱ LÄTT",
  medium: "▰▰▱ MEDEL",
  hard: "▰▰▰ SVÅR",
};

type OpenQuestion = {
  id: number;
  scenario_md: string;
  options: Array<{ index: number; text: string }>;
  difficulty: number;
};

type AnswerResult = {
  delta_applied: number;
  chosen_explanation: string;
  correct_path_md: string;
};

export function ArbetsgivarenV2() {
  const [data, setData] = useState<EmployerData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [openQ, setOpenQ] = useState<OpenQuestion | null>(null);
  const [answering, setAnswering] = useState(false);
  const [answerResult, setAnswerResult] = useState<AnswerResult | null>(null);
  const [loadingQ, setLoadingQ] = useState(false);
  const navigate = useNavigate();

  function refresh() {
    v2Api
      .arbetsgivaren()
      .then(setData)
      .catch((e) => setError(String((e as Error)?.message || e)));
  }

  useEffect(() => {
    refresh();
  }, []);

  async function openNextQuestion() {
    setLoadingQ(true);
    setError(null);
    setAnswerResult(null);
    try {
      const q = await v2Api.employerNextQuestion();
      if (q == null) {
        setError("Ingen ny fråga just nu — kom tillbaka senare.");
        return;
      }
      setOpenQ({
        id: q.id,
        scenario_md: q.scenario_md,
        options: q.options,
        difficulty: q.difficulty,
      });
    } catch (e) {
      setError(String((e as Error)?.message || e));
    } finally {
      setLoadingQ(false);
    }
  }

  async function answerQuestion(chosenIndex: number) {
    if (!openQ) return;
    setAnswering(true);
    try {
      const r = await v2Api.employerAnswerQuestion(openQ.id, chosenIndex);
      setAnswerResult({
        delta_applied: r.delta_applied,
        chosen_explanation: r.chosen_explanation,
        correct_path_md: r.correct_path_md,
      });
      refresh();
    } catch (e) {
      setError(String((e as Error)?.message || e));
    } finally {
      setAnswering(false);
    }
  }

  function closeQuestion() {
    setOpenQ(null);
    setAnswerResult(null);
  }

  if (error) {
    return (
      <div className="v2-arbg-root">
        <V2Banner status={{ role: "student", is_super_admin: false }} />
        <div className="bank-loading">
          <div>
            <div style={{ color: "#fca5a5", marginBottom: 8 }}>
              Kunde inte ladda arbetsgivar-data
            </div>
            <pre style={{ fontSize: 11 }}>{error}</pre>
          </div>
        </div>
      </div>
    );
  }
  if (!data) {
    return (
      <div className="v2-arbg-root">
        <V2Banner status={{ role: "student", is_super_admin: false }} />
        <div className="bank-loading">Laddar arbetsgivar-data…</div>
      </div>
    );
  }

  const {
    profession,
    employer,
    agreement_name,
    agreement_union,
    gross_salary_monthly,
    net_salary_monthly,
    pension_pct,
    pension_monthly,
    employed_since,
    next_revision_date,
    market_low,
    market_high,
    satisfaction,
    negotiation,
    salary_slips,
    agreement_benefits,
    questions,
  } = data;

  // Wellbeing-konsekvens: AI:ns senaste bud i procent → kr/mån-ökning
  const proposedRaise =
    negotiation?.proposed_pct != null
      ? Math.round((gross_salary_monthly * negotiation.proposed_pct) / 100)
      : null;

  return (
    <div className="v2-arbg-root">
      <V2Banner status={{ role: "student", is_super_admin: false }} />

      <div className="shell">
        <a
          className="actor-back"
          onClick={(e) => {
            e.preventDefault();
            navigate("/v2/hub");
          }}
          href="#"
        >
          Tillbaka till pentagonen
        </a>

        <header className="actor-head">
          <div>
            <span className="pill warm">Aktör 02 · Arbetsgivaren</span>
            <h1 className="actor-name" style={{ marginTop: 14 }}>
              {employer} — <em>din arbetsplats</em>.
            </h1>
            <p className="actor-sub">
              {profession}
              {agreement_union ? ` · kollektivavtal ${agreement_union}` : ""}
            </p>
          </div>
          <div className="actor-meta">
            {employed_since && (
              <>
                Anställd sedan{" "}
                <strong>{MONTH_DATE(employed_since)}</strong>
                <br />
              </>
            )}
            {next_revision_date && (
              <>
                Lönerevision{" "}
                <strong>{SHORT_DATE(next_revision_date)}</strong>
                <br />
              </>
            )}
            {agreement_name ? (
              <>
                Avtalsvillkor <strong>{agreement_name}</strong>
              </>
            ) : (
              <>
                Bruttolön{" "}
                <strong>{SEK(gross_salary_monthly)} kr/mån</strong>
              </>
            )}
          </div>
        </header>

        <div className="act-grid">
          <div>
            {/* CTA · Maria-samtalet */}
            {negotiation && negotiation.status === "active" ? (
              <article className="cta-card">
                <div className="cta-eye">Pågående lönesamtal · Maria</div>
                <div className="cta-h">
                  Du är i{" "}
                  <em>
                    runda {negotiation.round_no} av {negotiation.max_rounds}
                  </em>{" "}
                  med Maria.
                </div>
                <p className="cta-prose">
                  Startade på{" "}
                  <strong>{SEK(negotiation.starting_salary)} kr/mån</strong>.
                  {negotiation.proposed_pct != null && (
                    <>
                      {" "}
                      Marias senaste bud:{" "}
                      <strong>
                        +{negotiation.proposed_pct.toFixed(1)} %
                        {proposedRaise && ` (≈ +${SEK(proposedRaise)} kr/mån)`}
                      </strong>
                      .
                    </>
                  )}
                  {market_low && market_high && (
                    <>
                      {" "}
                      Marknadssnittet är{" "}
                      <strong>
                        {SEK(market_low)}–{SEK(market_high)} kr
                      </strong>
                      .
                    </>
                  )}
                  {negotiation.avtal_norm_pct != null && (
                    <>
                      {" "}
                      Centralt avtal:{" "}
                      <strong>
                        minst {negotiation.avtal_norm_pct.toFixed(1)} %
                      </strong>{" "}
                      revision.
                    </>
                  )}
                </p>
                <button
                  type="button"
                  className="cta-btn"
                  onClick={() => navigate("/v2/maria")}
                >
                  Fortsätt lönesamtalet →
                </button>
              </article>
            ) : (
              <article className="cta-card">
                <div className="cta-eye">Lönesamtal · Maria</div>
                <div className="cta-h">
                  {negotiation
                    ? <>Senaste samtal är <em>klart</em>.</>
                    : <>Inget pågående <em>lönesamtal</em>.</>}
                </div>
                <p className="cta-prose">
                  Maria är AI-arbetsgivaren. Du argumenterar för en löneökning
                  i upp till 5 ronder, och hon svarar utifrån{" "}
                  {employer}:s budget och kollektivavtalet
                  {agreement_name && ` (${agreement_name})`}. Du tränas i att
                  förbereda BATNA, ankra, och argumentera utifrån data.
                </p>
                <button
                  type="button"
                  className="cta-btn"
                  onClick={() => navigate("/v2/maria")}
                >
                  Starta lönesamtal →
                </button>
              </article>
            )}

            {/* LÖNESPECAR */}
            <div className="section-eye">Lönespecar · senaste 4 månader</div>
            {salary_slips.length === 0 ? (
              <div
                style={{
                  padding: 20,
                  border: "1px solid var(--line)",
                  borderRadius: 6,
                  fontFamily: "var(--serif)",
                  color: "var(--text-mid)",
                  marginBottom: 24,
                }}
              >
                Inga lönespecar än. När arbetsgivaren skickar lön (positiv
                transaktion med "Lön" i beskrivningen) dyker de upp här.
              </div>
            ) : (
              <div className="tx-list">
                {salary_slips.map((slip) => (
                  <div className="tx-row" key={slip.id}>
                    <span className="tx-date">{MONTH_DATE(slip.date)}</span>
                    <div>
                      <div className="tx-name">
                        Lönespec · {SHORT_DATE(slip.date)}
                      </div>
                      <div className="tx-name-sub">
                        {slip.gross_amount && (
                          <>Brutto {SEK(slip.gross_amount)} · </>
                        )}
                        {slip.tax_amount != null && slip.tax_amount > 0 && (
                          <>skatt {SEK(slip.tax_amount)} · </>
                        )}
                        netto {SEK(slip.net_amount)}
                        {slip.pension_amount != null &&
                          slip.pension_amount > 0 && (
                            <> · ITP {SEK(slip.pension_amount)}</>
                          )}
                      </div>
                    </div>
                    <span className="tx-cat">Klar</span>
                    <span className="tx-amt in">
                      <em>+ {SEK(slip.net_amount)}</em> kr
                    </span>
                  </div>
                ))}
              </div>
            )}

            {/* KOLLEKTIVAVTALET */}
            <div className="section-eye" style={{ marginTop: 24 }}>
              Kollektivavtalet · vad det säger
            </div>
            <div className="tx-list">
              {agreement_benefits.map((b, i) => (
                <div className="tx-row agreement-row" key={i}>
                  <div>
                    <div className="tx-name">{b.name}</div>
                    <div className="tx-name-sub">{b.detail}</div>
                  </div>
                  <span className="tx-amt">
                    <em>{b.value}</em>
                  </span>
                </div>
              ))}
            </div>

            {/* ARBETSGIVAR-FRÅGOR · nöjdhet + tabell */}
            <div className="section-eye" style={{ marginTop: 24 }}>
              Frågor från arbetsgivaren · påverkar din nöjdhet
            </div>
            <div className="sat-card">
              <div className="sat-row">
                <div>
                  <div className="sat-eye">Din arbetsgivar-nöjdhet</div>
                  <div className="sat-num">{satisfaction.score} / 100</div>
                </div>
                <div style={{ textAlign: "right" }}>
                  <div className="sat-eye">Senaste 4 v</div>
                  <div
                    className={`sat-delta ${
                      satisfaction.delta_4w >= 0 ? "up" : "down"
                    }`}
                  >
                    {satisfaction.delta_4w >= 0 ? "+ " : "− "}
                    {Math.abs(satisfaction.delta_4w)} pkt
                  </div>
                </div>
              </div>
              <div className="sat-bar">
                <div
                  className="sat-bar-fill"
                  style={{
                    width: `${Math.max(0, Math.min(100, satisfaction.score))}%`,
                  }}
                />
              </div>
              <div className="sat-meta">
                Nöjdheten påverkar din position i lönesamtalet med Maria. Hög
                nöjdhet → bättre BATNA.
              </div>
            </div>

            {questions.length > 0 ? (
              <div className="biz-table">
                <div className="biz-table-row head">
                  <span>Datum</span>
                  <span>Fråga</span>
                  <span>Svårighet</span>
                  <span>Status</span>
                </div>
                {questions.map((q) => (
                  <div
                    className={`biz-table-row${q.is_open ? " open-row" : ""}`}
                    key={q.is_open ? `open-${q.question_id}` : `q-${q.id}`}
                  >
                    <span
                      style={{
                        fontFamily: "var(--mono)",
                        fontSize: 10,
                        color: q.is_open ? "var(--accent)" : "var(--text-mid)",
                      }}
                    >
                      {q.is_open
                        ? "NY"
                        : SHORT_DATE(q.answered_at)}
                    </span>
                    <div>
                      <div
                        style={{
                          fontFamily: "var(--serif)",
                          fontSize: 14,
                          color: "#fff",
                          fontWeight: q.is_open ? 700 : 600,
                        }}
                      >
                        "{q.question_text}"
                      </div>
                      {q.student_answer && (
                        <div
                          style={{
                            fontFamily: "var(--mono)",
                            fontSize: 9.5,
                            color: "var(--text-dim)",
                            marginTop: 3,
                          }}
                        >
                          Du svarade:{" "}
                          <em
                            style={{
                              color:
                                (q.delta || 0) >= 0 ? "#6ee7b7" : "#fda594",
                            }}
                          >
                            "{q.student_answer}"
                          </em>
                        </div>
                      )}
                      {q.is_open && (
                        <div
                          style={{
                            fontFamily: "var(--mono)",
                            fontSize: 9.5,
                            color: "var(--text-dim)",
                            marginTop: 3,
                          }}
                        >
                          Ditt val påverkar nöjdheten
                        </div>
                      )}
                    </div>
                    <span className={`difficulty ${q.difficulty}`}>
                      {DIFFICULTY_LABEL[q.difficulty]}
                    </span>
                    {q.is_open ? (
                      <button
                        type="button"
                        className="biz-status open"
                        onClick={openNextQuestion}
                        disabled={loadingQ}
                        style={{
                          border: 0,
                          cursor: "pointer",
                          background: "var(--accent)",
                          color: "#fff",
                        }}
                      >
                        {loadingQ ? "Laddar…" : "Svara nu →"}
                      </button>
                    ) : (
                      <span
                        className={`biz-status ${
                          (q.delta || 0) >= 0 ? "delta-up" : "delta-down"
                        }`}
                      >
                        {(q.delta || 0) >= 0 ? "+" : "−"}
                        {Math.abs(q.delta || 0)} nöjd
                      </span>
                    )}
                  </div>
                ))}
              </div>
            ) : (
              <div
                style={{
                  padding: 20,
                  border: "1px solid var(--line)",
                  borderRadius: 6,
                  fontFamily: "var(--serif)",
                  color: "var(--text-mid)",
                  marginBottom: 24,
                }}
              >
                Inga arbetsplats-frågor än. När arbetsgivaren ställer en fråga
                dyker den upp som "Svara nu" här.
              </div>
            )}

            {/* PEDAGOGIK */}
            <div className="peda">
              <div className="peda-eye">Pedagogik · vad du lär dig här</div>
              <div className="peda-h">
                Anställning är <em>mer</em> än lön på kontot.
              </div>
              <p className="peda-prose">
                Du ser <strong>{SEK(net_salary_monthly)} kr</strong> netto.
                Arbetsgivaren betalar typiskt{" "}
                <strong>~{SEK(gross_salary_monthly * 1.42)} kr</strong> totalt
                — skillnaden är <em>din samhällelighet</em>: skatt,
                socialavgifter, tjänstepension, friskvård. Du tränas i att läsa{" "}
                <code>lönespec</code>, förstå <code>kollektivavtal</code>, och
                se det <em>osynliga lönepaketet</em>.
              </p>
              <ul className="peda-bullets">
                <li className="peda-bullet">
                  <strong>{pension_pct ? `${pension_pct.toFixed(1)} %` : "Tjänstepension"}</strong>
                  {pension_monthly
                    ? `≈ ${SEK(pension_monthly)} kr/mån som arbetsgivaren sätter undan.`
                    : "Arbetsgivaren betalar — varierar med avtal."}
                </li>
                <li className="peda-bullet">
                  <strong>OB-tillägg</strong>Kväll +30 % · helg +50 % · röd dag
                  +100 %. Räknas på timlön.
                </li>
                <li className="peda-bullet">
                  <strong>Friskvård</strong>5 000 kr/år skattefritt · bara om
                  avtalet ger det.
                </li>
                <li className="peda-bullet">
                  <strong>Lönerevision</strong>Centralt avtal: minst{" "}
                  {negotiation?.avtal_norm_pct
                    ? `${negotiation.avtal_norm_pct.toFixed(1)} %`
                    : "2,4 %"}{" "}
                  årligen. Förhandlingsbart upp.
                </li>
              </ul>
              <div className="peda-concepts">
                <span className="peda-concept">Bruttolön</span>
                <span className="peda-concept">Nettolön</span>
                <span className="peda-concept">ITP1</span>
                <span className="peda-concept">Kollektivavtal</span>
                <span className="peda-concept">IBB</span>
                <span className="peda-concept">Marginalskatt</span>
              </div>
              <div className="peda-tip">
                {market_low && market_high
                  ? `När du går till Maria-samtalet — använd marknadssnittet (${SEK(
                      market_low,
                    )}–${SEK(
                      market_high,
                    )} kr) som ankarpunkt. Förhandlingen är inte personlig — den är data.`
                  : "När du går till Maria-samtalet — kom förberedd med data. Förhandlingen är inte personlig."}
              </div>
            </div>
          </div>

          {/* ASIDE */}
          <aside>
            {market_low && market_high && (
              <div className="side-card">
                <div className="side-card-eye">Marknadssnitt</div>
                <div className="side-card-h">
                  {SEK(market_low)}–{SEK(market_high)} kr
                </div>
                <div className="side-card-meta">
                  Uppskattat spann för {profession.toLowerCase()} · ±5 % runt
                  din nuvarande lön
                </div>
              </div>
            )}
            {proposedRaise && proposedRaise > 0 && (
              <div className="side-card">
                <div className="side-card-eye">Wellbeing-effekt</div>
                <div className="side-card-h">
                  + <em>{SEK(proposedRaise)}</em>/mån
                </div>
                <div className="side-card-meta">
                  Marias senaste bud i kr — ger snabbare buffert + sparmål
                </div>
                <a
                  className="side-card-link"
                  onClick={(e) => {
                    e.preventDefault();
                    navigate("/v2/hub");
                  }}
                  href="#"
                >
                  Se konsekvensen i pentagonen ↗
                </a>
              </div>
            )}
            <div className="side-card">
              <div className="side-card-eye">Modul i bakgrunden</div>
              <div className="side-card-h">Lönesamtalet</div>
              <div className="side-card-meta">
                {negotiation
                  ? `Steg ${negotiation.round_no}/${negotiation.max_rounds} · status ${negotiation.status}`
                  : "Inte startat — KALP + argumentlista byggs först"}
              </div>
            </div>
          </aside>
        </div>
      </div>

      {/* MODAL · arbetsplatsfråga */}
      {openQ && (
        <div
          onClick={closeQuestion}
          style={{
            position: "fixed",
            inset: 0,
            background: "rgba(0,0,0,0.7)",
            display: "grid",
            placeItems: "center",
            zIndex: 1000,
            padding: 20,
          }}
        >
          <div
            onClick={(e) => e.stopPropagation()}
            style={{
              maxWidth: 640,
              width: "100%",
              maxHeight: "90vh",
              overflowY: "auto",
              background: "rgba(15,21,37,0.98)",
              border: "1px solid var(--line-strong)",
              borderRadius: 8,
              padding: "24px 28px",
            }}
          >
            <div
              style={{
                fontFamily: "var(--mono)",
                fontSize: 9.5,
                letterSpacing: "1.2px",
                textTransform: "uppercase",
                color: "var(--accent)",
                marginBottom: 8,
              }}
            >
              ● Arbetsplatsfråga
            </div>
            <p
              style={{
                fontFamily: "var(--serif)",
                fontSize: 16,
                lineHeight: 1.5,
                color: "#fff",
                marginTop: 0,
              }}
            >
              {openQ.scenario_md}
            </p>

            {!answerResult ? (
              <div
                style={{
                  display: "flex",
                  flexDirection: "column",
                  gap: 8,
                  marginTop: 18,
                }}
              >
                {openQ.options.map((opt) => (
                  <button
                    key={opt.index}
                    type="button"
                    disabled={answering}
                    onClick={() => answerQuestion(opt.index)}
                    style={{
                      textAlign: "left",
                      padding: "14px 18px",
                      background: "rgba(255,255,255,0.04)",
                      border: "1px solid var(--line-strong)",
                      borderRadius: 6,
                      color: "#fff",
                      fontFamily: "var(--serif)",
                      fontSize: 14,
                      cursor: answering ? "wait" : "pointer",
                    }}
                  >
                    {opt.text}
                  </button>
                ))}
                <button
                  type="button"
                  onClick={closeQuestion}
                  className="cta-btn ghost"
                  style={{ marginTop: 8 }}
                >
                  Avbryt
                </button>
              </div>
            ) : (
              <div style={{ marginTop: 18 }}>
                <div
                  style={{
                    padding: "14px 18px",
                    background:
                      answerResult.delta_applied >= 0
                        ? "rgba(110,231,183,0.06)"
                        : "rgba(252,165,165,0.06)",
                    border:
                      answerResult.delta_applied >= 0
                        ? "1px solid rgba(110,231,183,0.4)"
                        : "1px solid rgba(252,165,165,0.4)",
                    borderRadius: 6,
                    fontFamily: "var(--serif)",
                    fontSize: 14,
                    color: "#fff",
                    marginBottom: 14,
                  }}
                >
                  <strong
                    style={{
                      color:
                        answerResult.delta_applied >= 0
                          ? "#6ee7b7"
                          : "#fca5a5",
                    }}
                  >
                    {answerResult.delta_applied >= 0 ? "+" : ""}
                    {answerResult.delta_applied} nöjdhet
                  </strong>
                  · {answerResult.chosen_explanation}
                </div>
                <div
                  style={{
                    fontFamily: "var(--mono)",
                    fontSize: 9.5,
                    letterSpacing: "1.2px",
                    textTransform: "uppercase",
                    color: "var(--text-mid)",
                    marginBottom: 6,
                  }}
                >
                  Rekommenderad väg
                </div>
                <p
                  style={{
                    fontFamily: "var(--serif)",
                    fontSize: 13.5,
                    lineHeight: 1.5,
                    color: "var(--text)",
                    whiteSpace: "pre-wrap",
                    marginTop: 0,
                  }}
                >
                  {answerResult.correct_path_md}
                </p>
                <button
                  type="button"
                  className="cta-btn"
                  onClick={closeQuestion}
                  style={{ marginTop: 10 }}
                >
                  Stäng
                </button>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
