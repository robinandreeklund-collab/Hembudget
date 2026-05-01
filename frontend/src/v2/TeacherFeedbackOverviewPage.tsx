/**
 * Lärar-vy · all feedback man gett en specifik elev.
 *
 * Använder /v2/teacher/students/{id}/feedback-overview. Lärare ser
 * exakt samma data som eleven (sin egen feedback) — pedagogiskt
 * värdefullt för att se vad man redan kommenterat och hur eleven
 * läst det.
 *
 * Routas via /teacher/v2/feedback/:studentId.
 */
import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import {
  v2Api,
  type V2TeacherFeedbackOverview,
  type V2FeedbackKind,
} from "./api";
import { V2Banner } from "./V2Banner";
import "./lan.css";

const SHORT_DATE = (iso: string): string => {
  const d = new Date(iso);
  return d.toLocaleDateString("sv-SE", {
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  });
};

const KIND_LABEL: Record<V2FeedbackKind, string> = {
  message: "Chat",
  module_step: "Modul-steg",
  module_step_quiz: "Modul-quiz",
  module_step_done: "Modul-godkänd",
  assignment: "Uppdrag",
};

export function TeacherFeedbackOverviewPage() {
  const { studentId } = useParams<{ studentId: string }>();
  const sid = studentId ? parseInt(studentId, 10) : 0;
  const [data, setData] = useState<V2TeacherFeedbackOverview | null>(
    null,
  );
  const [error, setError] = useState<string | null>(null);
  const navigate = useNavigate();

  useEffect(() => {
    if (!sid) return;
    v2Api
      .teacherFeedbackOverview(sid)
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
              Kunde inte ladda feedback
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
        <div className="bank-loading">Laddar feedback…</div>
      </div>
    );
  }

  const f = data.feedback;
  const s = f.summary;
  const recentlyActive =
    s.last_received_at != null &&
    new Date(s.last_received_at).getTime() >
      Date.now() - 7 * 24 * 60 * 60 * 1000;
  const stallFlag =
    s.last_received_at == null ||
    new Date(s.last_received_at).getTime() <
      Date.now() - 21 * 24 * 60 * 60 * 1000;

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
            <span className="pill warm">Lärar-vy · Feedback-historik</span>
            <h1 className="actor-name" style={{ marginTop: 14 }}>
              Feedback du gett{" "}
              <em>{data.student_name}</em>.
            </h1>
            <p className="actor-sub">
              {s.total_count} items · {s.unread_count} olästa av eleven ·{" "}
              {recentlyActive
                ? "aktiv senaste veckan"
                : stallFlag
                ? "▲ tyst i 3+ veckor"
                : "stabil dialog"}
            </p>
          </div>
          <div className="actor-meta">
            Olästa av eleven:{" "}
            <strong style={{ color: s.unread_count > 0 ? "#fda594" : "#6ee7b7" }}>
              {s.unread_count}
            </strong>
            <br />
            Totalt: <strong>{s.total_count}</strong>
            <br />
            Senaste:{" "}
            <strong>
              {s.last_received_at ? SHORT_DATE(s.last_received_at) : "—"}
            </strong>
          </div>
        </header>

        {/* SAMMANFATTNING */}
        <div className="acct-grid">
          <div className="acct active">
            <div>
              <div className="acct-eye">Modul-feedback</div>
              <div className="acct-name">{s.module_step_count}</div>
              <div className="acct-num">per-steg-noteringar</div>
            </div>
            <div>
              <div className="acct-bal">{s.message_count}</div>
              <div className="acct-bal-meta">chat-meddelanden</div>
            </div>
          </div>
          <div className="acct">
            <div>
              <div className="acct-eye">Uppdrag-feedback</div>
              <div className="acct-name">{s.assignment_count}</div>
              <div className="acct-num">korrigerade/godkända</div>
            </div>
            <div>
              <div className="acct-bal">{s.total_count}</div>
              <div className="acct-bal-meta">totalt</div>
            </div>
          </div>
          <div className="acct">
            <div>
              <div className="acct-eye">Olästa</div>
              <div
                className="acct-name"
                style={{
                  color: s.unread_count > 0 ? "#fda594" : "#6ee7b7",
                }}
              >
                {s.unread_count}
              </div>
              <div className="acct-num">av eleven</div>
            </div>
            <div>
              <div
                className="acct-bal"
                style={{ color: stallFlag ? "#fda594" : "#fff" }}
              >
                {s.last_received_at
                  ? Math.floor(
                      (Date.now() -
                        new Date(s.last_received_at).getTime()) /
                        86400000,
                    )
                  : "—"}
              </div>
              <div className="acct-bal-meta">dgr sedan senaste</div>
            </div>
          </div>
          <div className="acct">
            <div>
              <div className="acct-eye">Wellbeing-effekt</div>
              <div
                className="acct-name"
                style={{
                  color:
                    s.unread_count >= 5
                      ? "#fda594"
                      : s.unread_count === 0 && s.total_count > 0
                      ? "var(--warm)"
                      : "#fff",
                }}
              >
                {s.unread_count >= 5
                  ? "−2"
                  : s.unread_count === 0 && s.total_count > 0
                  ? "+1"
                  : "0"}
              </div>
              <div className="acct-num">social</div>
            </div>
            <div>
              <div
                className="acct-bal"
                style={{ color: "var(--text-mid)" }}
              >
                {s.unread_count >= 5
                  ? "missar dialog"
                  : s.unread_count === 0 && s.total_count > 0
                  ? "engagerad"
                  : "neutral"}
              </div>
              <div className="acct-bal-meta">för eleven</div>
            </div>
          </div>
        </div>

        <div className="act-grid">
          <div>
            <div className="section-eye">
              All feedback ({f.items.length})
            </div>
            {f.items.length === 0 ? (
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
                Du har inte gett {data.student_name} någon feedback de
                senaste 90 dagarna.
              </div>
            ) : (
              <div style={{ marginBottom: 22 }}>
                {f.items.map((item) => (
                  <article
                    key={`${item.kind}-${item.source_id}`}
                    style={{
                      background: item.is_unread
                        ? "rgba(220,76,43,0.04)"
                        : "rgba(15,21,37,0.5)",
                      borderLeft: `3px solid ${
                        item.is_unread ? "var(--accent)" : "var(--line-strong)"
                      }`,
                      borderRadius: 6,
                      padding: "14px 18px",
                      marginBottom: 12,
                    }}
                  >
                    <div
                      style={{
                        display: "flex",
                        justifyContent: "space-between",
                        alignItems: "baseline",
                        marginBottom: 8,
                      }}
                    >
                      <div
                        style={{
                          fontFamily: "var(--mono)",
                          fontSize: 9.5,
                          fontWeight: 700,
                          letterSpacing: "1.4px",
                          textTransform: "uppercase",
                          color: item.is_unread
                            ? "var(--accent)"
                            : "var(--text-mid)",
                        }}
                      >
                        {item.is_unread ? "● OLÄST · " : "○ läst · "}
                        {SHORT_DATE(item.created_at)} ·{" "}
                        {KIND_LABEL[item.kind]}
                        {item.context_label ? ` · ${item.context_label}` : ""}
                      </div>
                    </div>
                    {item.title && item.title !== item.body && (
                      <div
                        style={{
                          fontFamily: "var(--serif)",
                          fontSize: 14,
                          color: "#fff",
                          marginBottom: 6,
                        }}
                      >
                        {item.title}
                      </div>
                    )}
                    <p
                      style={{
                        fontFamily: "var(--serif)",
                        fontSize: 13.5,
                        color: "var(--text)",
                        lineHeight: 1.5,
                        fontStyle: "italic",
                        margin: 0,
                        whiteSpace: "pre-wrap",
                      }}
                    >
                      "{item.body}"
                    </p>
                  </article>
                ))}
              </div>
            )}
          </div>

          <aside>
            {stallFlag && s.total_count > 0 && (
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
                  ▲ Tyst i 3+ veckor
                </div>
                <div className="side-card-h">
                  Senaste feedback{" "}
                  <em>
                    {s.last_received_at
                      ? SHORT_DATE(s.last_received_at)
                      : "—"}
                  </em>
                </div>
                <div className="side-card-meta">
                  Eleven har inte fått feedback från dig i 3+ veckor.
                  Pedagogiskt regelbunden dialog är viktig — kanske dags
                  för en kommentar?
                </div>
              </div>
            )}
            <div className="side-card">
              <div className="side-card-eye">Wellbeing-effekt</div>
              <div className="side-card-h">
                Dialog <em>räknas</em>
              </div>
              <div className="side-card-meta">
                ≥ 5 olästa feedback senaste 30 dgr → -2 social ("missar
                dialog"). 0 olästa + minst 1 läst → +1 social ("engagerar
                sig"). Eleven ser sina egna effekter — du ser dem från
                lärar-perspektivet här.
              </div>
            </div>
            <div className="side-card">
              <div className="side-card-eye">Olästa</div>
              <div className="side-card-h">
                {s.unread_count} av {s.total_count}
              </div>
              <div className="side-card-meta">
                Eleven har inte ännu öppnat och läst{" "}
                {s.unread_count} av dina feedback-items. Detta speglar
                hur snabbt eleven engagerar sig i dialog.
              </div>
            </div>
          </aside>
        </div>
      </div>
    </div>
  );
}
