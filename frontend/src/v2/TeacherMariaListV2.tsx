/**
 * Lärar-vy · alla pågående och nyligen avslutade lönesamtal
 * (motsv. larare.html#p-maria).
 *
 * Routas via /teacher/v2/maria.
 *
 * 3-kolumns-layout med kort per lönesamtal:
 * - Avatar (M-gradient) + elev-namn + profession
 * - Senaste 1-2 ronder (bubblor: blå=Maria, accent=elev)
 * - Bud-historik + 5-stegs runda-track + smärtgräns-flagga
 * - Klickbart → /teacher/v2/maria/:studentId (befintlig overview)
 *
 * Avslutade · listas under aktiva med utfall.
 */
import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  v2Api,
  type V2MariaListResponse,
  type V2MariaListItem,
} from "./api";
import { V2Banner } from "./V2Banner";
import "./larare.css";

function fmtSEK(n: number | null): string {
  if (n === null || n === undefined) return "—";
  return Math.round(n).toLocaleString("sv-SE");
}

export function TeacherMariaListV2() {
  const [data, setData] = useState<V2MariaListResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const navigate = useNavigate();

  useEffect(() => {
    v2Api
      .teacherMariaList()
      .then(setData)
      .catch((e) => setError(String((e as Error)?.message || e)));
  }, []);

  if (error && !data) {
    return (
      <div className="v2-larare-root">
        <V2Banner status={{ role: "teacher", is_super_admin: false }} />
        <div className="larare-loading">
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
      <div className="v2-larare-root">
        <V2Banner status={{ role: "teacher", is_super_admin: false }} />
        <div className="larare-loading">Laddar lönesamtal…</div>
      </div>
    );
  }

  const s = data.summary;

  return (
    <div className="v2-larare-root">
      <V2Banner status={{ role: "teacher", is_super_admin: false }} />

      <div className="shell">
        <a
          className="attn-go"
          onClick={(e) => {
            e.preventDefault();
            navigate("/teacher/v2");
          }}
          href="#"
          style={{ marginBottom: 22, display: "inline-block" }}
        >
          ← Tillbaka till klassen
        </a>

        <header className="larare-head">
          <div>
            <span className="pill warm">
              Maria · {s.active_count} lönesamtal pågår
            </span>
            <h1 className="larare-head-h1">
              Klassens <em>förhandlingar</em>.
            </h1>
            <p
              style={{
                fontFamily: "Source Serif 4, Georgia, serif",
                fontSize: 16,
                color: "rgba(255,255,255,0.6)",
                marginTop: 12,
              }}
            >
              AI-Maria spelar olika roller (HR-chef, butikschef, IT-chef)
              parallellt — samma motor, olika smärtgränser och avtal.
            </p>
          </div>
          <div className="larare-head-meta">
            Snitt-runda klassen: <strong>{s.avg_round_no} av 5</strong>
            <br />
            Avslutade (30 d): <strong>{s.completed_count}</strong>
            {s.abandoned_count > 0 && (
              <>
                <br />
                Avbrutna: <strong>{s.abandoned_count}</strong>
              </>
            )}
          </div>
        </header>

        {s.near_pain_count > 0 && (
          <div
            style={{
              background: "rgba(220,76,43,0.06)",
              border: "1px solid rgba(220,76,43,0.25)",
              borderLeft: "3px solid var(--accent, #dc4c2b)",
              borderRadius: 6,
              padding: "12px 18px",
              marginBottom: 22,
              fontFamily: "JetBrains Mono, monospace",
              fontSize: 11,
              color: "var(--accent, #dc4c2b)",
              letterSpacing: 0.5,
            }}
          >
            ⚠ {s.near_pain_count} elev{s.near_pain_count === 1 ? "" : "er"}{" "}
            är nära Marias smärtgräns (proposed_pct ≥ 6,0). Förhandlingen
            kan bryta — eleven behöver kanske argument-stöd.
          </div>
        )}

        {/* Aktiva · 3-kolumns-grid */}
        {data.active.length === 0 ? (
          <div
            style={{
              padding: "24px 28px",
              border: "1px solid var(--line, rgba(255,255,255,0.1))",
              borderRadius: 6,
              fontFamily: "Source Serif 4, Georgia, serif",
              color: "rgba(255,255,255,0.5)",
              marginBottom: 28,
            }}
          >
            Ingen aktiv förhandling just nu. Eleverna startar Maria-samtal
            via lönesamtals-modulen i sin elev-vy.
          </div>
        ) : (
          <>
            <div className="section-title">
              Aktiva förhandlingar ({data.active.length})
            </div>
            <div
              style={{
                display: "grid",
                gridTemplateColumns: "repeat(auto-fit, minmax(360px, 1fr))",
                gap: 18,
                marginBottom: 28,
              }}
            >
              {data.active.map((item) => (
                <NegotiationCard
                  key={item.negotiation_id}
                  item={item}
                  navigate={navigate}
                />
              ))}
            </div>
          </>
        )}

        {/* Avslutade */}
        {data.completed.length > 0 && (
          <div className="s-card">
            <div className="s-card-eye">
              Avslutade lönesamtal · {data.completed.length} senaste 30 dgr
            </div>
            <ul className="attn-list">
              {data.completed.map((c) => (
                <li key={c.negotiation_id}>
                  <div>
                    <div className="attn-name">{c.student_name}</div>
                    <div className="attn-why">
                      {c.status === "completed"
                        ? `avslutad runda ${c.current_round_no}/${c.max_rounds} · landade ${fmtSEK(
                            c.final_salary,
                          )} kr`
                        : `avbruten runda ${c.current_round_no}/${c.max_rounds}`}
                      {c.final_pct != null
                        ? ` · ${c.final_pct.toFixed(1)} % från start`
                        : ""}
                      {c.avtal_norm_pct != null
                        ? ` · avtalsnorm ${c.avtal_norm_pct.toFixed(1)} %`
                        : ""}
                    </div>
                  </div>
                  <Link
                    className="attn-go"
                    to={`/teacher/v2/maria/${c.student_id}`}
                  >
                    se utfallet →
                  </Link>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </div>
  );
}

function NegotiationCard({
  item,
  navigate,
}: {
  item: V2MariaListItem;
  navigate: ReturnType<typeof useNavigate>;
}) {
  const isWarm = item.current_round_no >= 4;
  const isPain = item.near_pain_threshold;
  const trackColor = (i: number) => {
    if (i + 1 < item.current_round_no) return "var(--warm, #fbbf24)";
    if (i + 1 === item.current_round_no) {
      return isPain ? "var(--accent, #dc4c2b)" : "var(--accent, #dc4c2b)";
    }
    return "rgba(255,255,255,0.08)";
  };
  const cardBorderColor = isPain
    ? "rgba(220,76,43,0.4)"
    : "var(--line, rgba(255,255,255,0.1))";
  return (
    <button
      type="button"
      onClick={() => navigate(`/teacher/v2/maria/${item.student_id}`)}
      className="s-card"
      style={{
        padding: 0,
        overflow: "hidden",
        borderColor: cardBorderColor,
        textAlign: "left",
        cursor: "pointer",
        background: "rgba(15,21,37,0.7)",
      }}
    >
      {/* Header */}
      <div
        style={{
          padding: "14px 18px",
          borderBottom: "1px solid var(--line, rgba(255,255,255,0.1))",
          background: "rgba(99,102,241,0.08)",
        }}
      >
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 10,
            marginBottom: 6,
          }}
        >
          <div
            style={{
              width: 32,
              height: 32,
              borderRadius: "50%",
              background:
                "linear-gradient(135deg, #6366f1, #8b5cf6)",
              display: "grid",
              placeItems: "center",
              fontFamily: "Source Serif 4, Georgia, serif",
              fontWeight: 700,
              color: "#fff",
              fontSize: 14,
            }}
          >
            M
          </div>
          <div>
            <div
              style={{
                fontFamily: "Source Serif 4, Georgia, serif",
                fontSize: 14,
                fontWeight: 700,
                color: "#fff",
              }}
            >
              Maria → {item.student_name}
            </div>
            <div
              style={{
                fontFamily: "JetBrains Mono, monospace",
                fontSize: 9,
                color: "rgba(255,255,255,0.6)",
                letterSpacing: 1,
                textTransform: "uppercase",
              }}
            >
              {item.employer.toUpperCase()} · {item.profession.toUpperCase()}
            </div>
          </div>
        </div>
        <div
          style={{
            fontFamily: "JetBrains Mono, monospace",
            fontSize: 9.5,
            color: isPain
              ? "var(--accent, #dc4c2b)"
              : isWarm
              ? "var(--warm, #fbbf24)"
              : "rgba(255,255,255,0.5)",
            letterSpacing: 1.2,
            textTransform: "uppercase",
          }}
        >
          Runda {item.current_round_no} av {item.max_rounds} ·{" "}
          {isPain ? "nära smärtgräns" : isWarm ? "nära avslut" : "pågår"}
        </div>
      </div>

      {/* Senaste konversation (1-2 ronder) */}
      <div style={{ padding: "14px 18px" }}>
        {item.rounds.length === 0 ? (
          <div
            style={{
              fontFamily: "Source Serif 4, Georgia, serif",
              fontSize: 13,
              color: "rgba(255,255,255,0.5)",
              fontStyle: "italic",
            }}
          >
            Förberedelse · just startat. Ingen rond skickad än.
          </div>
        ) : (
          item.rounds.map((r) => (
            <div key={r.round_no} style={{ marginBottom: 8 }}>
              <div
                style={{
                  fontFamily: "Source Serif 4, Georgia, serif",
                  fontSize: 12.5,
                  color: "rgba(255,255,255,0.92)",
                  padding: "10px 12px",
                  background: "rgba(99,102,241,0.06)",
                  borderRadius: 6,
                  marginBottom: 6,
                  lineHeight: 1.45,
                }}
              >
                <em
                  style={{
                    color: "rgba(255,255,255,0.4)",
                    fontSize: 9,
                    display: "block",
                    marginBottom: 4,
                    letterSpacing: 1,
                  }}
                >
                  MARIA
                </em>
                "{r.employer_response}"
              </div>
              <div
                style={{
                  fontFamily: "Source Serif 4, Georgia, serif",
                  fontSize: 12.5,
                  color: "rgba(255,255,255,0.92)",
                  padding: "10px 12px",
                  background: "rgba(220,76,43,0.08)",
                  borderRadius: 6,
                  lineHeight: 1.45,
                }}
              >
                <em
                  style={{
                    color: "rgba(255,255,255,0.4)",
                    fontSize: 9,
                    display: "block",
                    marginBottom: 4,
                    letterSpacing: 1,
                  }}
                >
                  {item.student_name.toUpperCase()}
                </em>
                "{r.student_message}"
              </div>
            </div>
          ))
        )}
      </div>

      {/* Bud-historik + track */}
      <div
        style={{
          padding: "12px 18px",
          borderTop: "1px solid var(--line, rgba(255,255,255,0.1))",
          background: "rgba(255,255,255,0.02)",
        }}
      >
        <div
          style={{
            fontFamily: "JetBrains Mono, monospace",
            fontSize: 9,
            color: "rgba(255,255,255,0.4)",
            letterSpacing: 1,
            marginBottom: 6,
          }}
        >
          BUD-HISTORIK · start {fmtSEK(item.starting_salary)}
        </div>
        <div
          style={{
            fontFamily: "JetBrains Mono, monospace",
            fontSize: 10,
            color: "rgba(255,255,255,0.92)",
            lineHeight: 1.6,
          }}
        >
          {item.rounds.map((r) => (
            <div
              key={r.round_no}
              style={{
                color:
                  r.round_no === item.current_round_no
                    ? isPain
                      ? "var(--accent, #dc4c2b)"
                      : "var(--accent, #dc4c2b)"
                    : "rgba(255,255,255,0.92)",
              }}
            >
              R{r.round_no} · Maria{" "}
              {r.proposed_salary != null
                ? `${fmtSEK(r.proposed_salary)} (${r.proposed_pct?.toFixed(1)} %)`
                : "—"}
            </div>
          ))}
        </div>
        {/* Track */}
        <div
          style={{
            display: "flex",
            gap: 4,
            marginTop: 10,
          }}
        >
          {Array.from({ length: item.max_rounds }, (_, i) => (
            <div
              key={i}
              style={{
                flex: 1,
                height: 5,
                background: trackColor(i),
                borderRadius: 100,
              }}
            />
          ))}
        </div>
        {isPain && (
          <div
            style={{
              fontFamily: "JetBrains Mono, monospace",
              fontSize: 9,
              color: "var(--accent, #dc4c2b)",
              letterSpacing: 1,
              marginTop: 8,
              fontWeight: 700,
            }}
          >
            ⚠ MARIA NÄRA SMÄRTGRÄNS
          </div>
        )}
        {item.avtal_norm_pct != null && (
          <div
            style={{
              fontFamily: "JetBrains Mono, monospace",
              fontSize: 9,
              color: "rgba(255,255,255,0.4)",
              letterSpacing: 0.5,
              marginTop: 6,
            }}
          >
            avtalsnorm: {item.avtal_norm_pct.toFixed(1)} %
          </div>
        )}
      </div>
    </button>
  );
}
