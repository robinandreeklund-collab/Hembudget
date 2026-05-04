/**
 * Maria-AI lönesamtal — elev-vy.
 *
 * Speglar prototypen /proposals/vol-7/elev.html (p-maria):
 * - actor-head med pill ("Lönesamtal · runda X / Y"), AI-modell-info
 * - chat-card med Maria-avatar + meddelanden från Maria och eleven
 * - Round-card aside (runda X av Y, bud-historik, smärtgräns-meter,
 *   Echo taktiska tips, peda-block)
 *
 * Backend:
 * - GET /v2/maria — aktivt samtal + historik
 * - POST /employer/negotiation/start — starta nytt
 * - POST /employer/negotiation/{id}/message — skicka motbud
 *
 * Wellbeing: Aktivt lönesamtal +2 economy. Klart med löneökning
 * +economy. Avbrutet -3 economy. Hanteras i calculator.py sedan tidigare.
 */
import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import {
  v2Api,
  type V2MariaData,
  type V2MariaNegotiation,
} from "./api";
import { V2Banner } from "./V2Banner";
import "./lan.css";


type AcceptPreview = Awaited<ReturnType<typeof v2Api.mariaAcceptPreview>>;
type CompleteResult = Awaited<ReturnType<typeof v2Api.mariaComplete>>;
type RoundTone = { roundNo: number; score: number | null; reason: string | null };

