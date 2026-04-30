/**
 * Lärar-vy · full insyn i en elevs deklaration för ett givet år.
 *
 * Använder /v2/teacher/students/{id}/tax-overview som returnerar:
 * - gross_income / prelim_tax / deductions_total / final_tax / diff
 * - alla TaxDeduction (med möjlighet att se source: manual / förslag /
 *   auto-loan-genererat)
 * - alla TaxProposal (status pending/approved/rejected)
 * - submitted: TaxYearReturn om eleven lämnat in
 *
 * Lärar-actions:
 * - "Auto-generera förslag" — POST tax-proposals/auto-generate
 * - "Skapa manuellt förslag" — POST tax-proposals
 * - Ta bort förslag (DELETE)
 *
 * Routas via /teacher/v2/tax/:studentId.
 */
import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import {
  v2Api,
  type V2TeacherTaxOverview,
  type TaxDeductionKind,
} from "./api";
import { V2Banner } from "./V2Banner";
import "./lan.css";

const SEK = (n: number) =>
  new Intl.NumberFormat("sv-SE", { maximumFractionDigits: 0 }).format(n);

const SHORT_DATE = (iso: string | null): string => {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleDateString("sv-SE", {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
};

const KIND_LABEL: Record<TaxDeductionKind, string> = {
  rese: "Reseavdrag",
  "bolane-ranta": "Ränteavdrag bolån",
  "csn-ranta": "Ränteavdrag CSN",
  "dubbel-bosattning": "Dubbel bosättning",
  rot: "ROT-avdrag",
  rut: "RUT-avdrag",
  fackavgift: "Fackavgift",
  ovrig: "Övrigt avdrag",
};

const STATUS_LABEL: Record<string, string> = {
  pending: "Väntar på elev",
  approved: "Godkänt",
  rejected: "Avvisat",
};

export function TeacherTaxOverviewPage() {
  const { studentId } = useParams<{ studentId: string }>();
  const sid = studentId ? parseInt(studentId, 10) : 0;
  const [year, setYear] = useState<number>(new Date().getFullYear());
  const [data, setData] = useState<V2TeacherTaxOverview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const navigate = useNavigate();

  // Form-state · skapa förslag
  const [propKind, setPropKind] = useState<TaxDeductionKind>("rese");
  const [propName, setPropName] = useState("");
  const [propAmount, setPropAmount] = useState("");
  const [propDescription, setPropDescription] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [autoGenerating, setAutoGenerating] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  function refresh(): Promise<void> {
    return v2Api
      .teacherTaxOverview(sid, year)
      .then((d) => setData(d))
      .catch((e) => setError(String((e as Error)?.message || e)));
  }

  useEffect(() => {
    if (sid) refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sid, year]);

  async function autoGenerate() {
    setAutoGenerating(true);
    setActionError(null);
    try {
      await v2Api.teacherAutoGenerateTaxProposals(sid, year);
      await refresh();
    } catch (e) {
      setActionError(String((e as Error)?.message || e));
    } finally {
      setAutoGenerating(false);
    }
  }

  async function createProposal() {
    setActionError(null);
    const amt = parseFloat(propAmount.replace(/\s/g, "").replace(",", "."));
    if (!propName.trim()) {
      setActionError("Ange namn");
      return;
    }
    if (isNaN(amt) || amt < 0) {
      setActionError("Ange giltigt belopp");
      return;
    }
    setSubmitting(true);
    try {
      await v2Api.teacherCreateTaxProposal(sid, {
        year,
        kind: propKind,
        name: propName.trim(),
        description: propDescription || undefined,
        suggested_amount: amt,
      });
      setPropName("");
      setPropAmount("");
      setPropDescription("");
      await refresh();
    } catch (e) {
      setActionError(String((e as Error)?.message || e));
    } finally {
      setSubmitting(false);
    }
  }

  async function deleteProposal(propId: number) {
    if (!confirm("Ta bort förslaget?")) return;
    try {
      await v2Api.teacherDeleteTaxProposal(sid, propId);
      await refresh();
    } catch (e) {
      setError(String((e as Error)?.message || e));
    }
  }

  if (error) {
    return (
      <div className="v2-lan-root">
        <V2Banner status={{ role: "teacher", is_super_admin: false }} />
        <div className="bank-loading">
          <div>
            <div style={{ color: "#fca5a5", marginBottom: 8 }}>
              Kunde inte ladda deklarations-data
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
        <div className="bank-loading">Laddar…</div>
      </div>
    );
  }

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
            <span className="pill warm">Lärar-vy · Deklaration</span>
            <h1 className="actor-name" style={{ marginTop: 14 }}>
              {data.student_name}s <em>deklaration {data.year}</em>.
            </h1>
            <p className="actor-sub">
              Full insyn i Skatteverket-aktören. Allt påverkar elevens
              wellbeing-pentagon i realtid.
            </p>
          </div>
          <div className="actor-meta">
            <label
              style={{
                fontFamily: "var(--mono)",
                fontSize: 10,
                letterSpacing: "1.4px",
                textTransform: "uppercase",
                color: "var(--text-mid)",
                display: "block",
                marginBottom: 6,
              }}
            >
              Skatteår
            </label>
            <select
              value={year}
              onChange={(e) => setYear(parseInt(e.target.value, 10))}
              style={{
                background: "rgba(255, 255, 255, 0.04)",
                border: "1px solid var(--line-strong)",
                color: "#fff",
                padding: "6px 12px",
                borderRadius: 4,
                fontFamily: "var(--mono)",
                fontSize: 13,
                width: 120,
              }}
            >
              {[year - 1, year, year + 1].map((y) => (
                <option key={y} value={y}>
                  {y}
                </option>
              ))}
            </select>
          </div>
        </header>

        {/* SAMMANFATTNING */}
        <div className="acct-grid">
          <div className="acct active">
            <div>
              <div className="acct-eye">Bruttoinkomst</div>
              <div className="acct-name">{SEK(data.gross_income)} kr</div>
              <div className="acct-num">årslön projicerad</div>
            </div>
            <div>
              <div className="acct-bal">{SEK(data.prelim_tax_paid)}</div>
              <div className="acct-bal-meta">förskott betalt</div>
            </div>
          </div>
          <div className="acct">
            <div>
              <div className="acct-eye">Avdrag</div>
              <div className="acct-name">
                {data.deductions.length} st
              </div>
              <div className="acct-num">
                bruttobelopp {SEK(data.deductions_total)} kr
              </div>
            </div>
            <div>
              <div className="acct-bal">
                −{SEK(Math.round(data.deductions_total * 0.30))}
              </div>
              <div className="acct-bal-meta">skatteeffekt 30 %</div>
            </div>
          </div>
          <div className="acct">
            <div>
              <div className="acct-eye">Slutlig skatt</div>
              <div className="acct-name">{SEK(data.final_tax)} kr</div>
              <div className="acct-num">efter avdrag + ISK-schablon</div>
            </div>
            <div>
              <div
                className="acct-bal"
                style={{ color: data.diff >= 0 ? "#6ee7b7" : "#fda594" }}
              >
                {data.diff >= 0 ? "+" : "−"} {SEK(Math.abs(data.diff))}
              </div>
              <div className="acct-bal-meta">
                {data.diff >= 0 ? "återbäring" : "kvarskatt"}
              </div>
            </div>
          </div>
          <div className="acct">
            <div>
              <div className="acct-eye">Status</div>
              <div className="acct-name">
                {data.submitted ? "Inlämnad" : "Öppen"}
              </div>
              <div className="acct-num">
                {data.submitted
                  ? `Inlämnad ${SHORT_DATE(data.submitted.submitted_at)}`
                  : "Eleven kan fortfarande ändra"}
              </div>
            </div>
            <div>
              <button
                type="button"
                className="cta-btn"
                disabled={autoGenerating}
                onClick={autoGenerate}
                style={{ marginTop: 0 }}
              >
                {autoGenerating ? "Auto-genererar…" : "Auto-generera"}
              </button>
            </div>
          </div>
        </div>

        <div className="act-grid">
          <div>
            {/* FÖRSLAG */}
            <div className="section-eye">Skatteverkets förslag</div>
            {data.proposals.length === 0 ? (
              <div
                style={{
                  padding: "20px 24px",
                  border: "1px solid var(--line)",
                  borderRadius: 6,
                  fontFamily: "var(--serif)",
                  color: "var(--text-mid)",
                  marginBottom: 16,
                }}
              >
                Inga förslag för {year}. Klicka "Auto-generera" för att
                skapa ränteavdragsförslag baserat på elevens lån, eller
                lägg till manuellt nedan.
              </div>
            ) : (
              <div className="biz-table" style={{ marginBottom: 16 }}>
                <div
                  className="biz-table-row head"
                  style={{
                    gridTemplateColumns: "120px 1.4fr 90px 130px 70px",
                  }}
                >
                  <span>Typ</span>
                  <span>Förslag</span>
                  <span>Belopp</span>
                  <span>Status</span>
                  <span></span>
                </div>
                {data.proposals.map((p) => (
                  <div
                    className="biz-table-row"
                    key={p.id}
                    style={{
                      gridTemplateColumns: "120px 1.4fr 90px 130px 70px",
                    }}
                  >
                    <span
                      style={{
                        fontFamily: "var(--mono)",
                        fontSize: 10,
                        color: "var(--text-mid)",
                      }}
                    >
                      {KIND_LABEL[p.kind as TaxDeductionKind] || p.kind}
                    </span>
                    <div>
                      <div className="biz-factor-name">{p.name}</div>
                      <div className="biz-factor-detail">
                        {p.description || (p.source.startsWith("auto-")
                          ? "auto-genererat från lån"
                          : "manuellt skapat")}
                      </div>
                    </div>
                    <span style={{ fontFamily: "var(--serif)", fontSize: 13 }}>
                      {SEK(p.suggested_amount)} kr
                    </span>
                    <span
                      className={`biz-status ${
                        p.status === "approved"
                          ? "delta-up"
                          : p.status === "rejected"
                          ? "delta-down"
                          : "open"
                      }`}
                    >
                      {STATUS_LABEL[p.status]}
                    </span>
                    <button
                      type="button"
                      onClick={() => deleteProposal(p.id)}
                      style={{
                        background: "transparent",
                        border: "1px solid var(--line-strong)",
                        color: "var(--text-mid)",
                        padding: "4px 10px",
                        borderRadius: 100,
                        fontFamily: "var(--mono)",
                        fontSize: 9.5,
                        textTransform: "uppercase",
                        letterSpacing: "0.6px",
                        cursor: "pointer",
                      }}
                    >
                      Ta bort
                    </button>
                  </div>
                ))}
              </div>
            )}

            {/* SKAPA FÖRSLAG */}
            <div
              style={{
                background: "rgba(15, 21, 37, 0.7)",
                border: "1px solid var(--line)",
                borderRadius: 6,
                padding: "18px 22px",
                marginBottom: 22,
              }}
            >
              <div
                style={{
                  fontFamily: "var(--mono)",
                  fontSize: 10,
                  fontWeight: 700,
                  letterSpacing: "1.4px",
                  textTransform: "uppercase",
                  color: "var(--warm)",
                  marginBottom: 12,
                }}
              >
                ● Skapa manuellt förslag
              </div>
              <div
                style={{
                  display: "grid",
                  gridTemplateColumns: "1fr 1fr 110px",
                  gap: 8,
                  marginBottom: 8,
                  alignItems: "end",
                }}
              >
                <select
                  value={propKind}
                  onChange={(e) =>
                    setPropKind(e.target.value as TaxDeductionKind)
                  }
                  style={inputStyle()}
                >
                  {(Object.keys(KIND_LABEL) as TaxDeductionKind[]).map(
                    (k) => (
                      <option key={k} value={k}>
                        {KIND_LABEL[k]}
                      </option>
                    ),
                  )}
                </select>
                <input
                  placeholder="Namn (t.ex. Reseavdrag bil)"
                  value={propName}
                  onChange={(e) => setPropName(e.target.value)}
                  style={inputStyle()}
                />
                <input
                  type="number"
                  placeholder="Belopp"
                  value={propAmount}
                  onChange={(e) => setPropAmount(e.target.value)}
                  style={inputStyle()}
                />
              </div>
              <input
                placeholder="Beskrivning (valfritt)"
                value={propDescription}
                onChange={(e) => setPropDescription(e.target.value)}
                style={{ ...inputStyle(), marginBottom: 8 }}
              />
              {actionError && (
                <div
                  style={{
                    fontFamily: "var(--mono)",
                    fontSize: 11,
                    color: "#fca5a5",
                    marginBottom: 8,
                  }}
                >
                  {actionError}
                </div>
              )}
              <button
                type="button"
                className="cta-btn"
                disabled={submitting}
                onClick={createProposal}
              >
                {submitting ? "Skapar…" : "Skapa förslag"}
              </button>
            </div>

            {/* AVDRAG · godkända/manuella */}
            <div className="section-eye">Aktiva avdrag · {data.deductions.length} st</div>
            {data.deductions.length === 0 ? (
              <div
                style={{
                  padding: "20px 24px",
                  border: "1px solid var(--line)",
                  borderRadius: 6,
                  fontFamily: "var(--serif)",
                  color: "var(--text-mid)",
                  marginBottom: 16,
                }}
              >
                Inga avdrag registrerade. Eleven godkänner förslag eller
                lägger till egna i v2/skatten.
              </div>
            ) : (
              <div className="biz-table">
                <div
                  className="biz-table-row head"
                  style={{
                    gridTemplateColumns: "140px 1.6fr 100px 110px",
                  }}
                >
                  <span>Typ</span>
                  <span>Namn</span>
                  <span>Belopp</span>
                  <span>Källa</span>
                </div>
                {data.deductions.map((d) => (
                  <div
                    className="biz-table-row"
                    key={d.id}
                    style={{
                      gridTemplateColumns: "140px 1.6fr 100px 110px",
                    }}
                  >
                    <span
                      style={{
                        fontFamily: "var(--mono)",
                        fontSize: 10,
                        color: "var(--text-mid)",
                      }}
                    >
                      {KIND_LABEL[d.kind as TaxDeductionKind] || d.kind}
                    </span>
                    <div>
                      <div className="biz-factor-name">{d.name}</div>
                      <div className="biz-factor-detail">
                        {d.description ||
                          `Skatteeffekt ${SEK(Math.round(d.amount * 0.30))} kr`}
                      </div>
                    </div>
                    <span style={{ fontFamily: "var(--serif)", fontSize: 13 }}>
                      {SEK(d.amount)} kr
                    </span>
                    <span
                      style={{
                        fontFamily: "var(--mono)",
                        fontSize: 10,
                        color: "var(--text-mid)",
                      }}
                    >
                      {d.source.startsWith("from-proposal:")
                        ? "Förslag godkänt"
                        : d.source === "manual"
                        ? "Eleven själv"
                        : d.source}
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
                {data.submitted ? "Inlämnad" : "Öppen"}
              </div>
              <div className="side-card-meta">
                Inlämnad fjolårsdeklaration ger +3 economy. Stor återbäring
                ger +safety, stor kvarskatt sänker economy. Synligt i
                pentagonen.
              </div>
            </div>
            <div className="side-card">
              <div className="side-card-eye">Auto-generering</div>
              <div className="side-card-h">
                {data.proposals.filter((p) => p.source.startsWith("auto-"))
                  .length}{" "}
                förslag från lån
              </div>
              <div className="side-card-meta">
                Klicka "Auto-generera" så letar systemet ränte-avdrag på
                aktiva CSN-/bolån i scope-DB:n. Idempotent — befintliga
                förslag återskapas inte.
              </div>
            </div>
            <div className="side-card warning">
              <div className="side-card-eye">Pedagogiskt syfte</div>
              <div className="side-card-h">
                Skatten <em>rör sig</em>
              </div>
              <div className="side-card-meta">
                Skapa ett förslag, gå till elevens v2/skatten. Eleven ser
                "+ N kr återbäring", godkänner och slutskatten räknas om.
                "Lämna in" → wellbeing-pentagon reagerar.
              </div>
            </div>
          </aside>
        </div>
      </div>
    </div>
  );
}

function inputStyle(): React.CSSProperties {
  return {
    background: "rgba(255, 255, 255, 0.04)",
    border: "1px solid var(--line-strong)",
    color: "#fff",
    padding: "8px 12px",
    borderRadius: 4,
    fontFamily: "var(--mono)",
    fontSize: 12.5,
    width: "100%",
  };
}
