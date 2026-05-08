/**
 * Allabolag · företagsprofil-detail.
 *
 * Layout efterliknar allabolag.se:s riktiga företagsvy så eleven ser
 * spelets data i samma format som riktiga bolags publika data.
 *
 * Sektioner:
 *   - Header: namn + org.nr + adress
 *   - Översikt-rad: omsättning · resultat · EBITDA · bolagsform · år · anställda
 *   - Bokslut + stapeldiagram + sidebar
 *   - Nyckeltal-gauges (kassalikviditet · vinstmarginal · soliditet)
 *   - Officiell företagsinformation
 */
import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "@/api/client";
import { V2Topbar } from "./V2Topbar";


type HistoryPoint = {
  label: string;
  revenue: number;
  profit_after_finance: number;
};

type NyckeltalItem = {
  pct: number;
  label: string;
  prev_pct: number | null;
  direction: "up" | "down" | "flat";
};

type DetailOut = {
  company_id: number;
  name: string;
  org_number: string;
  form: string;
  started_on: string | null;
  sni_code: string | null;
  sni_label: string;
  industry_label: string | null;
  industry_key: string | null;
  city_key: string | null;
  city_display: string;
  address: string;
  ledamot: string | null;
  is_mine: boolean;
  is_published: boolean;

  revenue_period: number;
  profit_after_finance: number;
  ebitda: number;
  registreringsar: number;
  n_employees: number;
  share_capital: number | null;

  bokslut_label: string;
  omsattning: number;
  resultat_efter_finansnetto: number;
  arets_resultat: number;
  summa_tillgangar: number;
  eget_kapital: number;

  history: HistoryPoint[];

  kassalikviditet: NyckeltalItem;
  vinstmarginal: NyckeltalItem;
  soliditet: NyckeltalItem;

  verksamhet_text: string;
  vat_registered: boolean;
  f_skatt: boolean;
  arbetsgivaravgift: boolean;
  status_label: string;

  last_synced_at: string;
};


const SEK = (n: number) =>
  new Intl.NumberFormat("sv-SE", { maximumFractionDigits: 0 }).format(n);

const FORM_LABELS: Record<string, string> = {
  ab: "Aktiebolag",
  enskild_firma: "Enskild firma",
  handelsbolag: "Handelsbolag",
};


