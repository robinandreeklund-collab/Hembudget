/**
 * Lärar-vy · elev-detalj (motsv. larare.html#p-elev).
 *
 * Routas via /teacher/v2/elev/:studentId.
 *
 * Pekar på /v2/teacher/students/{id}/student-detail som aggregerar
 * pentagon, pågående moduler, senaste händelser, kompetens-grid,
 * nivå-progression, pågående lönesamtal, uppdrag-summary, postlåda.
 */
import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import {
  v2Api,
  type V2TeacherStudentDetail,
  type V2StudentDetailModule,
  type V2StudentDetailEvent,
  type V2StudentDetailCompetency,
} from "./api";
import { V2Banner } from "./V2Banner";
import "./larare.css";

const SHORT_DATE = (iso: string | null): string => {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleDateString("sv-SE", {
    day: "numeric",
    month: "short",
  });
};

const SHORT_DATETIME = (iso: string | null): string => {
  if (!iso) return "—";
  const d = new Date(iso);
  const today = new Date();
  const sameDay =
    d.getFullYear() === today.getFullYear()
    && d.getMonth() === today.getMonth()
    && d.getDate() === today.getDate();
  if (sameDay) {
    return d.toLocaleTimeString("sv-SE", {
      hour: "2-digit",
      minute: "2-digit",
    });
  }
  return d.toLocaleDateString("sv-SE", {
    day: "numeric",
    month: "short",
  });
};

