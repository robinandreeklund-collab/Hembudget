/**
 * Lärar-vy · Klassens anställnings-ekosystem (Fas H).
 *
 * Visar alla elever som noder, klasskompis-anställningar som edges.
 * Statistik: antal företagare, aktiva anställningar, total payroll-
 * volym senaste 30 dgr.
 */
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "@/api/client";
import { V2Banner } from "./V2Banner";
import "./lan.css";


type StudentNode = {
  student_id: number;
  display_name: string;
  class_label: string | null;
  is_employer: boolean;
  company_name: string | null;
  n_employees: number;
  employed_at: string | null;
};

type EmploymentEdge = {
  employment_id: number;
  owner_student_id: number;
  employee_student_id: number;
  company_name: string;
  role: string;
  monthly_gross: number;
  status: string;
  accepted_on: string | null;
  last_day: string | null;
};

type EcosystemData = {
  students: StudentNode[];
  employments: EmploymentEdge[];
  stats: {
    n_students_total: number;
    n_employers: number;
    n_active_employments: number;
    n_pending_offers: number;
    n_terminated: number;
    n_declined: number;
    total_payroll_paid_30d: number;
  };
};


type StatsBucket = {
  week_start: string;
  n_hire_offered: number;
  n_accepted: number;
  n_declined: number;
  n_terminated: number;
  n_bankrupted: number;
  payroll_paid: number;
};


const SEK = (n: number) =>
  new Intl.NumberFormat("sv-SE", { maximumFractionDigits: 0 }).format(n);