export function AllabolagDetailV2() {
  const { companyId } = useParams<{ companyId: string }>();
  const [data, setData] = useState<DetailOut | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!companyId) return;
    const prev = document.body.getAttribute("data-mode");
    document.body.setAttribute("data-mode", "private");
    setLoading(true);
    api<DetailOut>(`/v2/allabolag/${companyId}/detail`)
      .then(setData)
      .catch((e) => setError(String((e as Error).message || e)))
      .finally(() => setLoading(false));
    return () => {
      if (prev) document.body.setAttribute("data-mode", prev);
    };
  }, [companyId]);

  if (loading && !data) {
    return (
      <div className="v2-shell">
        <V2Topbar status={{ role: "student", is_super_admin: false }} />
        <div style={shellStyle}>Laddar företagsprofil…</div>
      </div>
    );
  }
  if (error || !data) {
    return (
      <div className="v2-shell">
        <V2Topbar status={{ role: "student", is_super_admin: false }} />
        <div style={shellStyle}>
          <div style={errorBoxStyle}>{error || "Kunde inte ladda företaget"}</div>
          <Link to="/v2/allabolag" style={{ color: "#c7d2fe" }}>← Tillbaka</Link>
        </div>
      </div>
    );
  }

  return (
    <div className="v2-shell">
      <V2Topbar status={{ role: "student", is_super_admin: false }} />
      <div style={shellStyle}>
        <Link to="/v2/allabolag" style={backLinkStyle}>
          ← Tillbaka till Allabolag
        </Link>

        {/* === HEADER === */}
        <header style={{ marginTop: 18, marginBottom: 24 }}>
          <span style={pillStyle}>● FÖRETAGSPROFIL · ALLABOLAG</span>
          <h1 style={h1Style}>
            {data.name}
          </h1>
          <p style={leadStyle}>
            {data.industry_label || data.sni_label} · {FORM_LABELS[data.form] || data.form} ·{" "}
            <em style={{ color: "#fbbf24", fontStyle: "italic" }}>
              {data.city_display}
            </em>
          </p>
          <div style={metaRowStyle}>
            <MetaPill label="ORG.NR" value={data.org_number} />
            <MetaPill label="ADRESS" value={data.address} />
          </div>
          {data.is_mine && (
            <div style={{ marginTop: 12 }}>
              <span style={{
                fontFamily: "JetBrains Mono, monospace", fontSize: 10, fontWeight: 700,
                color: "#fbbf24", letterSpacing: 1.4,
                background: "rgba(251,191,36,0.10)",
                border: "1px solid rgba(251,191,36,0.35)",
                padding: "5px 12px", borderRadius: 100,
              }}>
                ● DITT FÖRETAG
              </span>
            </div>
          )}
        </header>

        {/* === ÖVERSIKT-RAD · 6 nyckeltal === */}
        <div style={{
          display: "grid",
          gridTemplateColumns: "repeat(6, 1fr)",
          gap: 1,
          background: "rgba(255,255,255,0.08)",
          border: "1px solid rgba(255,255,255,0.08)",
          borderRadius: 10,
          overflow: "hidden",
          marginBottom: 22,
        }}>
          <OverviewCell eye={`OMSÄTTNING ${data.bokslut_label.toUpperCase()}`} value={`${SEK(data.revenue_period)} kr`} tone="warm" />
          <OverviewCell eye="RESULTAT EFTER FINANSNETTO" value={`${data.profit_after_finance >= 0 ? "+" : "−"}${SEK(Math.abs(data.profit_after_finance))} kr`} tone={data.profit_after_finance >= 0 ? "good" : "bad"} />
          <OverviewCell eye="EBITDA" value={`${data.ebitda >= 0 ? "+" : "−"}${SEK(Math.abs(data.ebitda))} kr`} tone={data.ebitda >= 0 ? "good" : "bad"} />
          <OverviewCell eye="BOLAGSFORM" value={FORM_LABELS[data.form] || data.form} tone="indigo" />
          <OverviewCell eye="REGISTRERINGSÅR" value={String(data.registreringsar)} tone="indigo" />
          <OverviewCell eye="ANSTÄLLDA" value={String(data.n_employees + 1)} tone="indigo" />
        </div>

        {/* === BOKSLUT (chart + sidebar) === */}
        <SectionTitle text="Bokslut och nyckeltal" sub="Belopp i kronor" />
        <div style={{
          display: "grid",
          gridTemplateColumns: "1.6fr 1fr",
          gap: 18,
          marginBottom: 22,
        }}>
          {/* Stapeldiagram */}
          <div style={cardStyle}>
            <div style={{ ...sectionEyeStyle, marginBottom: 14 }}>● BOKSLUT-HISTORIK · senaste perioderna</div>
            <BarChart history={data.history} />
          </div>

          {/* Sidebar · bokslut */}
          <div style={cardStyle}>
            <div style={{ ...sectionEyeStyle, marginBottom: 14 }}>● BOKSLUT · {data.bokslut_label}</div>
            <BokslutRow label="Omsättning" value={data.omsattning} highlight />
            <BokslutRow label="Resultat efter finansnetto" value={data.resultat_efter_finansnetto} highlight />
            <BokslutRow label="Årets resultat" value={data.arets_resultat} />
            <BokslutRow label="Summa tillgångar" value={data.summa_tillgangar} />
            <BokslutRow label="Eget kapital" value={data.eget_kapital} />
            <div style={{ marginTop: 14, fontFamily: "JetBrains Mono, monospace", fontSize: 9, color: "rgba(255,255,255,0.4)", letterSpacing: 1 }}>
              VALUTAKOD · SEK
            </div>
          </div>
        </div>

        {/* === NYCKELTAL · 3 gauges === */}
        <SectionTitle text="Nyckeltal" />
        <div style={{
          display: "grid",
          gridTemplateColumns: "repeat(3, 1fr)",
          gap: 18,
          marginBottom: 22,
        }}>
          <NyckeltalCard label="Kassalikviditet" item={data.kassalikviditet} suffix="%" />
          <NyckeltalCard label="Vinstmarginal" item={data.vinstmarginal} suffix="%" />
          <NyckeltalCard label="Soliditet" item={data.soliditet} suffix="%" />
        </div>

        {/* === OFFICIELL FÖRETAGSINFORMATION === */}
        <SectionTitle text="Officiell företagsinformation" />
        <div style={cardStyle}>
          <div style={{ marginBottom: 14 }}>
            <div style={{ ...eyebrowMonoStyle, marginBottom: 6 }}>VERKSAMHET & ÄNDAMÅL</div>
            <div style={{ fontFamily: "Source Serif 4, Georgia, serif", fontSize: 14, color: "rgba(255,255,255,0.85)", lineHeight: 1.55 }}>
              {data.verksamhet_text}
            </div>
          </div>
          <div style={{
            display: "grid",
            gridTemplateColumns: "1fr 1fr",
            gap: 18,
            paddingTop: 14,
            borderTop: "1px solid rgba(255,255,255,0.08)",
          }}>
            <div>
              <InfoRow label="Juridiskt namn" value={data.name} />
              <InfoRow label="Organisationsnummer" value={data.org_number} />
              <InfoRow label="Registreringsdatum" value={data.started_on || "—"} />
              <InfoRow label="Bolagsform" value={FORM_LABELS[data.form] || data.form} />
              <InfoRow label="Antal anställda" value={String(data.n_employees + 1)} />
              <InfoRow label="SNI-bransch" value={`${data.sni_code || ""} ${data.sni_label}`.trim()} />
              <InfoRow label="Ledamot" value={data.ledamot || "—"} />
            </div>
            <div>
              <InfoRow label="Adress" value={data.address} />
              <InfoRow label="Kommunsäte" value={data.city_display} />
              <InfoRow
                label="Registrerad för"
                multiline
                value={
                  <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
                    <RegPill on={data.vat_registered} label="Moms" />
                    <RegPill on={data.f_skatt} label="F-skatt" />
                    <RegPill on={data.arbetsgivaravgift} label="Arbetsgivaravgift" />
                  </div>
                }
              />
              {data.share_capital !== null && (
                <InfoRow label="Aktiekapital" value={`${SEK(data.share_capital)} kr`} />
              )}
              <InfoRow label="Status" value={data.status_label} />
            </div>
          </div>
          <div style={{ marginTop: 14, fontFamily: "JetBrains Mono, monospace", fontSize: 9, color: "rgba(255,255,255,0.35)", letterSpacing: 1 }}>
            KÄLLA · EKONOMILABBET (simulerat)
          </div>
        </div>
      </div>
    </div>
  );
}