function pentagonPoints(
  cx: number, cy: number, radius: number, values: number[],
): string {
  const angles = [-90, -18, 54, 126, 198];
  return values
    .map((v, i) => {
      const r = (radius * Math.max(0, Math.min(100, v))) / 100;
      const a = (angles[i] * Math.PI) / 180;
      const x = cx + r * Math.cos(a);
      const y = cy + r * Math.sin(a);
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");
}

const LEVEL_COLOR_CLASS: Record<number, string> = {
  1: "l1",
  2: "l2",
  3: "l3",
};

const LEVEL_BAR: Record<number, string> = {
  1: "▰▱▱",
  2: "▰▰▱",
  3: "▰▰▰",
};

export function TeacherStudentDetailV2() {
  const { studentId } = useParams<{ studentId: string }>();
  const sid = studentId ? parseInt(studentId, 10) : 0;
  const [data, setData] = useState<V2TeacherStudentDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const navigate = useNavigate();

  useEffect(() => {
    if (!sid) return;
    v2Api
      .teacherStudentDetail(sid)
      .then(setData)
      .catch((e) => setError(String((e as Error)?.message || e)));
  }, [sid]);

  if (error) {
    return (
      <div className="v2-larare-root">
        <V2Banner status={{ role: "teacher", is_super_admin: false }} />
        <div className="larare-loading">
          <div>
            <div style={{ color: "#fca5a5", marginBottom: 8 }}>
              Kunde inte ladda elev
            </div>
            <pre style={{ fontSize: 11 }}>{error}</pre>
          </div>
        </div>
      </div>
    );
  }
  if (!data) {
    return (
      <div className="v2-larare-root">
        <V2Banner status={{ role: "teacher", is_super_admin: false }} />
        <div className="larare-loading">Laddar elev-detalj…</div>
      </div>
    );
  }

  return (
    <div className="v2-larare-root">
      <V2Banner status={{ role: "teacher", is_super_admin: false }} />

      <div className="shell">
        <a
          className="attn-go"
          onClick={(e) => {
            e.preventDefault();
            navigate("/teacher/v2");
          }}
          href="#"
          style={{ marginBottom: 22, display: "inline-block" }}
        >
          ← Tillbaka till klassen
        </a>

        <Header data={data} />
        <ActionBar data={data} navigate={navigate} />
        {data.level_progression.ready_for_promotion && (
          <PromotionCard data={data} />
        )}

        <div className="class-stage">
          <StudentPentagon data={data} />
          <StudentSideStack data={data} />
        </div>

        <CompetencyGrid competencies={data.competencies} sid={data.student_id} />

        {data.recent_events.length > 0 && (
          <RecentEvents events={data.recent_events} />
        )}
      </div>
    </div>
  );
}

function Header({ data }: { data: V2TeacherStudentDetail }) {
  const cls = LEVEL_COLOR_CLASS[data.v2_level] || "l1";
  const inactivity =
    data.days_since_last_login === null
      ? "ej inloggad"
      : data.days_since_last_login === 0
      ? "nu"
      : `${data.days_since_last_login} d sedan`;
  const negText = data.pending_negotiation
    ? `runda ${data.pending_negotiation.round_no}/${data.pending_negotiation.max_rounds}`
    : "—";
  return (
    <header className="larare-head">
      <div>
        <span className="pill">Elev · {data.student_name}</span>
        <span
          className={`level-badge ${cls}`}
          style={{
            marginLeft: 8,
            display: "inline-flex",
            alignItems: "center",
            gap: 6,
            fontFamily: "JetBrains Mono, monospace",
            fontSize: 9,
            fontWeight: 700,
            padding: "4px 10px",
            borderRadius: 100,
            letterSpacing: 1.2,
            textTransform: "uppercase",
            background:
              data.v2_level === 1
                ? "rgba(110,231,183,0.18)"
                : data.v2_level === 2
                ? "rgba(251,191,36,0.18)"
                : "rgba(220,76,43,0.18)",
            color:
              data.v2_level === 1
                ? "#6ee7b7"
                : data.v2_level === 2
                ? "var(--warm)"
                : "#fda594",
            border: `1px solid ${
              data.v2_level === 1
                ? "rgba(110,231,183,0.35)"
                : data.v2_level === 2
                ? "rgba(251,191,36,0.35)"
                : "rgba(220,76,43,0.35)"
            }`,
          }}
        >
          {LEVEL_BAR[data.v2_level]} Nivå {data.v2_level} · {data.v2_level_label}
        </span>
        <h1 className="larare-head-h1">
          {data.student_name} — <em>balans {data.pentagon.total_score}</em>.
        </h1>
        <p
          style={{
            fontFamily: "Source Serif 4, Georgia, serif",
            fontSize: 16,
            color: "rgba(255,255,255,0.6)",
            marginTop: 12,
          }}
        >
          Kod: …{data.login_code_suffix} · pågående{" "}
          {data.active_modules.length} moduler ·{" "}
          {data.level_progression.ready_for_promotion ? (
            <em style={{ color: "#6ee7b7", fontStyle: "italic" }}>
              redo för Nivå {data.level_progression.target_level}
            </em>
          ) : (
            <span>
              Nivå {data.v2_level} · {data.level_progression.progress_pct} %
              progression
            </span>
          )}
        </p>
      </div>
      <div className="larare-head-meta">
        Senast inloggad <strong>{inactivity}</strong>
        <br />
        Lönesamtal: <strong>{negText}</strong>
        <br />
        Uppdrag · {data.assignments.active_count} aktiva
        {data.assignments.overdue_count > 0
          ? ` · ${data.assignments.overdue_count} försenade`
          : ""}
      </div>
    </header>
  );
}

function ActionBar({
  data,
  navigate,
}: {
  data: V2TeacherStudentDetail;
  navigate: ReturnType<typeof useNavigate>;
}) {
  return (
    <div
      style={{
        display: "flex",
        gap: 10,
        flexWrap: "wrap",
        marginBottom: 24,
      }}
    >
      <Link
        className="larare-tb-btn solid"
        to={`/teacher/v2/portfolio/${data.student_id}`}
      >
        Portfolio →
      </Link>
      <Link
        className="larare-tb-btn"
        to={`/teacher/v2/uppdrag/${data.student_id}`}
      >
        Uppdrag ({data.assignments.active_count})
      </Link>
      <Link
        className="larare-tb-btn"
        to={`/teacher/v2/feedback/${data.student_id}`}
      >
        Feedback-historik
      </Link>
      <Link
        className="larare-tb-btn"
        to={`/teacher/v2/messages/${data.student_id}`}
      >
        Meddelanden
      </Link>
      {data.pending_negotiation && (
        <button
          type="button"
          className="larare-tb-btn"
          onClick={() =>
            navigate(`/teacher/v2/maria/${data.student_id}`)
          }
          style={{
            background: "rgba(99,102,241,0.18)",
            color: "#c7d2fe",
            borderColor: "rgba(99,102,241,0.45)",
          }}
        >
          Maria · runda {data.pending_negotiation.round_no} →
        </button>
      )}
      <Link
        className="larare-tb-btn"
        to={`/teacher/v2/historik/${data.student_id}`}
        style={{
          background: "rgba(99,102,241,0.18)",
          color: "#c7d2fe",
          borderColor: "rgba(99,102,241,0.45)",
        }}
      >
        Aktivitets-historik →
      </Link>
    </div>
  );
}

function PromotionCard({ data }: { data: V2TeacherStudentDetail }) {
  const lp = data.level_progression;
  const grundOrFordjup = data.competencies.filter(
    (c) => c.level !== "B",
  ).length;
  return (
    <article
      className="s-card green"
      style={{
        background:
          "linear-gradient(135deg, rgba(110,231,183,0.06), rgba(15,21,37,0.5))",
        marginBottom: 24,
      }}
    >
      <div className="s-card-eye green">Nivå-progression</div>
      <div className="s-card-h">
        {data.student_name} är{" "}
        <em className="green" style={{ color: "#6ee7b7" }}>
          redo för Nivå {lp.target_level}
        </em>
        .
      </div>
      <p
        style={{
          fontFamily: "Source Serif 4, Georgia, serif",
          fontSize: 14,
          color: "rgba(255,255,255,0.6)",
          lineHeight: 1.5,
          marginBottom: 12,
        }}
      >
        {lp.weeks_at_level} veckor på Nivå {lp.current_level} (
        {data.v2_level_label}). Pent-balans {data.pentagon.total_score}.{" "}
        {grundOrFordjup} kompetenser till GRUND eller högre.{" "}
        {data.completed_modules_count} avslutade moduler.
      </p>
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(4, 1fr)",
          gap: 10,
          marginBottom: 14,
        }}
      >
        <PromoCell label="på nivån" value={`${lp.weeks_at_level} v`} />
        <PromoCell label="kompetenser" value={`${grundOrFordjup} G+`} />
        <PromoCell
          label="moduler klara"
          value={`${data.completed_modules_count}`}
        />
        <PromoCell
          label="krav uppfyllda"
          value={`${lp.requirements_met}/${lp.requirements_total}`}
        />
      </div>
      <div
        style={{
          fontFamily: "JetBrains Mono, monospace",
          fontSize: 10,
          color: "rgba(255,255,255,0.5)",
          letterSpacing: 0.5,
        }}
      >
        Vid aktivering:{" "}
        <strong style={{ color: "#fff" }}>
          eleven behåller karaktären
        </strong>{" "}
        men får svårare ekonomi · spendprofilen byts till{" "}
        <em style={{ color: "var(--warm)", fontStyle: "italic" }}>
          {lp.target_level === 2 ? "Balanserad" : "Slösa"}
        </em>{" "}
        · fler oväntade brev.
      </div>
    </article>
  );
}

