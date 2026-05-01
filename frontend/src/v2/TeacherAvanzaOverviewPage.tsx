/**
 * Lärar-vy · full insyn i en elevs Avanza ISK + aktiehandel.
 *
 * Använder /v2/teacher/students/{id}/avanza-overview som returnerar
 * hela elevens fond + aktie-portfölj + senaste trades med rationale.
 *
 * Lärare ser:
 * - Sammanfattning (totalt värde, schablonskatt, månads-spar)
 * - Fonder
 * - Aktier (med last_price från LatestStockQuote + unrealized PnL)
 * - Senaste 10 trades med "student_rationale" — pedagogiskt viktigt
 *   för bedömning ("varför handlade eleven?")
 *
 * Routas via /teacher/v2/avanza/:studentId.
 */
import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import {
  v2Api,
  type V2TeacherAvanzaOverview,
} from "./api";
import { V2Banner } from "./V2Banner";
import "./lan.css";

const SEK = (n: number) =>
  new Intl.NumberFormat("sv-SE", { maximumFractionDigits: 0 }).format(n);

const DATE_LABEL = (iso: string): string => {
  const d = new Date(iso);
  return d.toLocaleDateString("sv-SE", {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
};

export function TeacherAvanzaOverviewPage() {
  const { studentId } = useParams<{ studentId: string }>();
  const sid = studentId ? parseInt(studentId, 10) : 0;
  const [data, setData] = useState<V2TeacherAvanzaOverview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const navigate = useNavigate();

  useEffect(() => {
    if (!sid) return;
    v2Api
      .teacherAvanzaOverview(sid)
      .then(setData)
      .catch((e) => setError(String((e as Error)?.message || e)));
  }, [sid]);

  if (error) {
    return (
      <div className="v2-lan-root">
        <V2Banner status={{ role: "teacher", is_super_admin: false }} />
        <div className="bank-loading">
          <div>
            <div style={{ color: "#fca5a5", marginBottom: 8 }}>
              Kunde inte ladda Avanza-data
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
        <V2Banner status={{ role: "teacher", is_super_admin: false }} />
        <div className="bank-loading">Laddar Avanza-profil…</div>
      </div>
    );
  }

  const a = data.avanza;
  const s = a.summary;

  return (
    <div className="v2-lan-root">
      <V2Banner status={{ role: "teacher", is_super_admin: false }} />

      <div className="shell">
        <a
          className="actor-back"
          onClick={(e) => {
            e.preventDefault();
            navigate("/teacher/v2");
          }}
          href="#"
        >
          Tillbaka till v2-rostern
        </a>

        <header className="actor-head">
          <div>
            <span className="pill warm">Lärar-vy · Avanza ISK</span>
            <h1 className="actor-name" style={{ marginTop: 14 }}>
              {data.student_name}s <em>ISK-portfölj</em>.
            </h1>
            <p className="actor-sub">
              Investeringssparkonto · {s.fund_count} fonder ·{" "}
              {s.stock_count} aktier · senaste {a.recent_trades.length}{" "}
              affärer med rationale.
            </p>
          </div>
          <div className="actor-meta">
            Total: <strong>{SEK(s.total_value)} kr</strong>
            <br />
            Cash: <strong>{SEK(s.cash_balance)} kr</strong>
            <br />
            Schablonskatt: <strong>{SEK(s.schablonskatt_estimate)} kr/år</strong>
          </div>
        </header>

        {!s.isk_account_id && (
          <div
            style={{
              padding: "20px 24px",
              border: "1px solid var(--line)",
              borderRadius: 6,
              fontFamily: "var(--serif)",
              color: "var(--text-mid)",
              marginBottom: 22,
            }}
          >
            Eleven har inget ISK-konto. Det skapas vid första
            insättning från lönen, eller via /v2/banken.
            {s.monthly_savings > 0 && (
              <>
                {" "}
                Månads-spar är satt till{" "}
                <strong style={{ color: "var(--warm)" }}>
                  {SEK(s.monthly_savings)} kr/mån
                </strong>{" "}
                (intent från Pension-vyn) men inget kapital att sätta in på än.
              </>
            )}
          </div>
        )}

        {/* SAMMANFATTNING */}
        <div className="acct-grid">
          <div className="acct active">
            <div>
              <div className="acct-eye">Konto</div>
              <div className="acct-name">
                {s.isk_account_name || "Inget ISK"}
              </div>
              <div className="acct-num">
                {s.isk_account_id
                  ? `Konto-id ${s.isk_account_id}`
                  : "—"}
              </div>
            </div>
            <div>
              <div className="acct-bal">{SEK(s.total_value)}</div>
              <div className="acct-bal-meta">totalt värde</div>
            </div>
          </div>
          <div className="acct">
            <div>
              <div className="acct-eye">Fonder</div>
              <div className="acct-name">{s.fund_count} st</div>
              <div className="acct-num">
                {SEK(s.funds_value)} kr värde
              </div>
            </div>
            <div>
              <div className="acct-bal">{SEK(s.cash_balance)}</div>
              <div className="acct-bal-meta">cash</div>
            </div>
          </div>
          <div className="acct">
            <div>
              <div className="acct-eye">Aktier</div>
              <div className="acct-name">{s.stock_count} st</div>
              <div className="acct-num">
                {SEK(s.stocks_value)} kr värde
              </div>
            </div>
            <div>
              <div className="acct-bal">
                {SEK(s.schablonskatt_estimate)}
              </div>
              <div className="acct-bal-meta">skatt/år</div>
            </div>
          </div>
          <div className="acct">
            <div>
              <div className="acct-eye">Månadssparande</div>
              <div
                className="acct-name"
                style={{ color: "var(--warm)" }}
              >
                {SEK(s.monthly_savings)} kr/mån
              </div>
              <div className="acct-num">från Pension-vyn</div>
            </div>
            <div>
              <div
                className="acct-bal"
                style={{ color: "var(--warm)" }}
              >
                {s.monthly_savings > 0 ? "+2" : "0"}
              </div>
              <div className="acct-bal-meta">economy (wellbeing)</div>
            </div>
          </div>
        </div>

        <div className="act-grid">
          <div>
            {/* FONDER */}
            <div className="section-eye">
              Fonder ({a.funds.length})
            </div>
            {a.funds.length === 0 ? (
              <div
                style={{
                  padding: "16px 20px",
                  border: "1px solid var(--line)",
                  borderRadius: 6,
                  fontFamily: "var(--serif)",
                  fontSize: 13,
                  color: "var(--text-mid)",
                  marginBottom: 22,
                }}
              >
                Inga fond-positioner.
              </div>
            ) : (
              <div className="biz-table" style={{ marginBottom: 22 }}>
                <div
                  className="biz-table-row head"
                  style={{
                    gridTemplateColumns:
                      "1fr 80px 100px 100px 90px",
                  }}
                >
                  <span>Fond</span>
                  <span>Andelar</span>
                  <span>Senast</span>
                  <span>Värde</span>
                  <span>Tot. avk</span>
                </div>
                {a.funds.map((f) => (
                  <div
                    className="biz-table-row"
                    key={f.id}
                    style={{
                      gridTemplateColumns:
                        "1fr 80px 100px 100px 90px",
                    }}
                  >
                    <span style={{ fontFamily: "var(--serif)", fontSize: 13 }}>
                      {f.fund_name}
                    </span>
                    <span style={{ fontFamily: "var(--mono)", fontSize: 11 }}>
                      {f.units != null ? f.units.toFixed(2) : "—"}
                    </span>
                    <span style={{ fontFamily: "var(--mono)", fontSize: 11 }}>
                      {f.last_price != null ? f.last_price.toFixed(2) : "—"}
                    </span>
                    <span style={{ fontFamily: "var(--mono)", fontSize: 12 }}>
                      {SEK(f.market_value)} kr
                    </span>
                    <span
                      style={{
                        fontFamily: "var(--mono)",
                        fontSize: 11,
                        color:
                          (f.change_pct || 0) >= 0
                            ? "#6ee7b7"
                            : "#fca5a5",
                      }}
                    >
                      {f.change_pct != null
                        ? `${f.change_pct >= 0 ? "+" : ""}${f.change_pct.toFixed(1)} %`
                        : "—"}
                    </span>
                  </div>
                ))}
              </div>
            )}

            {/* AKTIER */}
            <div className="section-eye">
              Aktier ({a.stocks.length})
            </div>
            {a.stocks.length === 0 ? (
              <div
                style={{
                  padding: "16px 20px",
                  border: "1px solid var(--line)",
                  borderRadius: 6,
                  fontFamily: "var(--serif)",
                  fontSize: 13,
                  color: "var(--text-mid)",
                  marginBottom: 22,
                }}
              >
                Inga aktiepositioner.
              </div>
            ) : (
              <div className="biz-table" style={{ marginBottom: 22 }}>
                <div
                  className="biz-table-row head"
                  style={{
                    gridTemplateColumns:
                      "100px 70px 90px 90px 100px 90px",
                  }}
                >
                  <span>Ticker</span>
                  <span>Antal</span>
                  <span>Snittkurs</span>
                  <span>Senast</span>
                  <span>Värde</span>
                  <span>PnL</span>
                </div>
                {a.stocks.map((st) => (
                  <div
                    className="biz-table-row"
                    key={st.id}
                    style={{
                      gridTemplateColumns:
                        "100px 70px 90px 90px 100px 90px",
                    }}
                  >
                    <span
                      style={{
                        fontFamily: "var(--mono)",
                        fontSize: 12,
                        color: "var(--warm)",
                      }}
                    >
                      {st.ticker}
                    </span>
                    <span style={{ fontFamily: "var(--mono)", fontSize: 11 }}>
                      {st.quantity}
                    </span>
                    <span style={{ fontFamily: "var(--mono)", fontSize: 11 }}>
                      {SEK(st.avg_cost)}
                    </span>
                    <span style={{ fontFamily: "var(--mono)", fontSize: 11 }}>
                      {st.last_price != null ? SEK(st.last_price) : "—"}
                    </span>
                    <span style={{ fontFamily: "var(--mono)", fontSize: 12 }}>
                      {SEK(st.market_value)}
                    </span>
                    <span
                      style={{
                        fontFamily: "var(--mono)",
                        fontSize: 11,
                        color:
                          st.unrealized_pnl >= 0
                            ? "#6ee7b7"
                            : "#fca5a5",
                      }}
                    >
                      {st.unrealized_pnl >= 0 ? "+" : ""}
                      {SEK(st.unrealized_pnl)}
                      {st.unrealized_pnl_pct != null && (
                        <em
                          style={{
                            display: "block",
                            fontSize: 9,
                            fontStyle: "italic",
                          }}
                        >
                          {st.unrealized_pnl_pct >= 0 ? "+" : ""}
                          {st.unrealized_pnl_pct.toFixed(1)} %
                        </em>
                      )}
                    </span>
                  </div>
                ))}
              </div>
            )}

            {/* TRADES MED RATIONALE */}
            <div className="section-eye">
              Senaste affärer med motivering
            </div>
            {a.recent_trades.length === 0 ? (
              <div
                style={{
                  padding: "16px 20px",
                  border: "1px solid var(--line)",
                  borderRadius: 6,
                  fontFamily: "var(--serif)",
                  fontSize: 13,
                  color: "var(--text-mid)",
                }}
              >
                Inga trades genomförda.
              </div>
            ) : (
              <div className="tx-list">
                {a.recent_trades.map((t) => (
                  <div
                    key={t.id}
                    className="tx-row"
                    style={{
                      gridTemplateColumns:
                        "100px 1fr 100px 100px",
                    }}
                  >
                    <span className="tx-date">
                      {DATE_LABEL(t.executed_at)}
                    </span>
                    <div>
                      <div className="tx-name">
                        <span
                          style={{
                            color:
                              t.side === "buy"
                                ? "var(--warm)"
                                : "#a5b4fc",
                          }}
                        >
                          {t.side === "buy" ? "KÖP" : "SÄLJ"}
                        </span>{" "}
                        {t.quantity} st {t.ticker} @ {SEK(t.price)} kr
                      </div>
                      <div
                        className="tx-name-sub"
                        style={
                          t.student_rationale
                            ? {
                                fontStyle: "italic",
                                color: "var(--text-mid)",
                              }
                            : { color: "var(--text-dim)" }
                        }
                      >
                        {t.student_rationale
                          ? `"${t.student_rationale}"`
                          : "(ingen motivering)"}
                      </div>
                    </div>
                    <span
                      style={{
                        fontFamily: "var(--mono)",
                        fontSize: 11,
                      }}
                    >
                      {SEK(t.total_amount)} kr
                    </span>
                    <span
                      style={{
                        fontFamily: "var(--mono)",
                        fontSize: 11,
                        color:
                          t.realized_pnl != null
                            ? t.realized_pnl >= 0
                              ? "#6ee7b7"
                              : "#fca5a5"
                            : "var(--text-mid)",
                      }}
                    >
                      {t.realized_pnl != null
                        ? `${t.realized_pnl >= 0 ? "+" : ""}${SEK(t.realized_pnl)} pnl`
                        : `${SEK(t.courtage)} courtage`}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </div>

          <aside>
            <div className="side-card">
              <div className="side-card-eye">Wellbeing-effekt</div>
              <div className="side-card-h">
                ISK <em>räknas</em>
              </div>
              <div className="side-card-meta">
                ISK-värde &gt; 0 → +2 economy. Långsiktigt sparande
                visar finansiell mognad. Frekvent trading utan rationale
                kan flagga för spekulation (kommer i senare fas).
              </div>
            </div>
            <div className="side-card">
              <div className="side-card-eye">Schablonskatt</div>
              <div className="side-card-h">
                {SEK(s.schablonskatt_estimate)} kr/år
              </div>
              <div className="side-card-meta">
                0,89 % av kapitalunderlaget 2026. Eleven betalar i
                deklarationen. Mycket billigare än 30 % på vinst i
                vanlig depå för långsiktigt sparande.
              </div>
            </div>
            <div className="side-card warning">
              <div className="side-card-eye">Pedagogiskt syfte</div>
              <div className="side-card-h">
                Rationale är <em>guld</em>
              </div>
              <div className="side-card-meta">
                Varje trade bär en motivering. Läs dem — de visar
                elevens tankegång ("varför Volvo?") och är bästa
                bedömnings-input för aktiekompetens.
              </div>
            </div>
          </aside>
        </div>
      </div>
    </div>
  );
}
