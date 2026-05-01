/**
 * Lärar-vy · full insyn i en elevs Mina moduler.
 *
 * Använder /v2/teacher/students/{id}/moduler-overview. Lärare ser
 * pågående + klara + tillgängliga moduler för en specifik elev.
 *
 * Routas via /teacher/v2/moduler/:studentId.
 */
import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import {
  v2Api,
  type V2TeacherModulerOverview,
} from "./api";
import { V2Banner } from "./V2Banner";
import "./lan.css";

const SHORT_DATE = (iso: string | null): string => {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleDateString("sv-SE", {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
};

export function TeacherModulerOverviewPage() {
  const { studentId } = useParams<{ studentId: string }>();
  const sid = studentId ? parseInt(studentId, 10) : 0;
  const [data, setData] = useState<V2TeacherModulerOverview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const navigate = useNavigate();

  useEffect(() => {
    if (!sid) return;
    v2Api
      .teacherModulerOverview(sid)
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
              Kunde inte ladda moduler
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
        <div className="bank-loading">Laddar moduler…</div>
      </div>
    );
  }

  const m = data.moduler;
  const s = m.summary;
  const stallFlag =
    s.in_progress_count > 0 &&
    s.last_activity_at != null &&
    new Date(s.last_activity_at).getTime() <
      Date.now() - 14 * 24 * 60 * 60 * 1000;

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
            <span className="pill warm">Lärar-vy · Mina moduler</span>
            <h1 className="actor-name" style={{ marginTop: 14 }}>
              {data.student_name}s <em>moduler</em>.
            </h1>
            <p className="actor-sub">
              {s.in_progress_count} pågår · {s.completed_count} klara ·{" "}
              {s.available_count} tillgängliga ·{" "}
              {stallFlag ? (
                <strong style={{ color: "#fda594" }}>
                  ▲ ingen aktivitet på 14+ dagar
                </strong>
              ) : (
                <span>
                  senast aktiv {SHORT_DATE(s.last_activity_at)}
                </span>
              )}
            </p>
          </div>
          <div className="actor-meta">
            Snitt-progress:{" "}
            <strong>{Math.round(s.avg_progress_pct)} %</strong>
            <br />
            Wellbeing:{" "}
            <strong style={{ color: "var(--warm)" }}>
              {s.completed_count > 0
                ? `+${Math.min(6, s.completed_count * 2)} leisure`
                : s.in_progress_count > 0
                ? "+1 leisure"
                : "0"}
            </strong>
            <br />
            Senast: <strong>{SHORT_DATE(s.last_activity_at)}</strong>
          </div>
        </header>

        {/* SAMMANFATTNING */}
        <div className="acct-grid">
          <div className="acct active">
            <div>
              <div className="acct-eye">Pågående</div>
              <div className="acct-name">{s.in_progress_count}</div>
              <div className="acct-num">moduler i arbete</div>
            </div>
            <div>
              <div className="acct-bal">
                {Math.round(s.avg_progress_pct)} %
              </div>
              <div className="acct-bal-meta">snitt</div>
            </div>
          </div>
          <div className="acct">
            <div>
              <div className="acct-eye">Klara</div>
              <div
                className="acct-name"
                style={{
                  color: s.completed_count > 0 ? "#6ee7b7" : "#fff",
                }}
              >
                {s.completed_count}
              </div>
              <div className="acct-num">slutförda hittills</div>
            </div>
            <div>
              <div className="acct-bal">
                {s.completed_count + s.in_progress_count}
              </div>
              <div className="acct-bal-meta">tilldelade</div>
            </div>
          </div>
          <div className="acct">
            <div>
              <div className="acct-eye">Tillgängliga</div>
              <div className="acct-name">{s.available_count}</div>
              <div className="acct-num">mallar att tilldela</div>
            </div>
            <div>
              <div
                className="acct-bal"
                style={{ color: stallFlag ? "#fda594" : "#fff" }}
              >
                {s.last_activity_at
                  ? Math.floor(
                      (Date.now() -
                        new Date(s.last_activity_at).getTime()) /
                        86400000,
                    )
                  : "—"}
              </div>
              <div className="acct-bal-meta">dagar sedan aktivitet</div>
            </div>
          </div>
          <div className="acct">
            <div>
              <div className="acct-eye">Wellbeing</div>
              <div
                className="acct-name"
                style={{ color: "var(--warm)" }}
              >
                {s.completed_count > 0
                  ? `+${Math.min(6, s.completed_count * 2)}`
                  : s.in_progress_count > 0
                  ? "+1"
                  : "0"}
              </div>
              <div className="acct-num">leisure (lärande)</div>
            </div>
            <div>
              <div className="acct-bal">{s.completed_count * 2}</div>
              <div className="acct-bal-meta">max bonus</div>
            </div>
          </div>
        </div>

        <div className="act-grid">
          <div>
            {/* PÅGÅENDE */}
            <div className="section-eye">
              Pågående moduler ({m.in_progress.length})
            </div>
            {m.in_progress.length === 0 ? (
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
                Inga moduler pågår just nu.
              </div>
            ) : (
              <div className="biz-table" style={{ marginBottom: 22 }}>
                <div
                  className="biz-table-row head"
                  style={{
                    gridTemplateColumns: "1.6fr 90px 90px 100px 90px",
                  }}
                >
                  <span>Modul</span>
                  <span>Steg</span>
                  <span>Progress</span>
                  <span>Tilldelad</span>
                  <span>Källa</span>
                </div>
                {m.in_progress.map((row) => (
                  <div
                    className="biz-table-row"
                    key={row.student_module_id}
                    style={{
                      gridTemplateColumns: "1.6fr 90px 90px 100px 90px",
                    }}
                  >
                    <div>
                      <div
                        style={{
                          fontFamily: "var(--serif)",
                          fontSize: 13,
                        }}
                      >
                        {row.title}
                      </div>
                      {row.summary && (
                        <div
                          style={{
                            fontFamily: "var(--mono)",
                            fontSize: 9,
                            color: "var(--text-dim)",
                          }}
                        >
                          {row.summary}
                        </div>
                      )}
                    </div>
                    <span style={{ fontFamily: "var(--mono)", fontSize: 11 }}>
                      {row.completed_step_count}/{row.step_count}
                    </span>
                    <span
                      style={{ fontFamily: "var(--mono)", fontSize: 11 }}
                    >
                      <div
                        style={{
                          height: 4,
                          background: "rgba(255,255,255,0.06)",
                          borderRadius: 100,
                          marginBottom: 3,
                        }}
                      >
                        <div
                          style={{
                            height: "100%",
                            width: `${row.progress_pct}%`,
                            background: "var(--warm)",
                            borderRadius: 100,
                          }}
                        />
                      </div>
                      {row.progress_pct} %
                    </span>
                    <span
                      style={{
                        fontFamily: "var(--mono)",
                        fontSize: 10,
                        color: "var(--text-mid)",
                      }}
                    >
                      {SHORT_DATE(row.assigned_at)}
                    </span>
                    <span
                      style={{
                        fontFamily: "var(--mono)",
                        fontSize: 9,
                        color: row.is_template
                          ? "var(--text-dim)"
                          : "var(--warm)",
                        letterSpacing: "0.6px",
                        textTransform: "uppercase",
                      }}
                    >
                      {row.is_template
                        ? "system"
                        : row.teacher_owned
                        ? "egen"
                        : "—"}
                    </span>
                  </div>
                ))}
              </div>
            )}

            {/* KLARA */}
            <div className="section-eye">
              Klara moduler ({m.completed.length})
            </div>
            {m.completed.length === 0 ? (
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
                Inga klara moduler än.
              </div>
            ) : (
              <div className="biz-table" style={{ marginBottom: 22 }}>
                <div
                  className="biz-table-row head"
                  style={{
                    gridTemplateColumns: "1.6fr 80px 110px 90px",
                  }}
                >
                  <span>Modul</span>
                  <span>Steg</span>
                  <span>Klar</span>
                  <span>Källa</span>
                </div>
                {m.completed.map((row) => (
                  <div
                    className="biz-table-row"
                    key={row.student_module_id}
                    style={{
                      gridTemplateColumns: "1.6fr 80px 110px 90px",
                    }}
                  >
                    <span style={{ fontFamily: "var(--serif)", fontSize: 13 }}>
                      {row.title}
                    </span>
                    <span style={{ fontFamily: "var(--mono)", fontSize: 11 }}>
                      {row.step_count}/{row.step_count}
                    </span>
                    <span
                      style={{
                        fontFamily: "var(--mono)",
                        fontSize: 11,
                        color: "#6ee7b7",
                      }}
                    >
                      {SHORT_DATE(row.completed_at)}
                    </span>
                    <span
                      style={{
                        fontFamily: "var(--mono)",
                        fontSize: 9,
                        color: row.is_template
                          ? "var(--text-dim)"
                          : "var(--warm)",
                        letterSpacing: "0.6px",
                        textTransform: "uppercase",
                      }}
                    >
                      {row.is_template
                        ? "system"
                        : row.teacher_owned
                        ? "egen"
                        : "—"}
                    </span>
                  </div>
                ))}
              </div>
            )}

            {/* TILLGÄNGLIGA */}
            <div className="section-eye">
              Tillgängliga mallar ({m.available.length})
            </div>
            {m.available.length === 0 ? (
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
                Inga mallar tillgängliga. Skapa egna i lärar-vyn
                /teacher/modules.
              </div>
            ) : (
              <div className="biz-table">
                <div
                  className="biz-table-row head"
                  style={{
                    gridTemplateColumns: "1.6fr 80px 80px 90px",
                  }}
                >
                  <span>Mall</span>
                  <span>Steg</span>
                  <span>Min</span>
                  <span>Källa</span>
                </div>
                {m.available.map((row) => (
                  <div
                    className="biz-table-row"
                    key={`av-${row.module_id}`}
                    style={{
                      gridTemplateColumns: "1.6fr 80px 80px 90px",
                    }}
                  >
                    <div>
                      <div style={{ fontFamily: "var(--serif)", fontSize: 13 }}>
                        {row.title}
                      </div>
                      {row.summary && (
                        <div
                          style={{
                            fontFamily: "var(--mono)",
                            fontSize: 9,
                            color: "var(--text-dim)",
                          }}
                        >
                          {row.summary}
                        </div>
                      )}
                    </div>
                    <span style={{ fontFamily: "var(--mono)", fontSize: 11 }}>
                      {row.step_count}
                    </span>
                    <span style={{ fontFamily: "var(--mono)", fontSize: 11 }}>
                      ~ {row.estimated_total_minutes}
                    </span>
                    <span
                      style={{
                        fontFamily: "var(--mono)",
                        fontSize: 9,
                        color: row.is_template
                          ? "var(--text-dim)"
                          : "var(--warm)",
                        letterSpacing: "0.6px",
                        textTransform: "uppercase",
                      }}
                    >
                      {row.is_template
                        ? "system"
                        : row.teacher_owned
                        ? "egen"
                        : "—"}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </div>

          <aside>
            {stallFlag && (
              <div
                className="side-card"
                style={{
                  background: "rgba(220,76,43,0.06)",
                  borderColor: "rgba(220,76,43,0.25)",
                }}
              >
                <div
                  className="side-card-eye"
                  style={{ color: "var(--accent)" }}
                >
                  ▲ Inaktivitet
                </div>
                <div className="side-card-h">
                  Ingen aktivitet på <em>14+ dagar</em>
                </div>
                <div className="side-card-meta">
                  Eleven har påbörjade moduler men inte rört dem på 2+
                  veckor. Pratstund? Pinga eller tilldela en kortare
                  modul som tar 15 min.
                </div>
              </div>
            )}
            <div className="side-card">
              <div className="side-card-eye">Wellbeing-effekt</div>
              <div className="side-card-h">
                Moduler <em>räknas</em>
              </div>
              <div className="side-card-meta">
                Klar modul → +2 leisure (max +6 vid 3+ klara). 1+
                pågående utan klar → +1 leisure. Lärande är frigörande
                — inte stress.
              </div>
            </div>
            <div className="side-card">
              <div className="side-card-eye">Tilldela ny modul</div>
              <div className="side-card-h">
                Via <em>lärar-modul-vyn</em>
              </div>
              <div className="side-card-meta">
                /teacher/modules visar hela ditt biblio. Skapa en egen
                eller klona en systemmall, sen tilldela till denna elev.
              </div>
              <a
                href="/teacher/modules"
                className="side-card-link"
                style={{ textDecoration: "none" }}
              >
                Öppna lärar-moduler ↗
              </a>
            </div>
          </aside>
        </div>
      </div>
    </div>
  );
}
