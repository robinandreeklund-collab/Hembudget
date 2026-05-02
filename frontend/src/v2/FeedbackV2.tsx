/**
 * Skola · Lärar-feedback — elev-vy.
 *
 * Speglar prototypen /proposals/vol-7/elev.html (p-feedback):
 * - actor-head med pill, olästa/totalt/senaste
 * - cc-summary med 5 stat-cards (komp-höjningar, modul-feedback,
 *   reflekt-svar, uppdrags-godkända, beröm)
 * - Filter-tabbar för feedback-typ (Allt / Modul / Komp / Reflekt /
 *   Uppdrag / Beröm)
 * - s-card för varje feedback med färg-kodad eye + title + body +
 *   ev. länk till källa
 * - peda-block "Feedback är spårbar, inte flyktig"
 *
 * Aggregerar Message + StudentStepProgress.teacher_feedback +
 * Assignment.teacher_feedback från master-DB.
 */
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  v2Api,
  type V2FeedbackData,
  type V2FeedbackItem,
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
  message: "CHAT",
  module_step: "MODUL-STEG",
  module_step_quiz: "MODUL-STEG QUIZ",
  module_step_done: "MODUL-STEG GODKÄND",
  assignment: "UPPDRAG",
};

type Filter = "all" | "module_step" | "message" | "assignment";

