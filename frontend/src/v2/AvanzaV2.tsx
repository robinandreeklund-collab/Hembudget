/**
 * Aktör 05 · Avanza · ISK + aktiehandel — elev-vy.
 *
 * Speglar prototypen /proposals/vol-7/elev.html (p-avanza):
 * - actor-head med pill, värde idag, avkastning, schablonskatt
 * - acct-grid · 4 fonder
 * - CTA till /v2/aktier (aktiehandel)
 * - Värdeutveckling tx-list
 * - aside · schablonskatt, simulator-länk, aktiemarknaden-länk
 * - peda-block "ISK gör tidsfaktorn till din vän"
 *
 * Hämtar via /v2/avanza · återanvänder /stocks/* (gammal API) för
 * själva trading-flowet via /v2/aktier.
 */
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { v2Api, type BankData, type V2AvanzaData } from "./api";
import { V2Banner } from "./V2Banner";
import "./lan.css";

const SEK = (n: number) =>
  new Intl.NumberFormat("sv-SE", { maximumFractionDigits: 0 }).format(n);

const MONTH_LABEL = (iso: string): string => {
  const d = new Date(iso);
  return d.toLocaleDateString("sv-SE", {
    month: "short",
    year: "numeric",
  });
};

export function AvanzaV2() {
  const [data, setData] = useState<V2AvanzaData | null>(null);
  const [bank, setBank] = useState<BankData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [buyOpen, setBuyOpen] = useState(false);
  const [buyFund, setBuyFund] = useState("");
  const [buyAccount, setBuyAccount] = useState<number | null>(null);
  const [buyAmount, setBuyAmount] = useState("1000");
  const [buyBusy, setBuyBusy] = useState(false);
  const [buyMsg, setBuyMsg] = useState<string | null>(null);

  function refresh() {
    v2Api
      .avanza()
      .then(setData)
      .catch((e) => setError(String((e as Error)?.message || e)));
    v2Api.bank(0).then(setBank).catch(() => null);
  }

  useEffect(() => {
    refresh();
  }, []);

  async function executeBuy() {
    if (!buyAccount || !buyFund.trim()) {
      setBuyMsg("Välj konto och fond");
      return;
    }
    const amt = parseFloat(buyAmount.replace(/\s/g, "").replace(",", "."));
    if (!amt || amt <= 0) {
      setBuyMsg("Ange ett positivt belopp");
      return;
    }
    setBuyBusy(true);
    setBuyMsg(null);
    try {
      const r = await v2Api.fundBuy({
        account_id: buyAccount,
        fund_name: buyFund.trim(),
        amount: amt,
      });
      setBuyMsg(
        `✓ Köpte ${r.fund_name} för ${amt} kr. Nytt värde: ` +
        `${Math.round(r.new_market_value)} kr · cash kvar: ` +
        `${Math.round(r.cash_remaining)} kr.`,
      );
      setBuyFund("");
      refresh();
    } catch (e) {
      setBuyMsg(`Fel: ${String((e as Error)?.message || e)}`);
    } finally {
      setBuyBusy(false);
    }
  }

  if (error && !data) {
    return (
      <div className="v2-lan-root">
        <V2Banner status={{ role: "student", is_super_admin: false }} />
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
        <V2Banner status={{ role: "student", is_super_admin: false }} />
        <div className="bank-loading">Laddar Avanza ISK…</div>
      </div>
    );
  }

  const { summary, funds, stocks, recent_trades } = data;
  const noAccount = summary.isk_account_id == null;

  const totalReturnPct =
    summary.total_value > 0 && funds.length
      ? funds.reduce(
          (sum, f) =>
            sum +
            (f.market_value * (f.change_pct || 0)) /
              summary.funds_value,
          0,
        )
      : 0;

  return (
    <div className="v2-lan-root">
      <V2Banner status={{ role: "student", is_super_admin: false }} />

      <div className="shell" data-guide="avanza-funds">
        <Link className="actor-back" to="/v2/hub">
          Tillbaka till pentagonen
        </Link>

        <header className="actor-head">
          <div>
            <span className="pill warm">Aktör 05 · Avanza</span>
            <h1 className="actor-name" style={{ marginTop: 14 }}>
              Avanza — <em>din ISK</em>.
            </h1>
            <p className="actor-sub">
              Investeringssparkonto · {summary.fund_count} fonder ·{" "}
              {summary.stock_count} aktier ·{" "}
              {summary.monthly_savings > 0
                ? `sparar ${SEK(summary.monthly_savings)} kr/mån`
                : "inget månadssparande satt"}
            </p>
          </div>
          <div className="actor-meta">
            Värde idag: <strong>{SEK(summary.total_value)} kr</strong>
            <br />
            {totalReturnPct !== 0 && (
              <>
                Avkastning:{" "}
                <strong
                  style={{
                    color: totalReturnPct >= 0 ? "#6ee7b7" : "#fca5a5",
                  }}
                >
                  {totalReturnPct >= 0 ? "+" : ""}
                  {totalReturnPct.toFixed(1)} %
                </strong>
                <br />
              </>
            )}
            Schablonskatt: ~ {SEK(summary.schablonskatt_estimate)} kr/år
          </div>
        </header>

        {noAccount ? (
          <div
            style={{
              padding: "24px 28px",
              border: "1px solid var(--line)",
              borderRadius: 6,
              fontFamily: "var(--serif)",
              color: "var(--text-mid)",
              marginBottom: 22,
            }}
          >
            Inget ISK-konto registrerat än. Ett ISK-konto skapas
            automatiskt vid första insättning från lönen, eller be läraren
            seedа Avanza-kontot. Sätt månadssparande via{" "}
            <Link
              to="/v2/pension"
              style={{ color: "var(--warm)" }}
            >
              Pensions-vyn
            </Link>{" "}
            (Pelare 3).
          </div>
        ) : (
          <>
            {/* FONDER · 4 kort */}
            {funds.length > 0 && (
              <div
                className="acct-grid"
                style={{
                  gridTemplateColumns: `repeat(${Math.min(funds.length, 4)}, 1fr)`,
                }}
              >
                {funds.slice(0, 4).map((f, idx) => (
                  <div key={f.id} className="acct">
                    <div>
                      <div className="acct-eye">
                        Fond {String(idx + 1).padStart(2, "0")}
                      </div>
                      <div className="acct-name">{f.fund_name}</div>
                      <div className="acct-num">
                        {f.units != null
                          ? `${f.units.toFixed(2)} andelar`
                          : "—"}
                      </div>
                    </div>
                    <div>
                      <div className="acct-bal">
                        {SEK(f.market_value)} kr
                      </div>
                      <div
                        className="acct-bal-meta"
                        style={{
                          color:
                            (f.change_pct || 0) >= 0
                              ? "#6ee7b7"
                              : "#fca5a5",
                        }}
                      >
                        {(f.change_pct || 0) >= 0 ? "+" : ""}
                        {(f.change_pct || 0).toFixed(1)} %
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}

            {/* KÖP FOND · cash → fond */}
            <article
              className="cta-card"
              style={{ marginTop: 22 }}
            >
              <div className="cta-eye">Köp fond · ISK</div>
              <div className="cta-h">
                Lägg <em>cash</em> i en fond.
              </div>
              <p className="cta-prose">
                Cash på ISK är räntelöst — flytta över till en
                indexfond eller branschfond för att starta tidsfaktorn.
                Pedagogiskt: när du klickar 'Köp' försvinner cash och
                fond-värdet växer. Totalvärdet är samma direkt efter
                köp — men över tid kommer fonden att växa.
              </p>
              {!buyOpen ? (
                <button
                  type="button"
                  className="cta-btn"
                  onClick={() => {
                    setBuyOpen(true);
                    const isk = bank?.accounts.find(
                      (a) => a.type === "isk",
                    );
                    setBuyAccount(
                      isk?.id || bank?.accounts[0]?.id || null,
                    );
                  }}
                >
                  Köp fond →
                </button>
              ) : (
                <div
                  style={{
                    marginTop: 12,
                    padding: "14px 18px",
                    background: "rgba(0,0,0,0.25)",
                    border: "1px solid var(--line-strong)",
                    borderRadius: 6,
                    display: "grid",
                    gap: 10,
                  }}
                >
                  <div
                    style={{
                      display: "grid",
                      gridTemplateColumns: "1fr 2fr 100px",
                      gap: 8,
                    }}
                  >
                    <select
                      value={buyAccount || ""}
                      onChange={(e) =>
                        setBuyAccount(parseInt(e.target.value, 10))
                      }
                      style={inpStyle}
                    >
                      {bank?.accounts.map((a) => (
                        <option key={a.id} value={a.id}>
                          {a.name} ({a.type})
                        </option>
                      ))}
                    </select>
                    <input
                      type="text"
                      list="known-funds"
                      placeholder="Fond (t.ex. 'Avanza Global')"
                      value={buyFund}
                      onChange={(e) => setBuyFund(e.target.value)}
                      style={inpStyle}
                    />
                    <datalist id="known-funds">
                      {data.funds.map((f) => (
                        <option key={f.id} value={f.fund_name} />
                      ))}
                    </datalist>
                    <input
                      type="number"
                      min="100"
                      step="100"
                      placeholder="kr"
                      value={buyAmount}
                      onChange={(e) => setBuyAmount(e.target.value)}
                      style={inpStyle}
                    />
                  </div>
                  <div style={{ display: "flex", gap: 8 }}>
                    <button
                      type="button"
                      className="cta-btn"
                      onClick={executeBuy}
                      disabled={buyBusy}
                    >
                      {buyBusy ? "Köper…" : "Bekräfta köp"}
                    </button>
                    <button
                      type="button"
                      className="cta-btn ghost"
                      onClick={() => {
                        setBuyOpen(false);
                        setBuyMsg(null);
                      }}
                    >
                      Avbryt
                    </button>
                  </div>
                  {buyMsg && (
                    <div
                      style={{
                        padding: "8px 12px",
                        borderRadius: 4,
                        fontFamily: "var(--mono)",
                        fontSize: 11,
                        color: buyMsg.startsWith("Fel")
                          ? "#fca5a5"
                          : "#6ee7b7",
                        background: buyMsg.startsWith("Fel")
                          ? "rgba(252,165,165,0.06)"
                          : "rgba(110,231,183,0.06)",
                        border: buyMsg.startsWith("Fel")
                          ? "1px solid rgba(252,165,165,0.4)"
                          : "1px solid rgba(110,231,183,0.4)",
                      }}
                    >
                      {buyMsg}
                    </div>
                  )}
                </div>
              )}
            </article>

            {/* CTA · Aktiehandel */}
            <article
              className="cta-card"
              style={{ marginTop: 22 }}
            >
              <div className="cta-eye">
                Aktiehandel · OMXS30 + USA large-caps
              </div>
              <div className="cta-h">
                Vill du <em>handla</em> aktier själv?
              </div>
              <p className="cta-prose">
                Förutom fonderna kan du köpa enskilda aktier — OMXS30 +
                30 USA-large-caps. Mini-courtage 1 kr min · 0,25 % över
                400 kr. Pedagogiskt: <em>fonder är bredd, aktier är
                fokus</em>. Lär dig diversifiering genom att handla själv.
              </p>
              <Link
                to="/v2/aktier"
                className="cta-btn"
                style={{ textDecoration: "none" }}
              >
                Öppna aktiemarknaden →
              </Link>
            </article>

            <div className="act-grid" style={{ marginTop: 22 }}>
              <div>
                {/* AKTIEINNEHAV */}
                {stocks.length > 0 && (
                  <>
                    <div className="section-eye">
                      Dina aktier ({stocks.length})
                    </div>
                    <div
                      className="biz-table"
                      style={{ marginBottom: 22 }}
                    >
                      <div
                        className="biz-table-row head"
                        style={{
                          gridTemplateColumns:
                            "100px 1fr 70px 90px 100px 90px",
                        }}
                      >
                        <span>Ticker</span>
                        <span>Snittkurs</span>
                        <span>Antal</span>
                        <span>Senast</span>
                        <span>Värde</span>
                        <span>Avkastning</span>
                      </div>
                      {stocks.map((st) => (
                        <div
                          className="biz-table-row"
                          key={st.id}
                          style={{
                            gridTemplateColumns:
                              "100px 1fr 70px 90px 100px 90px",
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
                          <span
                            style={{
                              fontFamily: "var(--mono)",
                              fontSize: 11,
                              color: "var(--text-mid)",
                            }}
                          >
                            {SEK(st.avg_cost)} kr
                          </span>
                          <span
                            style={{
                              fontFamily: "var(--mono)",
                              fontSize: 11,
                            }}
                          >
                            {st.quantity}
                          </span>
                          <span
                            style={{
                              fontFamily: "var(--mono)",
                              fontSize: 11,
                            }}
                          >
                            {st.last_price != null
                              ? SEK(st.last_price)
                              : "—"}
                          </span>
                          <span
                            style={{
                              fontFamily: "var(--mono)",
                              fontSize: 12,
                            }}
                          >
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
                            {SEK(st.unrealized_pnl)} kr
                            {st.unrealized_pnl_pct != null &&
                              ` (${st.unrealized_pnl_pct >= 0 ? "+" : ""}${st.unrealized_pnl_pct.toFixed(1)} %)`}
                          </span>
                        </div>
                      ))}
                    </div>
                  </>
                )}

                {/* TRADES-HISTORIK */}
                <div className="section-eye">
                  Senaste affärer ({recent_trades.length})
                </div>
                {recent_trades.length === 0 ? (
                  <div
                    style={{
                      padding: "16px 20px",
                      border: "1px solid var(--line)",
                      borderRadius: 6,
                      fontFamily: "var(--serif)",
                      fontSize: 13,
                      color: "var(--text-mid)",
                      marginBottom: 18,
                    }}
                  >
                    Inga affärer ännu. Klicka "Öppna aktiemarknaden"
                    ovan för att handla.
                  </div>
                ) : (
                  <div className="tx-list">
                    {recent_trades.map((t) => (
                      <div
                        key={t.id}
                        className="tx-row"
                        style={{
                          gridTemplateColumns:
                            "80px 1fr 80px 70px 100px",
                        }}
                      >
                        <span className="tx-date">
                          {MONTH_LABEL(t.executed_at)}
                        </span>
                        <div>
                          <div className="tx-name">
                            {t.ticker} · {t.quantity} st @{" "}
                            {SEK(t.price)} kr
                          </div>
                          {t.student_rationale && (
                            <div className="tx-name-sub">
                              "{t.student_rationale}"
                            </div>
                          )}
                        </div>
                        <span
                          className="tx-cat"
                          style={{
                            color:
                              t.side === "buy"
                                ? "var(--warm)"
                                : "#a5b4fc",
                          }}
                        >
                          {t.side === "buy" ? "Köp" : "Sälj"}
                        </span>
                        <span
                          style={{
                            fontFamily: "var(--mono)",
                            fontSize: 10,
                            color: "var(--text-mid)",
                          }}
                        >
                          {SEK(t.courtage)} courtage
                        </span>
                        <span
                          className="tx-amt"
                          style={
                            t.realized_pnl != null && t.realized_pnl < 0
                              ? { color: "#fca5a5" }
                              : t.realized_pnl != null && t.realized_pnl > 0
                              ? { color: "#6ee7b7" }
                              : undefined
                          }
                        >
                          {t.side === "buy" ? "−" : "+"}
                          {SEK(t.total_amount)} kr
                          {t.realized_pnl != null && t.realized_pnl !== 0 && (
                            <em
                              style={{
                                display: "block",
                                fontSize: 10,
                                fontStyle: "italic",
                              }}
                            >
                              {t.realized_pnl >= 0 ? "+" : ""}
                              {SEK(t.realized_pnl)} pnl
                            </em>
                          )}
                        </span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
              <aside>
                <div className="side-card">
                  <div className="side-card-eye">Schablonskatt 2026</div>
                  <div className="side-card-h">
                    ~ {SEK(summary.schablonskatt_estimate)} kr/år
                  </div>
                  <div className="side-card-meta">
                    0,89 % på kapitalunderlaget · betalas i deklarationen.
                  </div>
                  <Link
                    to="/v2/skatten"
                    className="side-card-link"
                    style={{ textDecoration: "none" }}
                  >
                    Se skatt-rummet ↗
                  </Link>
                </div>
                <div className="side-card">
                  <div className="side-card-eye">Cash på ISK</div>
                  <div className="side-card-h">
                    {SEK(summary.cash_balance)} kr
                  </div>
                  <div className="side-card-meta">
                    Outvecklat kapital · väntar på köp. Sätt
                    månadssparande för att autoinvestera vid varje insättning.
                  </div>
                </div>
                <div className="side-card">
                  <div className="side-card-eye">Aktiemarknaden</div>
                  <div className="side-card-h">
                    Live-kurser <em>idag</em>
                  </div>
                  <div className="side-card-meta">
                    OMXS30 + USA-large-caps · ~15 min fördröjning ·
                    courtage 1 kr min, 0,25 % över 400 kr.
                  </div>
                  <Link
                    to="/v2/aktier"
                    className="side-card-link"
                    style={{ textDecoration: "none" }}
                  >
                    Se marknaden ↗
                  </Link>
                </div>
              </aside>
            </div>
          </>
        )}

        {/* PEDA */}
        <div className="peda">
          <div className="peda-eye">Pedagogik · vad du lär dig här</div>
          <div className="peda-h">
            ISK gör <em>tidsfaktorn</em> till din vän.
          </div>
          <p className="peda-prose">
            Avanza är inte värdepappershandel — det är{" "}
            <strong>tidsdisciplin</strong>. Att spara 600 kr/mån från 16
            år ger ~ 1,2 Mkr vid 50 (vid 7 % real avkastning). Att starta
            vid 25 ger ~ 600 tkr. <em>Tioårsfönstret</em> 16–25 är värt
            ~600 tkr över livet. ISK beskattas med <code>schablon</code>{" "}
            på kapitalunderlag (~0,89 % 2026) istället för 30 % på vinst —
            billigare för långsiktigt sparande.
          </p>
          <ul className="peda-bullets">
            <li>
              <strong>Ränta-på-ränta</strong>Avkastningen genererar
              avkastning. Linje över tid blir kurva.
            </li>
            <li>
              <strong>Real avkastning</strong>Avkastning minus inflation.
              ~7 % över historiken.
            </li>
            <li>
              <strong>Schablonskatt</strong>Statslåneränta + 1 %, golv
              1,25 %. ~0,89 % 2026 av kapitalet.
            </li>
            <li>
              <strong>Index vs aktiv</strong>Indexfond &lt; 0,5 % avgift
              slår 80 % aktivt förvaltade på 10 år.
            </li>
          </ul>
          <div className="peda-concepts">
            <span className="peda-concept">ISK</span>
            <span className="peda-concept">Kapitalförsäkring</span>
            <span className="peda-concept">Indexfond</span>
            <span className="peda-concept">Schablonskatt</span>
            <span className="peda-concept">Spridning</span>
            <span className="peda-concept">TER</span>
          </div>
          <div className="peda-tip">
            Investeringssimulatorn låter dig jämföra: 600 kr/mån i 30 år
            vs 1 200 kr/mån i 15 år? Total insats lika, totalavkastning
            olika. Tiden är inte linjär.
          </div>
        </div>
      </div>
    </div>
  );
}

const inpStyle: React.CSSProperties = {
  background: "rgba(255,255,255,0.04)",
  border: "1px solid var(--line-strong)",
  color: "#fff",
  padding: "8px 10px",
  borderRadius: 6,
  fontFamily: "var(--mono)",
  fontSize: 12,
};