export function TeacherEmploymentEcosystem() {
  const [data, setData] = useState<EcosystemData | null>(null);
  const [trend, setTrend] = useState<StatsBucket[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [classLabel] = useState<string>("");

  function refresh() {
    api<EcosystemData>(
      `/v2/teacher/employment/ecosystem${
        classLabel ? `?class_label=${encodeURIComponent(classLabel)}` : ""
      }`,
    )
      .then(setData)
      .catch((e) => setError(String((e as Error)?.message || e)));
    api<{ weeks: StatsBucket[] }>("/v2/teacher/employment/stats-trend?weeks=12")
      .then((d) => setTrend(d.weeks))
      .catch(() => setTrend([]));
  }

  useEffect(() => {
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [classLabel]);

  if (error) {
    return (
      <div className="v2-lan-root">
        <V2Banner status={{ role: "teacher", is_super_admin: false }} />
        <div className="bank-loading">
          <div>
            <div style={{ color: "#fca5a5", marginBottom: 8 }}>
              Kunde inte ladda ekosystemet
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
        <div className="bank-loading">Laddar klassens ekosystem…</div>
      </div>
    );
  }

  const employers = data.students.filter((s) => s.is_employer);
  const orphans = data.students.filter(
    (s) => !s.is_employer && !s.employed_at,
  );

  // Map student_id → display_name för edges-rendering
  const nameMap = new Map<number, string>(
    data.students.map((s) => [s.student_id, s.display_name]),
  );
  const nameOf = (id: number) => nameMap.get(id) || `#${id}`;

  return (
    <div className="v2-lan-root">
      <V2Banner status={{ role: "teacher", is_super_admin: false }} />

      <div className="shell">
        <Link className="actor-back" to="/teacher/v2">
          Tillbaka till lärar-hub
        </Link>

        <header style={{ padding: "24px 0" }}>
          <div style={{
            fontFamily: "JetBrains Mono, monospace",
            fontSize: 10, letterSpacing: 1.4,
            color: "rgba(199,210,254,0.8)",
          }}>
            ● LÄRAR-VY · KLASSENS EKOSYSTEM
          </div>
          <h1 style={{
            fontFamily: "Source Serif 4, Georgia, serif",
            fontSize: 32, color: "#fff", margin: "12px 0",
          }}>
            Klassens anställnings-ekosystem
          </h1>
          <p style={{ color: "rgba(255,255,255,0.7)" }}>
            Vem äger ett bolag, vem är anställd hos vem,
            och hur mycket pengar flödar i klassens ekonomi.
          </p>
        </header>

        {/* Statistik-kort */}
        <div style={{
          display: "grid", gap: 12,
          gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))",
          marginBottom: 28,
        }}>
          <StatCard label="Elever totalt" value={data.stats.n_students_total} />
          <StatCard label="Företagare" value={data.stats.n_employers} accent="#fbbf24" />
          <StatCard label="Aktiva anställningar" value={data.stats.n_active_employments} accent="#6ee7b7" />
          <StatCard label="Pending erbjudanden" value={data.stats.n_pending_offers} accent="#a78bfa" />
          <StatCard label="Uppsagda" value={data.stats.n_terminated} accent="#fda594" />
          <StatCard
            label="Payroll 30d"
            value={`${SEK(data.stats.total_payroll_paid_30d)} kr`}
            accent="#fbbf24"
          />
        </div>

        {/* Trend-graf · 12 veckor (Fas J) */}
        {trend && trend.length > 0 && (
          <section style={{ marginBottom: 32 }}>
            <h2 style={sectionHeaderStyle}>
              ● TREND · senaste 12 veckor
            </h2>
            <TrendChart trend={trend} />
          </section>
        )}

        {/* Företagare-grupper */}
        <section style={{ marginBottom: 32 }}>
          <h2 style={sectionHeaderStyle}>
            ● FÖRETAGARE & TEAM · {employers.length} aktiva bolag
          </h2>
          {employers.length === 0 ? (
            <div style={emptyStyle}>
              Ingen elev i klassen är företagare med klasskompis-anställda än.
            </div>
          ) : (
            <div style={{ display: "grid", gap: 14 }}>
              {employers.map((emp) => {
                const myEmployments = data.employments.filter(
                  (e) => e.owner_student_id === emp.student_id
                    && e.status === "active",
                );
                const totalMonthly = myEmployments.reduce(
                  (sum, e) => sum + e.monthly_gross, 0,
                );
                return (
                  <div key={emp.student_id} style={employerCardStyle}>
                    <div style={{ display: "flex", alignItems: "baseline", gap: 12 }}>
                      <div>
                        <div style={{
                          fontFamily: "Source Serif 4, Georgia, serif",
                          fontSize: 18, fontWeight: 700, color: "#fff",
                        }}>
                          {emp.company_name || "Onamngivet bolag"}
                        </div>
                        <div style={{
                          fontFamily: "JetBrains Mono, monospace",
                          fontSize: 10, color: "rgba(255,255,255,0.55)",
                          letterSpacing: 0.6, marginTop: 4,
                        }}>
                          {emp.display_name}
                          {emp.class_label ? ` · ${emp.class_label}` : ""}
                          · {emp.n_employees} anställd{emp.n_employees === 1 ? "" : "a"}
                          · {SEK(totalMonthly)} kr/mån i lönesumma
                        </div>
                      </div>
                    </div>
                    <ul style={{
                      margin: "10px 0 0", padding: 0,
                      listStyle: "none", display: "grid", gap: 6,
                    }}>
                      {myEmployments.map((e) => (
                        <li key={e.employment_id} style={{
                          fontFamily: "Inter, sans-serif",
                          fontSize: 13, color: "rgba(255,255,255,0.85)",
                          paddingLeft: 16,
                          borderLeft: "2px solid rgba(110,231,183,0.4)",
                        }}>
                          <strong>{nameOf(e.employee_student_id)}</strong>
                          {" · "}{e.role}
                          {" · "}
                          <span style={{
                            fontFamily: "JetBrains Mono, monospace",
                            fontSize: 11, color: "#fbbf24",
                          }}>
                            {SEK(e.monthly_gross)} kr/mån
                          </span>
                        </li>
                      ))}
                    </ul>
                  </div>
                );
              })}
            </div>
          )}
        </section>

        {/* Pending erbjudanden */}
        {data.stats.n_pending_offers > 0 && (
          <section style={{ marginBottom: 32 }}>
            <h2 style={{ ...sectionHeaderStyle, color: "#a78bfa" }}>
              ● PENDING ERBJUDANDEN · {data.stats.n_pending_offers}
            </h2>
            <div style={{ display: "grid", gap: 8 }}>
              {data.employments
                .filter((e) => e.status === "pending_offer")
                .map((e) => (
                  <div key={e.employment_id} style={edgeRowStyle}>
                    <strong>{nameOf(e.owner_student_id)}</strong> erbjöd
                    {" "}<strong>{nameOf(e.employee_student_id)}</strong>
                    {" "}rollen som <em>{e.role}</em>
                    {" · "}{SEK(e.monthly_gross)} kr/mån
                  </div>
                ))}
            </div>
          </section>
        )}

        {/* Avslutade anställningar */}
        {data.stats.n_terminated > 0 && (
          <section style={{ marginBottom: 32 }}>
            <h2 style={{ ...sectionHeaderStyle, color: "#fda594" }}>
              ● AVSLUTADE ANSTÄLLNINGAR · {data.stats.n_terminated}
            </h2>
            <div style={{ display: "grid", gap: 8 }}>
              {data.employments
                .filter((e) => e.status === "terminated")
                .map((e) => (
                  <div key={e.employment_id} style={edgeRowStyle}>
                    <strong>{nameOf(e.employee_student_id)}</strong> uppsagd från
                    {" "}<strong>{e.company_name}</strong>
                    {e.last_day && ` · sista dag ${e.last_day}`}
                  </div>
                ))}
            </div>
          </section>
        )}

        {/* Orphans · varken anställda eller företagare */}
        {orphans.length > 0 && (
          <section style={{ marginBottom: 32 }}>
            <h2 style={{ ...sectionHeaderStyle, color: "rgba(255,255,255,0.5)" }}>
              ● UTANFÖR EKOSYSTEMET · {orphans.length} elever
            </h2>
            <p style={{ color: "rgba(255,255,255,0.6)", fontSize: 13 }}>
              Dessa elever är varken anställda av eller anställer någon klasskompis.
              De jobbar fortfarande på sitt onboarding-yrke.
            </p>
            <div style={{
              display: "grid", gap: 6,
              gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))",
            }}>
              {orphans.map((s) => (
                <span key={s.student_id} style={{
                  padding: "6px 10px",
                  background: "rgba(15,21,37,0.5)",
                  border: "1px solid rgba(255,255,255,0.08)",
                  borderRadius: 6,
                  fontFamily: "Inter, sans-serif",
                  fontSize: 12, color: "rgba(255,255,255,0.7)",
                }}>
                  {s.display_name}
                </span>
              ))}
            </div>
          </section>
        )}
      </div>
    </div>
  );
}