function PromoCell({ label, value }: { label: string; value: string }) {
  return (
    <div
      style={{
        textAlign: "center",
        padding: 10,
        background: "rgba(110,231,183,0.10)",
        borderRadius: 6,
      }}
    >
      <div
        style={{
          fontFamily: "Source Serif 4, Georgia, serif",
          fontStyle: "italic",
          fontWeight: 700,
          color: "#6ee7b7",
          fontSize: 18,
        }}
      >
        {value}
      </div>
      <div
        style={{
          fontFamily: "JetBrains Mono, monospace",
          fontSize: 9,
          color: "rgba(255,255,255,0.6)",
        }}
      >
        {label}
      </div>
    </div>
  );
}

function StudentPentagon({ data }: { data: V2TeacherStudentDetail }) {
  const p = data.pentagon;
  const radius = 230;
  const cx = 300;
  const cy = 300;
  const values = [p.economy, p.safety, p.health, p.social, p.leisure];
  const ringValues = [100, 75, 50, 25];
  return (
    <article className="class-pent">
      <div className="class-pent-eye">
        {data.student_name}s pentagon · live från scope-DB
      </div>
      <h2 className="class-pent-h">
        Tippad <em>mot {p.tipped_towards}</em>.
      </h2>
      <svg className="pent-svg" viewBox="0 0 600 600">
        {ringValues.map((rv) => (
          <polygon
            key={rv}
            className="p-axis-line"
            points={pentagonPoints(cx, cy, radius, [rv, rv, rv, rv, rv])}
          />
        ))}
        {[0, 1, 2, 3, 4].map((i) => {
          const a =
            (([-90, -18, 54, 126, 198][i] as number) * Math.PI) / 180;
          const x2 = cx + radius * Math.cos(a);
          const y2 = cy + radius * Math.sin(a);
          return (
            <line
              key={i}
              className="p-axis-line"
              x1={cx}
              y1={cy}
              x2={x2.toFixed(1)}
              y2={y2.toFixed(1)}
            />
          );
        })}
        <polygon
          className="p-class"
          points={pentagonPoints(cx, cy, radius, values)}
        />
        <text
          x={cx}
          y={cy + 6}
          textAnchor="middle"
          fontFamily="Source Serif 4"
          fontStyle="italic"
          fontWeight="700"
          fontSize="64"
          fill="#fbbf24"
        >
          {p.total_score}
        </text>
      </svg>
      <div className="axis-tags">
        <span>
          Ekonomi
          <strong>{p.economy}</strong>
        </span>
        <span>
          Karriär
          <strong>{p.safety}</strong>
        </span>
        <span>
          Hälsa
          <strong>{p.health}</strong>
        </span>
        <span>
          Relation
          <strong>{p.social}</strong>
        </span>
        <span>
          Fritid
          <strong>{p.leisure}</strong>
        </span>
      </div>
    </article>
  );
}

