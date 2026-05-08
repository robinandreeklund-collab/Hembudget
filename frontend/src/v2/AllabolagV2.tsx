/**
 * Allabolag · klass-skopig scoreboard över alla elev-företag.
 *
 * Designprinciper:
 * - Samma grafiska profil som övriga V2-aktörer · dark gradient,
 *   serif-rubriker, mono-eyebrows, indigo accent
 * - Sortering: vinstmarginal desc, omsättning desc som tiebreak
 * - Top-3 markeras pedagogiskt (1:a guld, 2:a silver, 3:e brons)
 * - Eget företag highlightas alltid
 * - Egen rad har Publish-toggle
 */
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "@/api/client";
import { V2Topbar } from "./V2Topbar";


type AllabolagRow = {
  company_id_in_scope: number;
  company_name: string;
  industry_label: string | null;
  industry_key: string | null;
  city_key: string | null;
  form: string;
  started_on: string | null;
  week_no: number;
  revenue_4w: number;
  profit_4w: number;
  margin_pct: number;
  kassa: number;
  n_employees: number;
  n_invoices_open: number;
  n_invoices_overdue: number;
  reputation: number;
  annual_report_status: string;
  annual_report_year: number | null;
  annual_report_decided_at: string | null;
  uc_score: number;
  uc_rating: string;
  company_level: string;
  is_mine: boolean;
  is_published: boolean;
  owner_display_name: string | null;
  last_synced_at: string;
};


const LEVEL_LABELS: Record<string, string> = {
  startup: "Startup",
  vaxande: "Växande",
  etablerat: "Etablerat",
  marknadsledare: "Marknadsledare",
};

const LEVEL_COLORS: Record<string, string> = {
  startup: "rgba(255,255,255,0.5)",
  vaxande: "#fbbf24",
  etablerat: "#c7d2fe",
  marknadsledare: "#6ee7b7",
};

type AllabolagOut = {
  rows: AllabolagRow[];
  class_total_revenue_4w: number;
  class_total_profit_4w: number;
  n_companies: number;
  n_published: number;
};


const SEK = (n: number) =>
  new Intl.NumberFormat("sv-SE", { maximumFractionDigits: 0 }).format(n);

const MEDAL = (rank: number): string | null => {
  if (rank === 0) return "🥇";
  if (rank === 1) return "🥈";
  if (rank === 2) return "🥉";
  return null;
};


