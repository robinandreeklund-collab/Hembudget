/**
 * Lärar-vy · alla uppdrag man gett en specifik elev.
 *
 * Använder /v2/teacher/students/{id}/uppdrag-overview. Lärare ser
 * exakt samma data som eleven (sina egna uppdrag) — inkl. live-status,
 * urgency och feedback-historik.
 *
 * Routas via /teacher/v2/uppdrag/:studentId.
 */
import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import {
  v2Api,
  type V2TeacherUppdragOverview,
  type V2UppdragRow,
  type V2UppdragUrgency,
} from "./api";
import { V2Banner } from "./V2Banner";
import "./lan.css";

const SHORT_DATE = (iso: string | null): string => {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleDateString("sv-SE", {
    day: "numeric",
    month: "short",
  });
};

const URGENCY_COLOR: Record<V2UppdragUrgency, string> = {
  overdue: "var(--accent)",
  today: "var(--accent)",
  tomorrow: "var(--warm)",
  this_week: "var(--warm)",
  later: "var(--text-mid)",
  none: "var(--text-mid)",
};

const URGENCY_LABEL: Record<V2UppdragUrgency, string> = {
  overdue: "FÖRSENAT",
  today: "förfaller idag",
  tomorrow: "förfaller imorgon",
  this_week: "denna vecka",
  later: "framåt",
  none: "ingen deadline",
};

export function TeacherUppdragOverviewPage() {
  const { studentId } = useParams<{ studentId: string }>();
  const sid = studentId ? parseInt(studentId, 10) : 0;
  const [data, setData] = useState<V2TeacherUppdragOverview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const navigate = useNavigate();

  useEffect(() => {
    if (!sid) return;
    v2Api
      .teacherUppdragOverview(sid)
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
              Kunde inte ladda uppdrag
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
        <div className="bank-loading">Laddar uppdrag…</div>
      </div>
    );
  }

  const u = data.uppdrag;
  const s = u.summary;

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
            <span className="pill warm">Lärar-vy · Uppdrag-historik</span>
            <h1 className="actor-name" style={{ marginTop: 14 }}>
              Uppdrag du gett <em>{data.student_name}</em>.
            </h1>
            <p className="actor-sub">
              {s.active_count} aktiva ·{" "}
              {s.completed_count} klara ·{" "}
              {s.overdue_count > 0
                ? `▲ ${s.overdue_count} försenade`
                : "ingen är försenad"}
            </p>
          </div>
          <div className="actor-meta">
            Aktiva: <strong>{s.active_count}</strong>
            <br />
            Närmaste deadline:{" "}
            <strong>{s.nearest_due_label || "—"}</strong>
            <br />
            Klara denna mån:{" "}
            <strong style={{ color: "#6ee7b7" }}>
              {s.completed_this_month}
            </strong>
          </div>
        </header>

        {/* SAMMANFATTNING */}
        <div className="acct-grid">
          <div className="acct active">
            <div>
              <div className="acct-eye">Aktiva</div>
              <div className="acct-name">{s.active_count}</div>
              <div className="acct-num">pågående uppdrag</div>
            </div>
            <div>
              <div
                className="acct-bal"
                style={{
                  color:
                    s.overdue_count > 0 ? "#fda594" : "#fff",
                }}
              >
                {s.overdue_count}
              </div>
              <div className="acct-bal-meta">försenade</div>
            </div>
          </div>
          <div className="acct">
            <div>
              <div className="acct-eye">Klara</div>
              <div
                className="acct-name"
                style={{ color: "#6ee7b7" }}
              >
                {s.completed_count}
              </div>
              <div className="acct-num">totalt klara</div>
            </div>
            <div>
              <div className="acct-bal">{s.completed_this_month}</div>
              <div className="acct-bal-meta">denna månad</div>
            </div>
          </div>
          <div className="acct">
            <div>
              <div className="acct-eye">Närmaste deadline</div>
              <div className="acct-name">
                {s.nearest_due_label || "—"}
              </div>
              <div className="acct-num">
                {s.nearest_due_date
                  ? SHORT_DATE(s.nearest_due_date)
                  : "ingen aktiv"}
              </div>
            </div>
            <div>
              <div
                className="acct-bal"
                style={{ color: "var(--text-mid)" }}
              >
                {s.active_count > 0
                  ? Math.round(
                      (s.completed_count /
                        Math.max(s.completed_count + s.active_count, 1)) *
                        100,
                    )
                  : 100}
                %
              </div>
              <div className="acct-bal-meta">klart-rate</div>
            </div>
          </div>
        </div>

        <div className="act-grid">
          <div>
            {u.active.length > 0 && (
              <>
                <div className="section-eye">
                  Aktiva ({u.active.length})
                </div>
                <div className="biz-table" style={{ marginBottom: 22 }}>
                  <div
                    className="biz-table-row head"
                    style={{
                      gridTemplateColumns: "50px 1.6fr 1fr 110px 110px",
                    }}
                  >
                    <span></span>
                    <span>Uppdrag</span>
                    <span>Status</span>
                    <span>Deadline</span>
                    <span>Urgency</span>
                  </div>
                  {u.active.map((r) => (
                    <ActiveRow key={r.id} row={r} />
                  ))}
                </div>
              </>
            )}

            {u.completed.length > 0 && (
              <>
                <div className="section-eye">
                  Klara ({u.completed.length})
                </div>
                <div className="biz-table" style={{ marginBottom: 22 }}>
                  <div
                    className="biz-table-row head"
                    style={{
                      gridTemplateColumns: "50px 1.6fr 1fr 100px 100px",
                    }}
                  >
                    <span></span>
                    <span>Uppdrag</span>
                    <span>Detalj</span>
                    <span>Klar</span>
                    <span>Status</span>
                  </div>
                  {u.completed.map((r) => (
                    <CompletedRow key={r.id} row={r} />
                  ))}
                </div>
              </>
            )}

            {u.active.length === 0 && u.completed.length === 0 && (
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
                Du har inte gett {data.student_name} något uppdrag än.
                Gå till lärar-dashboarden och skapa ett första uppdrag.
              </div>
            )}
          </div>

          <aside>
            {s.overdue_count > 0 && (
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
                  ▲ {s.overdue_count} försenade uppdrag
                </div>
                <div className="side-card-h">Eleven har glömt</div>
                <div className="side-card-meta">
                  Försenade uppdrag är ofta tecken på att eleven har
                  fastnat eller missförstått. Kanske dags för en
                  påminnelse eller feedback?
                </div>
              </div>
            )}
            <div className="side-card">
              <div className="side-card-eye">Self-complete</div>
              <div className="side-card-h">Free_text</div>
              <div className="side-card-meta">
                Eleven kan själv-klarmarkera reflektions-uppdrag.
                Andra kind:s bedöms automatiskt — du ser samma status
                här som eleven.
              </div>
            </div>
            <div className="side-card">
              <div className="side-card-eye">Skapa nytt uppdrag</div>
              <div className="side-card-h">Per elev → Skicka uppdrag</div>
              <div className="side-card-meta">
                Klicka in på en elev från klass-listan och använd knappen{" "}
                <strong>Skicka uppdrag</strong> uppe till höger på elev-detalj-vyn.
                Uppdraget visas i elevens postlåda och spåras här.
              </div>
            </div>
          </aside>
        </div>
      </div>
    </div>
  );
}

