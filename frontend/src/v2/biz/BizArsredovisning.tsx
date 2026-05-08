/**
 * BizArsredovisning · Årsbokslut + AI Bolagsverket-granskning.
 *
 * Spec: dev/feature-allabolag.md (Fas B)
 *
 * Eleven kan:
 * - Förhandsvisa nuvarande/föregående års bokslut
 * - Lämna in (skicka till AI Bolagsverket)
 * - Se historik (godkända + återsända)
 * - Vid rejected: läsa AI:s feedback + skicka in på nytt
 * - Vid approved: status syns på Allabolag · klassen ser
 */
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "@/api/client";
import { BizActorShell } from "./BizActorShell";


type Snapshot = {
  fiscal_year: number;
  revenue_total: number;
  expense_total: number;
  salary_total: number;
  profit_before_tax: number;
  corporate_tax: number;
  profit_after_tax: number;
  equity_end: number;
  n_invoices_paid: number;
  n_invoices_unpaid: number;
};

type AnnualReport = {
  id: number | null;
  fiscal_year: number;
  status: string;
  snapshot: Snapshot;
  student_note: string | null;
  ai_decision: string | null;
  ai_feedback_md: string | null;
  ai_issues: { category: string; explanation: string }[];
  submitted_at: string | null;
  decided_at: string | null;
};


const SEK = (n: number) =>
  new Intl.NumberFormat("sv-SE", { maximumFractionDigits: 0 }).format(n);