export function FeedbackV2() {
  const [data, setData] = useState<V2FeedbackData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<Filter>("all");

  function refresh() {
    return v2Api
      .feedback()
      .then(setData)
      .catch((e) => setError(String((e as Error)?.message || e)));
  }

  useEffect(() => {
    refresh();
    // Bug #15 · realtids-poll var 15:e sek så nya meddelanden från
    // läraren syns utan reload
    const t = setInterval(refresh, 15000);
    return () => clearInterval(t);
  }, []);

  // Markera unread items synliga i nuvarande filter som lästa via
  // klick på item — separat funktion. Här sker auto-mark vid mount?
  // Nej — eleven måste klicka på item för att markera. Det matchar
  // prototypen ("orange punkt = oläst, försvinner när du klickar").

  async function markRead(item: V2FeedbackItem) {
    if (!item.is_unread) return;
    try {
      await v2Api.feedbackMarkRead([
        { kind: item.kind, source_id: item.source_id },
      ]);
      await refresh();
    } catch (e) {
      setError(String((e as Error)?.message || e));
    }
  }

  async function markAllRead() {
    if (!data) return;
    const unread = data.items
      .filter((i) => i.is_unread)
      .map((i) => ({ kind: i.kind, source_id: i.source_id }));
    if (!unread.length) return;
    if (!confirm(`Markera ${unread.length} olästa som lästa?`)) return;
    try {
      await v2Api.feedbackMarkRead(unread);
      await refresh();
    } catch (e) {
      setError(String((e as Error)?.message || e));
    }
  }

  if (error && !data) {
    return (
      <div className="v2-lan-root">
        <V2Banner status={{ role: "student", is_super_admin: false }} />
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
        <V2Banner status={{ role: "student", is_super_admin: false }} />
        <div className="bank-loading">Laddar lärar-feedback…</div>
      </div>
    );
  }

  const s = data.summary;

  // Filter
  const filteredItems = data.items.filter((i) => {
    if (filter === "all") return true;
    if (filter === "module_step") return i.kind.startsWith("module_step");
    return i.kind === filter;
  });

  const formatTeacher = (t: V2FeedbackItem) =>
    t.teacher_name || "Lärare";

  return (
    <div className="v2-lan-root">
      <V2Banner status={{ role: "student", is_super_admin: false }} />

      <div className="shell">
        <Link className="actor-back" to="/v2/hub">
          Tillbaka till pentagonen
        </Link>

        <header className="actor-head">
          <div>
            <span className="pill">Skola · Feedback från läraren</span>
            <h1 className="actor-name" style={{ marginTop: 14 }}>
              Allt <em>läraren sagt</em>.
            </h1>
            <p className="actor-sub">
              Kommentarer, kompetenshöjningar, beröm och förslag · sparas
              i portfolio
            </p>
          </div>
          <div className="actor-meta">
            Olästa:{" "}
            <strong
              style={{
                color: s.unread_count > 0 ? "var(--warm)" : "#fff",
              }}
            >
              {s.unread_count}
            </strong>
            <br />
            Totalt: <strong>{s.total_count}</strong>
            <br />
            Senaste:{" "}
            <strong>
              {s.last_received_at
                ? SHORT_DATE(s.last_received_at)
                : "—"}
            </strong>
          </div>
        </header>

        {/* CC-SUMMARY · 4 stat-cards */}
        <div
          className="cc-summary"
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(4, 1fr)",
            gap: 10,
            marginBottom: 18,
          }}
        >
          <StatCard
            eye="Modul-feedback"
            num={s.module_step_count}
            sub="per-steg-noteringar"
            highlight
          />
          <StatCard
            eye="Chat-meddelanden"
            num={s.message_count}
            sub="från läraren"
          />
          <StatCard
            eye="Uppdrag-feedback"
            num={s.assignment_count}
            sub="korrigerade/godkända"
          />
          <StatCard
            eye="Olästa"
            num={s.unread_count}
            sub={
              s.unread_count > 0 ? "klicka för att läsa" : "alla lästa"
            }
            highlight={s.unread_count > 0}
            warm={s.unread_count > 0}
          />
        </div>

        {/* FILTER-TABBAR */}
        <div
          style={{
            display: "flex",
            gap: 6,
            flexWrap: "wrap",
            marginBottom: 18,
            alignItems: "center",
          }}
        >
          <FilterPill
            active={filter === "all"}
            onClick={() => setFilter("all")}
            label={`Allt (${s.total_count})`}
          />
          <FilterPill
            active={filter === "module_step"}
            onClick={() => setFilter("module_step")}
            label={`Modul-feedback (${s.module_step_count})`}
          />
          <FilterPill
            active={filter === "message"}
            onClick={() => setFilter("message")}
            label={`Chat (${s.message_count})`}
          />
          <FilterPill
            active={filter === "assignment"}
            onClick={() => setFilter("assignment")}
            label={`Uppdrag (${s.assignment_count})`}
          />
          {s.unread_count > 0 && (
            <button
              type="button"
              onClick={markAllRead}
              style={{
                marginLeft: "auto",
                fontFamily: "var(--mono)",
                fontSize: 10,
                fontWeight: 700,
                padding: "7px 12px",
                borderRadius: 100,
                background: "transparent",
                border: "1px solid var(--line-strong)",
                color: "var(--text-mid)",
                cursor: "pointer",
                letterSpacing: "1.2px",
                textTransform: "uppercase",
              }}
            >
              Markera alla {s.unread_count} som lästa
            </button>
          )}
        </div>

        {/* FEEDBACK-LISTA */}
        <div className="section-eye">Senaste · sorterat efter datum</div>
        {filteredItems.length === 0 ? (
          <div
            style={{
              padding: "20px 24px",
              border: "1px solid var(--line)",
              borderRadius: 6,
              fontFamily: "var(--serif)",
              color: "var(--text-mid)",
              marginBottom: 22,
            }}
          >
            {filter === "all"
              ? "Ingen lärar-feedback än. När din lärare ger feedback hamnar det här."
              : "Inga feedback-items i denna filter."}
          </div>
        ) : (
          <div style={{ marginBottom: 22 }}>
            {filteredItems.map((item) => (
              <FeedbackCard
                key={`${item.kind}-${item.source_id}`}
                item={item}
                teacherLabel={formatTeacher(item)}
                onMarkRead={() => markRead(item)}
              />
            ))}
          </div>
        )}

        {/* PEDA */}
        <div className="peda">
          <div className="peda-eye">Pedagogik · vad du lär dig här</div>
          <div className="peda-h">
            Feedback är <em>spårbar</em>, inte flyktig.
          </div>
          <p className="peda-prose">
            All feedback läraren ger sparas — du kan gå tillbaka och
            läsa om hur du tänkte i mars, vad läraren sa, och hur det
            förändrade ditt arbete. Det är så formativ bedömning faktiskt
            fungerar i den bästa pedagogiken:{" "}
            <em>kontinuerlig dialog över tid</em>, inte slut-betyg. Dina
            vårdnadshavare ser också detta — så om föräldrasamtalet
            kommer har ni gemensam läsning.
          </p>
          <ul className="peda-bullets">
            <li>
              <strong>Komp-höjningar</strong>Spårbara med motivering ·
              går alltid att gå tillbaka till.
            </li>
            <li>
              <strong>Reflektion-svar</strong>Läraren kommenterar dina
              inlägg — du svarar tillbaka.
            </li>
            <li>
              <strong>Uppdrags-status</strong>Klar / korrigeras / godkänd
              · alla med kommentar.
            </li>
            <li>
              <strong>Beröm</strong>Spontant — inte krav. Markeras
              tydligt i flödet.
            </li>
          </ul>
          <div className="peda-tip">
            När du läst en feedback markeras den som "läst" automatiskt.
            Olästa har en orange punkt — så du vet vad som är nytt.
            Många olästa = -2 social i wellbeing (du missar dialogen).
            Alla lästa = +1 social.
          </div>
        </div>
      </div>
    </div>
  );
}