function TrendChart({ trend }: { trend: StatsBucket[] }) {
  const maxEvents = Math.max(
    1,
    ...trend.map((b) =>
      b.n_hire_offered + b.n_accepted + b.n_declined
        + b.n_terminated + b.n_bankrupted
    ),
  );
  const maxPayroll = Math.max(1, ...trend.map((b) => b.payroll_paid));

  return (
    <div style={{
      padding: 18,
      background: "rgba(15,21,37,0.55)",
      border: "1px solid rgba(255,255,255,0.08)",
      borderRadius: 10,
    }}>
      <div style={{ display: "flex", gap: 4, alignItems: "flex-end", height: 140 }}>
        {trend.map((b) => {
          const totalEvents = b.n_hire_offered + b.n_accepted
            + b.n_declined + b.n_terminated + b.n_bankrupted;
          const h = (totalEvents / maxEvents) * 100;
          const payH = (b.payroll_paid / maxPayroll) * 100;
          return (
            <div key={b.week_start} style={{
              flex: 1, display: "flex", flexDirection: "column",
              gap: 2, height: "100%", justifyContent: "flex-end",
            }}>
              {/* Events bar (staplad) */}
              <div title={`Vecka ${b.week_start} · ${totalEvents} händelser`} style={{
                height: `${h}%`,
                display: "flex", flexDirection: "column",
                background: "rgba(255,255,255,0.05)",
                borderRadius: 3, overflow: "hidden",
                minHeight: totalEvents > 0 ? 2 : 0,
              }}>
                {b.n_bankrupted > 0 && (
                  <div style={{ flex: b.n_bankrupted, background: "#dc4c2b" }} />
                )}
                {b.n_terminated > 0 && (
                  <div style={{ flex: b.n_terminated, background: "#fda594" }} />
                )}
                {b.n_declined > 0 && (
                  <div style={{ flex: b.n_declined, background: "rgba(255,255,255,0.3)" }} />
                )}
                {b.n_accepted > 0 && (
                  <div style={{ flex: b.n_accepted, background: "#6ee7b7" }} />
                )}
                {b.n_hire_offered > 0 && (
                  <div style={{ flex: b.n_hire_offered, background: "#a78bfa" }} />
                )}
              </div>
              {/* Payroll-spår · liten gul markör */}
              <div title={`Payroll ${b.payroll_paid} kr`} style={{
                height: 6,
                width: "100%",
                background: b.payroll_paid > 0
                  ? `linear-gradient(to top, #fbbf24 ${payH}%, transparent ${payH}%)`
                  : "transparent",
                borderRadius: 2,
              }} />
            </div>
          );
        })}
      </div>
      {/* Legend */}
      <div style={{
        display: "flex", gap: 14, flexWrap: "wrap",
        marginTop: 14, fontFamily: "JetBrains Mono, monospace",
        fontSize: 10, color: "rgba(255,255,255,0.7)",
      }}>
        <Legend color="#a78bfa" label="Erbjudande skickat" />
        <Legend color="#6ee7b7" label="Accepterat" />
        <Legend color="rgba(255,255,255,0.3)" label="Nekat" />
        <Legend color="#fda594" label="Uppsagd" />
        <Legend color="#dc4c2b" label="Konkurs" />
        <Legend color="#fbbf24" label="Payroll-volym (proportionellt)" />
      </div>
      <div style={{
        display: "flex", justifyContent: "space-between",
        marginTop: 6, fontFamily: "JetBrains Mono, monospace",
        fontSize: 9, color: "rgba(255,255,255,0.45)",
      }}>
        <span>{trend[0]?.week_start}</span>
        <span>{trend[trend.length - 1]?.week_start}</span>
      </div>
    </div>
  );
}


