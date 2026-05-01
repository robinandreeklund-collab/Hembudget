/**
 * Lärar-vy · kompetens-detalj för en specifik elev.
 *
 * Använder /v2/teacher/students/{id}/kompetens/{cid}. Lärare ser
 * samma data som eleven — pedagogiskt värdefullt för bedömning.
 *
 * Routas via /teacher/v2/kompetens/:studentId/:competencyId.
 */
import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import {
  v2Api,
  type V2TeacherKompetensOverview,
  type V2KompetensTimelineEvent,
  type V2KompetensModuleStatus,
  type V2KompetensRequirement,
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

const LEVEL_COLOR: Record<string, string> = {
  B: "var(--text-dim)",
  G: "var(--accent)",
  F: "#6ee7b7",
};

const EVENT_BADGE_COLOR: Record<string, string> = {
  step_completed: "var(--warm)",
  module_completed: "#6ee7b7",
  level_reached: "var(--accent)",
  assigned: "var(--text-mid)",
};

export function TeacherKompetensOverviewPage() {
  const { studentId, competencyId } = useParams<{
    studentId: string;
    competencyId: string;
  }>();
  const sid = studentId ? parseInt(studentId, 10) : 0;
  const cid = competencyId ? parseInt(competencyId, 10) : 0;
  const [data, setData] = useState<V2TeacherKompetensOverview | null>(
    null,
  );
  const [error, setError] = useState<string | null>(null);
  const navigate = useNavigate();

  useEffect(() => {
    if (!sid || !cid) return;
    v2Api
      .teacherKompetensOverview(sid, cid)
      .then(setData)
      .catch((e) => setError(String((e as Error)?.message || e)));
  }, [sid, cid]);

  if (error) {
    return (
      <div className="v2-lan-root">
        <V2Banner status={{ role: "teacher", is_super_admin: false }} />
        <div className="bank-loading">
          <div>
            <div style={{ color: "#fca5a5", marginBottom: 8 }}>
              Kunde inte ladda kompetens
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
        <div className="bank-loading">Laddar kompetens…</div>
      </div>
    );
  }

  const d = data.detail;
  const masteryPct = Math.round(d.mastery * 100);
  const progressPct = Math.round(d.progress_to_next * 100);
  const color = LEVEL_COLOR[d.level];
  const nextColor = d.next_level
    ? LEVEL_COLOR[d.next_level]
    : color;

  return (
    <div className="v2-lan-root">
      <V2Banner status={{ role: "teacher", is_super_admin: false }} />

      <div className="shell">
        <a
          className="actor-back"
          onClick={(e) => {
            e.preventDefault();
            navigate(`/teacher/v2/portfolio/${sid}`);
          }}
          href="#"
        >
          Tillbaka till elevens portfolio
        </a>

        <header className="actor-head">
          <div>
            <span className="pill warm">
              Lärar-vy · Kompetens-detalj
            </span>
            <h1 className="actor-name" style={{ marginTop: 14 }}>
              {data.student_name} ·{" "}
              <em style={{ color }}>
                {d.name} {d.level_label}
              </em>
              .
            </h1>
            <p className="actor-sub">
              {d.completed_steps} av {d.total_steps} kopplade steg
              klara · mastery {masteryPct} %
            </p>
          </div>
          <div className="actor-meta">
            Nuvarande:{" "}
            <strong style={{ color }}>{d.level_label}</strong>
            <br />
            Nästa:{" "}
            <strong style={{ color: nextColor }}>
              {d.next_level_label || "max-nivå"}
            </strong>
            <br />
            Senaste händelse:{" "}
            <strong>
              {d.last_event_at ? SHORT_DATE(d.last_event_at) : "—"}
            </strong>
          </div>
        </header>

        <div className="acct-grid">
          <div className="acct active">
            <div>
              <div className="acct-eye">Mastery</div>
              <div className="acct-name" style={{ color }}>
                {masteryPct} %
              </div>
              <div className="acct-num">
                {d.completed_steps}/{d.total_steps} steg
              </div>
            </div>
            <div>
              <div
                className="acct-bal"
                style={{ color }}
              >
                {d.level_label}
              </div>
              <div className="acct-bal-meta">nuvarande nivå</div>
            </div>
          </div>
          <div className="acct">
            <div>
              <div className="acct-eye">Progress till nästa</div>
              <div
                className="acct-name"
                style={{ color: nextColor }}
              >
                {d.next_level ? `${progressPct} %` : "MAX"}
              </div>
              <div className="acct-num">
                {d.next_level_label || "ingen nästa"}
              </div>
            </div>
            <div>
              <div
                className="acct-bal"
                style={{ color: "var(--text-mid)" }}
              >
                {d.next_level ? progressPct : 100}
              </div>
              <div className="acct-bal-meta">% av span</div>
            </div>
          </div>
          <div className="acct">
            <div>
              <div className="acct-eye">Anslutna moduler</div>
              <div className="acct-name">
                {d.connected_modules.filter((m) => m.completed).length}
                /{d.connected_modules.length}
              </div>
              <div className="acct-num">klara av kopplade</div>
            </div>
            <div>
              <div
                className="acct-bal"
                style={{ color: "var(--text-mid)" }}
              >
                {d.timeline.length}
              </div>
              <div className="acct-bal-meta">events i timeline</div>
            </div>
          </div>
          <div className="acct">
            <div>
              <div className="acct-eye">Earned weight</div>
              <div className="acct-name">
                {d.earned_weight.toFixed(2)}
              </div>
              <div className="acct-num">
                av {d.total_weight.toFixed(2)} totalt
              </div>
            </div>
            <div>
              <div
                className="acct-bal"
                style={{ color: "var(--text-mid)" }}
              >
                {d.total_weight > 0
                  ? Math.round(
                      (d.earned_weight / d.total_weight) * 100,
                    )
                  : 0}
              </div>
              <div className="acct-bal-meta">% av total weight</div>
            </div>
          </div>
        </div>

        <div className="act-grid">
          <div>
            <div className="section-eye">
              Vad eleven gjort · timeline
            </div>
            {d.timeline.length === 0 ? (
              <div
                style={{
                  padding: "16px 20px",
                  border: "1px solid var(--line)",
                  borderRadius: 6,
                  fontFamily: "var(--serif)",
                  color: "var(--text-mid)",
                  marginBottom: 22,
                }}
              >
                Inga händelser registrerade än för {data.student_name} på{" "}
                {d.name}.
              </div>
            ) : (
              <div className="biz-table" style={{ marginBottom: 22 }}>
                {d.timeline.map((ev, i) => (
                  <TimelineRow key={`${ev.event_type}-${i}`} ev={ev} />
                ))}
              </div>
            )}

            {d.next_level && (
              <>
                <div className="section-eye" style={{ marginTop: 24 }}>
                  Krav för{" "}
                  <em style={{ color: nextColor }}>
                    {d.next_level_label}
                  </em>
                </div>
                <div className="biz-table" style={{ marginBottom: 22 }}>
                  {d.requirements_for_next.map((req, i) => (
                    <RequirementRow key={i} req={req} />
                  ))}
                </div>
              </>
            )}
          </div>

          <aside>
            <div className="side-card">
              <div className="side-card-eye">Anslutna moduler</div>
              <div className="side-card-h">
                {d.connected_modules.filter((m) => m.completed).length}{" "}
                av {d.connected_modules.length} klara
              </div>
              {d.connected_modules.length === 0 ? (
                <div
                  className="side-card-meta"
                  style={{ marginTop: 8 }}
                >
                  Inga moduler är ännu kopplade till {d.name}.
                </div>
              ) : (
                <ul
                  style={{
                    listStyle: "none",
                    padding: 0,
                    margin: "8px 0 0",
                    fontFamily: "Inter, sans-serif",
                    fontSize: 12.5,
                  }}
                >
                  {d.connected_modules.map((m) => (
                    <ModuleListItem key={m.module_id} m={m} />
                  ))}
                </ul>
              )}
            </div>

            <div className="side-card">
              <div className="side-card-eye">Bedömning</div>
              <div className="side-card-h">Auto + manuellt</div>
              <div className="side-card-meta">
                Mastery beräknas på modul-steg klar × steg-vikt mot
                kompetensen. Du kan höja eleven manuellt via lärar-
                dashboarden om hen visat förståelse på annat sätt.
              </div>
            </div>

            <div className="side-card">
              <div className="side-card-eye">Wellbeing-koppling</div>
              <div className="side-card-h">
                FÖRDJUPNING bygger health
              </div>
              <div className="side-card-meta">
                5+ kompetenser på FÖRDJUPNING → +3 health för eleven.
                2-4 → +1. Klassas som health eftersom kunskap = trygg
                självbild.
              </div>
            </div>
          </aside>
        </div>
      </div>
    </div>
  );
}

function TimelineRow({ ev }: { ev: V2KompetensTimelineEvent }) {
  const badgeColor =
    EVENT_BADGE_COLOR[ev.event_type] || "var(--text-mid)";
  return (
    <div
      className="biz-table-row"
      style={{ gridTemplateColumns: "100px 1fr 120px" }}
    >
      <span
        style={{
          fontFamily: "var(--mono)",
          fontSize: 10,
          color: "var(--text-mid)",
        }}
      >
        {SHORT_DATE(ev.occurred_at)}
      </span>
      <div>
        <div style={{ fontFamily: "var(--serif)", fontSize: 14, color: "#fff" }}>
          {ev.title}
        </div>
        {ev.detail && (
          <div
            style={{
              fontFamily: "var(--mono)",
              fontSize: 9.5,
              color: "var(--text-dim)",
              marginTop: 2,
            }}
          >
            {ev.detail}
          </div>
        )}
      </div>
      <span
        style={{
          fontFamily: "var(--mono)",
          fontSize: 9,
          fontWeight: 700,
          color: badgeColor,
          letterSpacing: 1,
        }}
      >
        {ev.badge || ev.event_type}
      </span>
    </div>
  );
}

function RequirementRow({ req }: { req: V2KompetensRequirement }) {
  return (
    <div
      className="biz-table-row"
      style={{ gridTemplateColumns: "32px 1fr 90px" }}
    >
      <span
        style={{
          fontFamily: "var(--mono)",
          fontSize: 12,
          color: req.met ? "#6ee7b7" : "var(--text-dim)",
        }}
      >
        {req.met ? "✓" : "○"}
      </span>
      <div>
        <div style={{ fontFamily: "var(--serif)", fontSize: 13.5, color: "#fff" }}>
          {req.label}
        </div>
        {req.description && (
          <div style={{ fontFamily: "var(--mono)", fontSize: 9, color: "var(--text-dim)" }}>
            {req.description}
          </div>
        )}
      </div>
      <span
        style={{
          fontFamily: "var(--mono)",
          fontSize: 10,
          color: req.met ? "#6ee7b7" : "var(--warm)",
        }}
      >
        {req.value_label}
      </span>
    </div>
  );
}

function ModuleListItem({ m }: { m: V2KompetensModuleStatus }) {
  return (
    <li
      style={{
        display: "flex",
        gap: 8,
        padding: "5px 0",
        borderBottom: "1px dashed var(--line)",
        alignItems: "center",
      }}
    >
      <span style={{ color: m.completed ? "#6ee7b7" : "var(--text-dim)" }}>
        {m.completed ? "✓" : "○"}
      </span>
      <span style={{ flex: 1 }}>{m.title}</span>
      <span
        style={{
          fontFamily: "var(--mono)",
          fontSize: 9,
          color: "var(--text-dim)",
        }}
      >
        {m.completed_steps}/{m.total_steps}
      </span>
    </li>
  );
}