function StatCard({
  eye, num, sub, highlight, warm,
}: {
  eye: string;
  num: number;
  sub: string;
  highlight?: boolean;
  warm?: boolean;
}) {
  return (
    <div
      style={{
        padding: "16px 20px",
        border: "1px solid var(--line)",
        borderRadius: 6,
      }}
    >
      <div
        style={{
          fontFamily: "var(--mono)",
          fontSize: 9.5,
          letterSpacing: "1.2px",
          textTransform: "uppercase",
          color: "var(--text-dim)",
        }}
      >
        {eye}
      </div>
      <div
        style={{
          fontFamily: "var(--serif)",
          fontSize: 28,
          fontStyle: "italic",
          fontWeight: 700,
          color: warm
            ? "var(--warm)"
            : highlight
            ? "#fff"
            : "#fff",
          marginTop: 4,
        }}
      >
        {num}
      </div>
      <div
        style={{
          fontFamily: "var(--mono)",
          fontSize: 10,
          color: "var(--text-mid)",
          marginTop: 4,
        }}
      >
        {sub}
      </div>
    </div>
  );
}

function FilterPill({
  active, onClick, label,
}: {
  active: boolean;
  onClick: () => void;
  label: string;
}) {
  return (
    <a
      href="#"
      onClick={(e) => {
        e.preventDefault();
        onClick();
      }}
      style={{
        fontFamily: "var(--mono)",
        fontSize: 10,
        fontWeight: 700,
        padding: "7px 12px",
        borderRadius: 100,
        background: active ? "var(--warm)" : "rgba(255,255,255,0.04)",
        color: active ? "#422006" : "var(--text-mid)",
        textDecoration: "none",
        letterSpacing: "1.2px",
        textTransform: "uppercase",
        border: active
          ? "1px solid var(--warm)"
          : "1px solid var(--line-strong)",
      }}
    >
      {label}
    </a>
  );
}

function FeedbackCard({
  item, teacherLabel, onMarkRead,
}: {
  item: V2FeedbackItem;
  teacherLabel: string;
  onMarkRead: () => void;
}) {
  // Färg-kod baserat på kind
  const kindColors: Record<V2FeedbackKind, {
    bg: string; border: string; eye: string;
  }> = {
    message: {
      bg: "rgba(59,130,246,0.06)",
      border: "#3b82f6",
      eye: "#93c5fd",
    },
    module_step: {
      bg: "rgba(168,85,247,0.06)",
      border: "#c084fc",
      eye: "#c084fc",
    },
    module_step_quiz: {
      bg: "rgba(168,85,247,0.05)",
      border: "#c084fc",
      eye: "#c084fc",
    },
    module_step_done: {
      bg: "rgba(168,85,247,0.05)",
      border: "#c084fc",
      eye: "#c084fc",
    },
    assignment: {
      bg: "rgba(251,191,36,0.05)",
      border: "var(--warm)",
      eye: "var(--warm)",
    },
  };
  const c = kindColors[item.kind] || kindColors.message;

  return (
    <article
      onClick={onMarkRead}
      style={{
        background: c.bg,
        borderLeft: `3px solid ${c.border}`,
        borderRadius: 6,
        padding: "14px 18px",
        marginBottom: 12,
        cursor: item.is_unread ? "pointer" : "default",
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
            color: c.eye,
          }}
        >
          {item.is_unread ? "● " : "○ "}
          {SHORT_DATE(item.created_at)} · {item.is_unread ? "NY · " : ""}
          {KIND_LABEL[item.kind] || "FEEDBACK"}
          {item.context_label ? ` · ${item.context_label}` : ""}
        </div>
        <div
          style={{
            fontFamily: "var(--mono)",
            fontSize: 9,
            color: "var(--text-dim)",
          }}
        >
          {teacherLabel}
        </div>
      </div>
      {item.title && item.title !== item.body && (
        <div
          style={{
            fontFamily: "var(--serif)",
            fontSize: 16,
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
          fontSize: 14.5,
          color: "var(--text)",
          lineHeight: 1.5,
          fontStyle: "italic",
          margin: 0,
          whiteSpace: "pre-wrap",
        }}
      >
        "{item.body}"
      </p>
      {item.link_target && (
        <Link
          to={item.link_target}
          onClick={(e) => e.stopPropagation()}
          style={{
            display: "inline-block",
            marginTop: 10,
            fontFamily: "var(--mono)",
            fontSize: 10,
            fontWeight: 700,
            letterSpacing: "1px",
            color: c.eye,
            textDecoration: "none",
            padding: "6px 12px",
            border: `1px solid ${c.border}`,
            borderRadius: 100,
            opacity: 0.75,
          }}
        >
          {item.kind === "message"
            ? "Öppna postlådan ↗"
            : item.kind.startsWith("module_step")
            ? "Öppna modul-steg ↗"
            : "Se i källa ↗"}
        </Link>
      )}
    </article>
  );
}