function StudentSideStack({ data }: { data: V2TeacherStudentDetail }) {
  return (
    <aside className="side-stack">
      {/* Pågående moduler */}
      <div className="s-card">
        <div className="s-card-eye">Pågående moduler</div>
        <div className="s-card-h">
          {data.active_modules.length === 0
            ? "Inga aktiva"
            : `${data.active_modules.length} i `}
          {data.active_modules.length > 0 && <em>arbete</em>}
        </div>
        {data.active_modules.length === 0 ? (
          <p
            style={{
              fontFamily: "Source Serif 4, Georgia, serif",
              fontSize: 13,
              color: "rgba(255,255,255,0.5)",
              lineHeight: 1.5,
              margin: "0 0 0",
            }}
          >
            Eleven har inga pågående moduler. Tilldela en via lärar-
            dashboarden för att starta nästa lärande-resa.
          </p>
        ) : (
          <ul className="attn-list">
            {data.active_modules.map((m) => (
              <ModuleListItem key={m.student_module_id} m={m} />
            ))}
          </ul>
        )}
      </div>

      {/* Senaste händelser */}
      <div className="s-card">
        <div className="s-card-eye">Senaste händelser i elevens vy</div>
        <div className="s-card-h">
          {data.recent_events.length === 0
            ? "Inga händelser"
            : SHORT_DATETIME(data.recent_events[0].occurred_at)}
        </div>
        {data.recent_events.length === 0 ? (
          <p
            style={{
              fontFamily: "Source Serif 4, Georgia, serif",
              fontSize: 13,
              color: "rgba(255,255,255,0.5)",
              margin: 0,
            }}
          >
            Inga aktiviteter senaste 30 dgr.
          </p>
        ) : (
          <ul className="attn-list">
            {data.recent_events.slice(0, 5).map((ev, i) => (
              <li key={i}>
                <div>
                  <div className="attn-name">{ev.summary}</div>
                  <div className="attn-why">
                    {SHORT_DATETIME(ev.occurred_at)}
                    {ev.detail ? ` · ${ev.detail}` : ""}
                  </div>
                </div>
                {ev.badge && (
                  <span
                    style={{
                      fontFamily: "JetBrains Mono, monospace",
                      fontSize: 9,
                      color: "var(--warm)",
                      letterSpacing: 1,
                    }}
                  >
                    {ev.badge}
                  </span>
                )}
              </li>
            ))}
          </ul>
        )}
      </div>

      {/* Postlåda */}
      {data.mailbox_unhandled_count > 0 && (
        <div className="s-card alert">
          <div className="s-card-eye accent">Postlådan</div>
          <div className="s-card-h">
            {data.mailbox_unhandled_count} <em>ohanterade</em> brev
          </div>
          <p
            style={{
              fontFamily: "Source Serif 4, Georgia, serif",
              fontSize: 13,
              color: "rgba(255,255,255,0.6)",
              margin: 0,
            }}
          >
            {data.mailbox_oldest_days != null
              ? `Äldsta är ${data.mailbox_oldest_days} dgr gammalt. `
              : ""}
            Eleven måste granska och bokföra dessa innan auto-status
            uppdateras.
          </p>
        </div>
      )}

      {/* Nivå-progression-blockare */}
      {!data.level_progression.ready_for_promotion
        && data.v2_level < 3
        && data.level_progression.blockers.length > 0 && (
          <div className="s-card">
            <div className="s-card-eye">
              Krav för Nivå {data.level_progression.target_level}
            </div>
            <div className="s-card-h">
              {data.level_progression.requirements_met} av{" "}
              {data.level_progression.requirements_total}
            </div>
            <ul
              style={{
                listStyle: "none",
                padding: 0,
                margin: 0,
                fontFamily: "JetBrains Mono, monospace",
                fontSize: 10.5,
              }}
            >
              {data.level_progression.blockers.map((b, i) => (
                <li
                  key={i}
                  style={{
                    padding: "5px 0",
                    color: "var(--warm)",
                    letterSpacing: 0.4,
                  }}
                >
                  ○ {b}
                </li>
              ))}
            </ul>
          </div>
        )}

      {/* Karaktär */}
      {(data.spend_profile || data.fairness_choice || data.partner_model) && (
        <div className="s-card purple">
          <div className="s-card-eye purple">Karaktär från onboarding</div>
          <div className="s-card-h">Profil-val</div>
          <div
            style={{
              fontFamily: "JetBrains Mono, monospace",
              fontSize: 10.5,
              color: "rgba(255,255,255,0.7)",
              lineHeight: 1.7,
            }}
          >
            {data.spend_profile && (
              <div>
                ▸ Spend-profil:{" "}
                <strong style={{ color: "#fff" }}>
                  {data.spend_profile}
                </strong>
              </div>
            )}
            {data.fairness_choice && (
              <div>
                ▸ Rättvisa-val:{" "}
                <strong style={{ color: "#fff" }}>
                  {data.fairness_choice}
                </strong>
              </div>
            )}
            {data.partner_model && (
              <div>
                ▸ Partner:{" "}
                <strong style={{ color: "#fff" }}>
                  {data.partner_model}
                </strong>
              </div>
            )}
          </div>
        </div>
      )}
    </aside>
  );
}

