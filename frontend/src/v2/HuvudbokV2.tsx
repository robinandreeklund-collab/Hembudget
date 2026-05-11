/**
 * V2 Huvudbok · klassisk bokföring (balansrapport + resultaträkning +
 * avstämning). Återintroducerar V1-`/ledger/` i V2-stil.
 *
 * Datakälla: GET /v2/ledger/?month=YYYY-MM eller ?year=YYYY (mountad
 * via main.py:include_router(ledger.router, prefix='/v2'))
 *
 * Rendering:
 *   - KPI-rad: Inkomster · Utgifter · Netto · Nettoförmögenhet
 *   - Avstämnings-checks (rad per kontroll med ok/warn/fail-status)
 *   - Balansrapport per konto (opening + flöden + closing)
 *   - Resultaträkning per kategori (inkomst, utgift, netto, count)
 *
 * Skiljer sig från BokforingV2 (= klassificeringsverktyg) genom att
 * fokusera på avstämning, balanser och totalbild — inte enskilda
 * transaktioners kategorier.
 */
import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { v2Api, type LedgerData } from "./api";
import { V2Banner } from "./V2Banner";
import "./lan.css";
import "./huvudbok.css";

const SEK = (n: number) =>
  new Intl.NumberFormat("sv-SE", { maximumFractionDigits: 0 }).format(n);

function currentMonth(): string {
  // Fallback om /v2/game-time inte hunnit svara · sätt till spel-anchor
  // (2026-01) istället för real-tid. Annars defaultar perioden till
  // "Maj 2026" (real-tid) trots att eleven är i Jan 2026 i spel-tid —
  // huvudboken visar då 0 kr inkomster/utgifter eftersom ingen data
  // finns i real-månaden. Riktiga värdet hämtas via v2Api.gameTime().
  return "2026-01";
}

function lastNMonths(n: number, base: string): string[] {
  // Bygg N månader BAKÅT från SPEL-månaden, inte real-månad.
  // Default-base är 2026-01 (anchor) tills /v2/game-time har laddats.
  const [yStr, mStr] = base.split("-");
  const baseY = parseInt(yStr, 10) || 2026;
  const baseM = (parseInt(mStr, 10) || 1) - 1;  // 0-indexerat
  const out: string[] = [];
  for (let i = 0; i < n; i++) {
    const dt = new Date(baseY, baseM - i, 1);
    out.push(
      `${dt.getFullYear()}-${String(dt.getMonth() + 1).padStart(2, "0")}`,
    );
  }
  return out;
}

const ACCOUNT_TYPE_LABEL: Record<string, string> = {
  checking: "Lönekonto",
  savings: "Sparkonto",
  isk: "ISK",
  credit_card: "Kreditkort",
  loan: "Lån",
  cash: "Kontant",
};

