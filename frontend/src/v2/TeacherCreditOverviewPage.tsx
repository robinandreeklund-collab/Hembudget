/**
 * Lärar-vy · full insyn i en elevs kreditprofil.
 *
 * Använder /v2/teacher/students/{id}/credit-overview som returnerar:
 * - annual_income / total_debt / debt_ratio
 * - alla aktiva betalningsanmärkningar (med möjlighet att lägga
 *   till nya eller ta bort)
 * - latest_credit_check (UC-score class A-E)
 * - kalp_history (20 senaste KALP-beräkningar eleven gjort)
 * - antal lån-produkter (totalt + tillgängliga) i scope-DB
 *
 * Routas via /v2/teacher/credit/:studentId — länk från V2RosterPage.
 */
import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import {
  v2Api,
  type V2TeacherCreditOverview,
  type V2KALPResponse,
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

const KIND_LABEL: Record<string, string> = {
  "obetald-faktura": "Obetald faktura",
  kronofogden: "Kronofogden",
  betalningsforelaggande: "Betalningsföreläggande",
};

export function TeacherCreditOverviewPage() {
  const { studentId } = useParams<{ studentId: string }>();
  const sid = studentId ? parseInt(studentId, 10) : 0;
  const [data, setData] = useState<V2TeacherCreditOverview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const navigate = useNavigate();

  // Form-state för nya anmärkningar
  const [markCreditor, setMarkCreditor] = useState("");
  const [markAmount, setMarkAmount] = useState("");
  const [markDate, setMarkDate] = useState(
    new Date().toISOString().slice(0, 10),
  );
  const [markKind, setMarkKind] = useState<
    "obetald-faktura" | "kronofogden" | "betalningsforelaggande"
  >("obetald-faktura");
  const [seedingProducts, setSeedingProducts] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  function refresh() {
    return v2Api
      .teacherCreditOverview(sid)
      .then(setData)
      .catch((e) => setError(String((e as Error)?.message || e)));
  }

  useEffect(() => {
    if (sid) refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sid]);

  async function seedDefaults() {
    setSeedingProducts(true);
    try {
      await v2Api.teacherSeedDefaultLoanProducts(sid);
      await refresh();
    } catch (e) {
      setError(String((e as Error)?.message || e));
    } finally {
      setSeedingProducts(false);
    }
  }

  async function addMark() {
    setSubmitError(null);
    const amt = parseFloat(markAmount.replace(/\s/g, "").replace(",", "."));
    if (!markCreditor.trim()) {
      setSubmitError("Ange borgenär");
      return;
    }
    if (isNaN(amt) || amt < 0) {
      setSubmitError("Ange giltigt belopp");
      return;
    }
    setSubmitting(true);
    try {
      await v2Api.teacherCreatePaymentMark(sid, {
        occurred_on: markDate,
        creditor: markCreditor.trim(),
        amount: amt,
        kind: markKind,
      });
      setMarkCreditor("");
      setMarkAmount("");
      await refresh();
    } catch (e) {
      setSubmitError(String((e as Error)?.message || e));
    } finally {
      setSubmitting(false);
    }
  }

  async function deleteMark(markId: number) {
    if (!confirm("Ta bort anmärkningen?")) return;
    try {
      await v2Api.teacherDeletePaymentMark(sid, markId);
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
              Kunde inte ladda kreditprofil
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
        <div className="bank-loading">Laddar kreditprofil…</div>
      </div>
    );
  }

  const check = data.latest_credit_check;
  const ucClass = check?.uc_score_class || "—";
  const severity =
    ucClass === "A"
      ? "good"
      : ucClass === "B" || ucClass === "C"
      ? "warn"
      : "bad";

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
          Tillbaka till klass-hubben
        </a>

        <header className="actor-head">
          <div>
            <span className="pill warm">Lärar-vy · Kreditprofil</span>
            <h1 className="actor-name" style={{ marginTop: 14 }}>
              {data.student_name}s <em>kreditprofil</em>.
            </h1>
            <p className="actor-sub">
              Full insyn i Lånegivaren-aktören. Allt här påverkar elevens
              wellbeing-pentagon i realtid.
            </p>
          </div>
          <div className="actor-meta">
            Inkomst: <strong>{SEK(data.annual_income)} kr/år</strong>
            <br />
            Total skuld: <strong>{SEK(data.total_debt)} kr</strong>
            <br />
            Skuldkvot: <strong>{data.debt_ratio.toFixed(2)}×</strong>
          </div>
        </header>

        {/* SAMMANFATTNINGS-KORT */}
        <div className="acct-grid">
          <div className="acct active">
            <div>
              <div className="acct-eye">UC-score</div>
              <div className="acct-name">{ucClass}-klass</div>
              <div className="acct-num">
                {check
                  ? `Räknad: ${SHORT_DATE(check.computed_at)}`
                  : "Ingen prövning gjord än"}
              </div>
            </div>
            <div>
              <div
                className={`acct-bal`}
                style={{
                  color:
                    severity === "good"
                      ? "#6ee7b7"
                      : severity === "warn"
                      ? "var(--warm)"
                      : "#fda594",
                }}
              >
                {check ? `${check.uc_score_value}/100` : "—"}
              </div>
              <div className="acct-bal-meta">UC-score 0-100</div>
            </div>
          </div>
          <div className="acct">
            <div>
              <div className="acct-eye">Aktiva lån</div>
              <div className="acct-name">{data.active_loans_count} st</div>
              <div className="acct-num">i scope-DB:n</div>
            </div>
            <div>
              <div className="acct-bal">{SEK(data.total_debt)}</div>
              <div className="acct-bal-meta">utestående</div>
            </div>
          </div>
          <div className="acct">
            <div>
              <div className="acct-eye">Anmärkningar</div>
              <div className="acct-name">
                {data.payment_marks.length} aktiva
              </div>
              <div className="acct-num">ej utgångna</div>
            </div>
            <div>
              <div
                className="acct-bal"
                style={{
                  color: data.payment_marks.length > 0 ? "#fda594" : "#6ee7b7",
                }}
              >
                {data.payment_marks.length}
              </div>
              <div className="acct-bal-meta">
                wellbeing-impact
              </div>
            </div>
          </div>
          <div className="acct">
            <div>
              <div className="acct-eye">Låneprodukter</div>
              <div className="acct-name">
                {data.loan_products_count} totalt
              </div>
              <div className="acct-num">
                {data.available_products_count} tillgängliga
              </div>
            </div>
            <div>
              <button
                type="button"
                className="cta-btn"
                disabled={seedingProducts}
                onClick={seedDefaults}
                style={{ marginTop: 0 }}
              >
                {seedingProducts ? "Seedar…" : "Seedа default"}
              </button>
            </div>
          </div>
        </div>

        <div className="act-grid">
          <div>
            {/* ANMÄRKNINGAR · tabell + lägg till */}
            <div className="section-eye">Betalningsanmärkningar</div>
            {data.payment_marks.length === 0 ? (
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
                Inga aktiva anmärkningar. Lägg till nedan för att simulera
                kreditstämplade scenarier.
              </div>
            ) : (
              <div className="biz-table" style={{ marginBottom: 16 }}>
                <div
                  className="biz-table-row head"
                  style={{
                    gridTemplateColumns: "100px 1.4fr 90px 130px 70px",
                  }}
                >
                  <span>Datum</span>
                  <span>Borgenär</span>
                  <span>Belopp</span>
                  <span>Typ</span>
                  <span></span>
                </div>
                {data.payment_marks.map((m) => (
                  <div
                    className="biz-table-row"
                    key={m.id}
                    style={{
                      gridTemplateColumns: "100px 1.4fr 90px 130px 70px",
                    }}
                  >
                    <span
                      style={{
                        fontFamily: "var(--mono)",
                        fontSize: 11,
                        color: "var(--text-mid)",
                      }}
                    >
                      {SHORT_DATE(m.occurred_on)}
                    </span>
                    <div>
                      <div className="biz-factor-name">{m.creditor}</div>
                      <div className="biz-factor-detail">
                        Försvinner {SHORT_DATE(m.expires_at)}
                      </div>
                    </div>
                    <span style={{ fontFamily: "var(--serif)", fontSize: 13 }}>
                      {SEK(m.amount)} kr
                    </span>
                    <span
                      style={{
                        fontFamily: "var(--mono)",
                        fontSize: 10,
                        color: "var(--text-mid)",
                      }}
                    >
                      {KIND_LABEL[m.kind] || m.kind}
                    </span>
                    <button
                      type="button"
                      onClick={() => deleteMark(m.id)}
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

            {/* LÄGG TILL NY ANMÄRKNING */}
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
                ● Lägg till anmärkning
              </div>
              <div
                style={{
                  display: "grid",
                  gridTemplateColumns: "1fr 1fr 130px 100px",
                  gap: 8,
                  marginBottom: 10,
                  alignItems: "end",
                }}
              >
                <input
                  placeholder="Borgenär (t.ex. Telia)"
                  value={markCreditor}
                  onChange={(e) => setMarkCreditor(e.target.value)}
                  style={inputStyle()}
                />
                <input
                  type="number"
                  placeholder="Belopp"
                  value={markAmount}
                  onChange={(e) => setMarkAmount(e.target.value)}
                  style={inputStyle()}
                />
                <select
                  value={markKind}
                  onChange={(e) =>
                    setMarkKind(e.target.value as typeof markKind)
                  }
                  style={inputStyle()}
                >
                  <option value="obetald-faktura">Obetald faktura</option>
                  <option value="kronofogden">Kronofogden</option>
                  <option value="betalningsforelaggande">
                    Betalningsföreläggande
                  </option>
                </select>
                <input
                  type="date"
                  value={markDate}
                  onChange={(e) => setMarkDate(e.target.value)}
                  style={inputStyle()}
                />
              </div>
              {submitError && (
                <div
                  style={{
                    fontFamily: "var(--mono)",
                    fontSize: 11,
                    color: "#fca5a5",
                    marginBottom: 8,
                  }}
                >
                  {submitError}
                </div>
              )}
              <button
                type="button"
                className="cta-btn"
                disabled={submitting}
                onClick={addMark}
                style={{ marginTop: 0 }}
              >
                {submitting ? "Sparar…" : "Lägg till anmärkning"}
              </button>
            </div>

            {/* KALP-HISTORIK */}
            <div className="section-eye" style={{ marginTop: 8 }}>
              KALP-historik · 20 senaste
            </div>
            {data.kalp_history.length === 0 ? (
              <div
                style={{
                  padding: "20px 24px",
                  border: "1px solid var(--line)",
                  borderRadius: 6,
                  fontFamily: "var(--serif)",
                  color: "var(--text-mid)",
                }}
              >
                Eleven har inte räknat någon KALP än.
              </div>
            ) : (
              <div className="biz-table">
                <div
                  className="biz-table-row head"
                  style={{
                    gridTemplateColumns: "120px 130px 100px 110px 90px",
                  }}
                >
                  <span>Tidpunkt</span>
                  <span>Lånebelopp</span>
                  <span>Stress 7 %</span>
                  <span>Kvar/mån</span>
                  <span>Resultat</span>
                </div>
                {data.kalp_history.map((k: V2KALPResponse) => (
                  <div
                    className="biz-table-row"
                    key={k.id}
                    style={{
                      gridTemplateColumns: "120px 130px 100px 110px 90px",
                    }}
                  >
                    <span
                      style={{
                        fontFamily: "var(--mono)",
                        fontSize: 11,
                        color: "var(--text-mid)",
                      }}
                    >
                      {SHORT_DATE(k.computed_at)}
                    </span>
                    <span style={{ fontFamily: "var(--serif)", fontSize: 13 }}>
                      {SEK(k.loan_amount)} kr
                    </span>
                    <span style={{ fontFamily: "var(--mono)", fontSize: 11 }}>
                      {SEK(k.monthly_loan_payment_at_stress)}
                    </span>
                    <span
                      style={{
                        fontFamily: "var(--serif)",
                        fontSize: 13,
                        color: k.passed ? "#6ee7b7" : "#fda594",
                      }}
                    >
                      {SEK(k.monthly_left_after_all)}
                    </span>
                    <span
                      className={`biz-status ${k.passed ? "delta-up" : "delta-down"}`}
                    >
                      {k.passed ? "passerad" : "underkänd"}
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
                <em>{data.payment_marks.length}</em> anmärkningar
              </div>
              <div className="side-card-meta">
                Varje aktiv anmärkning sänker safety-axeln med 5 pkt och
                economy med 3 pkt (max −15 / −10). UC-klass D/E sänker
                safety ytterligare. Synligt i pentagonen.
              </div>
            </div>
            <div className="side-card">
              <div className="side-card-eye">Låneprodukter</div>
              <div className="side-card-h">
                {data.available_products_count} tillgängliga
              </div>
              <div className="side-card-meta">
                Default-katalogen har 5 produkter (CSN, bolån, billån,
                privatlån, sms-lån). Klicka "Seedа default" om listan är
                tom — eleven kan då se möjliga låntyper i sin v2/lan-vy.
              </div>
            </div>
            <div className="side-card warning">
              <div className="side-card-eye">Pedagogiskt syfte</div>
              <div className="side-card-h">
                Konsekvenser <em>känns</em> direkt
              </div>
              <div className="side-card-meta">
                Lägg en anmärkning, gå till elevens v2/hub och se
                pentagonens safety-axel sjunka. Det är skillnaden mellan
                "skuldfälla" som ord och som upplevd verklighet.
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
