/**
 * Lärar-vy · alla elevens sparade Investerings- och Låne-scenarier.
 *
 * Använder /v2/teacher/students/{id}/simulator-overview. Lärare ser
 * alla scenarier eleven sparat — pedagogiskt värdefullt för att
 * bedöma "har eleven tänkt långsiktigt?".
 */
import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import {
  v2Api,
  type V2TeacherSimulatorOverview,
} from "./api";
import { V2Banner } from "./V2Banner";
import "./lan.css";

const SEK = (n: number) =>
  new Intl.NumberFormat("sv-SE", { maximumFractionDigits: 0 }).format(n);

const SHORT_DATE = (iso: string): string => {
  const d = new Date(iso);
  return d.toLocaleDateString("sv-SE", {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
};

export function TeacherSimulatorOverviewPage() {
  const { studentId } = useParams<{ studentId: string }>();
  const sid = studentId ? parseInt(studentId, 10) : 0;
  const [data, setData] = useState<V2TeacherSimulatorOverview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const navigate = useNavigate();

  useEffect(() => {
    if (!sid) return;
    v2Api
      .teacherSimulatorOverview(sid)
      .then(setData)
      .catch((e) => setError(String((e as Error)?.message || e)));
  }, [sid]);

  if (error) {
    return (
      <div className="v2-lan-root">
        <V2Banner status={{ role: "teacher", is_super_admin: false }} />
        <div className="bank-loading">
          <div>
            <div style={{ color: "#fca5a5", marginBottom: 8 }}>
              Kunde inte ladda simulator-data
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
        <div className="bank-loading">Laddar simulator-profil…</div>
      </div>
    );
  }

  const investRows = data.scenarios.filter((sc) => sc.kind === "invest");
  const loanRows = data.scenarios.filter((sc) => sc.kind === "loan");

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
            <span className="pill warm">Lärar-vy · Simulatorer</span>
            <h1 className="actor-name" style={{ marginTop: 14 }}>
              {data.student_name}s <em>scenario-tankesätt</em>.
            </h1>
            <p className="actor-sub">
              Sparade investerings- och låne-scenarier · pedagogiskt
              viktigt för att se "har eleven tänkt långsiktigt?".
            </p>
          </div>
          <div className="actor-meta">
            Investeringar: <strong>{data.invest_count} scenarier</strong>
            <br />
            Lån: <strong>{data.loan_count} scenarier</strong>
            <br />
            Längsta horisont:{" "}
            <strong>{data.longest_horizon_years} år</strong>
          </div>
        </header>

        {/* SAMMANFATTNING */}
        <div className="acct-grid">
          <div className="acct active">
            <div>
              <div className="acct-eye">Investeringar</div>
              <div className="acct-name">{data.invest_count}</div>
              <div className="acct-num">sparade scenarier</div>
            </div>
            <div>
              <div className="acct-bal">
                {data.longest_horizon_years}
              </div>
              <div className="acct-bal-meta">år max-horisont</div>
            </div>
          </div>
          <div className="acct">
            <div>
              <div className="acct-eye">Lån</div>
              <div className="acct-name">{data.loan_count}</div>
              <div className="acct-num">sparade scenarier</div>
            </div>
            <div>
              <div className="acct-bal">
                {SEK(data.biggest_principal)}
              </div>
              <div className="acct-bal-meta">största belopp</div>
            </div>
          </div>
          <div className="acct">
            <div>
              <div className="acct-eye">Wellbeing-effekt</div>
              <div
                className="acct-name"
                style={{
                  color:
                    data.longest_horizon_years >= 20
                      ? "var(--warm)"
                      : "var(--text-mid)",
                }}
              >
                {data.longest_horizon_years >= 20 ? "+1" : "0"}
              </div>
              <div className="acct-num">economy</div>
            </div>
            <div>
              <div
                className="acct-bal"
                style={{
                  color:
                    data.longest_horizon_years >= 20
                      ? "#6ee7b7"
                      : "var(--text-dim)",
                }}
              >
                {data.longest_horizon_years >= 20
                  ? "lång planering"
                  : "—"}
              </div>
              <div className="acct-bal-meta">
                ≥ 20 års horisont
              </div>
            </div>
          </div>
          <div className="acct">
            <div>
              <div className="acct-eye">Total aktivitet</div>
              <div className="acct-name">{data.scenarios.length}</div>
              <div className="acct-num">scenarier sparade</div>
            </div>
            <div>
              <div className="acct-bal">
                {data.scenarios.length > 0
                  ? SHORT_DATE(data.scenarios[0].created_at).split(
                      " ",
                    )[0]
                  : "—"}
              </div>
              <div className="acct-bal-meta">senast sparad</div>
            </div>
          </div>
        </div>

        <div className="act-grid">
          <div>
            {/* INVESTERINGS-SCENARIER */}
            <div className="section-eye">
              Investerings-scenarier ({investRows.length})
            </div>
            {investRows.length === 0 ? (
              <div
                style={{
                  padding: "16px 20px",
                  border: "1px solid var(--line)",
                  borderRadius: 6,
                  fontFamily: "var(--serif)",
                  fontSize: 13,
                  color: "var(--text-mid)",
                  marginBottom: 22,
                }}
              >
                Eleven har inte sparat några investerings-scenarier än.
              </div>
            ) : (
              <div className="biz-table" style={{ marginBottom: 22 }}>
                <div
                  className="biz-table-row head"
                  style={{
                    gridTemplateColumns:
                      "1.4fr 80px 60px 60px 110px 90px",
                  }}
                >
                  <span>Namn</span>
                  <span>Mån-spar</span>
                  <span>År</span>
                  <span>%</span>
                  <span>Slutvärde</span>
                  <span>Sparat</span>
                </div>
                {investRows.map((sc) => {
                  const finalVal = Number(
                    (sc.result || {})["final_value"] || 0,
                  );
                  const monthly = Number(sc.params.monthly_save) || 0;
                  const years = Number(sc.params.years) || 0;
                  const pct = Number(sc.params.return_pct) || 0;
                  return (
                    <div
                      className="biz-table-row"
                      key={sc.id}
                      style={{
                        gridTemplateColumns:
                          "1.4fr 80px 60px 60px 110px 90px",
                      }}
                    >
                      <div>
                        <div
                          style={{
                            fontFamily: "var(--serif)",
                            fontSize: 13,
                          }}
                        >
                          {sc.name}
                        </div>
                        <div
                          style={{
                            fontFamily: "var(--mono)",
                            fontSize: 9,
                            color: "var(--text-dim)",
                          }}
                        >
                          {sc.params.is_isk ? "ISK" : "depå"} ·{" "}
                          start {SEK(Number(sc.params.start_amount) || 0)}{" "}
                          kr
                        </div>
                      </div>
                      <span style={{ fontFamily: "var(--mono)", fontSize: 11 }}>
                        {SEK(monthly)}
                      </span>
                      <span style={{ fontFamily: "var(--mono)", fontSize: 11 }}>
                        {years}
                      </span>
                      <span style={{ fontFamily: "var(--mono)", fontSize: 11 }}>
                        {pct}
                      </span>
                      <span
                        style={{
                          fontFamily: "var(--serif)",
                          fontSize: 13,
                          fontStyle: "italic",
                          color: "var(--warm)",
                        }}
                      >
                        {SEK(finalVal)} kr
                      </span>
                      <span
                        style={{
                          fontFamily: "var(--mono)",
                          fontSize: 10,
                          color: "var(--text-mid)",
                        }}
                      >
                        {SHORT_DATE(sc.created_at)}
                      </span>
                    </div>
                  );
                })}
              </div>
            )}

            {/* LÅNE-SCENARIER */}
            <div className="section-eye">
              Låne-scenarier ({loanRows.length})
            </div>
            {loanRows.length === 0 ? (
              <div
                style={{
                  padding: "16px 20px",
                  border: "1px solid var(--line)",
                  borderRadius: 6,
                  fontFamily: "var(--serif)",
                  fontSize: 13,
                  color: "var(--text-mid)",
                }}
              >
                Eleven har inte sparat några låne-scenarier än.
              </div>
            ) : (
              <div className="biz-table">
                <div
                  className="biz-table-row head"
                  style={{
                    gridTemplateColumns:
                      "1.4fr 110px 70px 80px 110px 90px",
                  }}
                >
                  <span>Namn</span>
                  <span>Belopp</span>
                  <span>Ränta</span>
                  <span>Löptid</span>
                  <span>Total ränta</span>
                  <span>Sparat</span>
                </div>
                {loanRows.map((sc) => {
                  const principal = Number(sc.params.principal) || 0;
                  const rate = Number(sc.params.interest_rate_pct) || 0;
                  const months_t = Number(sc.params.term_months) || 0;
                  const totalInterest = Number(
                    ((sc.result || {})[
                      "with_extra"
                    ] as Record<string, unknown> || {})["total_interest"] ||
                      0,
                  );
                  return (
                    <div
                      className="biz-table-row"
                      key={sc.id}
                      style={{
                        gridTemplateColumns:
                          "1.4fr 110px 70px 80px 110px 90px",
                      }}
                    >
                      <div>
                        <div
                          style={{
                            fontFamily: "var(--serif)",
                            fontSize: 13,
                          }}
                        >
                          {sc.name}
                        </div>
                        <div
                          style={{
                            fontFamily: "var(--mono)",
                            fontSize: 9,
                            color: "var(--text-dim)",
                          }}
                        >
                          {sc.params.amortization_type as string} ·{" "}
                          extra{" "}
                          {SEK(
                            Number(
                              sc.params.extra_amortization_monthly,
                            ) || 0,
                          )}{" "}
                          kr/mån
                        </div>
                      </div>
                      <span
                        style={{
                          fontFamily: "var(--mono)",
                          fontSize: 11,
                        }}
                      >
                        {SEK(principal)}
                      </span>
                      <span
                        style={{
                          fontFamily: "var(--mono)",
                          fontSize: 11,
                        }}
                      >
                        {rate} %
                      </span>
                      <span
                        style={{
                          fontFamily: "var(--mono)",
                          fontSize: 11,
                        }}
                      >
                        {months_t} mån
                      </span>
                      <span
                        style={{
                          fontFamily: "var(--mono)",
                          fontSize: 11,
                          color: "#fda594",
                        }}
                      >
                        {SEK(totalInterest)}
                      </span>
                      <span
                        style={{
                          fontFamily: "var(--mono)",
                          fontSize: 10,
                          color: "var(--text-mid)",
                        }}
                      >
                        {SHORT_DATE(sc.created_at)}
                      </span>
                    </div>
                  );
                })}
              </div>
            )}
          </div>

          <aside>
            <div className="side-card">
              <div className="side-card-eye">Wellbeing-effekt</div>
              <div className="side-card-h">
                Långsiktig planering <em>räknas</em>
              </div>
              <div className="side-card-meta">
                Sparat invest-scenario med ≥ 20 års horisont → +1
                economy ("planering räknas"). Sparade låne-scenarier är
                informativa (eleven förstår vad lån kostar) men ger
                ingen direkt poäng.
              </div>
            </div>
            <div className="side-card">
              <div className="side-card-eye">Pedagogiskt värde</div>
              <div className="side-card-h">
                Scenarier visar <em>tankesätt</em>
              </div>
              <div className="side-card-meta">
                Vad har eleven sparat? 600 kr/mån i 40 år eller 5 000 i
                3 år? Det första visar ränta-på-ränta-förståelse, det
                andra kortsiktig planering. Använd för bedömning av
                Investering- och Lån-kompetenser.
              </div>
            </div>
            {data.longest_horizon_years >= 30 && (
              <div className="side-card">
                <div className="side-card-eye">Bra signal</div>
                <div className="side-card-h">
                  {data.longest_horizon_years} år horisont
                </div>
                <div className="side-card-meta">
                  Eleven har räknat på 30+ år — visar att de förstår
                  tidsfaktorn. Höj kompetens "Investering" till GRUND
                  om de inte redan har den.
                </div>
              </div>
            )}
          </aside>
        </div>
      </div>
    </div>
  );
}