export function AllabolagV2() {
  const [data, setData] = useState<AllabolagOut | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [togglingPublish, setTogglingPublish] = useState(false);

  function refresh() {
    setLoading(true);
    api<AllabolagOut>("/v2/allabolag")
      .then(setData)
      .catch((e) => setError(String((e as Error).message || e)))
      .finally(() => setLoading(false));
  }

  useEffect(() => {
    // Sätt body till privat-mode (Allabolag är publik · ingen specifik
    // affärs-vy)
    const prev = document.body.getAttribute("data-mode");
    document.body.setAttribute("data-mode", "private");
    refresh();
    return () => {
      if (prev) document.body.setAttribute("data-mode", prev);
    };
  }, []);

  async function togglePublish(currentlyPublished: boolean) {
    setTogglingPublish(true);
    try {
      await api("/v2/allabolag/publish", {
        method: "POST",
        body: JSON.stringify({ is_published: !currentlyPublished }),
      });
      refresh();
    } catch (e) {
      alert(`Fel: ${(e as Error).message || e}`);
    } finally {
      setTogglingPublish(false);
    }
  }

  if (loading && !data) {
    return (
      <div className="v2-shell">
        <V2Topbar status={{ role: "student", is_super_admin: false }} />
        <div style={shellStyle}>Laddar Allabolag…</div>
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="v2-shell">
        <V2Topbar status={{ role: "student", is_super_admin: false }} />
        <div style={shellStyle}>
          <div style={errorBoxStyle}>{error || "Kunde inte ladda Allabolag"}</div>
          <Link to="/v2/hub" style={{ color: "#c7d2fe" }}>← Tillbaka</Link>
        </div>
      </div>
    );
  }

  const myRow = data.rows.find((r) => r.is_mine);
  const profitable = data.rows.filter((r) => r.profit_4w > 0).length;

  return (
    <div className="v2-shell">
      <V2Topbar status={{ role: "student", is_super_admin: false }} />
      <div style={shellStyle}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 18 }}>
          <Link to="/v2/hub" style={backLinkStyle}>
            ← Tillbaka till hubben
          </Link>
          <Link to="/v2/leaderboard" style={{
            fontFamily: "JetBrains Mono, monospace", fontSize: 10.5,
            color: "#c7d2fe", letterSpacing: 1.2, textDecoration: "none",
            background: "rgba(99,102,241,0.12)", border: "1px solid rgba(99,102,241,0.35)",
            padding: "6px 12px", borderRadius: 6,
          }}>
            ● 12-KATEGORI-LEADERBOARD →
          </Link>
        </div>

        <header style={{ marginBottom: 32 }}>
          <span style={pillStyle}>● AKTÖR · ALLABOLAG · KLASSEN</span>
          <h1 style={h1Style}>
            {data.n_companies} {data.n_companies === 1 ? "företag" : "företag"}{" "}
            i klassen — <em style={{ color: "#fbbf24", fontStyle: "italic", fontWeight: 600 }}>
              vem går bäst?
            </em>
          </h1>
          <p style={leadStyle}>
            Scoreboard över alla elever som driver bolag. Vinstmarginal avgör
            ordningen — omsättning är tiebreaker.
          </p>
        </header>

        {/* Klass-aggregat */}
        <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 16, marginBottom: 28 }}>
          <StatBox eye="OMSÄTTNING 4V (klass)" value={`${SEK(data.class_total_revenue_4w)} kr`} tone="warm" />
          <StatBox
            eye="VINST 4V (klass)"
            value={`${data.class_total_profit_4w >= 0 ? "+ " : "− "}${SEK(Math.abs(data.class_total_profit_4w))} kr`}
            tone={data.class_total_profit_4w >= 0 ? "good" : "bad"}
          />
          <StatBox eye="LÖNSAMMA BOLAG" value={`${profitable} / ${data.n_companies}`} tone="indigo" />
          <StatBox eye="PUBLICERADE" value={`${data.n_published} / ${data.n_companies}`} tone="muted" />
        </div>

        {/* Mitt-företag-card */}
        {myRow && (
          <div style={myCompanyCardStyle}>
            <div style={{ ...eyebrowMonoStyle, color: "#fbbf24" }}>
              ● DITT FÖRETAG · {myRow.is_published ? "publicerat" : "dolt för klassen"}
            </div>
            <div style={{ display: "flex", alignItems: "baseline", gap: 14, marginTop: 6 }}>
              <h2 style={{ fontFamily: "Source Serif 4, Georgia, serif", fontSize: 22, fontWeight: 700, color: "#fff", margin: 0 }}>
                {myRow.company_name}
              </h2>
              <span style={{ color: "rgba(255,255,255,0.55)", fontFamily: "JetBrains Mono, monospace", fontSize: 11 }}>
                {myRow.industry_label || myRow.industry_key} · {myRow.form === "ab" ? "AB" : "Enskild firma"}
              </span>
              <span style={{ flex: 1 }} />
              <button
                onClick={() => togglePublish(myRow.is_published)}
                disabled={togglingPublish}
                style={togglePublishBtn}
              >
                {myRow.is_published ? "Dölj från klassen" : "Publicera till klassen"}
              </button>
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(5, 1fr)", gap: 14, marginTop: 14 }}>
              <Mini eye="OMSÄTTNING 4V" value={`${SEK(myRow.revenue_4w)} kr`} />
              <Mini eye="VINST 4V" value={`${myRow.profit_4w >= 0 ? "+" : "−"} ${SEK(Math.abs(myRow.profit_4w))} kr`} tone={myRow.profit_4w >= 0 ? "good" : "bad"} />
              <Mini eye="MARGINAL" value={`${myRow.margin_pct.toFixed(1)} %`} />
              <Mini eye="KASSA" value={`${SEK(myRow.kassa)} kr`} />
              <Mini eye="RYKTE" value={`${myRow.reputation} / 100`} />
            </div>
            <Link to="/v2/foretag/bokforing" style={{ color: "#fbbf24", fontFamily: "JetBrains Mono, monospace", fontSize: 10, letterSpacing: 1.2, textDecoration: "none", marginTop: 12, display: "inline-block" }}>
              ÖPPNA FÖRETAGET →
            </Link>
          </div>
        )}

        {/* Scoreboard */}
        <div style={{ marginBottom: 12 }}>
          <span style={sectionEyeStyle}>● SCOREBOARD · sorterat på vinstmarginal</span>
        </div>
        {data.rows.length === 0 ? (
          <div style={emptyStateStyle}>
            Inga företag har skapats än. Aktivera företagsläget och starta ditt
            första bolag — du blir klassens första entreprenör!
          </div>
        ) : (
          <div style={{ display: "grid", gap: 8 }}>
            {data.rows.map((r, idx) => (
              <CompanyRow key={r.company_id_in_scope + ":" + (r.owner_display_name || "")} row={r} rank={idx} />
            ))}
          </div>
        )}

        <div style={footerNoteStyle}>
          Datan uppdateras automatiskt när bolagen tickas (auto-motorn drar
          fram en vecka per timme). Stale-tolerance ~1 timme.
        </div>
      </div>
    </div>
  );
}


