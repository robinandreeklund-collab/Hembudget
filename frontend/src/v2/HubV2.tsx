/**
 * V2 Hub · pentagon, karaktärs-kort, recap, kompass.
 * All data hämtas live från /v2/hub-endpointen.
 */
import { useEffect, useState } from "react";
import { CompanyModeWrapper } from "./CompanyMode";
import { Link } from "react-router-dom";
import { v2Api, type HubData, type V2PentAxis } from "./api";
import { V2Banner } from "./V2Banner";
import { useAutoStartIntroGuide } from "./guides/GuideContext";
import { PentagonFlipCard } from "./PentagonFlipCard";
import "./hub.css";

const SEK = (n: number) =>
  new Intl.NumberFormat("sv-SE", { maximumFractionDigits: 0 }).format(n);

export function HubV2() {
  const [hub, setHub] = useState<HubData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [activeAxis, setActiveAxis] = useState<V2PentAxis | null>(null);
  // Bug #14 · brev-räknare på Postlådan-länken
  const [mailUnread, setMailUnread] = useState<number>(0);

  // Auto-starta intro-guide om eleven inte sett den (efter onboarding)
  useAutoStartIntroGuide();

  useEffect(() => {
    v2Api
      .hub()
      .then(setHub)
      .catch((e) => setError(String((e as Error)?.message || e)));
  }, []);

  // Bug #14 · ohanterade brev (poll var 15:e sek för realtid)
  useEffect(() => {
    const fetchMail = () => {
      v2Api
        .postladan("unhandled")
        .then((d) => setMailUnread(d.summary?.total_count || 0))
        .catch(() => undefined);
    };
    fetchMail();
    const t = setInterval(fetchMail, 15000);
    return () => clearInterval(t);
  }, []);

  if (error) {
    return (
      <div className="v2-hub-root">
        <div className="hub-loading">
          <div>
            <div style={{ color: "#fca5a5", marginBottom: 8 }}>
              Kunde inte ladda hub-data
            </div>
            <pre style={{ fontSize: 11 }}>{error}</pre>
          </div>
        </div>
      </div>
    );
  }
  if (!hub) {
    return (
      <div className="v2-hub-root">
        <div className="hub-loading">Laddar hub-data…</div>
      </div>
    );
  }

  const { character, pentagon, month_summary, total_balance, accounts_count } = hub;
  const score = pentagon?.total_score ?? 0;
  const ekonomi = pentagon?.ekonomi ?? 0;
  const karriar = pentagon?.karriar ?? 0;
  const halsa = pentagon?.halsa ?? 0;
  const relation = pentagon?.relation ?? 0;
  const fritid = pentagon?.fritid ?? 0;

  // Skala pentagon-polygon från 0-100 → 0-260 (radius i SVG)
  const scale = (n: number) => Math.max(0, Math.min(260, (n / 100) * 260));
  const points = [
    [0, -scale(ekonomi)],                          // top  · ekonomi
    [scale(relation) * 0.95, -scale(relation) * 0.31],  // right
    [scale(halsa) * 0.59, scale(halsa) * 0.81],         // bottom-right
    [-scale(fritid) * 0.59, scale(fritid) * 0.81],      // bottom-left
    [-scale(karriar) * 0.95, -scale(karriar) * 0.31],   // left
  ]
    .map(([x, y]) => `${x.toFixed(0)},${y.toFixed(0)}`)
    .join(" ");

  const levelClass = `l${hub.v2_level}` as "l1" | "l2" | "l3";
  const profileLabel =
    hub.v2_spend_profile === "sparsam"
      ? "Sparsam"
      : hub.v2_spend_profile === "balanserad"
      ? "Balanserad"
      : "Slösa";

  // Karaktärs-meta
  const metaParts = [
    character.age != null ? `${character.age} år` : null,
    character.profession,
    character.city,
    character.family_status,
  ].filter(Boolean);

  return (
    <div className="v2-hub-root">
      <V2Banner
        status={{
          role: "student",
          is_super_admin: false,
        }}
      />

      <CompanyModeWrapper>
      <div className="hub-shell">
        <header className="hub-head">
          <div>
            <span className="hub-pill">Privatekonomi som händer</span>
            <h1 className="hub-h1">
              {character.first_name || character.display_name.split(" ")[0]},{" "}
              <em>din vardag</em>.
            </h1>
            <p className="hub-lead">
              Du driver din ekonomi i <em>realtid</em>. Pentagonen tippar när
              något händer. Allt här är{" "}
              <em>live från databasen</em> — inga mockar.
            </p>
          </div>

          <article className="hub-char-card">
            <div className="hub-char-eye">
              {pentagon?.year_month || "—"} · Vol. 18
              <span className={`hub-level-badge ${levelClass}`}>
                Nivå {hub.v2_level} · {profileLabel}
              </span>
            </div>
            <div className="hub-char-name">{character.display_name}</div>
            <div className="hub-char-meta">
              {metaParts.length > 0
                ? metaParts.map((m, i) => (
                    <span key={i}>
                      {m}
                      {i < metaParts.length - 1 && (
                        <span className="hub-char-meta-divider">·</span>
                      )}
                    </span>
                  ))
                : "—"}
            </div>

            {(character.gross_salary_monthly ||
              character.net_salary_monthly ||
              character.housing_monthly) && (
              <>
                <div className="hub-char-section">Hennes ekonomi</div>
                <p className="hub-char-prose">
                  {character.net_salary_monthly && (
                    <>
                      Tjänar{" "}
                      <em>{SEK(character.net_salary_monthly)} kr/mån</em>{" "}
                      netto.{" "}
                    </>
                  )}
                  {character.housing_monthly && (
                    <>
                      Hyran är{" "}
                      <strong>
                        {SEK(character.housing_monthly)} kr
                      </strong>
                      .{" "}
                    </>
                  )}
                  {accounts_count > 0 && (
                    <>
                      {accounts_count} konton · totalt saldo{" "}
                      <em>{SEK(total_balance)} kr</em>.
                    </>
                  )}
                </p>
              </>
            )}
          </article>
        </header>

        {/* RECAP-STRIPE · 4 nyckeltal */}
        <div className="hub-recap">
          <div className="hub-recap-cell">
            <div className="hub-recap-eye">Inkomst denna mån</div>
            <div className="hub-recap-num">
              <em className="up">+ {SEK(month_summary.income)}</em> kr
            </div>
            <div className="hub-recap-sub">
              {month_summary.transactions_count} transaktioner totalt
            </div>
          </div>
          <div className="hub-recap-cell">
            <div className="hub-recap-eye">Utgifter denna mån</div>
            <div className="hub-recap-num">
              − {SEK(month_summary.expenses)} kr
            </div>
            <div className="hub-recap-sub">live från transactions</div>
          </div>
          <div className="hub-recap-cell">
            <div className="hub-recap-eye">Sparat denna mån</div>
            <div className="hub-recap-num">
              <em className="warm">
                {month_summary.saved >= 0 ? "+ " : "− "}
                {SEK(Math.abs(month_summary.saved))}
              </em>{" "}
              kr
            </div>
            <div className="hub-recap-sub">in − ut</div>
          </div>
          <div className="hub-recap-cell">
            <div className="hub-recap-eye">Sparkvot</div>
            <div className="hub-recap-num">
              {month_summary.save_rate_pct.toFixed(1)} %
            </div>
            <div className="hub-recap-bar">
              <div
                className="hub-recap-bar-fill"
                style={{
                  width: `${Math.max(0, Math.min(100, month_summary.save_rate_pct))}%`,
                }}
              />
            </div>
            <div className="hub-recap-sub">mål 15 %</div>
          </div>
        </div>

        {/* PENTAGON · live från wellbeing · klick på axel = flip-card */}
        {pentagon ? (
          <PentagonFlipCard
            activeAxis={activeAxis}
            onClose={() => setActiveAxis(null)}
            fetchDetail={(axis) => v2Api.pentagonAxisDetail(axis)}
            front={
              <div
                className="hub-pent-stage"
                data-guide="hub-pentagon"
              >
                <svg
                  className="hub-pent-svg"
                  viewBox="0 0 600 600"
                  aria-label="Wellbeing-pentagon"
                >
                  <g transform="translate(300,300)">
                    <polygon
                      points="0,-260 247,-80 153,210 -153,210 -247,-80"
                      className="hub-p-axis-line"
                    />
                    <polygon
                      points="0,-195 185,-60 115,158 -115,158 -185,-60"
                      className="hub-p-axis-line"
                    />
                    <polygon
                      points="0,-130 124,-40 76,105 -76,105 -124,-40"
                      className="hub-p-axis-line"
                    />
                    <polygon
                      points="0,-65 62,-20 38,53 -38,53 -62,-20"
                      className="hub-p-axis-line"
                    />
                    <line x1="0" y1="0" x2="0" y2="-260" className="hub-p-axis-line" />
                    <line x1="0" y1="0" x2="247" y2="-80" className="hub-p-axis-line" />
                    <line x1="0" y1="0" x2="153" y2="210" className="hub-p-axis-line" />
                    <line x1="0" y1="0" x2="-153" y2="210" className="hub-p-axis-line" />
                    <line x1="0" y1="0" x2="-247" y2="-80" className="hub-p-axis-line" />
                    {/* Live polygon */}
                    <polygon points={points} className="hub-p-now" />
                  </g>
                </svg>

                <button
                  type="button"
                  className="hub-axis-label hub-ax-eko axis-clickable"
                  onClick={() => setActiveAxis("economy")}
                  aria-label="Visa Ekonomi-detaljer"
                >
                  <div className="hub-axis-eye">Axel 01</div>
                  <div className="hub-axis-name">Ekonomi</div>
                  <div className="hub-axis-num">
                    <em>{ekonomi}</em> / 100
                  </div>
                </button>
                <button
                  type="button"
                  className="hub-axis-label hub-ax-rel axis-clickable"
                  onClick={() => setActiveAxis("social")}
                  aria-label="Visa Relation-detaljer"
                >
                  <div className="hub-axis-eye">Axel 02</div>
                  <div className="hub-axis-name">Relation</div>
                  <div className="hub-axis-num">
                    <em>{relation}</em> / 100
                  </div>
                </button>
                <button
                  type="button"
                  className="hub-axis-label hub-ax-har axis-clickable"
                  onClick={() => setActiveAxis("health")}
                  aria-label="Visa Hälsa-detaljer"
                >
                  <div className="hub-axis-eye">Axel 03</div>
                  <div className="hub-axis-name">Hälsa</div>
                  <div className="hub-axis-num">
                    <em>{halsa}</em> / 100
                  </div>
                </button>
                <button
                  type="button"
                  className="hub-axis-label hub-ax-fri axis-clickable"
                  onClick={() => setActiveAxis("leisure")}
                  aria-label="Visa Fritid-detaljer"
                >
                  <div className="hub-axis-eye">Axel 04</div>
                  <div className="hub-axis-name">Fritid</div>
                  <div className="hub-axis-num">
                    <em>{fritid}</em> / 100
                  </div>
                </button>
                <button
                  type="button"
                  className="hub-axis-label hub-ax-kar axis-clickable"
                  onClick={() => setActiveAxis("safety")}
                  aria-label="Visa Karriär-detaljer"
                >
                  <div className="hub-axis-eye">Axel 05</div>
                  <div className="hub-axis-name">Karriär</div>
                  <div className="hub-axis-num">
                    <em>{karriar}</em> / 100
                  </div>
                </button>

                <div className="hub-center">
                  <div className="hub-center-eye">Pentagon</div>
                  <div className="hub-center-num">{score}</div>
                  <div className="hub-center-meta">
                    av 100 · {pentagon.year_month}
                  </div>
                </div>
              </div>
            }
          />
        ) : (
          <div className="hub-peda">
            <div className="hub-peda-eye">Pentagon väntar</div>
            <div className="hub-peda-h">
              Inga wellbeing-data än för {character.display_name}.
            </div>
            <div className="hub-peda-prose">
              Pentagonen byggs upp så fort scope-databasen får sina första
              transaktioner. Lärar-genererad månadsdata triggar wellbeing-
              beräkningen.
            </div>
          </div>
        )}

        {/* === KOMPASSEN · navigation till alla aktörer + verktyg === */}
        <div className="compass" data-guide="hub-compass">
          <div className="compass-eye">Aktörerna · åtta rum + postlådan</div>
          <div className="compass-grid" style={{ marginBottom: 18 }}>
            <Link
              to="/v2/postladan"
              className="compass-node alert"
              data-guide="postladan-link"
              style={{
                background: "rgba(220,76,43,0.08)",
                borderColor: "rgba(220,76,43,0.4)",
                position: "relative",
              }}
            >
              {mailUnread > 0 && (
                <span
                  style={{
                    position: "absolute",
                    top: 8,
                    right: 8,
                    background: "var(--accent, #dc4c2b)",
                    color: "#fff",
                    fontFamily: "JetBrains Mono, monospace",
                    fontSize: 10,
                    fontWeight: 700,
                    padding: "3px 8px",
                    borderRadius: 100,
                    minWidth: 22,
                    textAlign: "center",
                  }}
                  title={`${mailUnread} ohanterade brev`}
                >
                  {mailUnread}
                </span>
              )}
              <div className="compass-node-eye" style={{ color: "var(--warm)" }}>
                Meta
              </div>
              <div className="compass-node-name">Postlådan</div>
              <div className="compass-node-val">
                {mailUnread > 0
                  ? `${mailUnread} ohanterade brev`
                  : "brev som landar"}
              </div>
            </Link>
            <Link to="/v2/banken" className="compass-node">
              <div className="compass-node-eye">Aktör 01</div>
              <div className="compass-node-name">Banken</div>
              <div className="compass-node-val">
                <em>{SEK(total_balance)}</em> kr
              </div>
            </Link>
            <Link to="/v2/arbetsgivaren" className="compass-node">
              <div className="compass-node-eye">Aktör 02</div>
              <div className="compass-node-name">Arbetsgivaren</div>
              <div className="compass-node-val">
                {character.employer || "Lön + samtal"}
              </div>
            </Link>
            <Link to="/v2/skatten" className="compass-node alert">
              <div className="compass-node-eye">Aktör 03</div>
              <div className="compass-node-name">Skatteverket</div>
              <div className="compass-node-val">deklaration</div>
            </Link>
            <Link to="/v2/lan" className="compass-node">
              <div className="compass-node-eye">Aktör 04</div>
              <div className="compass-node-name">Lånegivaren</div>
              <div className="compass-node-val">CSN + lån</div>
            </Link>
            <Link to="/v2/avanza" className="compass-node">
              <div className="compass-node-eye">Aktör 05</div>
              <div className="compass-node-name">Avanza · ISK</div>
              <div className="compass-node-val">fonder + aktier</div>
            </Link>
            <Link to="/v2/forsakringar" className="compass-node">
              <div className="compass-node-eye">Aktör 06</div>
              <div className="compass-node-name">Försäkringar</div>
              <div className="compass-node-val">premie + skador</div>
            </Link>
            <Link to="/v2/forbrukning" className="compass-node">
              <div className="compass-node-eye">Aktör 07</div>
              <div className="compass-node-name">Förbrukning</div>
              <div className="compass-node-val">el · mobil · spotpris</div>
            </Link>
            <Link to="/v2/boendemarknad" className="compass-node">
              <div className="compass-node-eye">Aktör 08</div>
              <div className="compass-node-name">Boendemarknaden</div>
              <div className="compass-node-val">hyra · köp · sälj</div>
            </Link>
            <Link to="/v2/pension" className="compass-node">
              <div className="compass-node-eye">Aktör 09</div>
              <div className="compass-node-name">Pension</div>
              <div className="compass-node-val">3 pelare + ISK</div>
            </Link>
            <Link to="/v2/arbetsformedlingen" className="compass-node">
              <div className="compass-node-eye">Aktör 10</div>
              <div className="compass-node-name">Arbetsförmedlingen</div>
              <div className="compass-node-val">jobbsök · 5-rond med Mats</div>
            </Link>
          </div>

          <div className="compass-eye" style={{ marginTop: 18 }}>
            Verktygen · där du tänker
          </div>
          <div className="compass-grid" data-guide="hub-tools">
            <Link to="/v2/budget" className="compass-node">
              <div className="compass-node-eye">Verktyg 03</div>
              <div className="compass-node-name">Budget</div>
              <div className="compass-node-val">plan vs utfall</div>
            </Link>
            <Link to="/v2/mal" className="compass-node">
              <div className="compass-node-eye">Verktyg 04</div>
              <div className="compass-node-name">Mål</div>
              <div className="compass-node-val">sparmål</div>
            </Link>
            <Link to="/v2/bokforing" className="compass-node">
              <div className="compass-node-eye">Verktyg 02</div>
              <div className="compass-node-name">Bokföring</div>
              <div className="compass-node-val">klassa transaktioner</div>
            </Link>
            <Link to="/v2/simulator" className="compass-node">
              <div className="compass-node-eye">Verktyg 05</div>
              <div className="compass-node-name">Investeringssim</div>
              <div className="compass-node-val">ränta-på-ränta</div>
            </Link>
            <Link to="/v2/lanekalkylator" className="compass-node">
              <div className="compass-node-eye">Verktyg 06</div>
              <div className="compass-node-name">Lånekalkylator</div>
              <div className="compass-node-val">amorteringsplan</div>
            </Link>
            <Link to="/v2/moduler" className="compass-node">
              <div className="compass-node-eye">Skola 09</div>
              <div className="compass-node-name">Mina moduler</div>
              <div className="compass-node-val">lärar-tilldelade</div>
            </Link>
            <Link to="/v2/feedback" className="compass-node">
              <div className="compass-node-eye">Skola</div>
              <div className="compass-node-name">Lärar-feedback</div>
              <div className="compass-node-val">spårbar dialog</div>
            </Link>
            <Link to="/v2/meddelanden" className="compass-node">
              <div className="compass-node-eye">Skola</div>
              <div className="compass-node-name">Meddelanden</div>
              <div className="compass-node-val">chat med lärare</div>
            </Link>
            <Link to="/v2/portfolio" className="compass-node">
              <div className="compass-node-eye">Skola</div>
              <div className="compass-node-name">Portfolio</div>
              <div className="compass-node-val">kompetens-karta</div>
            </Link>
            <Link
              to="/v2/uppdrag"
              className="compass-node"
              style={{ borderColor: "rgba(220,76,43,0.4)" }}
              data-guide="uppdrag-link"
            >
              <div
                className="compass-node-eye"
                style={{ color: "var(--accent)" }}
              >
                Skola
              </div>
              <div className="compass-node-name">Mina uppdrag</div>
              <div className="compass-node-val">
                lärar-tilldelade · deadline
              </div>
            </Link>
          </div>
        </div>

        {/* Echo · global AI-chat (visas bara om AI är aktiverad) */}
      </div>
      </CompanyModeWrapper>
    </div>
  );
}
