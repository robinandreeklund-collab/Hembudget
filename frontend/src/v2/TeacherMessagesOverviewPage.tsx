/**
 * Lärar-vy · chat med en specifik elev (samma som elev-vyn men från
 * lärar-perspektiv, plus kan skicka egna meddelanden).
 *
 * Routas via /teacher/v2/messages/:studentId.
 */
import { useEffect, useRef, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import {
  v2Api,
  type V2TeacherMessagesOverview,
  type V2MessageRow,
} from "./api";
import { V2Banner } from "./V2Banner";
import "./lan.css";

const TIME = (iso: string): string => {
  const d = new Date(iso);
  return d.toLocaleTimeString("sv-SE", {
    hour: "2-digit",
    minute: "2-digit",
  });
};

const DAY_KEY = (iso: string): string => {
  const d = new Date(iso);
  return d.toLocaleDateString("sv-SE", {
    weekday: "short",
    day: "numeric",
    month: "short",
    year: "numeric",
  }).toUpperCase();
};

export function TeacherMessagesOverviewPage() {
  const { studentId } = useParams<{ studentId: string }>();
  const sid = studentId ? parseInt(studentId, 10) : 0;
  const [data, setData] = useState<V2TeacherMessagesOverview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [body, setBody] = useState("");
  const [sending, setSending] = useState(false);
  const chatRef = useRef<HTMLDivElement>(null);
  const navigate = useNavigate();

  function refresh() {
    return v2Api
      .teacherMessagesOverview(sid)
      .then(setData)
      .catch((e) => setError(String((e as Error)?.message || e)));
  }

  useEffect(() => {
    if (sid) refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sid]);

  useEffect(() => {
    chatRef.current?.scrollTo({
      top: chatRef.current.scrollHeight,
      behavior: "smooth",
    });
  }, [data?.messages.messages.length]);

  async function send() {
    if (!body.trim()) return;
    setSending(true);
    try {
      await v2Api.teacherSendMessage(sid, body.trim());
      setBody("");
      await refresh();
    } catch (e) {
      setError(String((e as Error)?.message || e));
    } finally {
      setSending(false);
    }
  }

  if (error) {
    return (
      <div className="v2-lan-root">
        <V2Banner status={{ role: "teacher", is_super_admin: false }} />
        <div className="bank-loading">
          <div>
            <div style={{ color: "#fca5a5", marginBottom: 8 }}>
              Kunde inte ladda chat
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
        <div className="bank-loading">Laddar chat…</div>
      </div>
    );
  }

  const m = data.messages;
  const groups: Array<{ day: string; messages: V2MessageRow[] }> = [];
  for (const msg of m.messages) {
    const day = DAY_KEY(msg.created_at);
    const last = groups[groups.length - 1];
    if (!last || last.day !== day) {
      groups.push({ day, messages: [msg] });
    } else {
      last.messages.push(msg);
    }
  }

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
            <span className="pill warm">Lärar-vy · Meddelanden</span>
            <h1 className="actor-name" style={{ marginTop: 14 }}>
              Chat med <em>{data.student_name}</em>.
            </h1>
            <p className="actor-sub">
              {m.messages.length} meddelanden ·{" "}
              {data.teacher_unread_count} olästa av dig ·{" "}
              {data.student_unread_count} olästa av eleven
            </p>
          </div>
          <div className="actor-meta">
            Olästa av dig:{" "}
            <strong style={{ color: data.teacher_unread_count > 0 ? "#fda594" : "#6ee7b7" }}>
              {data.teacher_unread_count}
            </strong>
            <br />
            Olästa av eleven:{" "}
            <strong>{data.student_unread_count}</strong>
            <br />
            Sparas i portfolio
          </div>
        </header>

        <article
          style={{
            background: "rgba(15,21,37,0.7)",
            border: "1px solid var(--line)",
            borderRadius: 8,
            padding: "20px 22px",
            display: "flex",
            flexDirection: "column",
            minHeight: 540,
            marginBottom: 22,
          }}
        >
          <div
            ref={chatRef}
            style={{
              flex: 1,
              overflowY: "auto",
              display: "flex",
              flexDirection: "column",
              gap: 12,
              paddingRight: 8,
              minHeight: 380,
              maxHeight: 600,
            }}
          >
            {groups.length === 0 ? (
              <div
                style={{
                  textAlign: "center",
                  padding: "40px 20px",
                  fontFamily: "var(--serif)",
                  color: "var(--text-mid)",
                }}
              >
                Ingen chat med {data.student_name} än. Skriv ett
                meddelande nedan för att starta dialogen.
              </div>
            ) : (
              groups.map((group, gi) => (
                <div key={gi}>
                  <div
                    style={{
                      textAlign: "center",
                      fontFamily: "var(--mono)",
                      fontSize: 9.5,
                      color: "var(--text-dim)",
                      letterSpacing: "1.2px",
                      margin: "10px 0 6px",
                    }}
                  >
                    — {group.day} —
                  </div>
                  {group.messages.map((msg) => {
                    const isTeacher = msg.sender_role === "teacher";
                    return (
                      <div
                        key={msg.id}
                        style={{
                          background: isTeacher
                            ? "rgba(59,130,246,0.10)"
                            : "rgba(220,76,43,0.08)",
                          borderLeft: `3px solid ${isTeacher ? "#3b82f6" : "var(--accent)"}`,
                          padding: "10px 14px",
                          borderRadius: 4,
                          marginBottom: 6,
                        }}
                      >
                        <div
                          style={{
                            fontFamily: "var(--mono)",
                            fontSize: 9.5,
                            letterSpacing: "1.2px",
                            textTransform: "uppercase",
                            color: isTeacher ? "#93c5fd" : "var(--accent)",
                            marginBottom: 4,
                          }}
                        >
                          {isTeacher ? "Du" : data.student_name} ·{" "}
                          {TIME(msg.created_at)}
                          {!isTeacher && msg.read_at == null && (
                            <span
                              style={{
                                marginLeft: 8,
                                padding: "1px 6px",
                                background: "var(--accent)",
                                color: "#fff",
                                borderRadius: 100,
                                fontSize: 8,
                              }}
                            >
                              OLÄST
                            </span>
                          )}
                        </div>
                        <p
                          style={{
                            fontFamily: "var(--serif)",
                            fontSize: 13.5,
                            lineHeight: 1.5,
                            margin: 0,
                            fontStyle: "italic",
                            whiteSpace: "pre-wrap",
                          }}
                        >
                          {msg.body}
                        </p>
                      </div>
                    );
                  })}
                </div>
              ))
            )}
          </div>

          <div
            style={{
              marginTop: 14,
              paddingTop: 14,
              borderTop: "1px solid var(--line)",
              display: "flex",
              gap: 8,
            }}
          >
            <textarea
              value={body}
              onChange={(e) => setBody(e.target.value)}
              placeholder={`Skriv till ${data.student_name}…`}
              rows={3}
              style={{
                flex: 1,
                background: "rgba(255,255,255,0.04)",
                border: "1px solid var(--line-strong)",
                color: "#fff",
                padding: "10px 14px",
                borderRadius: 6,
                fontFamily: "var(--serif)",
                fontSize: 13.5,
                resize: "vertical",
              }}
              onKeyDown={(e) => {
                if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
                  e.preventDefault();
                  send();
                }
              }}
            />
            <button
              type="button"
              className="cta-btn"
              disabled={sending || !body.trim()}
              onClick={send}
              style={{ alignSelf: "flex-end" }}
            >
              {sending ? "Skickar…" : "Skicka"}
            </button>
          </div>
        </article>

        <div className="peda">
          <div className="peda-eye">Pedagogik · vad du gör här</div>
          <div className="peda-h">
            Sokratiskt stöd <em>över tid</em>.
          </div>
          <p className="peda-prose">
            Använd chatten för att ställa frågor som leder till
            reflektion — undvik direkta svar. Eleven ska komma fram till
            insikten själv. Allt sparas i portfolio och kan läsas av
            vårdnadshavare.
          </p>
        </div>
      </div>
    </div>
  );
}