// === Sub-komponenter ===

function MetaPill({ label, value }: { label: string; value: string }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
      <span style={{
        fontFamily: "JetBrains Mono, monospace", fontSize: 9.5, fontWeight: 700,
        letterSpacing: 1.4, color: "rgba(255,255,255,0.45)",
      }}>
        {label}
      </span>
      <span style={{
        fontFamily: "Source Serif 4, Georgia, serif", fontSize: 14,
        color: "rgba(255,255,255,0.88)",
      }}>
        {value}
      </span>
    </div>
  );
}

function OverviewCell({ eye, value, tone = "default" }: {
  eye: string; value: string; tone?: "default" | "good" | "bad" | "warm" | "indigo";
}) {
  const colors: Record<string, string> = {
    default: "#fff",
    good: "#6ee7b7",
    bad: "#fda594",
    warm: "#fbbf24",
    indigo: "#c7d2fe",
  };
  return (
    <div style={{ background: "rgba(15,21,37,0.55)", padding: "16px 18px" }}>
      <div style={{ ...eyebrowMonoStyle, fontSize: 9 }}>{eye}</div>
      <div style={{
        fontFamily: "Source Serif 4, Georgia, serif",
        fontStyle: "italic",
        fontSize: 22, fontWeight: 700, color: colors[tone], marginTop: 6,
      }}>
        {value}
      </div>
    </div>
  );
}

