/**
 * Lärar-vy · full insyn i en elevs arbetsgivar-aktör.
 *
 * Använder /v2/teacher/students/{id}/employer-overview som returnerar:
 * - profession + employer + agreement
 * - pension_pct + market_low/high (från MarketSalaryRange)
 * - benefits-lista (från AgreementBenefit)
 * - satisfaction (score + trend + delta_4w)
 * - salary_negotiations (10 senaste)
 * - questions counts (besvarade + väntande)
 *
 * Lärare kan också:
 * - Seedа default-katalogen (SCB-löner + kollektivavtals-förmåner)
 * - Justera marknadsspann för elevens yrke + ort
 *
 * Routas via /teacher/v2/employer/:studentId.
 */
import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import {
  v2Api,
  type V2TeacherEmployerOverview,
  type V2MarketSalaryRangeOut,
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

const NEG_STATUS_LABEL: Record<string, string> = {
  active: "Aktivt",
  completed: "Klart",
  abandoned: "Avbrutet",
};

export function TeacherEmployerOverviewPage() {
  const { studentId } = useParams<{ studentId: string }>();
  const sid = studentId ? parseInt(studentId, 10) : 0;
  const [data, setData] = useState<V2TeacherEmployerOverview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [seedingBenefits, setSeedingBenefits] = useState(false);
  const [seedingRanges, setSeedingRanges] = useState(false);
  const [seedMessage, setSeedMessage] = useState<string | null>(null);

  // Marknadsspann-form
  const [ranges, setRanges] = useState<V2MarketSalaryRangeOut[]>([]);
  const [rangeCity, setRangeCity] = useState("");
  const [rangeYear, setRangeYear] = useState(new Date().getFullYear());
  const [rangeLow, setRangeLow] = useState("");
  const [rangeHigh, setRangeHigh] = useState("");
  const [rangeError, setRangeError] = useState<string | null>(null);
  const [rangeSubmitting, setRangeSubmitting] = useState(false);

  const navigate = useNavigate();

  function refresh(): Promise<void> {
    return v2Api
      .teacherEmployerOverview(sid)
      .then((d) => {
        setData(d);
        // Ladda marknadsspann för elevens yrke
        return v2Api.teacherListMarketRanges(d.profession);
      })
      .then((rs) => setRanges(rs))
      .catch((e) => setError(String((e as Error)?.message || e)));
  }

  useEffect(() => {
    if (sid) refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sid]);

  async function seedBenefits() {
    setSeedingBenefits(true);
    setSeedMessage(null);
    try {
      const r = await v2Api.teacherSeedDefaultAgreementBenefits();
      setSeedMessage(`+${r.created} förmåner seedade`);
      await refresh();
    } catch (e) {
      setError(String((e as Error)?.message || e));
    } finally {
      setSeedingBenefits(false);
    }
  }

  async function seedRanges() {
    setSeedingRanges(true);
    setSeedMessage(null);
    try {
      const r = await v2Api.teacherSeedDefaultMarketRanges();
      setSeedMessage(`+${r.created} marknadsspann seedade (SCB 2026)`);
      await refresh();
    } catch (e) {
      setError(String((e as Error)?.message || e));
    } finally {
      setSeedingRanges(false);
    }
  }

  async function addRange() {
    setRangeError(null);
    if (!data) return;
    if (!rangeCity.trim()) {
      setRangeError("Ange ort");
      return;
    }
    const lo = parseFloat(rangeLow.replace(/\s/g, "").replace(",", "."));
    const hi = parseFloat(rangeHigh.replace(/\s/g, "").replace(",", "."));
    if (isNaN(lo) || isNaN(hi) || hi < lo) {
      setRangeError("low ≤ high · giltiga belopp krävs");
      return;
    }
    setRangeSubmitting(true);
    try {
      await v2Api.teacherCreateMarketRange({
        profession: data.profession,
        city: rangeCity.trim(),
        year: rangeYear,
        experience_band: "alla",
        low: lo,
        high: hi,
        source: "Lärar-justerat",
      });
      setRangeCity("");
      setRangeLow("");
      setRangeHigh("");
      await refresh();
    } catch (e) {
      setRangeError(String((e as Error)?.message || e));
    } finally {
      setRangeSubmitting(false);
    }
  }

  async function deleteRange(rangeId: number) {
    if (!confirm("Ta bort marknadsspann?")) return;
    try {
      await v2Api.teacherDeleteMarketRange(rangeId);
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
              Kunde inte ladda arbetsgivar-data
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
        <div className="bank-loading">Laddar arbetsgivar-profil…</div>
      </div>
    );
  }

  const sevColor =
    data.satisfaction_score >= 70
      ? "#6ee7b7"
      : data.satisfaction_score >= 50
      ? "var(--warm)"
      : "#fda594";

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
            <span className="pill warm">Lärar-vy · Arbetsgivaren</span>
            <h1 className="actor-name" style={{ marginTop: 14 }}>
              {data.student_name}s <em>arbetsgivar-profil</em>.
            </h1>
            <p className="actor-sub">
              Yrke + lön + kollektivavtal + marknadsspann + lönesamtal +
              arbetsplats-frågor. Allt påverkar wellbeing-pentagonen.
            </p>
          </div>
          <div className="actor-meta">
            Yrke: <strong>{data.profession}</strong>
            <br />
            Arbetsgivare: <strong>{data.employer}</strong>
            <br />
            Avtal:{" "}
            <strong>
              {data.agreement_name || "ej kopplat"}
            </strong>
          </div>
        </header>

        {seedMessage && (
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
            ● {seedMessage}
          </div>
        )}

        {/* SAMMANFATTNING */}
        <div className="acct-grid">
          <div className="acct active">
            <div>
              <div className="acct-eye">Bruttolön</div>
              <div className="acct-name">
                {SEK(data.gross_salary_monthly)} kr/mån
              </div>
              <div className="acct-num">
                {data.market_low != null && data.market_high != null
                  ? `marknad: ${SEK(data.market_low)}–${SEK(data.market_high)}`
                  : "ingen marknadsspann seedat"}
              </div>
            </div>
            <div>
              {data.market_low != null &&
              data.gross_salary_monthly < data.market_low ? (
                <div
                  className="acct-bal"
                  style={{ color: "#fda594", fontSize: 14 }}
                >
                  under marknad
                </div>
              ) : data.market_high != null &&
                data.gross_salary_monthly > data.market_high ? (
                <div
                  className="acct-bal"
                  style={{ color: "#6ee7b7", fontSize: 14 }}
                >
                  över marknad
                </div>
              ) : (
                <div className="acct-bal" style={{ fontSize: 14 }}>
                  i spann
                </div>
              )}
            </div>
          </div>
          <div className="acct">
            <div>
              <div className="acct-eye">Tjänstepension</div>
              <div className="acct-name">
                {data.pension_pct != null
                  ? `${data.pension_pct.toFixed(1)} %`
                  : "ej satt"}
              </div>
              <div className="acct-num">arbetsgivar-betald</div>
            </div>
            <div>
              <div className="acct-bal">{data.benefits.length}</div>
              <div className="acct-bal-meta">förmåner total</div>
            </div>
          </div>
          <div className="acct">
            <div>
              <div className="acct-eye">Nöjdhet</div>
              <div className="acct-name" style={{ color: sevColor }}>
                {data.satisfaction_score} / 100
              </div>
              <div className="acct-num">trend: {data.satisfaction_trend}</div>
            </div>
            <div>
              <div
                className="acct-bal"
                style={{
                  color:
                    data.satisfaction_delta_4w >= 0 ? "#6ee7b7" : "#fda594",
                }}
              >
                {data.satisfaction_delta_4w >= 0 ? "+" : "−"}
                {Math.abs(data.satisfaction_delta_4w)}
              </div>
              <div className="acct-bal-meta">senaste 4 v</div>
            </div>
          </div>
          <div className="acct">
            <div>
              <div className="acct-eye">Frågor</div>
              <div className="acct-name">
                {data.questions_answered_count} svarat
              </div>
              <div className="acct-num">
                {data.questions_pending_count} kvar att möta
              </div>
            </div>
            <div>
              <div className="acct-bal">
                {data.salary_negotiations.length}
              </div>
              <div className="acct-bal-meta">lönesamtal</div>
            </div>
          </div>
        </div>

        <div className="act-grid">
          <div>
            {/* FÖRMÅNER */}
            <div className="section-eye">Kollektivavtals-förmåner</div>
            {data.benefits.length === 0 ? (
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
                Inga förmåner registrerade på{" "}
                {data.agreement_name || "avtalet"} än. Klicka "Seedа
                default-katalogen" nedan för att fylla i Sverige-mallen för
                Kommunal HÖK / Vårdförbundet / IT-tjm-avtalet etc.
              </div>
            ) : (
              <div className="biz-table" style={{ marginBottom: 16 }}>
                <div
                  className="biz-table-row head"
                  style={{ gridTemplateColumns: "180px 1.6fr 110px" }}
                >
                  <span>Förmån</span>
                  <span>Beskrivning</span>
                  <span>Värde</span>
                </div>
                {data.benefits.map((b, idx) => (
                  <div
                    className="biz-table-row"
                    key={`${b.name}-${idx}`}
                    style={{ gridTemplateColumns: "180px 1.6fr 110px" }}
                  >
                    <span style={{ fontFamily: "var(--serif)", fontSize: 14 }}>
                      {b.name}
                    </span>
                    <span
                      style={{
                        fontFamily: "var(--mono)",
                        fontSize: 11,
                        color: "var(--text-mid)",
                      }}
                    >
                      {b.detail || "—"}
                    </span>
                    <span
                      style={{
                        fontFamily: "var(--serif)",
                        fontStyle: "italic",
                        color: "var(--warm)",
                        fontSize: 14,
                      }}
                    >
                      {b.value}
                    </span>
                  </div>
                ))}
              </div>
            )}

            <button
              type="button"
              className="cta-btn"
              disabled={seedingBenefits}
              onClick={seedBenefits}
              style={{ marginRight: 8, marginBottom: 22 }}
            >
              {seedingBenefits
                ? "Seedar förmåner…"
                : "Seedа default-katalog (avtal)"}
            </button>

            {/* MARKNADSSPANN */}
            <div className="section-eye">
              Marknadsspann · {data.profession}
            </div>
            {ranges.length === 0 ? (
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
                Inga marknadsspann seedat för {data.profession}. Klicka
                "Seedа SCB-katalog" eller skapa eget nedan.
              </div>
            ) : (
              <div className="biz-table" style={{ marginBottom: 16 }}>
                <div
                  className="biz-table-row head"
                  style={{
                    gridTemplateColumns: "100px 80px 110px 110px 110px 70px",
                  }}
                >
                  <span>Stad</span>
                  <span>År</span>
                  <span>Låg</span>
                  <span>Median</span>
                  <span>Hög</span>
                  <span></span>
                </div>
                {ranges.map((r) => (
                  <div
                    className="biz-table-row"
                    key={r.id}
                    style={{
                      gridTemplateColumns: "100px 80px 110px 110px 110px 70px",
                    }}
                  >
                    <span style={{ fontFamily: "var(--serif)", fontSize: 13 }}>
                      {r.city}
                    </span>
                    <span style={{ fontFamily: "var(--mono)", fontSize: 11 }}>
                      {r.year}
                    </span>
                    <span style={{ fontFamily: "var(--mono)", fontSize: 12 }}>
                      {SEK(r.low)}
                    </span>
                    <span style={{ fontFamily: "var(--mono)", fontSize: 12 }}>
                      {r.median != null ? SEK(r.median) : "—"}
                    </span>
                    <span style={{ fontFamily: "var(--mono)", fontSize: 12 }}>
                      {SEK(r.high)}
                    </span>
                    <button
                      type="button"
                      onClick={() => deleteRange(r.id)}
                      style={{
                        background: "transparent",
                        border: "1px solid var(--line-strong)",
                        color: "var(--text-mid)",
                        padding: "4px 8px",
                        borderRadius: 100,
                        fontFamily: "var(--mono)",
                        fontSize: 9,
                        textTransform: "uppercase",
                        letterSpacing: "0.6px",
                        cursor: "pointer",
                      }}
                    >
                      X
                    </button>
                  </div>
                ))}
              </div>
            )}

            {/* SKAPA NYTT MARKNADSSPANN */}
            <div
              style={{
                background: "rgba(15,21,37,0.7)",
                border: "1px solid var(--line)",
                borderRadius: 6,
                padding: "16px 20px",
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
                ● Lägg till marknadsspann för {data.profession}
              </div>
              <div
                style={{
                  display: "grid",
                  gridTemplateColumns: "1fr 80px 110px 110px",
                  gap: 8,
                  marginBottom: 8,
                  alignItems: "end",
                }}
              >
                <input
                  placeholder="Stad (t.ex. Helsingborg)"
                  value={rangeCity}
                  onChange={(e) => setRangeCity(e.target.value)}
                  style={inputStyle()}
                />
                <input
                  type="number"
                  placeholder="År"
                  value={rangeYear}
                  onChange={(e) =>
                    setRangeYear(parseInt(e.target.value, 10))
                  }
                  style={inputStyle()}
                />
                <input
                  type="number"
                  placeholder="Låg"
                  value={rangeLow}
                  onChange={(e) => setRangeLow(e.target.value)}
                  style={inputStyle()}
                />
                <input
                  type="number"
                  placeholder="Hög"
                  value={rangeHigh}
                  onChange={(e) => setRangeHigh(e.target.value)}
                  style={inputStyle()}
                />
              </div>
              {rangeError && (
                <div
                  style={{
                    fontFamily: "var(--mono)",
                    fontSize: 11,
                    color: "#fca5a5",
                    marginBottom: 8,
                  }}
                >
                  {rangeError}
                </div>
              )}
              <button
                type="button"
                className="cta-btn"
                disabled={rangeSubmitting}
                onClick={addRange}
                style={{ marginRight: 8 }}
              >
                {rangeSubmitting ? "Sparar…" : "Spara marknadsspann"}
              </button>
              <button
                type="button"
                className="cta-btn ghost"
                disabled={seedingRanges}
                onClick={seedRanges}
              >
                {seedingRanges ? "Seedar…" : "Seedа SCB-katalog"}
              </button>
            </div>

            {/* LÖNESAMTAL-HISTORIK */}
            <div className="section-eye">Lönesamtal · senaste 10</div>
            {data.salary_negotiations.length === 0 ? (
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
                Inga lönesamtal startade. När eleven öppnar Maria-AI:n
                skapas en SalaryNegotiation och visas här.
              </div>
            ) : (
              <div className="biz-table">
                <div
                  className="biz-table-row head"
                  style={{
                    gridTemplateColumns: "120px 110px 80px 100px 90px",
                  }}
                >
                  <span>Startad</span>
                  <span>Startlön</span>
                  <span>Ronder</span>
                  <span>Resultat</span>
                  <span>Status</span>
                </div>
                {data.salary_negotiations.map((n) => (
                  <div
                    className="biz-table-row"
                    key={n.id}
                    style={{
                      gridTemplateColumns: "120px 110px 80px 100px 90px",
                    }}
                  >
                    <span
                      style={{
                        fontFamily: "var(--mono)",
                        fontSize: 11,
                        color: "var(--text-mid)",
                      }}
                    >
                      {SHORT_DATE(n.started_at)}
                    </span>
                    <span style={{ fontFamily: "var(--serif)", fontSize: 13 }}>
                      {SEK(n.starting_salary)}
                    </span>
                    <span style={{ fontFamily: "var(--mono)", fontSize: 11 }}>
                      {n.round_no} / {n.max_rounds}
                    </span>
                    <span style={{ fontFamily: "var(--mono)", fontSize: 11 }}>
                      {n.final_pct != null
                        ? `+${n.final_pct.toFixed(1)} %`
                        : n.proposed_pct != null
                        ? `bud +${n.proposed_pct.toFixed(1)} %`
                        : "—"}
                    </span>
                    <span
                      className={`biz-status ${
                        n.status === "completed"
                          ? "delta-up"
                          : n.status === "abandoned"
                          ? "delta-down"
                          : "open"
                      }`}
                    >
                      {NEG_STATUS_LABEL[n.status] || n.status}
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
                Lönesamtal <em>räknas</em>
              </div>
              <div className="side-card-meta">
                Aktivt samtal +2 economy. Klart med löneökning +economy
                (max +8). Avbrutet samtal -3 economy. Synligt i pentagonen.
              </div>
            </div>
            <div className="side-card">
              <div className="side-card-eye">Marknadsposition</div>
              <div className="side-card-h">
                {data.market_low != null &&
                data.gross_salary_monthly < data.market_low
                  ? "Under marknad"
                  : data.market_high != null &&
                    data.gross_salary_monthly > data.market_high
                  ? "Över marknad"
                  : "I spann"}
              </div>
              <div className="side-card-meta">
                Eleven kan använda spannet i Maria-AI:n som BATNA.
              </div>
            </div>
            <div className="side-card warning">
              <div className="side-card-eye">Pedagogiskt syfte</div>
              <div className="side-card-h">
                Anställning är <em>mer än lön</em>
              </div>
              <div className="side-card-meta">
                Eleven ska känna att förmåner (pension, friskvård,
                lönerevision) är ekonomi. Strukturerade benefits gör det
                jämförbart mellan avtal.
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
