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
import { EchoButton } from "./EchoButton";
import "./lan.css";


export function MariaV2() {
  const [data, setData] = useState<V2MariaData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState("");
  const [sending, setSending] = useState(false);
  const [starting, setStarting] = useState(false);
  const chatRef = useRef<HTMLDivElement>(null);

  function refresh() {
    return v2Api
      .maria()
      .then(setData)
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
      await v2Api.mariaStart();
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
      await v2Api.mariaSendMessage(data.active.id, message.trim());
      setMessage("");
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

              {/* Bug #8 · 'Acceptera bud'-knapp som v1 hade */}
              {active.status === "active" && active.rounds.length > 0 && (
                <div
                  style={{
                    marginTop: 12,
                    padding: 14,
                    background: "rgba(110,231,183,0.06)",
                    border: "1px solid rgba(110,231,183,0.25)",
                    borderRadius: 10,
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "center",
                  }}
                >
                  <div style={{ color: "rgba(255,255,255,0.85)", fontSize: "0.9rem" }}>
                    Nöjd med Marias senaste bud? Avsluta förhandlingen och
                    aktivera nya lönen från nästa månads lönespec.
                  </div>
                  <button
                    type="button"
                    onClick={async () => {
                      if (!confirm("Acceptera senaste bud och avsluta förhandlingen?")) return;
                      try {
                        const r = await fetch(
                          `/employer/negotiation/${active.id}/complete`,
                          {
                            method: "POST",
                            headers: {
                              "Content-Type": "application/json",
                              Authorization: `Bearer ${localStorage.getItem("hb_token") || ""}`,
                            },
                            body: JSON.stringify({ accept_offer: true }),
                          },
                        );
                        if (r.ok) {
                          window.location.reload();
                        } else {
                          alert(`Fel: ${await r.text()}`);
                        }
                      } catch (e) {
                        alert(`Fel: ${String((e as Error).message || e)}`);
                      }
                    }}
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
        <EchoButton context="Lönesamtal med Maria — taktik, BATNA, nästa drag" />
      </div>
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