function CompanyRow({ row, rank }: { row: AllabolagRow; rank: number }) {
  const medal = MEDAL(rank);
  const positiveProfit = row.profit_4w >= 0;
  const reportTone = (() => {
    switch (row.annual_report_status) {
      case "approved": return { color: "#6ee7b7", label: "Godkänd årsredovisning" };
      case "rejected": return { color: "#fda594", label: "Återsänd · rättning krävs" };
      case "submitted":
      case "reviewing": return { color: "#fbbf24", label: "Bolagsverket granskar" };
      case "draft": return { color: "rgba(255,255,255,0.4)", label: "Utkast" };
      default: return null;
    }
  })();

  return (
    <div
      style={{
        display: "grid",
        gridTemplateColumns: "44px 1.4fr 0.9fr repeat(4, 0.8fr)",
        gap: 14,
        alignItems: "center",
        padding: "14px 16px",
        background: row.is_mine
          ? "linear-gradient(135deg, rgba(251,191,36,0.10), rgba(15,21,37,0.55))"
          : medal
            ? "linear-gradient(135deg, rgba(99,102,241,0.07), rgba(15,21,37,0.55))"
            : "rgba(15,21,37,0.45)",
        border: `1px solid ${row.is_mine ? "rgba(251,191,36,0.35)" : "rgba(255,255,255,0.08)"}`,
        borderRadius: 10,
      }}
    >
      <div style={{ fontFamily: "Source Serif 4, Georgia, serif", fontSize: medal ? 22 : 18, fontWeight: 700, color: medal ? "#fff" : "rgba(255,255,255,0.4)", textAlign: "center" }}>
        {medal || `#${rank + 1}`}
      </div>
      <div>
        <div style={{ fontFamily: "Source Serif 4, Georgia, serif", fontSize: 16, fontWeight: 700, color: "#fff", display: "flex", gap: 8, alignItems: "baseline" }}>
          {row.company_name}
          <span style={{
            fontFamily: "JetBrains Mono, monospace", fontSize: 9, fontWeight: 700,
            letterSpacing: 1.2, padding: "2px 8px", borderRadius: 100,
            background: "rgba(255,255,255,0.05)",
            border: `1px solid ${LEVEL_COLORS[row.company_level]}`,
            color: LEVEL_COLORS[row.company_level],
            textTransform: "uppercase",
          }}>
            {LEVEL_LABELS[row.company_level] || row.company_level}
          </span>
          {row.is_mine && (
            <span style={{ fontFamily: "JetBrains Mono, monospace", fontSize: 9, color: "#fbbf24", letterSpacing: 1.2 }}>
              · DITT
            </span>
          )}
        </div>
        <div style={{ fontFamily: "JetBrains Mono, monospace", fontSize: 10, color: "rgba(255,255,255,0.5)", marginTop: 2, letterSpacing: 0.5 }}>
          {row.industry_label || row.industry_key} · {row.form === "ab" ? "AB" : "EF"}
          {row.owner_display_name && ` · ägare: ${row.owner_display_name}`} · UC {row.uc_rating} ({row.uc_score})
        </div>
        {reportTone && (
          <div style={{ fontFamily: "JetBrains Mono, monospace", fontSize: 9, color: reportTone.color, marginTop: 4, letterSpacing: 0.8 }}>
            ● {reportTone.label}
          </div>
        )}
      </div>
      <div style={cellStyle}>
        <div style={cellEyeStyle}>OMS 4V</div>
        <div style={{ ...cellValStyle, color: row.revenue_4w > 0 ? "#fff" : "rgba(255,255,255,0.45)" }}>
          {SEK(row.revenue_4w)} kr
        </div>
      </div>
      <div style={cellStyle}>
        <div style={cellEyeStyle}>MARGINAL</div>
        <div style={{ ...cellValStyle, color: row.margin_pct >= 15 ? "#6ee7b7" : row.margin_pct >= 0 ? "#fff" : "#fda594" }}>
          {row.margin_pct.toFixed(1)} %
        </div>
      </div>
      <div style={cellStyle}>
        <div style={cellEyeStyle}>VINST</div>
        <div style={{ ...cellValStyle, color: positiveProfit ? "#6ee7b7" : "#fda594" }}>
          {positiveProfit ? "+" : "−"} {SEK(Math.abs(row.profit_4w))} kr
        </div>
      </div>
      <div style={cellStyle}>
        <div style={cellEyeStyle}>RYKTE</div>
        <div style={cellValStyle}>{row.reputation}/100</div>
      </div>
      <div style={cellStyle}>
        <div style={cellEyeStyle}>FAKTUROR</div>
        <div style={{ ...cellValStyle, color: row.n_invoices_overdue > 0 ? "#dc4c2b" : "#fff" }}>
          {row.n_invoices_open}{row.n_invoices_overdue > 0 ? ` · ${row.n_invoices_overdue} sena` : ""}
        </div>
      </div>
    </div>
  );
}