export function BizArsredovisning() {
  const today = new Date();
  // Default = föregående år (måste vara avslutat)
  const defaultYear = today.getFullYear() - 1;

  const [year, setYear] = useState<number>(defaultYear);
  const [preview, setPreview] = useState<Snapshot | null>(null);
  const [history, setHistory] = useState<AnnualReport[]>([]);
  const [studentNote, setStudentNote] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [latestResult, setLatestResult] = useState<AnnualReport | null>(null);

  function refresh() {
    Promise.all([
      api<Snapshot>(`/v2/foretag/annual-report/preview?fiscal_year=${year}`),
      api<AnnualReport[]>("/v2/foretag/annual-report"),
    ])
      .then(([p, h]) => {
        setPreview(p);
        setHistory(h);
      })
      .catch((e) => setError(String((e as Error).message || e)));
  }

  useEffect(() => {
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [year]);

  async function submit() {
    setSubmitting(true);
    setError(null);
    try {
      const result = await api<AnnualReport>(
        "/v2/foretag/annual-report/submit",
        {
          method: "POST",
          body: JSON.stringify({
            fiscal_year: year,
            student_note: studentNote.trim() || undefined,
          }),
        },
      );
      setLatestResult(result);
      setStudentNote("");
      refresh();
    } catch (e) {
      setError(String((e as Error).message || e));
    } finally {
      setSubmitting(false);
    }
  }

  const existing = history.find((h) => h.fiscal_year === year);
  const isApproved = existing?.status === "approved";

  return (
    <BizActorShell
      pillLabel="Aktör · biz · Årsredovisning & Bolagsverket"
      title={
        <>
          Årsbokslut {year} — <em>AI Bolagsverket</em>.
        </>
      }
      subtitle="Lämna in årsredovisning · AI granskar · godkänd dyker upp på Allabolag"
      meta={
        <>
          Bolagsår: <strong>{year}</strong>
          <br />
          Status:{" "}
          <strong>
            {existing
              ? STATUS_LABELS[existing.status] || existing.status
              : "Inte inlämnad"}
          </strong>
        </>
      }
    >
      {error && <div style={errorBoxStyle}>{error}</div>}

      {/* Year-väljare */}
      <div style={{ marginBottom: 18, display: "flex", gap: 12, alignItems: "center" }}>
        <span style={{ fontFamily: "JetBrains Mono, monospace", fontSize: 10, color: "rgba(255,255,255,0.6)", letterSpacing: 1.4 }}>
          BOKSLUTSÅR
        </span>
        <select
          value={year}
          onChange={(e) => setYear(parseInt(e.target.value, 10))}
          style={selectStyle}
        >
          {[defaultYear, defaultYear - 1, defaultYear - 2].map((y) => (
            <option key={y} value={y}>{y}</option>
          ))}
        </select>
        {year >= today.getFullYear() && (
          <span style={{ color: "#fbbf24", fontFamily: "Source Serif 4, Georgia, serif", fontSize: 13, fontStyle: "italic" }}>
            ⚠ Året är inte avslutat — du kan bara lämna in årsbokslut för avslutade år.
          </span>
        )}
      </div>

      {/* Preview-snapshot */}
      {preview && (
        <div style={{ display: "grid", gridTemplateColumns: "2fr 1fr", gap: 18, marginBottom: 24 }}>
          <div style={cardStyle}>
            <div style={sectionEyeStyle}>
              ● RESULTATRÄKNING {preview.fiscal_year}
            </div>
            <table style={{ width: "100%", borderCollapse: "collapse", marginTop: 12 }}>
              <tbody>
                <Row label="Intäkter (omsättning)" value={preview.revenue_total} positive />
                <Row label="Kostnader" value={-preview.expense_total} positive={false} />
                <Row label="Lön" value={-preview.salary_total} positive={false} />
                <Row label="Vinst före skatt" value={preview.profit_before_tax} positive={preview.profit_before_tax >= 0} bold />
                <Row label="Bolagsskatt 20.6 %" value={-preview.corporate_tax} positive={false} />
                <Row label="Vinst efter skatt" value={preview.profit_after_tax} positive={preview.profit_after_tax >= 0} bold totalRow />
              </tbody>
            </table>
            <div style={{ marginTop: 18 }}>
              <div style={{ ...sectionEyeStyle, fontSize: 9.5, color: "rgba(255,255,255,0.5)" }}>
                BALANSRÄKNING (förenklad)
              </div>
              <table style={{ width: "100%", borderCollapse: "collapse", marginTop: 8 }}>
                <tbody>
                  <Row label="Eget kapital, utgående" value={preview.equity_end} positive={preview.equity_end >= 0} bold />
                </tbody>
              </table>
            </div>
          </div>

          <div style={cardStyle}>
            <div style={sectionEyeStyle}>● FAKTUROR {preview.fiscal_year}</div>
            <div style={{ marginTop: 12 }}>
              <Stat eye="Betalda" value={String(preview.n_invoices_paid)} tone="good" />
              <Stat
                eye="Obetalda"
                value={String(preview.n_invoices_unpaid)}
                tone={preview.n_invoices_unpaid > 0 ? "bad" : "default"}
              />
            </div>
          </div>
        </div>
      )}

      {/* AI-feedback om finns (existing rapport eller nytt result) */}
      {(latestResult || existing) && (
        <AIFeedbackPanel report={latestResult || existing!} />
      )}

      {/* Inlämnings-form */}
      {!isApproved && year < today.getFullYear() && (
        <div style={cardStyle}>
          <div style={sectionEyeStyle}>● LÄMNA IN ÅRSREDOVISNING</div>
          <p style={{ color: "rgba(255,255,255,0.75)", fontFamily: "Source Serif 4, Georgia, serif", fontSize: 14, lineHeight: 1.55, margin: "12px 0" }}>
            Klicka för att skicka årsredovisningen till AI Bolagsverket. AI:n granskar
            siffrorna, kontrollerar aritmetiken och godkänner eller återsänder med
            rättningar. Godkänd årsredovisning syns publikt på <Link to="/v2/allabolag" style={{ color: "#fbbf24" }}>Allabolag</Link>.
          </p>
          <textarea
            value={studentNote}
            onChange={(e) => setStudentNote(e.target.value)}
            placeholder="Frivillig kommentar till handläggaren (max 2000 tecken). T.ex. förklara varför kostnader avviker, varför obetalda fakturor finns…"
            style={textareaStyle}
          />
          <div style={{ display: "flex", gap: 12, marginTop: 12 }}>
            <button onClick={submit} disabled={submitting} style={btnPrimary}>
              {submitting ? "Granskar…" : (existing ? "Skicka in på nytt →" : "Skicka in årsbokslutet →")}
            </button>
          </div>
        </div>
      )}

      {/* Historik */}
      {history.length > 0 && (
        <div style={{ marginTop: 24 }}>
          <div style={sectionEyeStyle}>● HISTORIK · alla årsredovisningar</div>
          <div style={{ display: "grid", gap: 8, marginTop: 12 }}>
            {history.map((h) => (
              <div
                key={h.id}
                onClick={() => setYear(h.fiscal_year)}
                style={{
                  padding: "12px 16px",
                  background: h.status === "approved" ? "rgba(110,231,183,0.06)" : h.status === "rejected" ? "rgba(220,76,43,0.05)" : "rgba(15,21,37,0.4)",
                  border: `1px solid ${h.status === "approved" ? "rgba(110,231,183,0.25)" : h.status === "rejected" ? "rgba(220,76,43,0.25)" : "rgba(255,255,255,0.08)"}`,
                  borderRadius: 8,
                  cursor: "pointer",
                  display: "flex",
                  gap: 14,
                  alignItems: "center",
                }}
              >
                <span style={{ fontFamily: "Source Serif 4, Georgia, serif", fontSize: 18, fontWeight: 700, color: "#fff", minWidth: 56 }}>
                  {h.fiscal_year}
                </span>
                <span style={{ ...statusPillStyle, color: h.status === "approved" ? "#6ee7b7" : h.status === "rejected" ? "#fda594" : "#fbbf24" }}>
                  {STATUS_LABELS[h.status] || h.status}
                </span>
                <span style={{ fontFamily: "JetBrains Mono, monospace", fontSize: 11, color: "rgba(255,255,255,0.6)", marginLeft: "auto" }}>
                  Vinst {SEK(h.snapshot.profit_after_tax)} kr · oms {SEK(h.snapshot.revenue_total)} kr
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </BizActorShell>
  );
}


function AIFeedbackPanel({ report }: { report: AnnualReport }) {
  if (!report.ai_decision) return null;
  const isApproved = report.ai_decision === "approved";
  return (
    <div
      style={{
        ...cardStyle,
        borderLeft: `3px solid ${isApproved ? "#6ee7b7" : "#fda594"}`,
        background: isApproved ? "rgba(110,231,183,0.05)" : "rgba(220,76,43,0.05)",
        marginBottom: 24,
      }}
    >
      <div style={sectionEyeStyle}>
        ● AI BOLAGSVERKET · {isApproved ? "GODKÄND" : "ÅTERSÄND FÖR RÄTTNING"}
      </div>
      <h3 style={{ fontFamily: "Source Serif 4, Georgia, serif", fontSize: 18, fontWeight: 700, color: "#fff", margin: "10px 0 6px" }}>
        {isApproved
          ? "Bolagsverket godkänner ditt årsbokslut."
          : "Bolagsverket vill att du rättar några saker."}
      </h3>
      {report.ai_feedback_md && (
        <p style={{ color: "rgba(255,255,255,0.85)", fontFamily: "Source Serif 4, Georgia, serif", fontSize: 14, lineHeight: 1.6, margin: "8px 0", whiteSpace: "pre-wrap" }}>
          {report.ai_feedback_md}
        </p>
      )}
      {!isApproved && report.ai_issues.length > 0 && (
        <div style={{ marginTop: 12 }}>
          <div style={{ fontFamily: "JetBrains Mono, monospace", fontSize: 9.5, color: "#fda594", letterSpacing: 1.2 }}>
            RÄTTNINGAR SOM KRÄVS
          </div>
          <ul style={{ marginTop: 6, paddingLeft: 22, color: "#fff", fontFamily: "Source Serif 4, Georgia, serif", fontSize: 14, lineHeight: 1.6 }}>
            {report.ai_issues.map((iss, i) => (
              <li key={i} style={{ marginBottom: 4 }}>
                <strong style={{ color: "#fda594" }}>{iss.category}:</strong> {iss.explanation}
              </li>
            ))}
          </ul>
        </div>
      )}
      {report.decided_at && (
        <div style={{ marginTop: 10, fontFamily: "JetBrains Mono, monospace", fontSize: 10, color: "rgba(255,255,255,0.45)" }}>
          Beslut: {new Date(report.decided_at).toLocaleString("sv-SE")}
        </div>
      )}
    </div>
  );
}


function Row({
  label, value, positive, bold = false, totalRow = false,
}: {
  label: string;
  value: number;
  positive: boolean;
  bold?: boolean;
  totalRow?: boolean;
}) {
  const fontFamily = bold
    ? "Source Serif 4, Georgia, serif"
    : "Inter, sans-serif";
  const cellPadding = totalRow ? "10px 0" : "6px 0";
  const rowBorder = totalRow ? "1px solid rgba(255,255,255,0.18)" : "1px dashed rgba(255,255,255,0.06)";
  return (
    <tr style={{ borderTop: rowBorder }}>
      <td style={{ padding: cellPadding, color: bold ? "#fff" : "rgba(255,255,255,0.75)", fontFamily, fontSize: bold ? 15 : 14, fontWeight: bold ? 700 : 400 }}>
        {label}
      </td>
      <td style={{
        padding: cellPadding,
        textAlign: "right",
        fontFamily: "Source Serif 4, Georgia, serif",
        fontStyle: "italic",
        fontWeight: bold ? 700 : 600,
        fontSize: bold ? 16 : 14,
        color: positive ? (bold ? "#6ee7b7" : "#fff") : "#fda594",
      }}>
        {value < 0 ? "− " : ""}{SEK(Math.abs(value))} kr
      </td>
    </tr>
  );
}


function Stat({ eye, value, tone = "default" }: { eye: string; value: string; tone?: "default" | "good" | "bad" }) {
  const colors: Record<string, string> = {
    default: "#fff",
    good: "#6ee7b7",
    bad: "#fda594",
  };
  return (
    <div style={{ marginBottom: 10 }}>
      <div style={{ fontFamily: "JetBrains Mono, monospace", fontSize: 9, color: "rgba(255,255,255,0.4)", letterSpacing: 1.2 }}>
        {eye}
      </div>
      <div style={{ fontFamily: "Source Serif 4, Georgia, serif", fontStyle: "italic", fontWeight: 700, fontSize: 22, color: colors[tone], marginTop: 4 }}>
        {value}
      </div>
    </div>
  );
}


const STATUS_LABELS: Record<string, string> = {
  draft: "Utkast",
  submitted: "Inskickad",
  reviewing: "Granskar…",
  approved: "Godkänd ✓",
  rejected: "Återsänd",
};


// === Styles ===
const cardStyle: React.CSSProperties = {
  background: "rgba(15,21,37,0.55)",
  border: "1px solid rgba(255,255,255,0.08)",
  borderRadius: 10,
  padding: 20,
  marginBottom: 18,
};

const sectionEyeStyle: React.CSSProperties = {
  fontFamily: "JetBrains Mono, monospace",
  fontSize: 10.5,
  fontWeight: 700,
  letterSpacing: 1.4,
  color: "#c7d2fe",
  textTransform: "uppercase",
};

const selectStyle: React.CSSProperties = {
  background: "rgba(15,21,37,0.7)",
  border: "1px solid rgba(255,255,255,0.18)",
  color: "#fff",
  padding: "6px 14px",
  borderRadius: 6,
  fontFamily: "JetBrains Mono, monospace",
  fontSize: 12,
};

const textareaStyle: React.CSSProperties = {
  width: "100%",
  minHeight: 80,
  background: "rgba(0,0,0,0.25)",
  border: "1px solid rgba(255,255,255,0.12)",
  borderRadius: 6,
  padding: 12,
  color: "rgba(255,255,255,0.92)",
  fontFamily: "Source Serif 4, Georgia, serif",
  fontSize: 14,
  lineHeight: 1.5,
  resize: "vertical",
};

const btnPrimary: React.CSSProperties = {
  background: "#fbbf24",
  border: "none",
  color: "#422006",
  padding: "10px 22px",
  borderRadius: 6,
  fontFamily: "JetBrains Mono, monospace",
  fontSize: 11,
  fontWeight: 700,
  letterSpacing: 1.2,
  textTransform: "uppercase",
  cursor: "pointer",
};

const statusPillStyle: React.CSSProperties = {
  fontFamily: "JetBrains Mono, monospace",
  fontSize: 10,
  fontWeight: 700,
  letterSpacing: 1.2,
  textTransform: "uppercase",
  padding: "4px 10px",
  background: "rgba(255,255,255,0.04)",
  border: "1px solid rgba(255,255,255,0.12)",
  borderRadius: 100,
};

const errorBoxStyle: React.CSSProperties = {
  marginBottom: 14,
  padding: 12,
  background: "rgba(220,76,43,0.08)",
  border: "1px solid rgba(220,76,43,0.35)",
  borderRadius: 6,
  color: "#fda594",
  fontFamily: "Source Serif 4, Georgia, serif",
};
