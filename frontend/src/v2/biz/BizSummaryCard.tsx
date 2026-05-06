/**
 * BizSummaryCard · visas i privat-hub om eleven har aktiverat
 * företagsläget OCH skapat ett bolag. Pedagogiskt syfte: påminna
 * eleven att karaktären driver företag PARALLELLT med vanligt jobb,
 * och att företagets resultat påverkar privat-pentagon via faktorer.
 *
 * Renderas BARA om bizApi.privateSummary().has_company = true. Annars
 * visas ingenting (eleven har företagsläget aktiverat men inget bolag).
 */
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { bizApi } from "./api";


const SEK = (n: number) =>
  new Intl.NumberFormat("sv-SE", { maximumFractionDigits: 0 }).format(n);


export function BizSummaryCard() {
  const [data, setData] = useState<
    Awaited<ReturnType<typeof bizApi.privateSummary>> | null
  >(null);

  useEffect(() => {
    bizApi
      .privateSummary()
      .then(setData)
      .catch(() => setData(null));
  }, []);

  // Renderas inte alls om eleven inte har företag (mode kan vara
  // aktiverat men inget bolag skapat än)
  if (!data || !data.has_company) return null;

  const isPositive = data.margin_pct >= 15;
  const isNegative = data.margin_pct < 0 || data.n_invoices_overdue > 0;

  return (
    <Link
      to="/v2/foretag"
      style={{
        display: "block",
        padding: "20px 22px",
        marginTop: 16,
        marginBottom: 16,
        borderRadius: 10,
        textDecoration: "none",
        color: "inherit",
        background:
          "linear-gradient(135deg, rgba(99,102,241,0.10), rgba(15,21,37,0.6))",
        border: "1px solid rgba(99,102,241,0.30)",
        borderLeft: `3px solid ${
          isNegative ? "#fda594" : isPositive ? "#6ee7b7" : "#818cf8"
        }`,
        transition: "all 0.2s ease",
      }}
      onMouseEnter={(e) => {
        e.currentTarget.style.background =
          "linear-gradient(135deg, rgba(99,102,241,0.18), rgba(15,21,37,0.6))";
      }}
      onMouseLeave={(e) => {
        e.currentTarget.style.background =
          "linear-gradient(135deg, rgba(99,102,241,0.10), rgba(15,21,37,0.6))";
      }}
    >
      <div
        style={{
          fontFamily: "JetBrains Mono, monospace",
          fontSize: 9.5,
          fontWeight: 700,
          letterSpacing: 1.4,
          textTransform: "uppercase",
          color: "#c7d2fe",
          marginBottom: 6,
        }}
      >
        ● Du driver också företag
      </div>
      <div
        style={{
          fontFamily: "Source Serif 4, Georgia, serif",
          fontWeight: 700,
          fontSize: 22,
          letterSpacing: -0.5,
          color: "#fff",
          marginBottom: 4,
        }}
      >
        {data.company_name}{" "}
        <em
          style={{
            color: "#c7d2fe",
            fontStyle: "italic",
            fontWeight: 500,
            fontSize: 14,
            marginLeft: 6,
          }}
        >
          · {data.industry_label}
          {data.city_display ? ` · ${data.city_display}` : ""}
        </em>
      </div>
      <p
        style={{
          fontFamily: "Source Serif 4, Georgia, serif",
          fontSize: 14,
          color: "rgba(255,255,255,0.75)",
          margin: "10px 0 12px",
          lineHeight: 1.5,
        }}
      >
        {data.summary_text}
      </p>
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(4, 1fr)",
          gap: 12,
          fontFamily: "JetBrains Mono, monospace",
          fontSize: 10,
          color: "rgba(255,255,255,0.55)",
          letterSpacing: 0.4,
        }}
      >
        <div>
          <div style={{ color: "rgba(255,255,255,0.4)", fontSize: 9 }}>
            OMSÄTTNING 4V
          </div>
          <div
            style={{
              fontFamily: "Source Serif 4, Georgia, serif",
              fontStyle: "italic",
              fontSize: 16,
              color: data.income_4w > 0 ? "#c7d2fe" : "#fda594",
              fontWeight: 700,
              marginTop: 2,
            }}
          >
            {SEK(data.income_4w)} kr
          </div>
        </div>
        <div>
          <div style={{ color: "rgba(255,255,255,0.4)", fontSize: 9 }}>
            VINST
          </div>
          <div
            style={{
              fontFamily: "Source Serif 4, Georgia, serif",
              fontStyle: "italic",
              fontSize: 16,
              color: data.profit_4w >= 0 ? "#6ee7b7" : "#fda594",
              fontWeight: 700,
              marginTop: 2,
            }}
          >
            {data.profit_4w >= 0 ? "+ " : "− "}
            {SEK(Math.abs(data.profit_4w))} kr
          </div>
        </div>
        <div>
          <div style={{ color: "rgba(255,255,255,0.4)", fontSize: 9 }}>
            KASSA
          </div>
          <div
            style={{
              fontFamily: "Source Serif 4, Georgia, serif",
              fontStyle: "italic",
              fontSize: 16,
              color: data.kassa > 5000 ? "#fff" : "#fbbf24",
              fontWeight: 700,
              marginTop: 2,
            }}
          >
            {SEK(data.kassa)} kr
          </div>
        </div>
        <div>
          <div style={{ color: "rgba(255,255,255,0.4)", fontSize: 9 }}>
            FAKTUROR
          </div>
          <div
            style={{
              fontFamily: "Source Serif 4, Georgia, serif",
              fontStyle: "italic",
              fontSize: 16,
              color: data.n_invoices_overdue > 0 ? "#dc4c2b" : "#fff",
              fontWeight: 700,
              marginTop: 2,
            }}
          >
            {data.n_invoices_open} öppna
            {data.n_invoices_overdue > 0 && (
              <span style={{ fontSize: 11, marginLeft: 6 }}>
                ({data.n_invoices_overdue} sena)
              </span>
            )}
          </div>
        </div>
      </div>

      <div
        style={{
          marginTop: 14,
          fontFamily: "JetBrains Mono, monospace",
          fontSize: 9.5,
          color: "#c7d2fe",
          letterSpacing: 1.2,
        }}
      >
        Öppna företaget →
      </div>
    </Link>
  );
}
