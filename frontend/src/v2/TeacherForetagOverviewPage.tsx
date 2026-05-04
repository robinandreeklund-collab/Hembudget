/**
 * Lärar-vy · full insyn i en elevs företagsläge.
 *
 * Använder /v2/teacher/foretag/overview/{id} som returnerar:
 * - business_mode_enabled (lärartoggle på/av)
 * - company (om eleven startat ett bolag)
 * - pentagon (5-axlad biz-pentagon score)
 * - n_transactions / n_invoices / n_invoices_unpaid
 * - n_owner_salaries / last_owner_salary_date
 * - next_vat_due
 * - summary_md (auto-genererad sammanfattning)
 *
 * Läraren kan här toggla om eleven har företagsläget aktiverat.
 *
 * Routas via /teacher/v2/foretag/:studentId — länk från elev-detaljvyn.
 */
import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { teacherBizApi, type TeacherForetagOverview } from "./biz/api";
import { V2Banner } from "./V2Banner";
import "./lan.css";

const SEK = (n: number) =>
  new Intl.NumberFormat("sv-SE", { maximumFractionDigits: 0 }).format(n);

export function TeacherForetagOverviewPage() {
  const { studentId } = useParams<{ studentId: string }>();
  const sid = studentId ? parseInt(studentId, 10) : 0;
  const [data, setData] = useState<TeacherForetagOverview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [toggling, setToggling] = useState(false);
  const navigate = useNavigate();

  function refresh(): Promise<void> {
    return teacherBizApi
      .overview(sid)
      .then(setData)
      .catch((e) => setError(String((e as Error)?.message || e)));
  }

  useEffect(() => {
    if (sid) refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sid]);

  async function toggleBiz() {
    if (data === null) return;
    setToggling(true);
    try {
      await teacherBizApi.toggle(sid, !data.business_mode_enabled);
      await refresh();
    } catch (e) {
      setError(String((e as Error)?.message || e));
    } finally {
      setToggling(false);
    }
  }

  if (error) {
    return (
      <div className="v2-shell">
        <V2Banner status={{ role: "teacher", is_super_admin: false }} />
        <div className="lan-container">
          <p className="error">Fel: {error}</p>
          <button onClick={() => navigate("/teacher/v2/roster")}>
            Tillbaka
          </button>
        </div>
      </div>
    );
  }

  if (!data) {
    return (
      <div className="v2-shell">
        <V2Banner status={{ role: "teacher", is_super_admin: false }} />
        <div className="lan-container">
          <p>Laddar elevens företagsdata…</p>
        </div>
      </div>
    );
  }

  return (
    <div className="v2-shell">
      <V2Banner status={{ role: "teacher", is_super_admin: false }} />
      <div className="lan-container" style={{ paddingBottom: 64 }}>
        <button
          onClick={() => navigate(`/teacher/v2/elev/${sid}`)}
          style={{
            background: "transparent",
            border: "1px solid rgba(99,102,241,0.3)",
            color: "#c7d2fe",
            padding: "6px 12px",
            borderRadius: 6,
            cursor: "pointer",
            marginBottom: 16,
          }}
        >
          ← Tillbaka till elev
        </button>

        <h1 style={{ margin: "0 0 8px 0" }}>
          {data.student_name} — Företagsläget
        </h1>
        <p style={{ color: "rgba(255,255,255,0.55)", marginTop: 0 }}>
          Aktör 11 · privat och företag delar samma elev. Allt som händer
          i bolaget påverkar privatekonomin och vice versa.
        </p>

        <div
          style={{
            background: "rgba(15,21,37,0.5)",
            border: "1px solid rgba(99,102,241,0.2)",
            borderRadius: 12,
            padding: 16,
            marginTop: 24,
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            gap: 16,
          }}
        >
          <div>
            <div
              style={{
                fontSize: 9,
                letterSpacing: 1.3,
                color: "#818cf8",
                textTransform: "uppercase",
                fontFamily: "JetBrains Mono, monospace",
              }}
            >
              Lärar-toggle
            </div>
            <div style={{ fontWeight: 700, marginTop: 4 }}>
              Företagsläget för eleven:{" "}
              <span
                style={{
                  color: data.business_mode_enabled ? "#6ee7b7" : "#fda594",
                }}
              >
                {data.business_mode_enabled ? "AKTIVT" : "AVAKTIVERAT"}
              </span>
            </div>
            <div
              style={{
                fontSize: "0.8rem",
                color: "rgba(255,255,255,0.55)",
                marginTop: 4,
              }}
            >
              När påslaget kan eleven driva enskild firma eller AB
              parallellt med lönearbete.
            </div>
          </div>
          <button
            onClick={toggleBiz}
            disabled={toggling}
            style={{
              padding: "10px 20px",
              borderRadius: 8,
              border: "none",
              background: data.business_mode_enabled
                ? "rgba(248,113,113,0.18)"
                : "rgba(34,197,94,0.18)",
              color: data.business_mode_enabled ? "#fda594" : "#6ee7b7",
              fontWeight: 700,
              cursor: toggling ? "not-allowed" : "pointer",
            }}
          >
            {toggling
              ? "…"
              : data.business_mode_enabled
              ? "Avaktivera"
              : "Aktivera"}
          </button>
        </div>

        {/* Sammanfattning */}
        <div
          style={{
            background: "rgba(15,21,37,0.4)",
            border: "1px solid rgba(99,102,241,0.18)",
            borderRadius: 12,
            padding: 20,
            marginTop: 16,
            whiteSpace: "pre-wrap",
            fontSize: "0.95rem",
            lineHeight: 1.55,
          }}
        >
          {data.summary_md.split("\n").map((line, i) => {
            if (line.startsWith("## ")) {
              return (
                <h2
                  key={i}
                  style={{ marginTop: i === 0 ? 0 : 16, marginBottom: 8 }}
                >
                  {line.slice(3)}
                </h2>
              );
            }
            if (line.startsWith("- ")) {
              return (
                <div key={i} style={{ marginLeft: 16, marginTop: 4 }}>
                  • {line
                    .slice(2)
                    .split(/(\*\*[^*]+\*\*)/)
                    .map((part, j) =>
                      part.startsWith("**") ? (
                        <strong key={j}>{part.slice(2, -2)}</strong>
                      ) : (
                        part
                      ),
                    )}
                </div>
              );
            }
            return <div key={i}>{line}</div>;
          })}
        </div>

        {/* Företagsdata om bolag finns */}
        {data.company && data.pentagon && (
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "1fr 1fr",
              gap: 16,
              marginTop: 16,
            }}
          >
            <div
              style={{
                background: "rgba(15,21,37,0.4)",
                border: "1px solid rgba(99,102,241,0.18)",
                borderRadius: 12,
                padding: 20,
              }}
            >
              <h3 style={{ marginTop: 0 }}>Bolag</h3>
              <div>
                <strong>{data.company.name}</strong> ({data.company.form})
              </div>
              {data.company.org_number && (
                <div style={{ fontSize: "0.85rem", color: "#aab" }}>
                  Org.nr: {data.company.org_number}
                </div>
              )}
              <div style={{ fontSize: "0.85rem", color: "#aab" }}>
                Startat: {data.company.started_on}
              </div>
              <div
                style={{
                  fontSize: "0.85rem",
                  color: data.company.vat_registered ? "#6ee7b7" : "#aab",
                }}
              >
                Moms: {data.company.vat_registered
                  ? `Registrerad (${data.company.vat_period})`
                  : "Inte registrerad"}
              </div>
            </div>

            <div
              style={{
                background: "rgba(15,21,37,0.4)",
                border: "1px solid rgba(99,102,241,0.18)",
                borderRadius: 12,
                padding: 20,
              }}
            >
              <h3 style={{ marginTop: 0 }}>Aktivitet</h3>
              <div>Bokförda transaktioner: <strong>{data.n_transactions_total}</strong></div>
              <div>
                Fakturor: <strong>{data.n_invoices_total}</strong> ({data.n_invoices_unpaid} obetalda)
              </div>
              <div>Löneuttag: <strong>{data.n_owner_salaries}</strong></div>
              {data.next_vat_due && (
                <div style={{ marginTop: 8, color: "#fbbf24" }}>
                  Nästa moms-due: <strong>{data.next_vat_due}</strong>
                </div>
              )}
            </div>

            <div
              style={{
                background: "rgba(15,21,37,0.4)",
                border: "1px solid rgba(99,102,241,0.18)",
                borderRadius: 12,
                padding: 20,
                gridColumn: "1 / -1",
              }}
            >
              <h3 style={{ marginTop: 0 }}>Företagets pentagon</h3>
              <div
                style={{ display: "flex", gap: 16, flexWrap: "wrap" }}
              >
                <PentagonAxis
                  label="Omsättning"
                  score={data.pentagon.axes.omsattning}
                />
                <PentagonAxis
                  label="Kundbas"
                  score={data.pentagon.axes.kundbas}
                />
                <PentagonAxis
                  label="Likviditet"
                  score={data.pentagon.axes.likviditet}
                />
                <PentagonAxis
                  label="Tidsåtgång"
                  score={data.pentagon.axes.tidsatgang}
                />
                <PentagonAxis
                  label="Vinst"
                  score={data.pentagon.axes.vinst}
                />
              </div>
              <div style={{ marginTop: 12, fontSize: "0.9rem", color: "#aab" }}>
                Total: <strong style={{ color: "white" }}>{data.pentagon.total_score}/100</strong>
                {"  ·  "}
                Omsättning 4v: {SEK(data.pentagon.metrics.income_4w)} kr
                {"  ·  "}
                Vinst 4v: {SEK(data.pentagon.metrics.profit_4w)} kr ({data.pentagon.metrics.margin_4w_pct.toFixed(0)}% marginal)
                {"  ·  "}
                Kassa: {SEK(data.pentagon.metrics.kassa)} kr
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}


function PentagonAxis({ label, score }: { label: string; score: number }) {
  const color = score >= 60 ? "#6ee7b7" : score >= 40 ? "#fbbf24" : "#fda594";
  return (
    <div style={{ minWidth: 120 }}>
      <div
        style={{
          fontSize: 9,
          letterSpacing: 1.2,
          textTransform: "uppercase",
          color: "#818cf8",
          fontFamily: "JetBrains Mono, monospace",
        }}
      >
        {label}
      </div>
      <div style={{ fontSize: "1.4rem", fontWeight: 700, color }}>
        {score}
        <span style={{ fontSize: "0.8rem", color: "#aab" }}>/100</span>
      </div>
    </div>
  );
}
