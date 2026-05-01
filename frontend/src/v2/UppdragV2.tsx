/**
 * Skola · Mina uppdrag — elev-vy.
 *
 * Speglar prototypen /proposals/vol-7/elev.html (p-uppdrag):
 * - actor-head med pill, antal aktiva/klara, nästa deadline
 * - top-3 cc_summary-kort (urgency-färgade) för aktiva uppdrag
 * - biz-table över klara uppdrag i april
 * - peda-rutan "Lärar-uppdrag är verklighetsförankring"
 *
 * Free_text-uppdrag kan eleven själv-klarmarkera. Andra kind:s
 * bedöms automatiskt.
 */
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  v2Api,
  type V2UppdragData,
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

const KIND_LABEL: Record<string, string> = {
  set_budget: "Budget",
  import_batch: "Import",
  balance_month: "Bokslut",
  review_loan: "Lån",
  categorize_all: "Bokföring",
  save_amount: "Sparande",
  mortgage_decision: "Bolån",
  link_transfer: "Överföring",
  make_transfer: "Överföring",
  stock_open_account: "Aktier",
  stock_diversify: "Aktier",
  trigger_credit_flow: "Kredit",
  add_upcoming: "Räkning",
  free_text: "Reflektion",
};

function urgencyDays(row: V2UppdragRow): string {
  const d = row.days_until_due;
  if (d == null) return "—";
  if (d < 0) return `${Math.abs(d)} d försenat`;
  if (d === 0) return "idag";
  if (d === 1) return "imorgon";
  return `${d} dgr`;
}