function Legend({ color, label }: { color: string; label: string }) {
  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
      <span style={{
        width: 10, height: 10, background: color,
        borderRadius: 2, display: "inline-block",
      }} />
      {label}
    </span>
  );
}


function StatCard({
  label, value, accent,
}: {
  label: string;
  value: string | number;
  accent?: string;
}) {
  return (
    <div style={{
      padding: 14,
      background: "rgba(15,21,37,0.55)",
      border: "1px solid rgba(255,255,255,0.08)",
      borderRadius: 10,
    }}>
      <div style={{
        fontFamily: "JetBrains Mono, monospace",
        fontSize: 9.5, letterSpacing: 1.2,
        color: "rgba(199,210,254,0.7)",
      }}>
        {label.toUpperCase()}
      </div>
      <div style={{
        fontFamily: "Source Serif 4, Georgia, serif",
        fontSize: 26, fontWeight: 700,
        color: accent || "#fff",
        marginTop: 4,
      }}>
        {value}
      </div>
    </div>
  );
}


const sectionHeaderStyle: React.CSSProperties = {
  fontFamily: "JetBrains Mono, monospace",
  fontSize: 11, fontWeight: 700, letterSpacing: 1.5,
  color: "#c7d2fe", textTransform: "uppercase",
  marginBottom: 14,
};

const employerCardStyle: React.CSSProperties = {
  padding: 18,
  background: "linear-gradient(135deg, rgba(251,191,36,0.05), rgba(15,21,37,0.55))",
  border: "1px solid rgba(251,191,36,0.25)",
  borderRadius: 10,
};

const edgeRowStyle: React.CSSProperties = {
  padding: "10px 14px",
  background: "rgba(15,21,37,0.5)",
  border: "1px solid rgba(255,255,255,0.06)",
  borderRadius: 6,
  fontFamily: "Inter, sans-serif",
  fontSize: 13, color: "rgba(255,255,255,0.85)",
};

const emptyStyle: React.CSSProperties = {
  padding: "32px 24px", textAlign: "center",
  background: "rgba(15,21,37,0.5)",
  border: "1px dashed rgba(255,255,255,0.15)",
  borderRadius: 10, color: "rgba(255,255,255,0.7)",
  fontFamily: "Source Serif 4, Georgia, serif",
};