export function MariaV2() {
  const [data, setData] = useState<V2MariaData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState("");
  const [sending, setSending] = useState(false);
  const [starting, setStarting] = useState(false);
  // Maria öppnar samtalet · cachad i komponent-state mellan refreshes
  const [openingMessage, setOpeningMessage] = useState<string | null>(null);
  // AI-tonbedömning per rond — visas som liten badge i UI:n.
  // Bakåtkompat: bygger map från active.rounds + senaste send-svar.
  const [toneByRound, setToneByRound] = useState<Record<number, RoundTone>>({});
  // Konsekvens-modal innan eleven trycker Acceptera/Avsluta
  const [preview, setPreview] = useState<AcceptPreview | null>(null);
  const [previewMode, setPreviewMode] =
    useState<"accept" | "abandon" | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  // Slutskärm efter complete()
  const [completeResult, setCompleteResult] =
    useState<CompleteResult | null>(null);
  const chatRef = useRef<HTMLDivElement>(null);

  function refresh() {
    return v2Api
      .maria()
      .then((d) => {
        setData(d);
        // Hydrera tone-cache från befintliga ronder (om endpointen
        // hämtar tone_score från DB ska vi visa det också efter reload)
        const next: Record<number, RoundTone> = {};
        d.active?.rounds.forEach((r) => {
          const tone = (r as unknown as {
            tone_score?: number | null;
            tone_reason?: string | null;
          });
          if (tone?.tone_score != null) {
            next[r.round_no] = {
              roundNo: r.round_no,
              score: tone.tone_score,
              reason: tone.tone_reason ?? null,
            };
          }
        });
        setToneByRound((prev) => ({ ...prev, ...next }));
      })
      .catch((e) => setError(String((e as Error)?.message || e)));
  }

  useEffect(() => {
    refresh();
  }, []);

  useEffect(() => {
    chatRef.current?.scrollTo({
      top: chatRef.current.scrollHeight,
      behavior: "smooth",
    });
  }, [data?.active?.rounds.length]);

  async function startNegotiation() {
    setStarting(true);
    setError(null);
    try {
      const r = await v2Api.mariaStart();
      setOpeningMessage(r.opening_message);
      await refresh();
    } catch (e) {
      setError(String((e as Error)?.message || e));
    } finally {
      setStarting(false);
    }
  }

  async function sendMessage() {
    if (!data?.active || !message.trim()) return;
    setSending(true);
    setError(null);
    try {
      const r = await v2Api.mariaSendMessage(data.active.id, message.trim());
      setMessage("");
      // Spara tone-feedback från svaret för aktuell rond
      setToneByRound((prev) => ({
        ...prev,
        [r.round_no]: {
          roundNo: r.round_no,
          score: r.tone_score,
          reason: r.tone_reason,
        },
      }));
      await refresh();
    } catch (e) {
      setError(String((e as Error)?.message || e));
    } finally {
      setSending(false);
    }
  }

  async function openPreview(mode: "accept" | "abandon") {
    if (!data?.active) return;
    setPreviewMode(mode);
    setPreviewLoading(true);
    setError(null);
    try {
      const p = await v2Api.mariaAcceptPreview(data.active.id);
      setPreview(p);
    } catch (e) {
      setError(String((e as Error)?.message || e));
      setPreviewMode(null);
    } finally {
      setPreviewLoading(false);
    }
  }

  async function confirmComplete() {
    if (!data?.active || !previewMode) return;
    setSending(true);
    try {
      const r = await v2Api.mariaComplete(
        data.active.id, previewMode === "accept",
      );
      setCompleteResult(r);
      setPreview(null);
      setPreviewMode(null);
      await refresh();
    } catch (e) {
      setError(String((e as Error)?.message || e));
    } finally {
      setSending(false);
    }
  }

  if (error && !data) {
    return (
      <div className="v2-lan-root">
        <V2Banner status={{ role: "student", is_super_admin: false }} />
        <div className="bank-loading">
          <div>
            <div style={{ color: "#fca5a5", marginBottom: 8 }}>
              Kunde inte ladda lönesamtal
            </div>
            <pre style={{ fontSize: 11 }}>{error}</pre>
          </div>
        </div>
      </div>
    );
  }
  if (!data) {
    return (
      <div className="v2-lan-root">
        <V2Banner status={{ role: "student", is_super_admin: false }} />
        <div className="bank-loading">Laddar Maria-samtal…</div>
      </div>
    );
  }

  const active = data.active;
  const totalRounds = active?.max_rounds || 5;
  const currentRound = active ? active.rounds.length : 0;

  return (
    <div className="v2-lan-root">
      <V2Banner status={{ role: "student", is_super_admin: false }} />

      <div className="shell" data-guide="maria-chat">
        <Link className="actor-back" to="/v2/arbetsgivaren">
          Tillbaka till arbetsgivaren
        </Link>

        <header className="actor-head">
          <div>
            <span className="pill">
              {active
                ? `Lönesamtal · runda ${currentRound} / ${totalRounds}`
                : "Lönesamtal · ej startat"}
            </span>
            <h1 className="actor-name" style={{ marginTop: 14 }}>
              Du sitter mitt emot <em>Maria</em>.
            </h1>
            <p className="actor-sub">
              {active
                ? `HR-chef ${active.employer} · AI-driven motpart · spelar realistiskt`
                : "HR-chef · AI-driven motpart · klicka 'Starta' för att börja"}
            </p>
          </div>
          <div className="actor-meta">
            Modell: <strong>Claude Sonnet 4.6</strong>
            <br />
            Smärtgräns: <strong>dold</strong>
            <br />
            Sparas i din portfolio
          </div>
        </header>

        {error && (
          <div
            style={{
              padding: "10px 16px",
              border: "1px solid #fca5a5",
              borderRadius: 6,
              fontFamily: "var(--mono)",
              fontSize: 11,
              color: "#fca5a5",
              marginBottom: 14,
            }}
          >
            {error}
          </div>
        )}

        {!active && data.history.length === 0 && (
          <article
            className="cta-card"
            style={{ marginBottom: 22 }}
          >
            <div className="cta-eye">Ej startat · klicka för att börja</div>
            <div className="cta-h">
              Börja lönesamtalet med <em>Maria</em>.
            </div>
            <p className="cta-prose">
              Maria är AI-driven HR-chef på din arbetsplats. Hon har
              centralavtals-procent, marknadsdata och en dold smärtgräns.
              Du kan ha upp till 5 ronder. Stå kvar, hänvisa till data,
              använd tystnaden.
            </p>
            <button
              type="button"
              className="cta-btn"
              disabled={starting}
              onClick={startNegotiation}
            >
              {starting ? "Startar…" : "Starta lönesamtalet →"}
            </button>
          </article>
        )}

        {active && (
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "1.6fr 1fr",
              gap: 18,
              marginBottom: 22,
            }}
          >
            {/* Chat-card */}
            <article
              style={{
                background: "rgba(15,21,37,0.7)",
                border: "1px solid var(--line)",
                borderRadius: 8,
                padding: "20px 22px",
                display: "flex",
                flexDirection: "column",
                minHeight: 540,
              }}
            >
              <div
                style={{
                  display: "flex",
                  gap: 14,
                  alignItems: "center",
                  marginBottom: 14,
                  paddingBottom: 14,
                  borderBottom: "1px solid var(--line)",
                }}
              >
                <div
                  style={{
                    width: 44,
                    height: 44,
                    borderRadius: "50%",
                    background:
                      "linear-gradient(135deg, var(--warm) 0%, #fbbf24 100%)",
                    display: "grid",
                    placeItems: "center",
                    fontFamily: "var(--serif)",
                    fontSize: 20,
                    fontWeight: 700,
                    color: "#422006",
                    flexShrink: 0,
                  }}
                >
                  M
                </div>
                <div>
                  <div
                    style={{
                      fontFamily: "var(--serif)",
                      fontSize: 16,
                      fontWeight: 700,
                    }}
                  >
                    Maria <em>Andersson</em>
                  </div>
                  <div
                    style={{
                      fontFamily: "var(--mono)",
                      fontSize: 10,
                      color: "var(--text-mid)",
                    }}
                  >
                    HR-chef · {active.employer} · simulerad
                  </div>
                </div>
              </div>

              <div
                ref={chatRef}
                style={{
                  flex: 1,
                  overflowY: "auto",
                  display: "flex",
                  flexDirection: "column",
                  gap: 12,
                  paddingRight: 8,
                  minHeight: 350,
                  maxHeight: 500,
                }}
              >
                {/* Maria öppnar samtalet — visas före alla ronder */}
                {openingMessage && (
                  <div
                    style={{
                      background: "rgba(251,191,36,0.06)",
                      borderLeft: "3px solid var(--warm)",
                      padding: "12px 16px",
                      borderRadius: 4,
                    }}
                  >
                    <div
                      style={{
                        fontFamily: "var(--mono)",
                        fontSize: 9.5,
                        letterSpacing: "1.2px",
                        textTransform: "uppercase",
                        color: "var(--warm)",
                        marginBottom: 4,
                      }}
                    >
                      Maria · öppnar samtalet
                    </div>
                    <p
                      style={{
                        fontFamily: "var(--serif)",
                        fontSize: 14,
                        lineHeight: 1.5,
                        margin: 0,
                        fontStyle: "italic",
                      }}
                    >
                      {openingMessage}
                    </p>
                  </div>
                )}
                {active.rounds.map((r) => (
                  <div key={r.round_no}>
                    <div
                      style={{
                        background: "rgba(220,76,43,0.08)",
                        borderLeft: "3px solid var(--accent)",
                        padding: "12px 16px",
                        borderRadius: 4,
                        marginBottom: 8,
                      }}
                    >
                      <div
                        style={{
                          fontFamily: "var(--mono)",
                          fontSize: 9.5,
                          letterSpacing: "1.2px",
                          textTransform: "uppercase",
                          color: "var(--accent)",
                          marginBottom: 4,
                        }}
                      >
                        Du · runda {r.round_no}
                      </div>
                      <p
                        style={{
                          fontFamily: "var(--serif)",
                          fontSize: 14,
                          lineHeight: 1.5,
                          margin: 0,
                          fontStyle: "italic",
                        }}
                      >
                        {r.student_message}
                      </p>
                      {(() => {
                        const tone = toneByRound[r.round_no];
                        if (!tone || tone.score == null) return null;
                        const positive = tone.score > 0;
                        const neutral = tone.score === 0;
                        const color = positive
                          ? "#6ee7b7"
                          : neutral
                          ? "rgba(255,255,255,0.55)"
                          : "#fda594";
                        return (
                          <div
                            style={{
                              marginTop: 8,
                              fontFamily: "var(--mono)",
                              fontSize: 10,
                              color,
                              letterSpacing: "0.4px",
                            }}
                          >
                            ● Marias intryck:{" "}
                            <strong>
                              {positive ? "+" : ""}
                              {tone.score}
                            </strong>
                            {tone.reason ? ` · ${tone.reason}` : ""}
                          </div>
                        );
                      })()}
                    </div>
                    <div
                      style={{
                        background: "rgba(251,191,36,0.06)",
                        borderLeft: "3px solid var(--warm)",
                        padding: "12px 16px",
                        borderRadius: 4,
                      }}
                    >
                      <div
                        style={{
                          fontFamily: "var(--mono)",
                          fontSize: 9.5,
                          letterSpacing: "1.2px",
                          textTransform: "uppercase",
                          color: "var(--warm)",
                          marginBottom: 4,
                        }}
                      >
                        Maria · runda {r.round_no}
                        {r.proposed_pct != null
                          ? ` · bud +${r.proposed_pct.toFixed(1)} %`
                          : ""}
                      </div>
                      <p
                        style={{
                          fontFamily: "var(--serif)",
                          fontSize: 14,
                          lineHeight: 1.5,
                          margin: 0,
                          fontStyle: "italic",
                        }}
                      >
                        {r.employer_response}
                      </p>
                    </div>
                  </div>
                ))}
                {active.rounds.length === 0 && (
                  <div
                    style={{
                      textAlign: "center",
                      padding: "40px 20px",
                      fontFamily: "var(--serif)",
                      color: "var(--text-mid)",
                    }}
                  >
                    Skicka ditt första bud nedan för att starta rond 1.
                  </div>
                )}
              </div>

              {active.status === "active" &&
                currentRound < totalRounds && (
                  <div
                    style={{
                      marginTop: 14,
                      paddingTop: 14,
                      borderTop: "1px solid var(--line)",
                      display: "flex",
                      gap: 8,
                    }}
                  >
                    <textarea
                      value={message}
                      onChange={(e) => setMessage(e.target.value)}
                      placeholder="Ditt motbud eller fråga…"
                      rows={3}
                      style={{
                        flex: 1,
                        background: "rgba(255,255,255,0.04)",
                        border: "1px solid var(--line-strong)",
                        color: "#fff",
                        padding: "10px 14px",
                        borderRadius: 6,
                        fontFamily: "var(--serif)",
                        fontSize: 13.5,
                        resize: "vertical",
                      }}
                      onKeyDown={(e) => {
                        if (
                          e.key === "Enter" &&
                          (e.metaKey || e.ctrlKey)
                        ) {
                          e.preventDefault();
                          sendMessage();
                        }
                      }}
                    />
                    <button
                      type="button"
                      className="cta-btn"
                      disabled={sending || !message.trim()}
                      onClick={sendMessage}
                      style={{ alignSelf: "flex-end" }}
                    >
                      {sending ? "Skickar…" : "Skicka"}
                    </button>
                  </div>
                )}

              {/* Acceptera + Avsluta-knappar med konsekvens-preview */}
              {active.status === "active" && active.rounds.length > 0 && (
                <div
                  style={{
                    marginTop: 12,
                    padding: 14,
                    background: "rgba(110,231,183,0.06)",
                    border: "1px solid rgba(110,231,183,0.25)",
                    borderRadius: 10,
                    display: "flex",
                    gap: 10,
                    justifyContent: "space-between",
                    alignItems: "center",
                    flexWrap: "wrap",
                  }}
                >
                  <div
                    style={{
                      color: "rgba(255,255,255,0.85)",
                      fontSize: "0.9rem",
                      flex: "1 1 240px",
                    }}
                  >
                    Klar med samtalet? Se konsekvenserna innan du
                    bestämmer dig.
                  </div>
                  <div style={{ display: "flex", gap: 8 }}>
                    <button
                      type="button"
                      disabled={previewLoading}
                      onClick={() => openPreview("abandon")}
                      style={{
                        background: "transparent",
                        color: "#fda594",
                        border: "1px solid #fda594",
                        padding: "10px 16px",
                        borderRadius: 6,
                        cursor: "pointer",
                        fontWeight: 700,
                      }}
                    >
                      Avsluta utan ändring
                    </button>
                    <button
                      type="button"
                      disabled={previewLoading}
                      onClick={() => openPreview("accept")}
                      style={{
                        background: "#34d399",
                        color: "#0a3326",
                        padding: "10px 20px",
                        border: "none",
                        borderRadius: 6,
                        cursor: "pointer",
                        fontWeight: 700,
                      }}
                    >
                      Acceptera bud →
                    </button>
                  </div>
                </div>
              )}
              {active.status !== "active" && (
                <div
                  style={{
                    marginTop: 14,
                    paddingTop: 14,
                    borderTop: "1px solid var(--line)",
                    fontFamily: "var(--mono)",
                    fontSize: 11,
                    color:
                      active.status === "completed"
                        ? "#6ee7b7"
                        : "#fda594",
                    textAlign: "center",
                  }}
                >
                  ● {active.status === "completed" ? "Avslutat" : "Avbrutet"}
                  {active.final_pct != null
                    ? ` · slutbud +${active.final_pct.toFixed(1)} %`
                    : ""}
                </div>
              )}
            </article>

            {/* Aside · round + pain + echo + peda */}
            <aside
              style={{
                display: "flex",
                flexDirection: "column",
                gap: 12,
              }}
            >
              <div
                style={{
                  padding: "16px 20px",
                  border: "1px solid var(--line)",
                  borderRadius: 6,
                  background: "rgba(15,21,37,0.7)",
                }}
              >
                <div
                  style={{
                    fontFamily: "var(--mono)",
                    fontSize: 9.5,
                    letterSpacing: "1.2px",
                    textTransform: "uppercase",
                    color: "var(--text-dim)",
                  }}
                >
                  Runda {currentRound} av {totalRounds}
                </div>
                <div
                  style={{
                    fontFamily: "var(--serif)",
                    fontSize: 18,
                    fontWeight: 700,
                    margin: "6px 0 4px 0",
                  }}
                >
                  {active.status === "active"
                    ? currentRound === 0
                      ? "Skicka ditt första bud"
                      : "Pågår"
                    : active.status === "completed"
                    ? "Klart"
                    : "Avbrutet"}
                </div>
                <div
                  style={{
                    display: "flex",
                    gap: 6,
                    margin: "12px 0",
                  }}
                >
                  {Array.from({ length: totalRounds }).map((_, i) => (
                    <div
                      key={i}
                      style={{
                        flex: 1,
                        height: 6,
                        borderRadius: 100,
                        background:
                          i < currentRound
                            ? "var(--warm)"
                            : i === currentRound
                            ? "rgba(220,76,43,0.4)"
                            : "rgba(255,255,255,0.06)",
                      }}
                    />
                  ))}
                </div>

                <div
                  style={{
                    fontFamily: "var(--mono)",
                    fontSize: 9.5,
                    letterSpacing: "1px",
                    textTransform: "uppercase",
                    color: "var(--text-dim)",
                    marginTop: 14,
                    marginBottom: 8,
                  }}
                >
                  Bud-historik
                </div>
                <table
                  style={{
                    width: "100%",
                    fontFamily: "var(--mono)",
                    fontSize: 11,
                    borderCollapse: "collapse",
                  }}
                >
                  <tbody>
                    {active.rounds.map((r) => (
                      <tr key={r.round_no}>
                        <td
                          style={{
                            padding: "4px 0",
                            color: "var(--text-mid)",
                          }}
                        >
                          R{r.round_no} · Maria
                        </td>
                        <td
                          style={{
                            padding: "4px 0",
                            textAlign: "right",
                            color: "#fff",
                          }}
                        >
                          {r.proposed_pct != null
                            ? `+${r.proposed_pct.toFixed(1)} %`
                            : "—"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              <PainMeter
                rounds={currentRound}
                total={totalRounds}
                proposedPct={
                  active.rounds.length > 0
                    ? active.rounds[active.rounds.length - 1]
                        .proposed_pct
                    : null
                }
                avtalNorm={active.avtal_norm_pct || 2.4}
              />

              <EchoTacticalCard
                round={currentRound}
                hasProposal={
                  active.rounds.length > 0 &&
                  active.rounds[active.rounds.length - 1].proposed_pct !=
                    null
                }
              />

              <PedaCard />
            </aside>
          </div>
        )}

        {/* HISTORIK */}
        {data.history.length > 0 && (
          <>
            <div className="section-eye">
              Tidigare lönesamtal ({data.history.length})
            </div>
            <div className="biz-table" style={{ marginBottom: 22 }}>
              <div
                className="biz-table-row head"
                style={{
                  gridTemplateColumns: "100px 1.2fr 100px 110px 90px",
                }}
              >
                <span>Datum</span>
                <span>Yrke / arbetsgivare</span>
                <span>Ronder</span>
                <span>Slut-bud</span>
                <span>Status</span>
              </div>
              {data.history.map((n) => (
                <HistoryRow key={n.id} n={n} />
              ))}
            </div>
          </>
        )}

        {!active && data.history.length > 0 && (
          <button
            type="button"
            className="cta-btn ghost"
            disabled={starting}
            onClick={startNegotiation}
            style={{ marginBottom: 22 }}
          >
            {starting ? "Startar…" : "Starta nytt lönesamtal →"}
          </button>
        )}

        {/* Echo · taktiskt råd när som helst */}
      </div>

      {/* === Konsekvens-preview-modal innan Acceptera/Avsluta === */}
      {preview && previewMode && (
        <div
          role="dialog"
          aria-modal="true"
          onClick={() => {
            setPreview(null);
            setPreviewMode(null);
          }}
          style={{
            position: "fixed",
            inset: 0,
            background: "rgba(0,0,0,0.7)",
            display: "grid",
            placeItems: "center",
            zIndex: 100,
            padding: 20,
          }}
        >
          <div
            onClick={(e) => e.stopPropagation()}
            style={{
              maxWidth: 520,
              width: "100%",
              background: "#0f1525",
              border: "1px solid var(--accent, #dc4c2b)",
              borderRadius: 12,
              padding: "26px 24px",
              fontFamily: "var(--serif)",
              color: "#fff",
            }}
          >
            <div
              style={{
                fontFamily: "var(--mono)",
                fontSize: 9.5,
                letterSpacing: "1.4px",
                textTransform: "uppercase",
                color: "var(--accent)",
                marginBottom: 8,
              }}
            >
              ● Förhandsvisning
            </div>
            <h2 style={{ fontSize: 22, margin: "0 0 14px 0" }}>
              {previewMode === "accept"
                ? "Om du accepterar nu"
                : "Om du avslutar utan ändring"}
            </h2>
            {preview.warning_md && (
              <div
                style={{
                  padding: "10px 14px",
                  background: "rgba(252,165,165,0.08)",
                  border: "1px solid rgba(252,165,165,0.4)",
                  borderRadius: 6,
                  color: "#fca5a5",
                  fontSize: 13,
                  marginBottom: 14,
                }}
              >
                {preview.warning_md}
              </div>
            )}
            <ul
              style={{
                listStyle: "none",
                padding: 0,
                margin: 0,
                fontSize: 14,
                lineHeight: 1.7,
              }}
            >
              {previewMode === "accept" && preview.salary_delta_per_month != null && (
                <li>
                  <strong>
                    {preview.salary_delta_per_month >= 0 ? "+" : ""}
                    {Math.round(preview.salary_delta_per_month)
                      .toLocaleString("sv-SE")} kr/månad
                  </strong>{" "}
                  ({preview.salary_delta_per_year != null
                    ? `${(preview.salary_delta_per_year >= 0 ? "+" : "")}${
                        Math.round(preview.salary_delta_per_year).toLocaleString("sv-SE")
                      } kr/år`
                    : "—"})
                  · ny lön{" "}
                  <strong>
                    {preview.new_salary_if_accepted != null
                      ? Math.round(preview.new_salary_if_accepted).toLocaleString("sv-SE")
                      : "—"}{" "}
                    kr
                  </strong>
                </li>
              )}
              <li>
                Ekonomi{" "}
                <strong style={{ color: previewMode === "accept" && preview.accept_ekonomi_delta >= 0 ? "#6ee7b7" : "#fda594" }}>
                  {previewMode === "accept"
                    ? `${preview.accept_ekonomi_delta >= 0 ? "+" : ""}${preview.accept_ekonomi_delta}`
                    : "0"}
                </strong>
              </li>
              <li>
                Sociala band{" "}
                <strong style={{ color: previewMode === "accept" ? "#6ee7b7" : "#fda594" }}>
                  {previewMode === "accept"
                    ? `+${preview.accept_social_delta}`
                    : preview.abandon_social_delta}
                </strong>
              </li>
              <li>
                Karriär/Trygghet{" "}
                <strong style={{ color: previewMode === "accept" ? "#6ee7b7" : "#fda594" }}>
                  {previewMode === "accept"
                    ? `+${preview.accept_safety_delta}`
                    : preview.abandon_safety_delta}
                </strong>
              </li>
              <li>
                Marias nöjdhet{" "}
                <strong style={{ color: previewMode === "accept" ? "#6ee7b7" : "#fda594" }}>
                  {previewMode === "accept"
                    ? `+${preview.accept_employer_sat_delta}`
                    : preview.abandon_employer_sat_delta}
                </strong>
                {previewMode === "accept" && preview.accept_employer_sat_delta > 0 && (
                  <span style={{ color: "rgba(255,255,255,0.55)", fontSize: 12 }}>
                    {" "}· bättre projekt nästa kvartal
                  </span>
                )}
              </li>
            </ul>
            <div
              style={{
                marginTop: 22,
                display: "flex",
                gap: 10,
                justifyContent: "flex-end",
              }}
            >
              <button
                type="button"
                onClick={() => {
                  setPreview(null);
                  setPreviewMode(null);
                }}
                style={{
                  background: "transparent",
                  color: "rgba(255,255,255,0.7)",
                  border: "1px solid rgba(255,255,255,0.2)",
                  padding: "9px 16px",
                  borderRadius: 6,
                  cursor: "pointer",
                }}
              >
                Tillbaka
              </button>
              <button
                type="button"
                disabled={sending}
                onClick={confirmComplete}
                style={{
                  background:
                    previewMode === "accept" ? "#34d399" : "#fbbf24",
                  color: previewMode === "accept" ? "#0a3326" : "#422006",
                  padding: "9px 20px",
                  border: "none",
                  borderRadius: 6,
                  cursor: "pointer",
                  fontWeight: 700,
                }}
              >
                {sending
                  ? "Avslutar…"
                  : previewMode === "accept"
                  ? "Bekräfta"
                  : "Avsluta ändå"}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* === Slutskärm efter complete() — betyg + minne + pentagon === */}
      {completeResult && (
        <div
          role="dialog"
          aria-modal="true"
          style={{
            position: "fixed",
            inset: 0,
            background: "rgba(0,0,0,0.85)",
            display: "grid",
            placeItems: "center",
            zIndex: 110,
            padding: 20,
            overflowY: "auto",
          }}
        >
          <div
            style={{
              maxWidth: 620,
              width: "100%",
              background: "linear-gradient(180deg, #0f1525 0%, #0a0e1a 100%)",
              border: "1px solid var(--warm, #fbbf24)",
              borderRadius: 14,
              padding: "32px 28px",
              fontFamily: "var(--serif)",
              color: "#fff",
              boxShadow: "0 30px 80px -10px rgba(0,0,0,0.8)",
            }}
          >
            <div
              style={{
                fontFamily: "var(--mono)",
                fontSize: 10,
                letterSpacing: "1.6px",
                textTransform: "uppercase",
                color: "var(--warm)",
                marginBottom: 10,
              }}
            >
              ● Slutresultat · {completeResult.grade_label}
            </div>
            <div
              style={{
                display: "flex",
                gap: 26,
                alignItems: "center",
                flexWrap: "wrap",
                marginBottom: 18,
              }}
            >
              {/* Förhandlingsbetyg */}
              <div
                style={{
                  width: 130, height: 130,
                  borderRadius: "50%",
                  display: "grid", placeItems: "center",
                  background: `conic-gradient(var(--warm) 0 ${completeResult.grade * 3.6}deg, rgba(255,255,255,0.08) ${completeResult.grade * 3.6}deg 360deg)`,
                  flexShrink: 0,
                }}
              >
                <div
                  style={{
                    width: 110, height: 110,
                    borderRadius: "50%",
                    background: "#0f1525",
                    display: "grid", placeItems: "center",
                  }}
                >
                  <div style={{ textAlign: "center" }}>
                    <div style={{ fontSize: 30, fontWeight: 700 }}>
                      {completeResult.grade}
                    </div>
                    <div
                      style={{
                        fontSize: 10,
                        color: "rgba(255,255,255,0.55)",
                        fontFamily: "var(--mono)",
                        letterSpacing: "1px",
                      }}
                    >
                      AV 100
                    </div>
                  </div>
                </div>
              </div>
              <div style={{ flex: 1, minWidth: 220 }}>
                {completeResult.final_pct != null && (
                  <div
                    style={{
                      fontSize: 28,
                      fontWeight: 700,
                      lineHeight: 1.1,
                      marginBottom: 4,
                    }}
                  >
                    +{completeResult.final_pct.toFixed(1)} %
                    {completeResult.salary_delta_per_month != null && (
                      <span
                        style={{
                          fontSize: 18,
                          color: "var(--warm)",
                          marginLeft: 10,
                        }}
                      >
                        +{Math.round(completeResult.salary_delta_per_month)
                          .toLocaleString("sv-SE")} kr/mån
                      </span>
                    )}
                  </div>
                )}
                {completeResult.final_salary != null && (
                  <div style={{ color: "rgba(255,255,255,0.7)", fontSize: 14 }}>
                    Ny lön:{" "}
                    <strong>
                      {Math.round(completeResult.final_salary)
                        .toLocaleString("sv-SE")} kr/mån
                    </strong>
                  </div>
                )}
                {completeResult.salary_delta_per_year != null && (
                  <div
                    style={{
                      color: "rgba(255,255,255,0.55)",
                      fontSize: 12,
                      fontFamily: "var(--mono)",
                    }}
                  >
                    {completeResult.salary_delta_per_year >= 0 ? "+" : ""}
                    {Math.round(completeResult.salary_delta_per_year)
                      .toLocaleString("sv-SE")} kr/år
                  </div>
                )}
              </div>
            </div>

            {/* Pentagon-deltar */}
            {Object.keys(completeResult.pentagon_deltas || {}).length > 0 && (
              <div
                style={{
                  padding: "12px 14px",
                  background: "rgba(255,255,255,0.03)",
                  border: "1px solid rgba(255,255,255,0.08)",
                  borderRadius: 8,
                  marginBottom: 14,
                  display: "flex",
                  gap: 16,
                  flexWrap: "wrap",
                  fontSize: 13,
                }}
              >
                {Object.entries(completeResult.pentagon_deltas).map(
                  ([axis, delta]) => (
                    <div key={axis} style={{ display: "flex", gap: 6 }}>
                      <span style={{ color: "rgba(255,255,255,0.55)" }}>
                        {axis === "economy" ? "Ekonomi"
                          : axis === "social" ? "Sociala band"
                          : axis === "safety" ? "Karriär"
                          : axis === "health" ? "Hälsa"
                          : axis === "leisure" ? "Fritid"
                          : axis}
                      </span>
                      <strong
                        style={{
                          color: (delta as number) >= 0 ? "#6ee7b7" : "#fda594",
                        }}
                      >
                        {(delta as number) >= 0 ? "+" : ""}
                        {delta as number}
                      </strong>
                    </div>
                  ),
                )}
              </div>
            )}

            {/* Maria minns */}
            {completeResult.maria_memory_md && (
              <div
                style={{
                  padding: "12px 14px",
                  background:
                    completeResult.maria_memory_polarity === "positive"
                      ? "rgba(110,231,183,0.06)"
                      : completeResult.maria_memory_polarity === "negative"
                      ? "rgba(252,165,165,0.06)"
                      : "rgba(255,255,255,0.04)",
                  border: `1px solid ${
                    completeResult.maria_memory_polarity === "positive"
                      ? "rgba(110,231,183,0.4)"
                      : completeResult.maria_memory_polarity === "negative"
                      ? "rgba(252,165,165,0.4)"
                      : "rgba(255,255,255,0.15)"
                  }`,
                  borderRadius: 8,
                  marginBottom: 14,
                }}
              >
                <div
                  style={{
                    fontFamily: "var(--mono)",
                    fontSize: 9.5,
                    letterSpacing: "1.2px",
                    textTransform: "uppercase",
                    color:
                      completeResult.maria_memory_polarity === "positive"
                        ? "#6ee7b7"
                        : completeResult.maria_memory_polarity === "negative"
                        ? "#fda594"
                        : "rgba(255,255,255,0.7)",
                    marginBottom: 6,
                  }}
                >
                  ● Maria kommer ihåg det här
                </div>
                <div style={{ fontSize: 13, lineHeight: 1.5 }}>
                  {completeResult.maria_memory_md}
                </div>
              </div>
            )}

            {/* Strengths / Improvements */}
            <div
              style={{
                display: "grid",
                gridTemplateColumns: "1fr 1fr",
                gap: 12,
                marginBottom: 18,
              }}
            >
              <div>
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
                  ✓ Du gjorde bra
                </div>
                <ul style={{ paddingLeft: 18, fontSize: 13, margin: 0 }}>
                  {completeResult.grade_strengths.map((s, i) => (
                    <li key={i} style={{ marginBottom: 4 }}>{s}</li>
                  ))}
                </ul>
              </div>
              <div>
                <div
                  style={{
                    fontFamily: "var(--mono)",
                    fontSize: 9.5,
                    letterSpacing: "1.2px",
                    textTransform: "uppercase",
                    color: "#fbbf24",
                    marginBottom: 6,
                  }}
                >
                  → Tänk på till nästa gång
                </div>
                <ul style={{ paddingLeft: 18, fontSize: 13, margin: 0 }}>
                  {completeResult.grade_improvements.map((s, i) => (
                    <li key={i} style={{ marginBottom: 4 }}>{s}</li>
                  ))}
                </ul>
              </div>
            </div>

            <div
              style={{
                display: "flex",
                justifyContent: "flex-end",
                gap: 10,
              }}
            >
              <button
                type="button"
                onClick={() => setCompleteResult(null)}
                style={{
                  background: "var(--accent, #dc4c2b)",
                  color: "#fff",
                  padding: "10px 22px",
                  border: "none",
                  borderRadius: 100,
                  cursor: "pointer",
                  fontFamily: "var(--mono)",
                  fontSize: 11,
                  fontWeight: 700,
                  letterSpacing: "1.2px",
                  textTransform: "uppercase",
                }}
              >
                Stäng
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function PainMeter({
  rounds, total, proposedPct, avtalNorm,
}: {
  rounds: number;
  total: number;
  proposedPct: number | null;
  avtalNorm: number;
}) {
  // Pedagogisk indikator: hur "nära smärtgräns" Maria är.
  // Approximering: ju fler ronder, ju högre bud → desto närmare.
  const fill =
    proposedPct != null
      ? Math.min(
          100,
          ((proposedPct / (avtalNorm * 2.5)) * 0.5 +
            (rounds / total) * 0.5) * 100,
        )
      : (rounds / total) * 50;
  return (
    <div
      style={{
        padding: "16px 20px",
        border: "1px solid var(--line)",
        borderRadius: 6,
        background: "rgba(15,21,37,0.7)",
      }}
    >
      <div
        style={{
          fontFamily: "var(--mono)",
          fontSize: 9.5,
          letterSpacing: "1.2px",
          textTransform: "uppercase",
          color: "var(--text-dim)",
        }}
      >
        Marias smärtgräns · approximerad
      </div>
      <div
        style={{
          fontFamily: "var(--serif)",
          fontSize: 16,
          fontWeight: 700,
          margin: "6px 0",
        }}
      >
        <em>
          {fill > 80
            ? "Nära smärtgräns"
            : fill > 50
            ? "I förhandlingsspann"
            : "Bekvämt läge"}
        </em>
      </div>
      <div
        style={{
          fontFamily: "var(--mono)",
          fontSize: 10,
          color: "var(--text-mid)",
          marginBottom: 8,
        }}
      >
        Modellen visar bara <em>indikator</em>, inte siffran
      </div>
      <div
        style={{
          height: 8,
          background: "rgba(255,255,255,0.06)",
          borderRadius: 100,
          overflow: "hidden",
        }}
      >
        <div
          style={{
            height: "100%",
            width: `${fill}%`,
            background:
              fill > 80
                ? "linear-gradient(90deg, var(--warm) 0%, var(--accent) 100%)"
                : "var(--warm)",
            borderRadius: 100,
            transition: "width .4s var(--ease)",
          }}
        />
      </div>
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          marginTop: 6,
          fontFamily: "var(--mono)",
          fontSize: 9,
          color: "var(--text-dim)",
        }}
      >
        <span>nytt bud</span>
        <span>
          <em>nära smärtgräns</em>
        </span>
      </div>
    </div>
  );
}

function EchoTacticalCard({
  round, hasProposal,
}: { round: number; hasProposal: boolean }) {
  const tips =
    round === 0
      ? [
          "Öppna högt: hänvisa till marknadssnitt + dina uppsidor",
          "Använd centralavtalet som golv — yrkar över",
          "Skriv kort och konkret · undvik ursäkter",
        ]
      : round < 3
      ? [
          "Stå kvar — sänk inte i panik",
          "Hänvisa till friskvårds-/utbildnings-extra",
          "Föreslå att hänvisa till budget för nästa rond",
        ]
      : [
          "Be om svar innan ni avslutar dagens runda",
          "Föreslå paket: lön + extra utbildning",
          "80 % av framgångsrika förhandlare gör tystnaden till sin allierade",
        ];
  return (
    <div
      style={{
        padding: "16px 20px",
        border: "1px solid var(--line)",
        borderRadius: 6,
        background: "rgba(15,21,37,0.7)",
      }}
    >
      <div
        style={{
          fontFamily: "var(--mono)",
          fontSize: 9.5,
          letterSpacing: "1.2px",
          textTransform: "uppercase",
          color: "#a5b4fc",
        }}
      >
        Echo · taktiskt råd
      </div>
      <div
        style={{
          fontFamily: "var(--serif)",
          fontSize: 16,
          fontWeight: 700,
          margin: "6px 0 12px 0",
        }}
      >
        {hasProposal ? "Du är " : "Inga bud än — "}
        <em>
          {hasProposal
            ? round >= 3
              ? "nära mål — sänk inte mer"
              : "i god position"
            : "öppna högt"}
        </em>
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
        {tips.map((t, i) => (
          <div
            key={i}
            style={{
              padding: "8px 12px",
              background: "rgba(99,102,241,0.06)",
              border: "1px solid rgba(99,102,241,0.3)",
              borderRadius: 4,
              fontFamily: "var(--serif)",
              fontSize: 12,
              fontStyle: "italic",
              color: "#c7d2fe",
            }}
          >
            "{t}"
          </div>
        ))}
      </div>
    </div>
  );
}

function PedaCard() {
  return (
    <div
      style={{
        padding: "16px 20px",
        border: "1px solid var(--line)",
        borderRadius: 6,
        background: "rgba(15,21,37,0.5)",
      }}
    >
      <div
        style={{
          fontFamily: "var(--mono)",
          fontSize: 9.5,
          letterSpacing: "1.2px",
          textTransform: "uppercase",
          color: "var(--text-dim)",
        }}
      >
        Pedagogik · vad du lär dig
      </div>
      <div
        style={{
          fontFamily: "var(--serif)",
          fontSize: 16,
          fontWeight: 700,
          margin: "6px 0 8px 0",
        }}
      >
        Förhandling är <em>data</em>, inte konflikt.
      </div>
      <p
        style={{
          fontFamily: "var(--serif)",
          fontSize: 12,
          lineHeight: 1.5,
          color: "var(--text-mid)",
          margin: 0,
        }}
      >
        Anchoring (öppna högt). BATNA (ditt bästa alternativ). Smärtgräns
        (max Maria kan gå). Extra valuta (friskvård · utbildning ·
        flex).
      </p>
    </div>
  );
}

function HistoryRow({ n }: { n: V2MariaNegotiation }) {
  return (
    <div
      className="biz-table-row"
      style={{
        gridTemplateColumns: "100px 1.2fr 100px 110px 90px",
      }}
    >
      <span style={{ fontFamily: "var(--mono)", fontSize: 11 }}>
        {new Date(n.started_at).toLocaleDateString("sv-SE", {
          day: "numeric",
          month: "short",
          year: "numeric",
        })}
      </span>
      <span style={{ fontFamily: "var(--serif)", fontSize: 13 }}>
        {n.profession} · {n.employer}
      </span>
      <span style={{ fontFamily: "var(--mono)", fontSize: 11 }}>
        {n.rounds.length} / {n.max_rounds}
      </span>
      <span
        style={{
          fontFamily: "var(--mono)",
          fontSize: 11,
          color:
            n.final_pct != null
              ? n.final_pct > 0
                ? "#6ee7b7"
                : "#fff"
              : "var(--text-mid)",
        }}
      >
        {n.final_pct != null
          ? `+${n.final_pct.toFixed(1)} %`
          : "—"}
      </span>
      <span
        className={`biz-status ${
          n.status === "completed"
            ? "delta-up"
            : n.status === "abandoned"
            ? "delta-down"
            : "open"
        }`}
      >
        {n.status === "completed"
          ? "Klart"
          : n.status === "abandoned"
          ? "Avbrutet"
          : "Aktivt"}
      </span>
    </div>
  );
}