export function UppdragV2() {
  const [data, setData] = useState<V2UppdragData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState<number | null>(null);

  useEffect(() => {
    v2Api
      .uppdrag()
      .then(setData)
      .catch((e) => setError(String((e as Error)?.message || e)));
  }, []);

  async function selfComplete(id: number) {
    if (pending !== null) return;
    setPending(id);
    try {
      await v2Api.uppdragSelfComplete(id);
      const next = await v2Api.uppdrag();
      setData(next);
    } catch (e) {
      setError(String((e as Error)?.message || e));
    } finally {
      setPending(null);
    }
  }

  if (error && !data) {
    return (
      <div className="v2-lan-root">
        <V2Banner status={{ role: "student", is_super_admin: false }} />
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
        <V2Banner status={{ role: "student", is_super_admin: false }} />
        <div className="bank-loading">Laddar uppdrag…</div>
      </div>
    );
  }

  const s = data.summary;
  const teacherName = data.teacher_name || "läraren";
  const top3 = data.active.slice(0, 3);

  return (
    <div className="v2-lan-root" data-guide="uppdrag-list">
      <V2Banner status={{ role: "student", is_super_admin: false }} />

      <div className="shell">
        <Link className="actor-back" to="/v2/hub">
          Tillbaka till pentagonen
        </Link>

        <header className="actor-head">
          <div>
            <span className="pill">Skola · Mina uppdrag</span>
            <h1 className="actor-name" style={{ marginTop: 14 }}>
              {s.active_count > 0 ? (
                <>
                  {s.active_count} från <em>{teacherName}</em>
                  {s.overdue_count > 0
                    ? `, ${s.overdue_count} försenade.`
                    : "."}
                </>
              ) : (
                <>Inga aktiva uppdrag — bra jobbat!</>
              )}
            </h1>
            <p className="actor-sub">
              Specifika lärar-uppgifter med deadline · individuella eller
              delade
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

        {/* TOP-3 ACTIVA · färg-kodade efter urgency */}
        {top3.length > 0 ? (
          <div
            className="cc-summary"
            style={{
              display: "grid",
              gridTemplateColumns: `repeat(${top3.length}, 1fr)`,
              gap: 10,
              marginBottom: 22,
            }}
          >
            {top3.map((row, i) => (
              <ActiveCard
                key={row.id}
                row={row}
                index={i}
                pending={pending === row.id}
                onSelfComplete={selfComplete}
              />
            ))}
          </div>
        ) : null}

        {/* ÅTERKOPPLINGS-RUTOR (om läraren har lämnat feedback) */}
        {data.active
          .filter((r) => r.teacher_feedback)
          .map((r) => (
            <FeedbackBanner
              key={`fb-${r.id}`}
              row={r}
              teacherName={teacherName}
            />
          ))}

        {/* AKTIV LISTA · alla aktiva i tabell-form */}
        {data.active.length > top3.length && (
          <>
            <div className="section-eye">
              Övriga aktiva ({data.active.length - top3.length})
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
              {data.active.slice(top3.length).map((r) => (
                <UppdragRow key={r.id} row={r} />
              ))}
            </div>
          </>
        )}

        {/* KLARA */}
        {data.completed.length > 0 && (
          <>
            <div className="section-eye">
              Klara · {data.completed.length} uppdrag
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
              {data.completed.map((r) => (
                <CompletedRow key={r.id} row={r} />
              ))}
            </div>
          </>
        )}

        {/* TOM */}
        {data.active.length === 0 && data.completed.length === 0 && (
          <div
            style={{
              padding: "24px 28px",
              border: "1px solid var(--line)",
              borderRadius: 6,
              fontFamily: "var(--serif)",
              color: "var(--text-mid)",
              marginBottom: 22,
            }}
          >
            Du har inga uppdrag än. När din lärare ger dig ett uppdrag
            dyker det upp här — med deadline och status.
          </div>
        )}

        <div className="peda">
          <div className="peda-eye">Pedagogik · vad du lär dig här</div>
          <div className="peda-h">
            Lärar-uppdrag är <em>verklighetsförankring</em>.
          </div>
          <p className="peda-prose">
            {teacherName} har samma översikt på lärar-vyn av exakt vad du
            gör. Uppdragen knyter modulerna till ditt specifika liv:
            "räkna KALP för 2,4 Mkr i Hökarängen" tvingar dig hämta data
            från banken, lön från arbetsgivaren, mat från budgeten. Inget
            abstrakt — allt konkret.
          </p>
          <ul className="peda-bullets">
            <li>
              <strong>Auto-bedömt</strong>De flesta uppdrag bedöms av
              systemet — du gör jobbet i rätt verktyg så uppdateras
              status automatiskt.
            </li>
            <li>
              <strong>Reflektion</strong>Free_text-uppdrag markerar du
              själv som klart när du anser dig klar — läraren kan be dig
              göra om via feedback.
            </li>
            <li>
              <strong>Deadline</strong>Försenade uppdrag drar inte direkt
              wellbeing — men engagemang via klara uppdrag bygger health.
            </li>
          </ul>
        </div>
      </div>
    </div>
  );
}