function StatBox({ eye, value, tone }: { eye: string; value: string; tone: "warm" | "good" | "bad" | "indigo" | "muted" }) {
  const colors: Record<string, string> = {
    warm: "#fbbf24",
    good: "#6ee7b7",
    bad: "#fda594",
    indigo: "#c7d2fe",
    muted: "rgba(255,255,255,0.85)",
  };
  return (
    <div style={{ background: "rgba(15,21,37,0.55)", border: "1px solid rgba(255,255,255,0.08)", padding: "14px 16px", borderRadius: 10 }}>
      <div style={eyebrowMonoStyle}>{eye}</div>
      <div style={{ fontFamily: "Source Serif 4, Georgia, serif", fontStyle: "italic", fontWeight: 700, fontSize: 22, color: colors[tone], marginTop: 6 }}>
        {value}
      </div>
    </div>
  );
}


function Mini({ eye, value, tone = "default" }: { eye: string; value: string; tone?: "default" | "good" | "bad" }) {
  const colors: Record<string, string> = {
    default: "#fff",
    good: "#6ee7b7",
    bad: "#fda594",
  };
  return (
    <div>
      <div style={{ fontFamily: "JetBrains Mono, monospace", fontSize: 9, fontWeight: 700, letterSpacing: 1.2, color: "rgba(255,255,255,0.4)" }}>
        {eye}
      </div>
      <div style={{ fontFamily: "Source Serif 4, Georgia, serif", fontStyle: "italic", fontWeight: 700, fontSize: 16, color: colors[tone], marginTop: 4 }}>
        {value}
      </div>
    </div>
  );
}


// === Styles ===
const shellStyle: React.CSSProperties = {
  maxWidth: 1280,
  margin: "0 auto",
  padding: "32px 24px 80px",
};

