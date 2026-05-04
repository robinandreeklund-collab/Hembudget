/**
 * Skola · Meddelanden — elev-vy.
 *
 * Speglar prototypen /proposals/vol-7/elev.html (p-meddelanden):
 * - actor-head med pill, lärar-namn, online-status
 * - chat-card med Anders Lind-avatar (blå-gradient) + meddelanden
 *   sorterade kronologiskt med datum-separatorer
 * - lärar-bubblor blå (sender_role=teacher), elev-bubblor accent
 * - chat-foot med textarea + Skicka-knapp
 * - peda "Lärar-relation är tillgänglig, inte transaktionell"
 */
import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import {
  v2Api,
  type V2MessagesData,
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

export function MeddelandenV2() {
  const [data, setData] = useState<V2MessagesData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [body, setBody] = useState("");
  const [sending, setSending] = useState(false);
  const chatRef = useRef<HTMLDivElement>(null);

  function refresh() {
    return v2Api
      .messages()
      .then(setData)
      .catch((e) => setError(String((e as Error)?.message || e)));
  }

  async function markUnreadVisible(d: V2MessagesData) {
    const unread = d.messages.filter(
      (m) => m.is_unread && m.sender_role === "teacher",
    );
    for (const m of unread) {
      try {
        await v2Api.messagesMarkRead(m.id);
      } catch {
        // ignorera
      }
    }
  }

  useEffect(() => {
    refresh();
  }, []);

  useEffect(() => {
    if (data) markUnreadVisible(data);
    chatRef.current?.scrollTo({
      top: chatRef.current.scrollHeight,
      behavior: "smooth",
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data?.messages.length]);

  async function send() {
    if (!body.trim()) return;
    setSending(true);
    try {
      await v2Api.messagesSend(body.trim());
      setBody("");
      await refresh();
    } catch (e) {
      setError(String((e as Error)?.message || e));
    } finally {
      setSending(false);
    }
  }

  if (error && !data) {
    return (
      <div className="v2-lan-root">
        <V2Banner status={{ role: "student", is_super_admin: false }} />
        <div className="bank-loading">
          <div>
            <div style={{ color: "#fca5a5", marginBottom: 8 }}>
              Kunde inte ladda meddelanden
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
        <V2Banner status={{ role: "student", is_super_admin: false }} />
        <div className="bank-loading">Laddar meddelanden…</div>
      </div>
    );
  }

  // Group messages by day
  const groups: Array<{ day: string; messages: V2MessageRow[] }> = [];
  for (const msg of data.messages) {
    const day = DAY_KEY(msg.created_at);
    const last = groups[groups.length - 1];
    if (!last || last.day !== day) {
      groups.push({ day, messages: [msg] });
    } else {
      last.messages.push(msg);
    }
  }

  const teacherInitials = (data.teacher_name || "Lärare")
    .split(" ")
    .map((p) => p[0])
    .slice(0, 2)
    .join("")
    .toUpperCase();

  return (
    <div className="v2-lan-root">
      <V2Banner status={{ role: "student", is_super_admin: false }} />

      <div className="shell">
        <Link className="actor-back" to="/v2/hub">
          Tillbaka till pentagonen
        </Link>

        <header className="actor-head">
          <div>
            <span className="pill">Skola · Meddelanden</span>
            <h1 className="actor-name" style={{ marginTop: 14 }}>
              Chatt med <em>{data.teacher_name || "din lärare"}</em>.
            </h1>
            <p className="actor-sub">
              Direktmeddelande mellan dig och din lärare · sparas i din
              portfolio
            </p>
          </div>
          <div className="actor-meta">
            Olästa: <strong>{data.unread_count}</strong>
            <br />
            Senaste lärarsvar:{" "}
            <strong>
              {data.last_received_at
                ? TIME(data.last_received_at) +
                  " " +
                  DAY_KEY(data.last_received_at).split(" ")[0]
                : "—"}
            </strong>
            <br />
            Sokratisk · sparas i portfolio
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
            style={{
              display: "flex",
              gap: 14,
              alignItems: "center",
              marginBottom: 14,
              paddingBottom: 14,
              borderBottom: "1px solid var(--line)",
            }}
          >
            <div
              style={{
                width: 44,
                height: 44,
                borderRadius: "50%",
                background:
                  "linear-gradient(135deg, #1e3a8a 0%, #3b82f6 100%)",
                display: "grid",
                placeItems: "center",
                fontFamily: "var(--serif)",
                fontSize: 16,
                fontWeight: 700,
                color: "#fff",
                flexShrink: 0,
              }}
            >
              {teacherInitials}
            </div>
            <div>
              <div
                style={{
                  fontFamily: "var(--serif)",
                  fontSize: 16,
                  fontWeight: 700,
                }}
              >
                {data.teacher_name || "Lärare"}
              </div>
              <div
                style={{
                  fontFamily: "var(--mono)",
                  fontSize: 10,
                  color: "var(--text-mid)",
                }}
              >
                Lärare · Ekonomilabbet
              </div>
            </div>
          </div>

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
                Ingen chatt än. Skriv ett meddelande nedan så börjar
                konversationen.
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
                  {group.messages.map((m) => (
                    <MessageBubble
                      key={m.id}
                      msg={m}
                      teacherName={data.teacher_name || "Lärare"}
                    />
                  ))}
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
              placeholder={`Skriv till ${data.teacher_name || "läraren"}…`}
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
          <div className="peda-eye">Pedagogik · vad du lär dig här</div>
          <div className="peda-h">
            Lärar-relation är <em>tillgänglig</em>, inte transaktionell.
          </div>
          <p className="peda-prose">
            Läraren ser allt du gör i appen — bokföring, val, reflektioner —
            men hen är <em>inte</em> en datainsamlare. Chatten är till för
            att du kan ställa frågor, signalera att du behöver stöd, eller
            bara berätta hur det går. Allt sparas i din portfolio och kan
            läsas av läraren, dina vårdnadshavare och dig själv om 5 år.
          </p>
          <ul className="peda-bullets">
            <li>
              <strong>Sokratiskt stöd</strong>Läraren ger inte direkta
              svar — frågar om mönster och låter dig reflektera.
            </li>
            <li>
              <strong>Privacy</strong>Bara du, läraren och vårdnadshavare
              ser. Klassen ser inte din chat.
            </li>
            <li>
              <strong>Svarstid</strong>Läraren svarar inom 24 h på
              vardagar · helger ej.
            </li>
            <li>
              <strong>Eskalering</strong>Vid akuta saker (mående,
              ekonomisk kris) skicka "URGENT" först i meddelandet.
            </li>
          </ul>
          <div className="peda-tip">
            Du kan länka in en specifik vy i ditt meddelande, t.ex. "Kan
            du titta på Bokföring-vyn?" — så ser läraren direkt vad du
            syftar på. Olästa lärar-meddelanden räknas i wellbeing
            (social-axeln): 5+ olästa = -2 social.
          </div>
        </div>
      </div>
    </div>
  );
}

function MessageBubble({
  msg, teacherName,
}: {
  msg: V2MessageRow;
  teacherName: string;
}) {
  const isTeacher = msg.sender_role === "teacher";
  return (
    <div
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
        {isTeacher ? teacherName : "Du"} · {TIME(msg.created_at)}
        {msg.is_unread && isTeacher && (
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
            NY
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
}