function SectionTitle({ text, sub }: { text: string; sub?: string }) {
  return (
    <div style={{ marginBottom: 12, marginTop: 8 }}>
      <h2 style={{
        fontFamily: "Source Serif 4, Georgia, serif",
        fontWeight: 700, fontSize: 22, color: "#fff", margin: 0, display: "inline",
      }}>
        {text}
      </h2>
      {sub && (
        <span style={{
          marginLeft: 12, fontFamily: "JetBrains Mono, monospace",
          fontSize: 10, color: "rgba(255,255,255,0.5)", letterSpacing: 1,
          padding: "3px 8px", borderRadius: 100,
          background: "rgba(199,210,254,0.08)",
          border: "1px solid rgba(199,210,254,0.18)",
        }}>
          {sub}
        </span>
      )}
    </div>
  );
}

function BokslutRow({ label, value, highlight = false }: {
  label: string; value: number; highlight?: boolean;
}) {
  return (
    <div style={{
      display: "flex", justifyContent: "space-between",
      alignItems: "baseline",
      padding: "9px 0",
      borderBottom: "1px solid rgba(255,255,255,0.06)",
      ...(highlight ? {
        background: "linear-gradient(90deg, rgba(251,191,36,0.10) 0%, transparent 70%)",
        marginLeft: -10, marginRight: -10, paddingLeft: 10, paddingRight: 10,
        borderRadius: 6, borderBottom: "none",
      } : {}),
    }}>
      <span style={{
        fontFamily: "Source Serif 4, Georgia, serif", fontSize: 13,
        color: highlight ? "#fff" : "rgba(255,255,255,0.7)",
      }}>
        {label}
      </span>
      <span style={{
        fontFamily: "JetBrains Mono, monospace", fontSize: 14, fontWeight: 600,
        color: highlight ? "#fbbf24" : "#fff",
      }}>
        {SEK(value)}
      </span>
    </div>
  );
}

function BarChart({ history }: { history: HistoryPoint[] }) {
  const points = history.length > 0 ? history : [{ label: "—", revenue: 0, profit_after_finance: 0 }];
  const maxAbs = Math.max(
    1,
    ...points.map((p) => Math.abs(p.revenue)),
    ...points.map((p) => Math.abs(p.profit_after_finance)),
  );
  const HEIGHT = 180;
  const ZERO = HEIGHT * 0.72;  // 72% av höjden = noll-linje (negativa drar nedåt)

  return (
    <div>
      <div style={{
        position: "relative", height: HEIGHT,
        display: "grid",
        gridTemplateColumns: `repeat(${points.length}, 1fr)`,
        gap: 12,
      }}>
        {/* Noll-linje */}
        <div style={{
          position: "absolute", top: ZERO, left: 0, right: 0, height: 1,
          background: "rgba(255,255,255,0.15)", zIndex: 1,
        }} />
        {points.map((p, i) => {
          const revH = Math.abs(p.revenue) / maxAbs * (ZERO - 8);
          const profH = Math.abs(p.profit_after_finance) / maxAbs * (HEIGHT - ZERO - 8);
          const profIsNeg = p.profit_after_finance < 0;
          return (
            <div key={i} style={{ position: "relative" }}>
              {/* Omsättning · indigo stapel uppåt (V2-accent) */}
              <div title={`${p.label}: omsättning ${SEK(p.revenue)} kr`} style={{
                position: "absolute",
                left: "10%", width: "35%",
                bottom: HEIGHT - ZERO,
                height: revH,
                background: "linear-gradient(180deg, #c7d2fe 0%, #6366f1 100%)",
                borderRadius: "4px 4px 0 0",
                boxShadow: "0 0 12px rgba(99,102,241,0.25)",
              }} />
              {/* Resultat · guld om positiv, koral om negativ */}
              <div title={`${p.label}: resultat ${SEK(p.profit_after_finance)} kr`} style={{
                position: "absolute",
                left: "55%", width: "35%",
                ...(profIsNeg
                  ? {
                      top: ZERO,
                      height: profH,
                      background: "linear-gradient(180deg, #fda594 0%, #dc4c2b 100%)",
                      borderRadius: "0 0 4px 4px",
                    }
                  : {
                      bottom: HEIGHT - ZERO,
                      height: Math.min(profH, ZERO - 8),
                      background: "linear-gradient(180deg, #fcd34d 0%, #fbbf24 100%)",
                      borderRadius: "4px 4px 0 0",
                      boxShadow: "0 0 10px rgba(251,191,36,0.18)",
                    }
                ),
              }} />
            </div>
          );
        })}
      </div>
      <div style={{
        display: "grid",
        gridTemplateColumns: `repeat(${points.length}, 1fr)`,
        gap: 12, marginTop: 10,
      }}>
        {points.map((p, i) => (
          <div key={i} style={{
            fontFamily: "JetBrains Mono, monospace", fontSize: 10, fontWeight: 700,
            color: "rgba(255,255,255,0.5)", textAlign: "center", letterSpacing: 1,
          }}>
            {p.label}
          </div>
        ))}
      </div>
      <div style={{ display: "flex", gap: 18, marginTop: 14, justifyContent: "center" }}>
        <Legend color="#6366f1" label="Omsättning" />
        <Legend color="#fbbf24" label="Resultat efter finansnetto" />
      </div>
    </div>
  );
}