function ActiveCard({
  row,
  index,
  pending,
  onSelfComplete,
}: {
  row: V2UppdragRow;
  index: number;
  pending: boolean;
  onSelfComplete: (id: number) => void;
}) {
  const color = URGENCY_COLOR[row.urgency];
  const isFreeText = row.kind === "free_text";
  const due = row.due_date ? SHORT_DATE(row.due_date) : "ingen deadline";
  const days = urgencyDays(row);
  const num = String(index + 1).padStart(2, "0");
  return (
    <div
      style={{
        padding: "16px 20px",
        border: "1px solid var(--line)",
        borderRadius: 6,
        borderLeftWidth: 3,
        borderLeftColor: color,
        background:
          row.urgency === "overdue" || row.urgency === "today"
            ? "rgba(220,76,43,0.08)"
            : undefined,
      }}
    >
      <div
        style={{
          fontFamily: "var(--mono)",
          fontSize: 9.5,
          fontWeight: 700,
          letterSpacing: "1.2px",
          textTransform: "uppercase",
          color,
        }}
      >
        UPPDRAG {num} · {URGENCY_LABEL[row.urgency]}
      </div>
      <div
        style={{
          fontFamily: "var(--serif)",
          fontSize: 18,
          fontWeight: 700,
          fontStyle: "italic",
          marginTop: 6,
          color: "#fff",
        }}
      >
        {row.title}
      </div>
      <div
        style={{
          fontFamily: "var(--mono)",
          fontSize: 10,
          color: "var(--text-mid)",
          marginTop: 6,
          marginBottom: 10,
          lineHeight: 1.4,
        }}
      >
        {row.progress}
      </div>
      <div
        style={{
          fontFamily: "var(--mono)",
          fontSize: 9.5,
          color: "var(--text-dim)",
          letterSpacing: "0.8px",
          marginBottom: 8,
        }}
      >
        {KIND_LABEL[row.kind] || row.kind} · {due} · {days}
      </div>
      {isFreeText && (
        <button
          type="button"
          disabled={pending}
          onClick={() => onSelfComplete(row.id)}
          style={{
            marginTop: 8,
            padding: "8px 14px",
            background: pending ? "var(--line-strong)" : "var(--warm)",
            color: "#0c0e14",
            border: "none",
            borderRadius: 100,
            fontFamily: "var(--mono)",
            fontSize: 10,
            fontWeight: 700,
            letterSpacing: "1.2px",
            textTransform: "uppercase",
            cursor: pending ? "wait" : "pointer",
          }}
        >
          {pending ? "Markerar…" : "Markera som klar →"}
        </button>
      )}
    </div>
  );
}

function FeedbackBanner({
  row,
  teacherName,
}: {
  row: V2UppdragRow;
  teacherName: string;
}) {
  return (
    <article
      style={{
        background: "rgba(220,76,43,0.08)",
        border: "1px solid rgba(220,76,43,0.25)",
        borderLeft: "3px solid var(--accent)",
        borderRadius: 6,
        padding: "16px 22px",
        marginBottom: 16,
      }}
    >
      <div
        style={{
          fontFamily: "var(--mono)",
          fontSize: 9.5,
          fontWeight: 700,
          letterSpacing: "1.4px",
          textTransform: "uppercase",
          color: "var(--accent)",
          marginBottom: 6,
        }}
      >
        ● Feedback från {teacherName} ·{" "}
        {row.teacher_feedback_at
          ? SHORT_DATE(row.teacher_feedback_at)
          : "—"}
      </div>
      <div
        style={{
          fontFamily: "var(--serif)",
          fontSize: 14,
          color: "#fff",
          marginBottom: 6,
        }}
      >
        Uppdrag: {row.title}
      </div>
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
        "{row.teacher_feedback}"
      </p>
    </article>
  );
}

function UppdragRow({ row }: { row: V2UppdragRow }) {
  const due = row.due_date ? SHORT_DATE(row.due_date) : "—";
  const color = URGENCY_COLOR[row.urgency];
  return (
    <div
      className="biz-table-row"
      style={{
        gridTemplateColumns: "50px 1.6fr 1fr 110px 110px",
      }}
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
          {KIND_LABEL[row.kind] || row.kind}
          {row.target_year_month ? ` · ${row.target_year_month}` : ""}
        </div>
      </div>
      <span
        style={{
          fontFamily: "var(--mono)",
          fontSize: 10,
          color: "var(--text-mid)",
        }}
      >
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
      style={{
        gridTemplateColumns: "50px 1.6fr 1fr 100px 100px",
      }}
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
          {KIND_LABEL[row.kind] || row.kind}
          {row.target_year_month ? ` · ${row.target_year_month}` : ""}
        </div>
      </div>
      <span
        style={{
          fontFamily: "var(--mono)",
          fontSize: 10,
          color: "var(--text-mid)",
        }}
      >
        {row.progress}
      </span>
      <span
        style={{
          fontFamily: "var(--mono)",
          fontSize: 10,
          color: "#6ee7b7",
        }}
      >
        {SHORT_DATE(completedAt)}
      </span>
      <span style={{ fontFamily: "var(--mono)", fontSize: 9, color: "#6ee7b7" }}>
        Klar
      </span>
    </div>
  );
}
