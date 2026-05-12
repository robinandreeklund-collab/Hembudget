/**
 * Aktiehandel — elev-vy.
 *
 * Speglar gamla dashboardens stocks-vy. Listar aktiemarknaden
 * (StockMaster + LatestStockQuote) och låter eleven köpa/sälja via
 * /stocks/{ticker}/buy och /stocks/{ticker}/sell.
 *
 * Använder /v2/aktier/market för market-data + /v2/avanza för
 * kontoinfo + /stocks/* för själva trades (existerande gammal API).
 *
 * Wellbeing-koppling: trades påverkar StockHolding och därmed ISK-värde
 * → economy-faktorn i wellbeing.
 */
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { v2Api, type V2AvanzaData } from "./api";
import { V2Banner } from "./V2Banner";
import "./lan.css";

const SEK = (n: number) =>
  new Intl.NumberFormat("sv-SE", { maximumFractionDigits: 0 }).format(n);

type MarketRow = {
  ticker: string;
  name: string;
  sector: string | null;
  currency: string;
  last: number;
  change_pct: number | null;
  bid: number | null;
  ask: number | null;
};

export function AktierV2() {
  const [market, setMarket] = useState<MarketRow[]>([]);
  const [marketOpen, setMarketOpen] = useState(false);
  const [lastUpdatedAt, setLastUpdatedAt] =
    useState<string | null>(null);
  const [avanza, setAvanza] = useState<V2AvanzaData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState("");

  // Trade-form
  const [selected, setSelected] = useState<MarketRow | null>(null);
  const [qty, setQty] = useState("");
  const [side, setSide] = useState<"buy" | "sell">("buy");
  const [rationale, setRationale] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [tradeMessage, setTradeMessage] = useState<string | null>(null);
  const [tradeError, setTradeError] = useState<string | null>(null);

  function refresh(): Promise<unknown> {
    return Promise.all([
      v2Api.stocksMarket().then((m) => {
        setMarket(m.stocks);
        setMarketOpen(m.market_open);
        setLastUpdatedAt(m.last_updated_at);
      }),
      v2Api.avanza().then(setAvanza),
    ]).catch((e) => setError(String((e as Error)?.message || e)));
  }

  useEffect(() => {
    refresh();
    // Auto-refresha kurser var 30 sek så eleven ser levande priser
    // utan att behöva uppdatera sidan. Backend pollar yfinance var 5
    // min så ändringen syns kort efter att den landat i master-DB:n.
    const interval = window.setInterval(() => {
      refresh();
    }, 30000);
    return () => window.clearInterval(interval);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function fmtUpdatedAt(iso: string | null): string {
    if (!iso) return "—";
    const t = new Date(iso).getTime();
    const diff = Math.max(0, Date.now() - t);
    const min = Math.floor(diff / 60000);
    if (min < 1) return "just nu";
    if (min < 60) return `${min} min sedan`;
    const h = Math.floor(min / 60);
    if (h < 24) return `${h} h sedan`;
    return new Date(iso).toLocaleString("sv-SE", {
      day: "numeric", month: "short", hour: "2-digit", minute: "2-digit",
    });
  }

  const filtered = market.filter(
    (r) =>
      r.ticker.toLowerCase().includes(filter.toLowerCase()) ||
      r.name.toLowerCase().includes(filter.toLowerCase()),
  );

  const ownedQty = (ticker: string): number => {
    if (!avanza) return 0;
    const h = avanza.stocks.find((s) => s.ticker === ticker);
    return h ? h.quantity : 0;
  };

  async function executeTrade() {
    setTradeError(null);
    setTradeMessage(null);
    if (!selected || !avanza?.summary.isk_account_id) {
      setTradeError("Välj aktie och se till att du har ett ISK-konto");
      return;
    }
    const q = parseInt(qty, 10);
    if (isNaN(q) || q <= 0) {
      setTradeError("Antal måste vara > 0");
      return;
    }
    if (side === "sell" && ownedQty(selected.ticker) < q) {
      setTradeError(
        `Du äger bara ${ownedQty(selected.ticker)} ${selected.ticker}`,
      );
      return;
    }
    setSubmitting(true);
    try {
      const fn = side === "buy" ? v2Api.stocksBuy : v2Api.stocksSell;
      const r = await fn(selected.ticker, {
        account_id: avanza.summary.isk_account_id,
        quantity: q,
        student_rationale: rationale.trim() || undefined,
      });
      setTradeMessage(
        `${side === "buy" ? "Köpt" : "Sålt"} ${q} st ${selected.ticker} @ ${SEK(
          (r as { price: number }).price,
        )} kr`,
      );
      setQty("");
      setRationale("");
      setSelected(null);
      await refresh();
    } catch (e) {
      setTradeError(String((e as Error)?.message || e));
    } finally {
      setSubmitting(false);
    }
  }

  if (error && !market.length) {
    return (
      <div className="v2-lan-root">
        <V2Banner status={{ role: "student", is_super_admin: false }} />
        <div className="bank-loading">
          <div>
            <div style={{ color: "#fca5a5", marginBottom: 8 }}>
              Kunde inte ladda aktiemarknaden
            </div>
            <pre style={{ fontSize: 11 }}>{error}</pre>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="v2-lan-root">
      <V2Banner status={{ role: "student", is_super_admin: false }} />

      <div className="shell">
        <Link className="actor-back" to="/v2/avanza">
          Tillbaka till Avanza
        </Link>

        <header className="actor-head">
          <div>
            <span className="pill warm">Aktiehandel</span>
            <h1 className="actor-name" style={{ marginTop: 14 }}>
              Aktiemarknaden — <em>{market.length}</em> aktier.
            </h1>
            <p className="actor-sub">
              {marketOpen
                ? "● Marknad öppen · ~15 min fördröjning"
                : "○ Marknad stängd"}{" "}
              · OMXS30 + USA-large-caps · courtage 1 kr min, 0,25 % över
              400 kr.
            </p>
            <p
              className="actor-sub"
              style={{ marginTop: 4, opacity: 0.7, fontSize: 12 }}
            >
              Kurser uppdaterade <strong>{fmtUpdatedAt(lastUpdatedAt)}</strong>
              {" "}· auto-refresh var 30 sek
            </p>
          </div>
          <div className="actor-meta">
            ISK-värde:{" "}
            <strong>
              {SEK(avanza?.summary.total_value || 0)} kr
            </strong>
            <br />
            Cash: <strong>{SEK(avanza?.summary.cash_balance || 0)} kr</strong>
            <br />
            Aktier: <strong>{avanza?.summary.stock_count || 0} st</strong>
          </div>
        </header>

        {tradeMessage && (
          <div
            style={{
              padding: "10px 16px",
              border: "1px solid rgba(110,231,183,0.4)",
              background: "rgba(110,231,183,0.06)",
              borderRadius: 6,
              fontFamily: "var(--mono)",
              fontSize: 11,
              color: "#6ee7b7",
              marginBottom: 18,
              letterSpacing: "0.6px",
            }}
          >
            ✓ {tradeMessage}
          </div>
        )}

        {/* Sök + filter */}
        <div style={{ marginBottom: 12 }}>
          <input
            placeholder="Sök ticker eller namn (ABB, Volvo, AAPL...)"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            style={{
              background: "rgba(255,255,255,0.04)",
              border: "1px solid var(--line-strong)",
              color: "#fff",
              padding: "10px 14px",
              borderRadius: 4,
              fontFamily: "var(--mono)",
              fontSize: 13,
              width: "100%",
              maxWidth: 400,
            }}
          />
        </div>

        <div className="act-grid">
          <div>
            <div className="section-eye">
              Aktiemarknaden ({filtered.length})
            </div>
            {filtered.length === 0 ? (
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
                {market.length === 0
                  ? "Aktiemarknaden är tom — be admin köra stocks-poll."
                  : "Inga aktier matchar filtret."}
              </div>
            ) : (
              <div className="biz-table">
                <div
                  className="biz-table-row head"
                  style={{
                    gridTemplateColumns:
                      "100px 1fr 90px 90px 70px 70px",
                  }}
                >
                  <span>Ticker</span>
                  <span>Namn / sektor</span>
                  <span>Senast</span>
                  <span>Förändring</span>
                  <span>Innehav</span>
                  <span></span>
                </div>
                {filtered.map((r) => (
                  <div
                    className="biz-table-row"
                    key={r.ticker}
                    style={{
                      gridTemplateColumns:
                        "100px 1fr 90px 90px 70px 70px",
                      cursor: "pointer",
                      background:
                        selected?.ticker === r.ticker
                          ? "rgba(220,76,43,0.06)"
                          : undefined,
                    }}
                    onClick={() => {
                      setSelected(r);
                      setSide("buy");
                    }}
                  >
                    <span
                      style={{
                        fontFamily: "var(--mono)",
                        fontSize: 12,
                        color: "var(--warm)",
                      }}
                    >
                      {r.ticker}
                    </span>
                    <div>
                      <div
                        style={{
                          fontFamily: "var(--serif)",
                          fontSize: 13,
                        }}
                      >
                        {r.name}
                      </div>
                      <div
                        style={{
                          fontFamily: "var(--mono)",
                          fontSize: 9.5,
                          color: "var(--text-dim)",
                        }}
                      >
                        {r.sector || "—"}
                      </div>
                    </div>
                    <span
                      style={{
                        fontFamily: "var(--mono)",
                        fontSize: 12,
                      }}
                    >
                      {r.last.toFixed(2)} {r.currency}
                    </span>
                    <span
                      style={{
                        fontFamily: "var(--mono)",
                        fontSize: 11,
                        color:
                          (r.change_pct || 0) >= 0
                            ? "#6ee7b7"
                            : "#fca5a5",
                      }}
                    >
                      {r.change_pct != null
                        ? `${r.change_pct >= 0 ? "+" : ""}${r.change_pct.toFixed(2)} %`
                        : "—"}
                    </span>
                    <span
                      style={{
                        fontFamily: "var(--mono)",
                        fontSize: 11,
                        color:
                          ownedQty(r.ticker) > 0
                            ? "var(--warm)"
                            : "var(--text-dim)",
                      }}
                    >
                      {ownedQty(r.ticker) || "—"}
                    </span>
                    <button
                      type="button"
                      style={{
                        background: "transparent",
                        border: "1px solid var(--warm)",
                        color: "var(--warm)",
                        padding: "4px 10px",
                        borderRadius: 100,
                        fontFamily: "var(--mono)",
                        fontSize: 9,
                        textTransform: "uppercase",
                        letterSpacing: "0.6px",
                        cursor: "pointer",
                      }}
                    >
                      Handla
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>

          <aside>
            {!selected ? (
              <div className="side-card">
                <div className="side-card-eye">Hur du handlar</div>
                <div className="side-card-h">
                  Klicka på en <em>aktie</em>
                </div>
                <div className="side-card-meta">
                  Välj en aktie i listan för att öppna köp/sälj-formen.
                  Tänk pedagogiskt: skriv en motivering till varför du
                  handlar — Maria-AI:n ger feedback på den.
                </div>
              </div>
            ) : (
              <div
                className="side-card"
                style={{
                  background: "rgba(220,76,43,0.06)",
                  borderColor: "rgba(220,76,43,0.25)",
                }}
              >
                <div
                  className="side-card-eye"
                  style={{ color: "var(--accent)" }}
                >
                  ● Trade · {selected.ticker}
                </div>
                <div className="side-card-h">
                  {selected.name}
                </div>
                <div
                  className="side-card-meta"
                  style={{ marginBottom: 12 }}
                >
                  Senast {selected.last.toFixed(2)} {selected.currency}
                  {selected.change_pct != null &&
                    ` · ${selected.change_pct >= 0 ? "+" : ""}${selected.change_pct.toFixed(2)} %`}
                </div>
                <div
                  style={{
                    display: "flex",
                    gap: 6,
                    marginBottom: 8,
                  }}
                >
                  <button
                    type="button"
                    onClick={() => setSide("buy")}
                    style={{
                      flex: 1,
                      padding: "8px 12px",
                      border: `1px solid ${side === "buy" ? "var(--warm)" : "var(--line-strong)"}`,
                      background:
                        side === "buy"
                          ? "rgba(220,76,43,0.15)"
                          : "transparent",
                      color: side === "buy" ? "var(--warm)" : "#fff",
                      fontFamily: "var(--mono)",
                      fontSize: 11,
                      cursor: "pointer",
                      borderRadius: 4,
                    }}
                  >
                    KÖP
                  </button>
                  <button
                    type="button"
                    onClick={() => setSide("sell")}
                    disabled={ownedQty(selected.ticker) === 0}
                    style={{
                      flex: 1,
                      padding: "8px 12px",
                      border: `1px solid ${side === "sell" ? "#a5b4fc" : "var(--line-strong)"}`,
                      background:
                        side === "sell"
                          ? "rgba(99,102,241,0.15)"
                          : "transparent",
                      color: side === "sell" ? "#a5b4fc" : "#fff",
                      fontFamily: "var(--mono)",
                      fontSize: 11,
                      cursor:
                        ownedQty(selected.ticker) === 0
                          ? "not-allowed"
                          : "pointer",
                      borderRadius: 4,
                      opacity:
                        ownedQty(selected.ticker) === 0 ? 0.4 : 1,
                    }}
                  >
                    SÄLJ
                  </button>
                </div>
                <input
                  type="number"
                  placeholder="Antal aktier"
                  value={qty}
                  onChange={(e) => setQty(e.target.value)}
                  style={{
                    background: "rgba(255,255,255,0.04)",
                    border: "1px solid var(--line-strong)",
                    color: "#fff",
                    padding: "8px 12px",
                    borderRadius: 4,
                    fontFamily: "var(--mono)",
                    fontSize: 12,
                    width: "100%",
                    marginBottom: 8,
                  }}
                />
                <textarea
                  placeholder="Motivering — varför handlar du? (Maria-AI ger feedback)"
                  value={rationale}
                  onChange={(e) => setRationale(e.target.value)}
                  style={{
                    background: "rgba(255,255,255,0.04)",
                    border: "1px solid var(--line-strong)",
                    color: "#fff",
                    padding: "8px 12px",
                    borderRadius: 4,
                    fontFamily: "var(--mono)",
                    fontSize: 11,
                    width: "100%",
                    minHeight: 60,
                    marginBottom: 8,
                  }}
                />
                {qty && parseInt(qty, 10) > 0 && (
                  <div
                    style={{
                      fontFamily: "var(--mono)",
                      fontSize: 10,
                      color: "var(--text-mid)",
                      marginBottom: 8,
                      lineHeight: 1.5,
                    }}
                  >
                    Beräknat:{" "}
                    {SEK(parseInt(qty, 10) * selected.last)} kr
                    {parseInt(qty, 10) * selected.last > 400
                      ? ` + ~${SEK(
                          parseInt(qty, 10) * selected.last * 0.0025,
                        )} courtage (0,25 %)`
                      : " + 1 kr min-courtage"}
                  </div>
                )}
                {tradeError && (
                  <div
                    style={{
                      fontFamily: "var(--mono)",
                      fontSize: 10,
                      color: "#fca5a5",
                      marginBottom: 8,
                    }}
                  >
                    {tradeError}
                  </div>
                )}
                <button
                  type="button"
                  className="cta-btn"
                  disabled={submitting}
                  onClick={executeTrade}
                  style={{ width: "100%" }}
                >
                  {submitting
                    ? "Genomför…"
                    : side === "buy"
                    ? `Köp ${qty || 0} st ${selected.ticker}`
                    : `Sälj ${qty || 0} st ${selected.ticker}`}
                </button>
                <button
                  type="button"
                  onClick={() => setSelected(null)}
                  style={{
                    background: "transparent",
                    border: "none",
                    color: "var(--text-mid)",
                    fontFamily: "var(--mono)",
                    fontSize: 10,
                    cursor: "pointer",
                    marginTop: 6,
                    width: "100%",
                  }}
                >
                  Avbryt
                </button>
              </div>
            )}
            <div className="side-card">
              <div className="side-card-eye">Diversifiering</div>
              <div className="side-card-h">
                Sprid på <em>flera</em>
              </div>
              <div className="side-card-meta">
                En aktie kan gå ner 50 % på en dag. Tio aktier i olika
                sektorer ger samma snitt-avkastning men halv risk. Index-
                fonder är billigare än 30 enskilda köp.
              </div>
            </div>
          </aside>
        </div>
      </div>
    </div>
  );
}
