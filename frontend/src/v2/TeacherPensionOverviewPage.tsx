/**
 * Lärar-vy · full insyn i en elevs pensions-prognos.
 *
 * Använder /v2/teacher/students/{id}/pension-overview. Lärare kan
 * justera elevens antaganden (riktålder, real avkastning, ITP1-procent)
 * via /v2/teacher/students/{id}/pension/assumptions.
 *
 * Routas via /teacher/v2/pension/:studentId.
 */
import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import {
  v2Api,
  type V2TeacherPensionOverview,
} from "./api";
import { V2Banner } from "./V2Banner";
import "./lan.css";

const SEK = (n: number) =>
  new Intl.NumberFormat("sv-SE", { maximumFractionDigits: 0 }).format(n);

export function TeacherPensionOverviewPage() {
  const { studentId } = useParams<{ studentId: string }>();
  const sid = studentId ? parseInt(studentId, 10) : 0;
  const [data, setData] = useState<V2TeacherPensionOverview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [seeding, setSeeding] = useState(false);
  const [seedMsg, setSeedMsg] = useState<string | null>(null);

  const [retire, setRetire] = useState("");
  const [retReturn, setRetReturn] = useState("");
  const [iskMonthly, setIskMonthly] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const navigate = useNavigate();

  function refresh(): Promise<void> {
    return v2Api
      .teacherPensionOverview(sid)
      .then((d) => {
        setData(d);
        setRetire(String(d.forecast.assumptions.retire_age));
        setRetReturn(String(d.forecast.assumptions.real_return_pct));
        setIskMonthly(String(d.forecast.assumptions.custom_isk_monthly));
      })
      .catch((e) => setError(String((e as Error)?.message || e)));
  }

  useEffect(() => {
    if (sid) refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sid]);

  async function seed() {
    setSeeding(true);
    setSeedMsg(null);
    try {
      const r = await v2Api.teacherSeedDefaultPension(sid);
      setSeedMsg(
        r.created > 0
          ? "Pension-singleton skapad"
          : "Singleton fanns redan",
      );
      await refresh();
    } catch (e) {
      setError(String((e as Error)?.message || e));
    } finally {
      setSeeding(false);
    }
  }

  async function saveAssumptions() {
    setSubmitting(true);
    try {
      await v2Api.teacherPatchPensionAssumptions(sid, {
        retire_age: parseInt(retire, 10),
        real_return_pct: parseFloat(retReturn.replace(",", ".")),
        custom_isk_monthly: parseFloat(
          iskMonthly.replace(/\s/g, "").replace(",", "."),
        ),
      });
      await refresh();
    } catch (e) {
      setError(String((e as Error)?.message || e));
    } finally {
      setSubmitting(false);
    }
  }

  if (error) {
    return (
      <div className="v2-lan-root">
        <V2Banner status={{ role: "teacher", is_super_admin: false }} />
        <div className="bank-loading">
          <div>
            <div style={{ color: "#fca5a5", marginBottom: 8 }}>
              Kunde inte ladda pension
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
        <div className="bank-loading">Laddar pension…</div>
      </div>
    );
  }

  const f = data.forecast;

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
            <span className="pill warm">Lärar-vy · Pension</span>
            <h1 className="actor-name" style={{ marginTop: 14 }}>
              {data.student_name}s <em>pensions-profil</em>.
            </h1>
            <p className="actor-sub">
              4 pelare · prognos i dagens penningvärde · scenarier vid
              tidigt/sent uttag · ISK-koppling till Avanza-aktören.
            </p>
          </div>
          <div className="actor-meta">
            Total prognos:{" "}
            <strong>
              {SEK(f.total_monthly_at_retire)} kr/mån
            </strong>
            <br />
            Vid {f.assumptions.retire_age} år
            <br />
            ISK-värde: <strong>{SEK(f.isk_current_value)} kr</strong>
          </div>
        </header>

        {seedMsg && (
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
            ● {seedMsg}
          </div>
        )}

        {/* SAMMANFATTNING */}
        <div className="acct-grid">
          <div className="acct active">
            <div>
              <div className="acct-eye">Profil</div>
              <div className="acct-name">
                {f.age != null ? `${f.age} år` : "Profil saknas"}
              </div>
              <div className="acct-num">
                {f.gross_salary_monthly != null
                  ? `${SEK(f.gross_salary_monthly)} kr/mån brutto`
                  : "lön ej satt"}
              </div>
            </div>
            <div>
              <div className="acct-bal">{f.years_to_retire}</div>
              <div className="acct-bal-meta">år till pension</div>
            </div>
          </div>
          <div className="acct">
            <div>
              <div className="acct-eye">Kollektivavtal</div>
              <div
                className="acct-name"
                style={{
                  color: f.has_collective_agreement
                    ? "#6ee7b7"
                    : "#fda594",
                }}
              >
                {f.has_collective_agreement ? "JA" : "NEJ"}
              </div>
              <div className="acct-num">
                {f.has_collective_agreement
                  ? `ITP1 ${f.assumptions.itp1_low_pct}/${f.assumptions.itp1_high_pct} %`
                  : "ingen ITP1"}
              </div>
            </div>
            <div>
              <div className="acct-bal">
                {SEK(
                  f.pillars.find((p) => p.source === "agreement")
                    ?.monthly_at_retire || 0,
                )}
              </div>
              <div className="acct-bal-meta">ITP1 / mån</div>
            </div>
          </div>
          <div className="acct">
            <div>
              <div className="acct-eye">Privat (ISK)</div>
              <div
                className="acct-name"
                style={{ color: "var(--warm)" }}
              >
                {SEK(f.assumptions.custom_isk_monthly)} kr/mån
              </div>
              <div className="acct-num">
                ISK-värde {SEK(f.isk_current_value)} kr
              </div>
            </div>
            <div>
              <div className="acct-bal">
                {SEK(
                  f.pillars.find((p) => p.source === "isk")
                    ?.monthly_at_retire || 0,
                )}
              </div>
              <div className="acct-bal-meta">privat / mån</div>
            </div>
          </div>
          <div className="acct">
            <div>
              <div className="acct-eye">Wellbeing</div>
              <div
                className="acct-name"
                style={{ color: "var(--warm)" }}
              >
                {f.isk_current_value > 0
                  ? "+2"
                  : f.age != null && f.age >= 25
                  ? "−2"
                  : "0"}
              </div>
              <div className="acct-num">economy (ISK-status)</div>
            </div>
            <div>
              <div
                className="acct-bal"
                style={{ color: "var(--warm)" }}
              >
                {f.assumptions.real_return_pct} %
              </div>
              <div className="acct-bal-meta">real avk-antagande</div>
            </div>
          </div>
        </div>

        <div className="act-grid">
          <div>
            {/* PELARE */}
            <div className="section-eye">
              4 pelare ({f.pillars.length})
            </div>
            {f.pillars.length === 0 ? (
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
                Inga pelare beräknade. Eleven har inte fyllt i ålder
                eller lön — be elev göra onboardingen, eller seedа
                pension-singleton nedan.
              </div>
            ) : (
              <div className="biz-table" style={{ marginBottom: 16 }}>
                <div
                  className="biz-table-row head"
                  style={{
                    gridTemplateColumns: "100px 180px 1fr 130px 90px",
                  }}
                >
                  <span>Pelare</span>
                  <span>Namn</span>
                  <span>Beräkning</span>
                  <span>Vid pension</span>
                  <span>Källa</span>
                </div>
                {f.pillars.map((p) => (
                  <div
                    className="biz-table-row"
                    key={`${p.label}-${p.name}`}
                    style={{
                      gridTemplateColumns: "100px 180px 1fr 130px 90px",
                      opacity: p.source === "missing" ? 0.6 : 1,
                    }}
                  >
                    <span
                      style={{
                        fontFamily: "var(--mono)",
                        fontSize: 11,
                        color: "var(--text-mid)",
                      }}
                    >
                      {p.label}
                    </span>
                    <span style={{ fontFamily: "var(--serif)", fontSize: 13 }}>
                      {p.name}
                    </span>
                    <span
                      style={{
                        fontFamily: "var(--mono)",
                        fontSize: 11,
                        color: "var(--text-mid)",
                      }}
                    >
                      {p.detail}
                    </span>
                    <span
                      style={{
                        fontFamily: "var(--serif)",
                        fontSize: 13,
                        fontStyle: "italic",
                        color:
                          p.source === "missing"
                            ? "#fda594"
                            : "var(--warm)",
                      }}
                    >
                      {SEK(p.monthly_at_retire)} kr/mån
                    </span>
                    <span
                      className={`biz-status ${
                        p.source === "missing"
                          ? "delta-down"
                          : p.source === "isk"
                          ? "delta-up"
                          : "open"
                      }`}
                    >
                      {p.source}
                    </span>
                  </div>
                ))}
              </div>
            )}

            {/* SCENARIER */}
            <div className="section-eye">Scenarier · uttagsålder</div>
            <div
              style={{
                display: "grid",
                gridTemplateColumns: "1fr 1fr 1fr",
                gap: 10,
                marginBottom: 22,
              }}
            >
              <div
                style={{
                  padding: "16px 20px",
                  border: "1px solid var(--line)",
                  borderRadius: 6,
                  textAlign: "center",
                }}
              >
                <div
                  style={{
                    fontFamily: "var(--mono)",
                    fontSize: 10,
                    color: "var(--text-mid)",
                  }}
                >
                  65 år (tidigt)
                </div>
                <div
                  style={{
                    fontFamily: "var(--serif)",
                    fontSize: 24,
                    fontStyle: "italic",
                    color: "#fca5a5",
                    marginTop: 4,
                  }}
                >
                  {SEK(f.scenarios.age_65_early)}
                </div>
                <div
                  style={{
                    fontFamily: "var(--mono)",
                    fontSize: 10,
                    color: "var(--text-dim)",
                  }}
                >
                  kr/mån · −4 % per år
                </div>
              </div>
              <div
                style={{
                  padding: "16px 20px",
                  border: "1px solid var(--warm)",
                  borderRadius: 6,
                  textAlign: "center",
                  background: "rgba(220,76,43,0.04)",
                }}
              >
                <div
                  style={{
                    fontFamily: "var(--mono)",
                    fontSize: 10,
                    color: "var(--warm)",
                  }}
                >
                  {f.assumptions.retire_age} år (riktålder)
                </div>
                <div
                  style={{
                    fontFamily: "var(--serif)",
                    fontSize: 28,
                    fontStyle: "italic",
                    color: "var(--warm)",
                    marginTop: 4,
                  }}
                >
                  {SEK(f.scenarios.age_67_target)}
                </div>
                <div
                  style={{
                    fontFamily: "var(--mono)",
                    fontSize: 10,
                    color: "var(--text-dim)",
                  }}
                >
                  kr/mån · target
                </div>
              </div>
              <div
                style={{
                  padding: "16px 20px",
                  border: "1px solid var(--line)",
                  borderRadius: 6,
                  textAlign: "center",
                }}
              >
                <div
                  style={{
                    fontFamily: "var(--mono)",
                    fontSize: 10,
                    color: "var(--text-mid)",
                  }}
                >
                  70 år (sent)
                </div>
                <div
                  style={{
                    fontFamily: "var(--serif)",
                    fontSize: 24,
                    fontStyle: "italic",
                    color: "#6ee7b7",
                    marginTop: 4,
                  }}
                >
                  {SEK(f.scenarios.age_70_late)}
                </div>
                <div
                  style={{
                    fontFamily: "var(--mono)",
                    fontSize: 10,
                    color: "var(--text-dim)",
                  }}
                >
                  kr/mån · +8 % per år
                </div>
              </div>
            </div>

            {/* JUSTERA */}
            <div
              style={{
                background: "rgba(15,21,37,0.7)",
                border: "1px solid var(--line)",
                borderRadius: 6,
                padding: "16px 20px",
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
                ● Justera elevens antaganden
              </div>
              <div
                style={{
                  display: "grid",
                  gridTemplateColumns: "1fr 1fr 1fr",
                  gap: 8,
                  marginBottom: 8,
                }}
              >
                <div>
                  <div
                    style={{
                      fontFamily: "var(--mono)",
                      fontSize: 9,
                      color: "var(--text-dim)",
                      marginBottom: 4,
                    }}
                  >
                    Riktålder
                  </div>
                  <input
                    type="number"
                    value={retire}
                    onChange={(e) => setRetire(e.target.value)}
                    style={inputStyle()}
                  />
                </div>
                <div>
                  <div
                    style={{
                      fontFamily: "var(--mono)",
                      fontSize: 9,
                      color: "var(--text-dim)",
                      marginBottom: 4,
                    }}
                  >
                    Real avkastning %
                  </div>
                  <input
                    type="number"
                    step="0.1"
                    value={retReturn}
                    onChange={(e) => setRetReturn(e.target.value)}
                    style={inputStyle()}
                  />
                </div>
                <div>
                  <div
                    style={{
                      fontFamily: "var(--mono)",
                      fontSize: 9,
                      color: "var(--text-dim)",
                      marginBottom: 4,
                    }}
                  >
                    ISK-spar/mån
                  </div>
                  <input
                    type="number"
                    value={iskMonthly}
                    onChange={(e) => setIskMonthly(e.target.value)}
                    style={inputStyle()}
                  />
                </div>
              </div>
              <div style={{ display: "flex", gap: 8 }}>
                <button
                  type="button"
                  className="cta-btn"
                  disabled={submitting}
                  onClick={saveAssumptions}
                >
                  {submitting ? "Sparar…" : "Spara"}
                </button>
                <button
                  type="button"
                  className="cta-btn ghost"
                  disabled={seeding}
                  onClick={seed}
                >
                  {seeding ? "Seedar…" : "Skapa singleton om saknas"}
                </button>
              </div>
            </div>
          </div>

          <aside>
            <div className="side-card">
              <div className="side-card-eye">Wellbeing-effekt</div>
              <div className="side-card-h">
                ISK <em>räknas</em>
              </div>
              <div className="side-card-meta">
                ISK-portfölj &gt; 0 → +2 economy. Ålder ≥ 25 utan ISK →
                −2 economy (tappar tidsfönstret för ränta-på-ränta).
                Tomt ISK-konto loggas som info utan impact.
              </div>
            </div>
            <div className="side-card">
              <div className="side-card-eye">Beräkning</div>
              <div className="side-card-h">
                Auto från lön + ålder
              </div>
              <div className="side-card-meta">
                Inkomstpension 16 % av lön under {f.assumptions.ibb_yearly *
                  7.5 / 1000 | 0} tkr/år (7.5 IBB), premiepension 2.5 %,
                ITP1 {f.assumptions.itp1_low_pct} % under tak. Allt
                ackumuleras med {f.assumptions.real_return_pct} % real
                avkastning över {f.years_to_retire} år, omvandlas via
                delningstal {f.assumptions.delningstal}.
              </div>
            </div>
            <div className="side-card warning">
              <div className="side-card-eye">Pedagogiskt syfte</div>
              <div className="side-card-h">
                Pension är <em>40 år bort</em>
              </div>
              <div className="side-card-meta">
                Eleven ska känna att privat-sparande inte är lyx —
                allmän pension räcker knappt till hyra + mat. Att se
                siffran konkret i dagens penningvärde är hela poängen.
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