function Legend({ color, label }: { color: string; label: string }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
      <span style={{ width: 10, height: 10, borderRadius: 100, background: color }} />
      <span style={{ fontFamily: "JetBrains Mono, monospace", fontSize: 10, color: "rgba(255,255,255,0.6)" }}>
        {label}
      </span>
    </div>
  );
}

function NyckeltalCard({ label, item, suffix = "" }: {
  label: string; item: NyckeltalItem; suffix?: string;
}) {
  const tone = item.label === "Mycket bra" ? "#6ee7b7"
    : item.label === "Tillfredsst." ? "#fbbf24"
    : item.label === "Förlust" || item.label === "Otillfredsst." ? "#dc4c2b"
    : "#fda594";
  return (
    <div style={cardStyle}>
      <div style={{ ...eyebrowMonoStyle, marginBottom: 14 }}>{label.toUpperCase()}</div>
      <RingMeter pct={item.pct} tone={tone} suffix={suffix} />
      <div style={{ marginTop: 14, textAlign: "center" }}>
        <div style={{
          fontFamily: "Source Serif 4, Georgia, serif", fontStyle: "italic",
          fontSize: 17, fontWeight: 700, color: tone,
          display: "inline-flex", alignItems: "center", gap: 8,
        }}>
          {item.label}
          {item.direction !== "flat" && (
            <span style={{ fontSize: 14, color: item.direction === "up" ? "#6ee7b7" : "#fda594" }}>
              {item.direction === "up" ? "↗" : "↘"}
            </span>
          )}
        </div>
        {item.prev_pct !== null && (
          <div style={{ fontFamily: "JetBrains Mono, monospace", fontSize: 9, fontWeight: 700, color: "rgba(255,255,255,0.4)", marginTop: 6, letterSpacing: 1.2 }}>
            FÖRRA PERIODEN: {item.prev_pct.toFixed(1)}{suffix}
          </div>
        )}
      </div>
    </div>
  );
}

/**
 * Halvcirkel-meter · indigo grundbåge + tone-färgad fyllning utifrån pct.
 * Använder SVG för rena linjer. pct kapas till 0-200 så meter alltid syns.
 */