function ModuleListItem({ m }: { m: V2StudentDetailModule }) {
  return (
    <li>
      <div>
        <div className="attn-name">{m.title}</div>
        <div className="attn-why">
          steg {m.completed_steps} / {m.total_steps} · {m.progress_pct} %
          {m.next_step_title ? ` · nästa: ${m.next_step_title}` : ""}
        </div>
      </div>
      <span
        style={{
          fontFamily: "JetBrains Mono, monospace",
          fontSize: 10,
          color: "var(--warm)",
        }}
      >
        {m.last_activity_at ? SHORT_DATE(m.last_activity_at) : "—"}
      </span>
    </li>
  );
}

function CompetencyGrid({
  competencies,
  sid,
}: {
  competencies: V2StudentDetailCompetency[];
  sid: number;
}) {
  const counts = useMemo(() => {
    const out = { B: 0, G: 0, F: 0 };
    for (const c of competencies) {
      out[c.level] += 1;
    }
    return out;
  }, [competencies]);
  if (competencies.length === 0) return null;
  return (
    <div style={{ marginBottom: 36 }}>
      <div className="section-title">
        Kompetenser · {competencies.length} st · {counts.F} F · {counts.G}{" "}
        G · {counts.B} B
      </div>
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))",
          gap: 8,
        }}
      >
        {competencies.map((c) => (
          <Link
            key={c.competency_id}
            to={`/teacher/v2/kompetens/${sid}/${c.competency_id}`}
            style={{
              padding: "12px 14px",
              background: "rgba(15,21,37,0.7)",
              border: "1px solid var(--line, rgba(255,255,255,0.1))",
              borderLeftWidth: 3,
              borderLeftColor:
                c.level === "F"
                  ? "#6ee7b7"
                  : c.level === "G"
                  ? "var(--accent, #dc4c2b)"
                  : "var(--text-dim, rgba(255,255,255,0.4))",
              borderRadius: 4,
              textDecoration: "none",
              display: "flex",
              flexDirection: "column",
              gap: 2,
            }}
          >
            <div
              style={{
                fontFamily: "Source Serif 4, Georgia, serif",
                fontSize: 13.5,
                color: "#fff",
              }}
            >
              {c.name}
            </div>
            <div
              style={{
                fontFamily: "JetBrains Mono, monospace",
                fontSize: 9.5,
                color:
                  c.level === "F"
                    ? "#6ee7b7"
                    : c.level === "G"
                    ? "var(--accent, #dc4c2b)"
                    : "var(--text-dim, rgba(255,255,255,0.4))",
                letterSpacing: 1.2,
                textTransform: "uppercase",
              }}
            >
              {c.level} · {c.level_label} · {Math.round(c.mastery * 100)} %
            </div>
          </Link>
        ))}
      </div>
    </div>
  );
}