function ActiveRow({ row }: { row: V2UppdragRow }) {
  const due = row.due_date ? SHORT_DATE(row.due_date) : "—";
  const color = URGENCY_COLOR[row.urgency];
  return (
    <div
      className="biz-table-row"
      style={{ gridTemplateColumns: "50px 1.6fr 1fr 110px 110px" }}
    >
      <span
        style={{
          fontFamily: "var(--mono)",
          fontSize: 10,
          color: "var(--text-dim)",
        }}
      >
        U{String(row.id).padStart(2, "0")}
      </span>
      <div>
        <div style={{ fontFamily: "var(--serif)", fontSize: 13.5, color: "#fff" }}>
          {row.title}
        </div>
        <div style={{ fontFamily: "var(--mono)", fontSize: 9, color: "var(--text-dim)" }}>
          {row.kind}
          {row.target_year_month ? ` · ${row.target_year_month}` : ""}
        </div>
      </div>
      <span style={{ fontFamily: "var(--mono)", fontSize: 10, color: "var(--text-mid)" }}>
        {row.progress}
      </span>
      <span style={{ fontFamily: "var(--mono)", fontSize: 10, color: "var(--text-mid)" }}>
        {due}
      </span>
      <span style={{ fontFamily: "var(--mono)", fontSize: 9, color, fontWeight: 700, letterSpacing: 1 }}>
        {URGENCY_LABEL[row.urgency]}
      </span>
    </div>
  );
}

function CompletedRow({ row }: { row: V2UppdragRow }) {
  const completedAt = row.manually_completed_at || row.created_at;
  return (
    <div
      className="biz-table-row"
      style={{ gridTemplateColumns: "50px 1.6fr 1fr 100px 100px" }}
    >
      <span style={{ fontFamily: "var(--mono)", fontSize: 10, color: "var(--text-dim)" }}>
        U{String(row.id).padStart(2, "0")}
      </span>
      <div>
        <div style={{ fontFamily: "var(--serif)", fontSize: 13.5, color: "#fff" }}>
          {row.title}
        </div>
        <div style={{ fontFamily: "var(--mono)", fontSize: 9, color: "var(--text-dim)" }}>
          {row.kind}
          {row.target_year_month ? ` · ${row.target_year_month}` : ""}
        </div>
      </div>
      <span style={{ fontFamily: "var(--mono)", fontSize: 10, color: "var(--text-mid)" }}>
        {row.progress}
      </span>
      <span style={{ fontFamily: "var(--mono)", fontSize: 10, color: "#6ee7b7" }}>
        {SHORT_DATE(completedAt)}
      </span>
      <span style={{ fontFamily: "var(--mono)", fontSize: 9, color: "#6ee7b7" }}>
        Klar
      </span>
    </div>
  );
}