const backLinkStyle: React.CSSProperties = {
  fontFamily: "JetBrains Mono, monospace",
  fontSize: 10.5,
  color: "rgba(255,255,255,0.55)",
  letterSpacing: 1.2,
  textDecoration: "none",
  display: "inline-block",
  marginBottom: 18,
};

const pillStyle: React.CSSProperties = {
  display: "inline-block",
  padding: "5px 14px",
  borderRadius: 100,
  background: "rgba(99,102,241,0.10)",
  border: "1px solid rgba(99,102,241,0.30)",
  fontFamily: "JetBrains Mono, monospace",
  fontSize: 10,
  fontWeight: 700,
  letterSpacing: 1.6,
  color: "#c7d2fe",
};

const h1Style: React.CSSProperties = {
  fontFamily: "Source Serif 4, Georgia, serif",
  fontWeight: 700,
  fontSize: 38,
  letterSpacing: -0.6,
  color: "#fff",
  margin: "12px 0 8px",
  lineHeight: 1.1,
};

const leadStyle: React.CSSProperties = {
  fontFamily: "Source Serif 4, Georgia, serif",
  fontSize: 17,
  lineHeight: 1.55,
  color: "rgba(255,255,255,0.7)",
  margin: 0,
  maxWidth: 720,
};

const eyebrowMonoStyle: React.CSSProperties = {
  fontFamily: "JetBrains Mono, monospace",
  fontSize: 9.5,
  fontWeight: 700,
  letterSpacing: 1.4,
  color: "rgba(255,255,255,0.55)",
  textTransform: "uppercase",
};

const sectionEyeStyle: React.CSSProperties = {
  fontFamily: "JetBrains Mono, monospace",
  fontSize: 10.5,
  fontWeight: 700,
  letterSpacing: 1.4,
  color: "#c7d2fe",
};

const myCompanyCardStyle: React.CSSProperties = {
  background: "linear-gradient(135deg, rgba(251,191,36,0.08), rgba(15,21,37,0.6))",
  border: "1px solid rgba(251,191,36,0.30)",
  borderLeft: "3px solid #fbbf24",
  borderRadius: 10,
  padding: "18px 20px",
  marginBottom: 24,
};

const togglePublishBtn: React.CSSProperties = {
  background: "rgba(99,102,241,0.18)",
  border: "1px solid rgba(99,102,241,0.45)",
  color: "#c7d2fe",
  padding: "6px 12px",
  borderRadius: 6,
  fontFamily: "JetBrains Mono, monospace",
  fontSize: 9.5,
  fontWeight: 700,
  letterSpacing: 1.2,
  textTransform: "uppercase",
  cursor: "pointer",
};

const cellStyle: React.CSSProperties = {
  display: "flex",
  flexDirection: "column",
  gap: 2,
};

const cellEyeStyle: React.CSSProperties = {
  fontFamily: "JetBrains Mono, monospace",
  fontSize: 8.5,
  fontWeight: 700,
  letterSpacing: 1,
  color: "rgba(255,255,255,0.4)",
};

const cellValStyle: React.CSSProperties = {
  fontFamily: "Source Serif 4, Georgia, serif",
  fontStyle: "italic",
  fontWeight: 700,
  fontSize: 14.5,
  color: "#fff",
};

const emptyStateStyle: React.CSSProperties = {
  padding: "40px 30px",
  textAlign: "center",
  background: "rgba(15,21,37,0.5)",
  border: "1px dashed rgba(255,255,255,0.15)",
  borderRadius: 10,
  color: "rgba(255,255,255,0.7)",
  fontFamily: "Source Serif 4, Georgia, serif",
  fontSize: 15,
};

const errorBoxStyle: React.CSSProperties = {
  padding: 14,
  background: "rgba(220,76,43,0.08)",
  border: "1px solid rgba(220,76,43,0.35)",
  borderRadius: 6,
  color: "#fda594",
  fontFamily: "Source Serif 4, Georgia, serif",
  marginBottom: 16,
};

const footerNoteStyle: React.CSSProperties = {
  marginTop: 30,
  textAlign: "center",
  color: "rgba(255,255,255,0.4)",
  fontFamily: "Source Serif 4, Georgia, serif",
  fontStyle: "italic",
  fontSize: 13,
};