export function HuvudbokV2() {
  const [period, setPeriod] = useState<string>(currentMonth());
  const [gameYm, setGameYm] = useState<string>(currentMonth());
  const [data, setData] = useState<LedgerData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const navigate = useNavigate();

  // Hämta elevens spel-månad så period-väljaren defaultar dit i stället
  // för till real-tidens månad. Annars listar "Maj 2026" trots att
  // eleven precis skapats och spel-tiden är "Jan 2026".
  useEffect(() => {
    v2Api.gameTime()
      .then((gt) => {
        setGameYm(gt.year_month);
        // Om perioden fortfarande är fallback-default (anchor), byt till
        // elevens faktiska spel-månad. Användaren har inte rört väljaren
        // än så det är säkert att uppdatera.
        setPeriod((p) => (p === currentMonth() ? gt.year_month : p));
      })
      .catch(() => undefined);
  }, []);

  useEffect(() => {
    setLoading(true);
    setError(null);
    v2Api
      .huvudbok(period)
      .then((d) => {
        setData(d);
        setLoading(false);
      })
      .catch((e) => {
        setError(String((e as Error)?.message || e));
        setLoading(false);
      });
  }, [period]);

  const monthOptions = useMemo(() => lastNMonths(12, gameYm), [gameYm]);
  const gameYear = parseInt(gameYm.split("-")[0], 10) || 2026;

  return (
    <div className="v2-lan-root">
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
          ← Tillbaka till pentagonen
        </a>

        <header className="actor-head">
          <span className="pill warm">● Aktör · Huvudboken</span>
          <h1 className="actor-name">
            Huvudboken — <em>balanserar din ekonomi</em>?
          </h1>
          <p className="actor-sub">
            Klassisk dubbelbokföring. Varje kostnad ska kunna spåras till
            ett konto, varje intäkt ska finnas i resultaträkningen, varje
            överföring mellan dina konton ska summera till noll. Här ser
            du om det stämmer.
          </p>
        </header>

        {/* Periodväljare */}
        <div className="huv-periodbar">
          <label className="huv-period-label">
            Period
            <select
              className="huv-period-select"
              value={period}
              onChange={(e) => setPeriod(e.target.value)}
            >
              {monthOptions.map((m) => (
                <option key={m} value={m}>
                  {m}
                </option>
              ))}
              <option value={String(gameYear)}>
                Hela {gameYear}
              </option>
            </select>
          </label>
          <Link to="/v2/bokforing" className="huv-related-link">
            Bokföring (klassning) →
          </Link>
        </div>

        {error && <div className="huv-error">Kunde inte ladda: {error}</div>}
        {loading && <div className="huv-loading">Laddar huvudboken…</div>}

        {!loading && data && (
          <>
            {/* === KPI-rad === */}
            <section className="huv-kpis">
              <KpiCard
                label="Inkomster"
                value={data.totals.income}
                tone="positive"
              />
              <KpiCard
                label="Utgifter"
                value={-data.totals.expenses}
                tone="negative"
              />
              <KpiCard
                label="Netto-resultat"
                value={data.totals.net_result}
                tone={data.totals.net_result >= 0 ? "positive" : "negative"}
                emphasis
              />
              <KpiCard
                label="Nettoförmögenhet"
                value={data.totals.net_worth}
                tone="neutral"
                meta={`tillgångar ${SEK(data.totals.assets)} − skulder ${SEK(Math.abs(data.totals.liabilities))}`}
              />
            </section>

            {/* === Kontroller / avstämning === */}
            <section className="huv-section">
              <h2 className="huv-h2">Avstämning</h2>
              <p className="huv-sub">
                Allt ska balansera. Klicka en rad för att se underliggande
                transaktioner som inte stämmer.
              </p>
              <div className="huv-checks">
                {data.checks.length === 0 ? (
                  <div className="huv-empty">Inga kontroller har körts.</div>
                ) : (
                  data.checks.map((c) => (
                    <div
                      key={c.type}
                      className={`huv-check huv-check-${c.status}`}
                    >
                      <span className="huv-check-status">
                        {c.status === "ok" ? "✓" : c.status === "warn" ? "!" : "✗"}
                      </span>
                      <div className="huv-check-body">
                        <div className="huv-check-label">{c.label}</div>
                        <div className="huv-check-msg">{c.message}</div>
                      </div>
                      {(c.detail_count ?? 0) > 0 && (
                        <span className="huv-check-count">
                          {c.detail_count} rader
                        </span>
                      )}
                    </div>
                  ))
                )}
              </div>
            </section>

            {/* === Balansrapport === */}
            <section className="huv-section">
              <h2 className="huv-h2">Balansrapport · per konto</h2>
              <p className="huv-sub">
                Ingående saldo + flöden i perioden = utgående saldo.
              </p>
              <div className="huv-table-wrap">
                <table className="huv-table">
                  <thead>
                    <tr>
                      <th>Konto</th>
                      <th>Typ</th>
                      <th className="num">Ingående</th>
                      <th className="num">In</th>
                      <th className="num">Ut</th>
                      <th className="num">Trans+</th>
                      <th className="num">Trans−</th>
                      <th className="num">Utgående</th>
                      <th className="num">Rader</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.accounts.map((a) => (
                      <tr key={a.id}>
                        <td className="huv-cell-name">{a.name}</td>
                        <td className="huv-cell-type">
                          {ACCOUNT_TYPE_LABEL[a.type] || a.type}
                        </td>
                        <td className="num">{SEK(a.opening)} kr</td>
                        <td className="num positive">
                          {a.income > 0 ? `+ ${SEK(a.income)}` : "—"}
                        </td>
                        <td className="num negative">
                          {a.expense > 0 ? `− ${SEK(a.expense)}` : "—"}
                        </td>
                        <td className="num">
                          {a.transfer_in > 0
                            ? `+ ${SEK(a.transfer_in)}`
                            : "—"}
                        </td>
                        <td className="num">
                          {a.transfer_out > 0
                            ? `− ${SEK(a.transfer_out)}`
                            : "—"}
                        </td>
                        <td className="num huv-cell-emphasis">
                          {SEK(a.closing)} kr
                        </td>
                        <td className="num huv-cell-dim">{a.tx_count}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>

            {/* === Resultaträkning === */}
            <section className="huv-section">
              <h2 className="huv-h2">Resultaträkning · per kategori</h2>
              <p className="huv-sub">
                Var pengarna kommer ifrån och var de går till.
              </p>
              <div className="huv-table-wrap">
                <table className="huv-table">
                  <thead>
                    <tr>
                      <th>Kategori</th>
                      <th className="num">Inkomst</th>
                      <th className="num">Utgift</th>
                      <th className="num">Netto</th>
                      <th className="num">Rader</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.categories.map((c, i) => (
                      <tr key={c.id ?? `c-${i}`}>
                        <td className="huv-cell-name">{c.name}</td>
                        <td className="num positive">
                          {c.income > 0 ? `+ ${SEK(c.income)}` : "—"}
                        </td>
                        <td className="num negative">
                          {c.expense > 0 ? `− ${SEK(c.expense)}` : "—"}
                        </td>
                        <td
                          className={`num huv-cell-emphasis ${c.net >= 0 ? "positive" : "negative"}`}
                        >
                          {c.net >= 0 ? "+ " : "− "}
                          {SEK(Math.abs(c.net))} kr
                        </td>
                        <td className="num huv-cell-dim">{c.tx_count}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>

            {/* === Lån (om data finns) === */}
            {data.loans && data.loans.length > 0 && (
              <section className="huv-section">
                <h2 className="huv-h2">Lån · saldo-avstämning</h2>
                <div className="huv-table-wrap">
                  <table className="huv-table">
                    <thead>
                      <tr>
                        <th>Lån</th>
                        <th className="num">Förväntat saldo</th>
                        <th className="num">Matchat saldo</th>
                        <th className="num">Avvikelse</th>
                      </tr>
                    </thead>
                    <tbody>
                      {data.loans.map((l, i) => (
                        <tr key={`loan-${i}`}>
                          <td className="huv-cell-name">{l.name}</td>
                          <td className="num">{SEK(l.expected_balance)} kr</td>
                          <td className="num">{SEK(l.matched_balance)} kr</td>
                          <td
                            className={`num huv-cell-emphasis ${Math.abs(l.delta) < 1 ? "positive" : "negative"}`}
                          >
                            {l.delta >= 0 ? "+ " : "− "}
                            {SEK(Math.abs(l.delta))} kr
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </section>
            )}
          </>
        )}
      </div>
    </div>
  );
}

function KpiCard({
  label,
  value,
  tone,
  meta,
  emphasis = false,
}: {
  label: string;
  value: number;
  tone: "positive" | "negative" | "neutral";
  meta?: string;
  emphasis?: boolean;
}) {
  const sign = value > 0 ? "+ " : value < 0 ? "− " : "";
  const cls = `huv-kpi tone-${tone}${emphasis ? " huv-kpi-emphasis" : ""}`;
  return (
    <div className={cls}>
      <div className="huv-kpi-label">{label}</div>
      <div className="huv-kpi-value">
        {sign}
        {SEK(Math.abs(value))} kr
      </div>
      {meta && <div className="huv-kpi-meta">{meta}</div>}
    </div>
  );
}