function RingMeter({ pct, tone, suffix }: { pct: number; tone: string; suffix: string }) {
  const SIZE = 180;
  const STROKE = 12;
  const R = (SIZE / 2) - STROKE;
  const cy = SIZE / 2;
  // Halvcirkel: pi*R = båglängd. dasharray för bakgrundsbåge.
  const arcLen = Math.PI * R;
  const clamped = Math.min(200, Math.max(0, pct));
  const fillLen = (clamped / 200) * arcLen;

  return (
    <div style={{ position: "relative", width: SIZE, height: SIZE / 2 + 8, margin: "0 auto" }}>
      <svg width={SIZE} height={SIZE / 2 + 8} viewBox={`0 0 ${SIZE} ${SIZE / 2 + 8}`}>
        {/* Bakgrund · indigo med transparens */}
        <path
          d={`M ${STROKE / 2} ${cy} A ${R} ${R} 0 0 1 ${SIZE - STROKE / 2} ${cy}`}
          stroke="rgba(99,102,241,0.18)"
          strokeWidth={STROKE}
          strokeLinecap="round"
          fill="none"
        />
        {/* Fyllning · tone-färgad */}
        <path
          d={`M ${STROKE / 2} ${cy} A ${R} ${R} 0 0 1 ${SIZE - STROKE / 2} ${cy}`}
          stroke={tone}
          strokeWidth={STROKE}
          strokeLinecap="round"
          fill="none"
          strokeDasharray={`${fillLen} ${arcLen}`}
          style={{
            filter: `drop-shadow(0 0 6px ${tone}aa)`,
            transition: "stroke-dasharray 400ms ease",
          }}
        />
      </svg>
      <div style={{
        position: "absolute", left: 0, right: 0, top: SIZE / 2 - 28,
        textAlign: "center",
      }}>
        <div style={{
          fontFamily: "Source Serif 4, Georgia, serif", fontStyle: "italic",
          fontSize: 26, fontWeight: 700, color: "#fff",
        }}>
          {pct >= 999 ? "∞" : pct.toFixed(1)}
        </div>
        <div style={{
          fontFamily: "JetBrains Mono, monospace", fontSize: 9, fontWeight: 700,
          letterSpacing: 1.4, color: "rgba(255,255,255,0.45)",
        }}>
          {suffix.toUpperCase().replace("%", "PROCENT")}
        </div>
      </div>
    </div>
  );
}

function InfoRow({ label, value, multiline = false }: {
  label: string; value: string | React.ReactNode; multiline?: boolean;
}) {
  return (
    <div style={{
      display: multiline ? "block" : "flex",
      justifyContent: "space-between",
      gap: 12,
      padding: "8px 0",
      borderBottom: "1px solid rgba(255,255,255,0.05)",
    }}>
      <span style={{
        fontFamily: "JetBrains Mono, monospace", fontSize: 10,
        color: "rgba(255,255,255,0.5)", letterSpacing: 0.8,
        ...(multiline ? { display: "block", marginBottom: 6 } : {}),
      }}>
        {label}
      </span>
      <span style={{
        fontFamily: "Source Serif 4, Georgia, serif", fontSize: 13,
        color: "#fff", textAlign: multiline ? "left" : "right",
      }}>
        {value}
      </span>
    </div>
  );
}

function RegPill({ on, label }: { on: boolean; label: string }) {
  return (
    <span style={{
      fontFamily: "Source Serif 4, Georgia, serif", fontSize: 13,
      color: on ? "#6ee7b7" : "rgba(255,255,255,0.4)",
      display: "flex", alignItems: "center", gap: 6,
    }}>
      <span>{on ? "✓" : "○"}</span>
      {label}
    </span>
  );
}


// === Styles ===
const shellStyle: React.CSSProperties = {
  maxWidth: 1180,
  margin: "0 auto",
  padding: "32px 24px 80px",
};

const cardStyle: React.CSSProperties = {
  background: "rgba(15,21,37,0.55)",
  border: "1px solid rgba(255,255,255,0.08)",
  borderRadius: 10,
  padding: 18,
};

const backLinkStyle: React.CSSProperties = {
  fontFamily: "JetBrains Mono, monospace",
  fontSize: 10.5,
  fontWeight: 700,
  color: "rgba(255,255,255,0.55)",
  letterSpacing: 1.4,
  textDecoration: "none",
  display: "inline-block",
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
  fontSize: 16,
  lineHeight: 1.55,
  color: "rgba(255,255,255,0.7)",
  margin: 0,
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

const metaRowStyle: React.CSSProperties = {
  display: "flex", flexWrap: "wrap", gap: 24, marginTop: 12,
};

const errorBoxStyle: React.CSSProperties = {
  padding: 16,
  background: "rgba(220,76,43,0.10)",
  border: "1px solid rgba(220,76,43,0.4)",
  borderRadius: 8,
  color: "#fda594",
  marginBottom: 12,
};