function RecentEvents({ events }: { events: V2StudentDetailEvent[] }) {
  return (
    <div style={{ marginBottom: 36 }}>
      <div className="section-title">
        Aktivitets-flöde · senaste 30 dgr ({events.length})
      </div>
      <div
        style={{
          background: "rgba(15,21,37,0.7)",
          border: "1px solid var(--line, rgba(255,255,255,0.1))",
          borderRadius: 6,
          overflow: "hidden",
        }}
      >
        {events.map((ev, i) => (
          <div
            key={i}
            style={{
              display: "grid",
              gridTemplateColumns: "120px 1fr 100px",
              gap: 12,
              padding: "12px 18px",
              borderBottom:
                i < events.length - 1
                  ? "1px solid var(--line, rgba(255,255,255,0.05))"
                  : "0",
              alignItems: "center",
            }}
          >
            <span
              style={{
                fontFamily: "JetBrains Mono, monospace",
                fontSize: 10,
                color: "rgba(255,255,255,0.5)",
              }}
            >
              {SHORT_DATETIME(ev.occurred_at)}
            </span>
            <div>
              <div
                style={{
                  fontFamily: "Source Serif 4, Georgia, serif",
                  fontSize: 13.5,
                  color: "#fff",
                }}
              >
                {ev.summary}
              </div>
              {ev.detail && (
                <div
                  style={{
                    fontFamily: "JetBrains Mono, monospace",
                    fontSize: 9.5,
                    color: "rgba(255,255,255,0.4)",
                    marginTop: 2,
                  }}
                >
                  {ev.detail}
                </div>
              )}
            </div>
            <span
              style={{
                fontFamily: "JetBrains Mono, monospace",
                fontSize: 9,
                color: ev.badge?.startsWith("×")
                  ? "var(--accent, #dc4c2b)"
                  : "var(--warm, #fbbf24)",
                fontWeight: 700,
                letterSpacing: 1,
                textAlign: "right",
              }}
            >
              {ev.badge || ""}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
