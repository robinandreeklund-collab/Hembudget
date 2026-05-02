/**
 * Lärar-vy · klassens reflektioner (motsv. larare.html#p-refl).
 *
 * Routas via /teacher/v2/reflektioner.
 *
 * Listar reflect-step-progress för lärarens elever med:
 * - Filter: alla / oläst (utan teacher_feedback) / flagged (heuristik)
 * - Klick på "Skriv kommentar" öppnar inline-textarea och postar till
 *   /v2/teacher/reflections/{id}/feedback
 * - "Mår inte bra"-flagga visas röd när heuristiken slår
 */
import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  v2Api,
  type V2ReflectionsResponse,
  type V2ReflectionItem,
  type V2ReflectionFilter,
} from "./api";
import { V2Banner } from "./V2Banner";
import "./larare.css";

const SHORT_DATETIME = (iso: string | null): string => {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleString("sv-SE", {
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  });
};

export function TeacherReflectionsV2() {
  const [data, setData] = useState<V2ReflectionsResponse | null>(null);
  const [filter, setFilter] = useState<V2ReflectionFilter>("all");
  const [error, setError] = useState<string | null>(null);
  // Bug #19 · bulk + AI-summering
  const [aiSummary, setAiSummary] = useState<string | null>(null);
  const navigate = useNavigate();

  async function load(f: V2ReflectionFilter = filter) {
    try {
      const next = await v2Api.teacherReflections(f);
      setData(next);
    } catch (e) {
      setError(String((e as Error)?.message || e));
    }
  }

  useEffect(() => {
    load(filter);
  }, [filter]);

  if (error && !data) {
    return (
      <div className="v2-larare-root">
        <V2Banner status={{ role: "teacher", is_super_admin: false }} />
        <div className="larare-loading">
          <div>
            <div style={{ color: "#fca5a5", marginBottom: 8 }}>
              Kunde inte ladda reflektioner
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
        <div className="larare-loading">Laddar reflektioner…</div>
      </div>
    );
  }

  const s = data.summary;

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

        <header className="larare-head">
          <div>
            <span className="pill warm">Reflektioner · klass-flöde</span>
            <h1 className="larare-head-h1">
              Klassens <em>tankar</em> denna period.
            </h1>
            {/* Bug #19 · bulk-actions + AI-summering · v2-design */}
            <BulkActions
              n={data?.items?.length || 0}
              onBulkMarkRead={async () => {
                if (!confirm("Markera ALLA visade reflektioner som lästa?")) return;
                const ids = (data?.items || []).map((r) => r.progress_id);
                await Promise.all(
                  ids.map((id) =>
                    fetch(`/v2/teacher/reflections/${id}/mark-read`, {
                      method: "POST",
                      headers: { Authorization: `Bearer ${localStorage.getItem("hb_token") || ""}` },
                    }).catch(() => undefined),
                  ),
                );
                load(filter);
              }}
              onAiSummary={async () => {
                try {
                  setAiSummary("Hämtar klass-summering från Echo…");
                  const ids = (data?.items || []).map(
                    (r: { progress_id: number }) => r.progress_id,
                  );
                  const resp = await fetch("/ai/teacher/reflections-summary", {
                    method: "POST",
                    headers: {
                      "Content-Type": "application/json",
                      Authorization: `Bearer ${localStorage.getItem("hb_token") || ""}`,
                    },
                    body: JSON.stringify({ filter, ids }),
                  });
                  if (!resp.ok) {
                    setAiSummary(
                      resp.status === 503
                        ? "AI är inte aktiverat på ditt konto. Be super-admin slå på."
                        : `Fel: ${await resp.text()}`,
                    );
                    return;
                  }
                  const j = await resp.json();
                  setAiSummary(j.summary || j.suggestion || "Tomt svar.");
                } catch (e) {
                  setAiSummary(`Fel: ${String((e as Error).message || e)}`);
                }
              }}
            />
            <p
              style={{
                fontFamily: "Source Serif 4, Georgia, serif",
                fontSize: 16,
                color: "rgba(255,255,255,0.6)",
                marginTop: 12,
              }}
            >
              Reflect-steg från modul-arbetet · senaste 90 dagarna · sortering
              nyast först.
            </p>
          </div>
          <div className="larare-head-meta">
            Totalt <strong>{s.total_count}</strong>
            <br />
            Olästa <strong>{s.unread_count}</strong>
            <br />
            Snitt-längd <strong>{s.avg_word_count} ord</strong>
          </div>
        </header>

        {/* Bug #19 · AI-summering visas här när lärare bett om den */}
        {aiSummary && (
          <article
            style={{
              marginTop: 18,
              padding: 18,
              background: "linear-gradient(135deg, rgba(168,85,247,0.08), rgba(99,102,241,0.05))",
              border: "1px solid rgba(168,85,247,0.3)",
              borderRadius: 12,
            }}
          >
            <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 8 }}>
              <strong
                style={{
                  fontFamily: "JetBrains Mono, monospace",
                  fontSize: 11,
                  color: "#d8b4fe",
                  letterSpacing: 1.4,
                  textTransform: "uppercase",
                }}
              >
                ✨ Echo · klass-summering
              </strong>
              <button
                onClick={() => setAiSummary(null)}
                style={{
                  background: "transparent",
                  border: "none",
                  color: "rgba(255,255,255,0.5)",
                  cursor: "pointer",
                  fontSize: "1.2rem",
                }}
              >
                ✕
              </button>
            </div>
            <div
              style={{
                color: "rgba(255,255,255,0.85)",
                fontFamily: "Source Serif 4, Georgia, serif",
                lineHeight: 1.6,
                whiteSpace: "pre-wrap",
              }}
            >
              {aiSummary}
            </div>
          </article>
        )}

        {/* Filter-toggles */}
        <div
          style={{
            display: "flex",
            gap: 10,
            marginBottom: 24,
            flexWrap: "wrap",
          }}
        >
          <FilterButton
            label={`Alla (${s.total_count})`}
            active={filter === "all"}
            onClick={() => setFilter("all")}
          />
          <FilterButton
            label={`Olästa (${s.unread_count})`}
            active={filter === "unread"}
            onClick={() => setFilter("unread")}
            warm
          />
          <FilterButton
            label={`▲ Behöver stöd (${s.flagged_count})`}
            active={filter === "flagged"}
            onClick={() => setFilter("flagged")}
            accent
          />
        </div>

        {/* Lista */}
        {data.items.length === 0 ? (
          <div
            style={{
              padding: "24px 28px",
              border: "1px solid var(--line, rgba(255,255,255,0.1))",
              borderRadius: 6,
              fontFamily: "Source Serif 4, Georgia, serif",
              color: "rgba(255,255,255,0.5)",
              maxWidth: 880,
            }}
          >
            {filter === "all"
              ? "Klassen har inte skrivit några reflektioner senaste 90 dagarna."
              : filter === "unread"
              ? "Inga olästa reflektioner. Bra jobbat!"
              : "Inga elever flaggade just nu — alla verkar OK."}
          </div>
        ) : (
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "1fr",
              gap: 14,
              maxWidth: 880,
            }}
          >
            {data.items.map((it) => (
              <ReflectionCard
                key={it.progress_id}
                item={it}
                onUpdated={(updated) => {
                  setData((prev) =>
                    prev
                      ? {
                          ...prev,
                          items: prev.items.map((i) =>
                            i.progress_id === updated.progress_id
                              ? updated
                              : i,
                          ),
                          // Update summary unread/flagged-counts approx
                          summary: {
                            ...prev.summary,
                            unread_count: Math.max(
                              0,
                              prev.summary.unread_count
                                - (it.teacher_feedback === null ? 1 : 0),
                            ),
                          },
                        }
                      : prev,
                  );
                }}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function BulkActions({
  n,
  onBulkMarkRead,
  onAiSummary,
}: {
  n: number;
  onBulkMarkRead: () => void | Promise<void>;
  onAiSummary: () => void | Promise<void>;
}) {
  return (
    <div style={{ marginTop: 14, display: "flex", gap: 10, flexWrap: "wrap" }}>
      <button
        onClick={onBulkMarkRead}
        disabled={n === 0}
        style={{
          background: "rgba(255,255,255,0.05)",
          border: "1px solid rgba(255,255,255,0.18)",
          color: n === 0 ? "rgba(255,255,255,0.3)" : "rgba(255,255,255,0.85)",
          padding: "8px 14px",
          borderRadius: 6,
          cursor: n === 0 ? "not-allowed" : "pointer",
          fontSize: "0.85rem",
        }}
      >
        ✓ Markera alla ({n}) som lästa
      </button>
      <button
        onClick={onAiSummary}
        disabled={n === 0}
        style={{
          background: "rgba(168,85,247,0.12)",
          border: "1px solid rgba(168,85,247,0.4)",
          color: n === 0 ? "rgba(255,255,255,0.3)" : "#d8b4fe",
          padding: "8px 14px",
          borderRadius: 6,
          cursor: n === 0 ? "not-allowed" : "pointer",
          fontSize: "0.85rem",
          fontWeight: 600,
        }}
        title="Echo summerar trender över hela klassens reflektioner"
      >
        ✨ AI-summering av klassen
      </button>
    </div>
  );
}


function FilterButton({
  label,
  active,
  onClick,
  warm,
  accent,
}: {
  label: string;
  active: boolean;
  onClick: () => void;
  warm?: boolean;
  accent?: boolean;
}) {
  const color = accent
    ? "var(--accent, #dc4c2b)"
    : warm
    ? "var(--warm, #fbbf24)"
    : "rgba(255,255,255,0.7)";
  return (
    <button
      type="button"
      onClick={onClick}
      style={{
        fontFamily: "JetBrains Mono, monospace",
        fontSize: 10,
        fontWeight: 700,
        letterSpacing: 1.2,
        textTransform: "uppercase",
        padding: "8px 14px",
        borderRadius: 100,
        background: active
          ? accent
            ? "rgba(220,76,43,0.18)"
            : warm
            ? "rgba(251,191,36,0.15)"
            : "rgba(255,255,255,0.08)"
          : "transparent",
        border: `1px solid ${
          active
            ? accent
              ? "var(--accent, #dc4c2b)"
              : warm
              ? "var(--warm, #fbbf24)"
              : "var(--line-strong, rgba(255,255,255,0.18))"
            : "var(--line, rgba(255,255,255,0.1))"
        }`,
        color,
        cursor: "pointer",
      }}
    >
      {label}
    </button>
  );
}

function ReflectionCard({
  item,
  onUpdated,
}: {
  item: V2ReflectionItem;
  onUpdated: (it: V2ReflectionItem) => void;
}) {
  const [showForm, setShowForm] = useState(false);
  const [text, setText] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const isFlagged = item.flagged_for_help;
  const hasFeedback = !!item.teacher_feedback;

  async function submit() {
    if (text.trim().length === 0 || submitting) return;
    setSubmitting(true);
    setError(null);
    try {
      const updated = await v2Api.teacherReflectionFeedback(
        item.progress_id,
        text.trim(),
      );
      onUpdated(updated);
      setShowForm(false);
      setText("");
    } catch (e) {
      setError(String((e as Error)?.message || e));
    } finally {
      setSubmitting(false);
    }
  }

  // First-sentence quote for the title (max 100 chars)
  const headline = item.body
    .split(/[.!?]\s/)[0]
    .slice(0, 100)
    .trim();
  const eyeColor = isFlagged ? "#fca5a5" : hasFeedback ? "#6ee7b7" : "var(--warm, #fbbf24)";
  const eyeText = isFlagged
    ? `${item.student_name} · ${SHORT_DATETIME(item.completed_at)} · MÅR INTE BRA`
    : `${item.student_name} · ${SHORT_DATETIME(item.completed_at)}${
        hasFeedback ? " · KOMMENTERAD" : ""
      }`;
  const borderLeft = isFlagged
    ? "3px solid #fca5a5"
    : hasFeedback
    ? "3px solid #6ee7b7"
    : "3px solid var(--accent, #dc4c2b)";

  return (
    <article
      className="s-card"
      style={{
        borderLeft,
      }}
    >
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "baseline",
          marginBottom: 10,
          gap: 12,
        }}
      >
        <div style={{ flex: 1, minWidth: 0 }}>
          <div
            className="s-card-eye"
            style={{ marginBottom: 4, color: eyeColor }}
          >
            {eyeText}
          </div>
          <div className="s-card-h" style={{ marginBottom: 0 }}>
            "{headline}…"
          </div>
        </div>
        <div
          style={{
            fontFamily: "JetBrains Mono, monospace",
            fontSize: 9.5,
            color: isFlagged ? "#fca5a5" : "var(--warm, #fbbf24)",
            letterSpacing: 1,
            textTransform: "uppercase",
            textAlign: "right",
            whiteSpace: "nowrap",
          }}
        >
          {isFlagged
            ? "FLAGGA · STÖD BEHÖVS"
            : `RUBRIK · ${item.rubric_label || item.module_title.toUpperCase()}`}
        </div>
      </div>
      <p
        style={{
          fontFamily: "Source Serif 4, Georgia, serif",
          fontSize: 15,
          lineHeight: 1.55,
          color: "rgba(255,255,255,0.92)",
          fontStyle: "italic",
          margin: 0,
          whiteSpace: "pre-wrap",
        }}
      >
        "{item.body}"
      </p>
      <div
        style={{
          fontFamily: "JetBrains Mono, monospace",
          fontSize: 9.5,
          color: "rgba(255,255,255,0.4)",
          marginTop: 10,
          letterSpacing: 0.5,
        }}
      >
        {item.word_count} ord · modul: {item.module_title} · steg:{" "}
        {item.step_title}
      </div>

      {/* Existerande lärar-feedback */}
      {hasFeedback && !showForm && (
        <div
          style={{
            marginTop: 14,
            padding: "12px 16px",
            background: "rgba(110,231,183,0.06)",
            border: "1px solid rgba(110,231,183,0.25)",
            borderLeft: "3px solid #6ee7b7",
            borderRadius: 6,
          }}
        >
          <div
            style={{
              fontFamily: "JetBrains Mono, monospace",
              fontSize: 9.5,
              color: "#6ee7b7",
              letterSpacing: 1.2,
              textTransform: "uppercase",
              marginBottom: 6,
            }}
          >
            ● Din feedback · {SHORT_DATETIME(item.feedback_at)}
          </div>
          <p
            style={{
              fontFamily: "Source Serif 4, Georgia, serif",
              fontSize: 13.5,
              color: "rgba(255,255,255,0.85)",
              margin: 0,
              fontStyle: "italic",
              whiteSpace: "pre-wrap",
            }}
          >
            "{item.teacher_feedback}"
          </p>
        </div>
      )}

      {/* Feedback-form */}
      {showForm && (
        <div style={{ marginTop: 14 }}>
          <textarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder={
              isFlagged
                ? "Erbjud konkret stöd: boka tid eller skicka resurs."
                : "Skriv en formativ kommentar — 'jag märker', 'fortsätt så här'."
            }
            rows={4}
            style={{
              width: "100%",
              padding: "10px 12px",
              background: "rgba(255,255,255,0.04)",
              border: "1px solid var(--line-strong, rgba(255,255,255,0.18))",
              borderRadius: 6,
              fontFamily: "Source Serif 4, Georgia, serif",
              fontSize: 13.5,
              color: "#fff",
              resize: "vertical",
            }}
          />
          {error && (
            <div
              style={{
                color: "#fca5a5",
                fontSize: 11,
                marginTop: 6,
                fontFamily: "JetBrains Mono, monospace",
              }}
            >
              {error}
            </div>
          )}
          <div style={{ marginTop: 8, display: "flex", gap: 8 }}>
            <button
              type="button"
              disabled={submitting || text.trim().length === 0}
              onClick={submit}
              className="larare-tb-btn solid"
              style={{ cursor: submitting ? "wait" : "pointer" }}
            >
              {submitting ? "Sparar…" : "Spara feedback →"}
            </button>
            <button
              type="button"
              onClick={() => {
                setShowForm(false);
                setText("");
              }}
              className="larare-tb-btn"
            >
              Avbryt
            </button>
          </div>
        </div>
      )}

      {/* Action-bar */}
      {!showForm && (
        <div
          style={{
            display: "flex",
            gap: 8,
            flexWrap: "wrap",
            marginTop: 14,
          }}
        >
          <button
            type="button"
            onClick={() => {
              setShowForm(true);
              setText(item.teacher_feedback || "");
            }}
            className="attn-go"
            style={{
              border: isFlagged
                ? "1px solid var(--accent, #dc4c2b)"
                : "1px solid var(--line-strong, rgba(255,255,255,0.18))",
              padding: "7px 12px",
              borderRadius: 100,
              background: isFlagged ? "rgba(220,76,43,0.1)" : "transparent",
              color: isFlagged ? "var(--accent, #dc4c2b)" : "var(--warm, #fbbf24)",
              cursor: "pointer",
            }}
          >
            {isFlagged
              ? "Boka stund · DM"
              : hasFeedback
              ? "Ändra feedback"
              : "Skriv kommentar"}
          </button>
          <Link
            to={`/teacher/v2/elev/${item.student_id}`}
            className="attn-go"
            style={{
              border: "1px solid var(--line-strong, rgba(255,255,255,0.18))",
              padding: "7px 12px",
              borderRadius: 100,
            }}
          >
            Öppna {item.student_name.split(" ")[0]}s detalj →
          </Link>
        </div>
      )}
    </article>
  );
}
