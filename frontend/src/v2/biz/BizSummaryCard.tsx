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
import { useNavigate } from "react-router-dom";
import { bizApi } from "./api";


const SEK = (n: number) =>
  new Intl.NumberFormat("sv-SE", { maximumFractionDigits: 0 }).format(n);


type BizActivity = {
  kind: string;
  title: string;
  detail: string;
  when_label: string;
  tone: "positive" | "negative" | "neutral" | "warning";
};


function buildActivities(
  data: Awaited<ReturnType<typeof bizApi.privateSummary>>,
): BizActivity[] {
  // Spegla siffrorna från privateSummary till en notis-feed.
  // privateSummary returnerar redan aggregat (n_open_quotes, recent_*).
  // Här bygger vi pedagogiska rader · t.ex. "3 nya offertförfrågningar
  // väntar på svar". Backend kan utöka senare med riktiga timestamps.
  const out: BizActivity[] = [];
  if (data.n_new_opportunities && data.n_new_opportunities > 0) {
    out.push({
      kind: "new_opportunity",
      title: `${data.n_new_opportunities} nya offertförfrågningar`,
      detail: "Kunder väntar på din offert · skapa offert i Kunder-fliken.",
      when_label: "denna vecka",
      tone: "positive",
    });
  }
  if (data.n_quotes_pending && data.n_quotes_pending > 0) {
    out.push({
      kind: "quotes_pending",
      title: `${data.n_quotes_pending} offerter väntar på besked`,
      detail: "Kunden bestämmer sig de närmaste timmarna.",
      when_label: "pågår",
      tone: "neutral",
    });
  }
  if (data.n_quotes_won_recent && data.n_quotes_won_recent > 0) {
    out.push({
      kind: "quote_won",
      title: `${data.n_quotes_won_recent} vunna offerter`,
      detail: "Leverera klart för att fakturera.",
      when_label: "senaste vecka",
      tone: "positive",
    });
  }
  if (data.n_quotes_lost_recent && data.n_quotes_lost_recent > 0) {
    out.push({
      kind: "quote_lost",
      title: `${data.n_quotes_lost_recent} förlorade offerter`,
      detail: "Klicka in i företaget för att läsa varför.",
      when_label: "senaste vecka",
      tone: "warning",
    });
  }
  if (data.n_invoices_overdue && data.n_invoices_overdue > 0) {
    out.push({
      kind: "invoice_overdue",
      title: `${data.n_invoices_overdue} förfallna fakturor`,
      detail: "Kunder har inte betalat i tid · skicka påminnelse.",
      when_label: "akut",
      tone: "negative",
    });
  }
  return out;
}


export function BizSummaryCard() {
  const [data, setData] = useState<
    Awaited<ReturnType<typeof bizApi.privateSummary>> | null
  >(null);
  const navigate = useNavigate();

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
  const activities = buildActivities(data);

  function openBizHub(e: React.MouseEvent) {
    e.preventDefault();
    // Kortet ligger på privat-hubben (/v2/hub). Att navigera till
    // /v2/foretag funkade inte (ingen route där) · sidan föll till
    // catchall → V2RootRedirect → tillbaka till /v2/hub. Nu kör vi
    // istället mode-flip-animationen genom att sätta body[data-mode]
    // = "business" så CompanyModeWrapper växlar till BizHub-panelen.
    // Pre-monterade panels (commit 097de4b) gör swappen smooth utan
    // route-change.
    const target = document.getElementById("v2-flip-target");
    const reduced = window.matchMedia
      && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (target && !reduced) {
      target.classList.add("flip-out");
    }
    setTimeout(() => {
      try {
        localStorage.setItem("hb_company_mode", "business");
      } catch {
        // localStorage kan vara avstängd · ignorera
      }
      document.body.setAttribute("data-mode", "business");
      window.dispatchEvent(
        new CustomEvent("company-mode-changed", {
          detail: { mode: "business" },
        }),
      );
      if (window.location.pathname !== "/v2/hub") {
        navigate("/v2/hub");
      }
      if (target && !reduced) {
        target.classList.remove("flip-out");
        target.classList.add("flip-in");
        setTimeout(() => target.classList.remove("flip-in"), 550);
      }
    }, reduced ? 0 : 460);
  }

  return (
    <a
      href="#"
      onClick={openBizHub}
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
        cursor: "pointer",
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

      {/* Notis-feed · senaste händelser i företaget. Visas BARA om vi
       * har relevanta aggregat — annars hoppar vi över så kortet inte
       * blir tomt-snackigt för ett nystartat bolag. */}
      {activities.length > 0 && (
        <div
          style={{
            marginTop: 16,
            paddingTop: 14,
            borderTop: "1px dashed rgba(99,102,241,0.25)",
            display: "grid",
            gap: 8,
          }}
        >
          <div
            style={{
              fontFamily: "JetBrains Mono, monospace",
              fontSize: 9,
              fontWeight: 700,
              letterSpacing: 1.4,
              color: "rgba(199,210,254,0.75)",
              marginBottom: 2,
            }}
          >
            ● NYTT FRÅN FÖRETAGET
          </div>
          {activities.slice(0, 4).map((a) => {
            const dot =
              a.tone === "positive" ? "#6ee7b7"
                : a.tone === "negative" ? "#dc4c2b"
                : a.tone === "warning" ? "#fbbf24"
                : "#818cf8";
            return (
              <div
                key={a.kind}
                style={{
                  display: "grid",
                  gridTemplateColumns: "10px 1fr auto",
                  gap: 10,
                  alignItems: "baseline",
                }}
              >
                <span
                  style={{
                    color: dot,
                    fontSize: 14,
                    lineHeight: 1,
                    transform: "translateY(2px)",
                  }}
                >
                  ●
                </span>
                <div>
                  <div
                    style={{
                      fontFamily: "Source Serif 4, Georgia, serif",
                      fontSize: 13.5,
                      fontWeight: 700,
                      color: "#fff",
                    }}
                  >
                    {a.title}
                  </div>
                  <div
                    style={{
                      fontFamily: "Inter, sans-serif",
                      fontSize: 12,
                      color: "rgba(255,255,255,0.65)",
                      lineHeight: 1.4,
                      marginTop: 2,
                    }}
                  >
                    {a.detail}
                  </div>
                </div>
                <span
                  style={{
                    fontFamily: "JetBrains Mono, monospace",
                    fontSize: 9,
                    color: "rgba(255,255,255,0.4)",
                    letterSpacing: 0.8,
                    textTransform: "uppercase",
                    whiteSpace: "nowrap",
                  }}
                >
                  {a.when_label}
                </span>
              </div>
            );
          })}
        </div>
      )}

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
    </a>
  );
}
