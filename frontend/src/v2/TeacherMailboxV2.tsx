/**
 * Lärar-vy · klassens postlådor (motsv. larare.html#p-mail).
 *
 * Routas via /teacher/v2/postlador.
 *
 * Visar:
 * - 5 stat-kort (genererade / hanterade % / försenade / påminnelser / profiler)
 * - "Skicka brev"-formulär (bulk-inject) med målgrupper
 * - Tabell över alla postlådor med status (KLAR/I FAS/SLÄPER/RISK)
 *
 * Statusen beräknas på backend: oldest_days + unhandled_count + reminders.
 */
import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  v2Api,
  type V2MailboxResponse,
  type V2MailboxRow,
  type V2MailboxStatus,
  type V2MailboxBulkInjectIn,
} from "./api";
import { V2Banner } from "./V2Banner";
import "./larare.css";

const STATUS_COLOR: Record<V2MailboxStatus, string> = {
  klar: "#6ee7b7",
  i_fas: "#6ee7b7",
  släper: "var(--warm, #fbbf24)",
  risk: "#fda594",
};

const STATUS_LABEL: Record<V2MailboxStatus, string> = {
  klar: "KLAR",
  i_fas: "I FAS",
  släper: "SLÄPER",
  risk: "RISK",
};

const STATUS_BG: Record<V2MailboxStatus, string> = {
  klar: "rgba(110,231,183,0.16)",
  i_fas: "rgba(110,231,183,0.16)",
  släper: "rgba(251,191,36,0.18)",
  risk: "rgba(220,76,43,0.18)",
};

const PROFILE_LABEL: Record<string, string> = {
  sparsam: "Sparsam",
  balanserad: "Balanserad",
  slosa: "Slösa",
  slösa: "Slösa",
};

export function TeacherMailboxV2() {
  const [data, setData] = useState<V2MailboxResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [showInjectForm, setShowInjectForm] = useState(false);
  const [injectMessage, setInjectMessage] = useState<string | null>(null);
  const navigate = useNavigate();

  async function load() {
    try {
      const next = await v2Api.teacherMailboxes();
      setData(next);
    } catch (e) {
      setError(String((e as Error)?.message || e));
    }
  }

  useEffect(() => {
    load();
  }, []);

  if (error && !data) {
    return (
      <div className="v2-larare-root">
        <V2Banner status={{ role: "teacher", is_super_admin: false }} />
        <div className="larare-loading">
          <div>
            <div style={{ color: "#fca5a5", marginBottom: 8 }}>
              Kunde inte ladda postlådor
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
        <div className="larare-loading">Laddar postlådor…</div>
      </div>
    );
  }

  const s = data.summary;
  const profileEntries = Object.entries(s.profile_distribution);
  const totalUnhandled = data.rows.reduce(
    (acc, r) => acc + r.unhandled_count,
    0,
  );
  const minUnhandled = data.rows.length > 0
    ? Math.min(...data.rows.map((r) => r.unhandled_count))
    : 0;
  const maxUnhandled = data.rows.length > 0
    ? Math.max(...data.rows.map((r) => r.unhandled_count))
    : 0;

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
            <span className="pill">Postlådor · klass · meta-aktör</span>
            <h1 className="larare-head-h1">
              {s.total_students} postlådor — <em>{totalUnhandled} ohanterade</em>.
            </h1>
            <p
              style={{
                fontFamily: "Source Serif 4, Georgia, serif",
                fontSize: 16,
                color: "rgba(255,255,255,0.6)",
                marginTop: 12,
              }}
            >
              Var och en har sin egen inkorg. Här ser du klassens hanterings-
              mönster — vem är ifatt, vem släpar, vem håller på att få sina
              första påminnelser.
            </p>
          </div>
          <div className="larare-head-meta">
            Snitt-ohanterade ·{" "}
            <strong>
              {s.total_students > 0
                ? (totalUnhandled / s.total_students).toFixed(1)
                : "0"}{" "}
              brev
            </strong>
            <br />
            Spridning · <strong>{minUnhandled} till {maxUnhandled}</strong>
            <br />
            Påminnelser denna v · <strong>{s.reminders_total}</strong>
          </div>
        </header>

        {/* 5 stat-kort */}
        <div className="larare-stats">
          <div className="larare-stat">
            <div className="larare-stat-eye">Genererade brev (30 d)</div>
            <div className="larare-stat-num">
              <em>{s.total_generated_period}</em>
            </div>
            <div className="larare-stat-sub">
              {s.total_students > 0
                ? `${(s.total_generated_period / s.total_students).toFixed(1)} per elev i snitt`
                : "ingen elev"}
            </div>
          </div>
          <div className="larare-stat">
            <div className="larare-stat-eye">Hanterade i tid</div>
            <div className="larare-stat-num">{s.handled_pct} %</div>
            <div className="larare-stat-sub">
              {s.handled_in_time} av {s.total_generated_period}
            </div>
          </div>
          <div className="larare-stat">
            <div className="larare-stat-eye">Försenade</div>
            <div className={`larare-stat-num${s.overdue_count > 0 ? " accent" : ""}`}>
              {s.overdue_count > 0 ? <em>{s.overdue_count}</em> : s.overdue_count}
            </div>
            <div className="larare-stat-sub">förfallodatum passerat</div>
          </div>
          <div className="larare-stat">
            <div className="larare-stat-eye">Påminnelser ute</div>
            <div className={`larare-stat-num${s.reminders_total > 0 ? " accent" : ""}`}>
              {s.reminders_total > 0 ? (
                <em>{s.reminders_total}</em>
              ) : (
                s.reminders_total
              )}
            </div>
            <div className="larare-stat-sub">elever med påminnelser</div>
          </div>
          <div className="larare-stat">
            <div className="larare-stat-eye">Spendprofiler</div>
            <div className="larare-stat-num">{profileEntries.length}</div>
            <div className="larare-stat-sub">
              {profileEntries.length === 0
                ? "ingen elev har profil-val än"
                : profileEntries
                    .map(
                      ([p, n]) => `${n} ${PROFILE_LABEL[p] || p}`,
                    )
                    .join(" · ")}
            </div>
          </div>
        </div>

        {/* Skicka brev-formulär */}
        <div
          style={{
            background:
              "linear-gradient(135deg, rgba(99,102,241,0.06), rgba(15,21,37,0.5))",
            border: "1px solid rgba(99,102,241,0.2)",
            borderLeft: "3px solid #818cf8",
            borderRadius: 6,
            padding: "20px 24px",
            marginBottom: 22,
          }}
        >
          <div
            style={{
              fontFamily: "JetBrains Mono, monospace",
              fontSize: 10,
              color: "#a5b4fc",
              letterSpacing: 1.5,
              textTransform: "uppercase",
              marginBottom: 8,
            }}
          >
            ● Skicka brev till postlådorna
          </div>
          <h2
            style={{
              fontFamily: "Source Serif 4, Georgia, serif",
              fontSize: 22,
              fontWeight: 700,
              color: "#fff",
              margin: "0 0 8px",
            }}
          >
            Spräng in en <em style={{ color: "var(--warm)" }}>oväntad faktura</em>.
          </h2>
          <p
            style={{
              fontFamily: "Source Serif 4, Georgia, serif",
              fontSize: 14.5,
              color: "rgba(255,255,255,0.92)",
              lineHeight: 1.5,
              margin: "0 0 14px",
            }}
          >
            Fyll i en räkning, välj mottagare. Brevet dyker upp i elevernas
            postlådor som "ohanterad". Effekten ackumuleras i deras pentagon
            beroende på vad de gör med den.
          </p>
          {!showInjectForm ? (
            <button
              type="button"
              onClick={() => setShowInjectForm(true)}
              className="larare-tb-btn solid"
            >
              + Skapa nytt brev
            </button>
          ) : (
            <InjectForm
              students={data.rows}
              onClose={() => setShowInjectForm(false)}
              onCreated={(msg) => {
                setInjectMessage(msg);
                setShowInjectForm(false);
                load();
                window.setTimeout(() => setInjectMessage(null), 5000);
              }}
            />
          )}
          {injectMessage && (
            <div
              style={{
                marginTop: 12,
                padding: "10px 14px",
                background: "rgba(110,231,183,0.10)",
                border: "1px solid rgba(110,231,183,0.35)",
                borderRadius: 6,
                fontFamily: "JetBrains Mono, monospace",
                fontSize: 11,
                color: "#6ee7b7",
                letterSpacing: 0.6,
              }}
            >
              ✓ {injectMessage}
            </div>
          )}
        </div>

        {/* Tabell · alla postlådor */}
        <div className="section-title">
          {s.total_students} postlådor · status (sortering: risk → klar)
        </div>
        <div
          style={{
            background: "rgba(15,21,37,0.7)",
            border: "1px solid var(--line, rgba(255,255,255,0.1))",
            borderRadius: 6,
            overflow: "hidden",
          }}
        >
          <div
            style={{
              display: "grid",
              gridTemplateColumns:
                "30px 1.5fr 1fr 70px 90px 80px 90px 100px",
              gap: 10,
              padding: "12px 16px",
              background: "rgba(255,255,255,0.03)",
              borderBottom: "1px solid var(--line, rgba(255,255,255,0.1))",
              fontFamily: "JetBrains Mono, monospace",
              fontSize: 9.5,
              letterSpacing: 1.2,
              textTransform: "uppercase",
              color: "rgba(255,255,255,0.5)",
              alignItems: "center",
            }}
          >
            <span>#</span>
            <span>Elev</span>
            <span>Profil</span>
            <span>Brev (30d)</span>
            <span>Ohanterade</span>
            <span>Äldsta</span>
            <span>Påminn.</span>
            <span>Status</span>
          </div>
          {data.rows.map((row, i) => (
            <MailboxRow key={row.student_id} row={row} index={i} />
          ))}
        </div>

        {/* Pedagogik-card */}
        <div
          className="s-card"
          style={{
            marginTop: 22,
            background:
              "linear-gradient(135deg, rgba(99,102,241,0.06), rgba(15,21,37,0.5))",
            borderColor: "rgba(99,102,241,0.2)",
          }}
        >
          <div
            className="s-card-eye"
            style={{ color: "#a5b4fc" }}
          >
            Hur breven genereras
          </div>
          <div className="s-card-h">
            Spenderprofiler styr <em>brev-volym</em>.
          </div>
          <p
            style={{
              fontFamily: "Source Serif 4, Georgia, serif",
              fontSize: 14.5,
              lineHeight: 1.55,
              color: "rgba(255,255,255,0.92)",
              margin: 0,
            }}
          >
            Konsumentverkets schabloner × elevens spenderprofil ger antalet
            brev, beloppen och frekvensen. Sparsam-elever får ~10 brev/månad,
            balanserad ~14, slösa ~18. Ohanterade brev →{" "}
            <em style={{ color: "var(--warm)" }}>påminnelse efter 14 dgr</em>{" "}
            → inkassovarning efter{" "}
            <em style={{ color: "var(--warm)" }}>30</em>. Det är samma loop
            som i verkligheten.
          </p>
        </div>
      </div>
    </div>
  );
}

function MailboxRow({ row, index }: { row: V2MailboxRow; index: number }) {
  const oldestColor =
    row.oldest_days != null && row.oldest_days >= 14
      ? "var(--accent, #dc4c2b)"
      : row.oldest_days != null && row.oldest_days >= 8
      ? "var(--warm, #fbbf24)"
      : "rgba(255,255,255,0.6)";
  const unhandledColor =
    row.unhandled_count >= 8
      ? "var(--accent, #dc4c2b)"
      : row.unhandled_count >= 4
      ? "var(--warm, #fbbf24)"
      : row.unhandled_count > 0
      ? "var(--warm, #fbbf24)"
      : "#6ee7b7";
  return (
    <Link
      to={`/teacher/v2/elev/${row.student_id}`}
      style={{
        display: "grid",
        gridTemplateColumns: "30px 1.5fr 1fr 70px 90px 80px 90px 100px",
        gap: 10,
        padding: "12px 16px",
        borderBottom: "1px solid var(--line, rgba(255,255,255,0.05))",
        alignItems: "center",
        textDecoration: "none",
        color: "rgba(255,255,255,0.92)",
        fontFamily: "Inter, sans-serif",
        fontSize: 13,
        background: row.status === "risk" ? "rgba(220,76,43,0.05)" : undefined,
      }}
    >
      <span
        style={{
          fontFamily: "JetBrains Mono, monospace",
          fontSize: 10,
          color: "rgba(255,255,255,0.4)",
        }}
      >
        {String(index + 1).padStart(2, "0")}
      </span>
      <span
        style={{
          fontFamily: "Source Serif 4, Georgia, serif",
          fontWeight: 700,
          color: "#fff",
        }}
      >
        {row.student_name}
        {row.has_authority_unhandled && (
          <span
            style={{
              fontFamily: "JetBrains Mono, monospace",
              fontSize: 9,
              color: "var(--accent, #dc4c2b)",
              letterSpacing: 1,
              padding: "2px 6px",
              background: "rgba(220,76,43,0.1)",
              borderRadius: 3,
              marginLeft: 6,
            }}
          >
            MYNDIGHET
          </span>
        )}
      </span>
      <span
        style={{
          fontFamily: "JetBrains Mono, monospace",
          fontSize: 10,
          color: "rgba(255,255,255,0.6)",
          letterSpacing: 0.5,
          textTransform: "uppercase",
        }}
      >
        {row.spend_profile
          ? PROFILE_LABEL[row.spend_profile] || row.spend_profile
          : "—"}
      </span>
      <span
        style={{
          fontFamily: "JetBrains Mono, monospace",
          fontSize: 11,
          color: "rgba(255,255,255,0.92)",
        }}
      >
        {row.total_count_period}
      </span>
      <span
        style={{
          fontFamily: "Source Serif 4, Georgia, serif",
          fontStyle: "italic",
          color: unhandledColor,
          fontWeight: 700,
        }}
      >
        {row.unhandled_count}
      </span>
      <span
        style={{
          fontFamily: "JetBrains Mono, monospace",
          fontSize: 10,
          color: oldestColor,
          fontWeight: row.oldest_days != null && row.oldest_days >= 14 ? 700 : 400,
        }}
      >
        {row.oldest_days != null ? `${row.oldest_days} dgr` : "—"}
      </span>
      <span
        style={{
          fontFamily: "JetBrains Mono, monospace",
          fontSize: 10,
          color: row.reminders_count > 0
            ? "var(--accent, #dc4c2b)"
            : "rgba(255,255,255,0.4)",
          fontWeight: row.reminders_count > 0 ? 700 : 400,
        }}
      >
        {row.reminders_count > 0 ? row.reminders_count : "—"}
      </span>
      <span
        style={{
          fontFamily: "JetBrains Mono, monospace",
          fontSize: 9,
          padding: "3px 8px",
          borderRadius: 100,
          background: STATUS_BG[row.status],
          color: STATUS_COLOR[row.status],
          textAlign: "center",
          letterSpacing: 1,
          fontWeight: 700,
        }}
      >
        {STATUS_LABEL[row.status]}
      </span>
    </Link>
  );
}

function InjectForm({
  students,
  onClose,
  onCreated,
}: {
  students: V2MailboxRow[];
  onClose: () => void;
  onCreated: (msg: string) => void;
}) {
  const [sender, setSender] = useState("Folktandvården");
  const [mailType, setMailType] = useState<V2MailboxBulkInjectIn["mail_type"]>(
    "invoice",
  );
  const [subject, setSubject] = useState("Karies-bokning ej avbokad");
  const [body, setBody] = useState(
    "Du har en obetald karies-bokning från 14 mars som inte avbokats. Avgift 850 kr enligt avtalsvillkor.",
  );
  const [amount, setAmount] = useState<string>("850");
  const [dueDate, setDueDate] = useState<string>("");
  const [target, setTarget] = useState<"all" | "selected">("all");
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function toggleStudent(id: number) {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  async function submit() {
    if (submitting) return;
    setSubmitting(true);
    setError(null);
    try {
      const payload: V2MailboxBulkInjectIn = {
        sender: sender.trim(),
        mail_type: mailType,
        subject: subject.trim(),
        body: body.trim() || undefined,
        amount: amount ? parseFloat(amount) : undefined,
        due_date: dueDate || undefined,
        target_student_ids:
          target === "all" ? null : Array.from(selectedIds),
      };
      const res = await v2Api.teacherMailboxBulkInject(payload);
      onCreated(
        `Skickade till ${res.students_targeted} postlådor — ${res.mails_created} brev skapade.`,
      );
    } catch (e) {
      setError(String((e as Error)?.message || e));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div>
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "1fr 1fr",
          gap: 12,
          marginBottom: 12,
        }}
      >
        <FormField label="Avsändare">
          <input
            value={sender}
            onChange={(e) => setSender(e.target.value)}
            style={inputStyle()}
          />
        </FormField>
        <FormField label="Brevtyp">
          <select
            value={mailType}
            onChange={(e) =>
              setMailType(e.target.value as V2MailboxBulkInjectIn["mail_type"])
            }
            style={inputStyle()}
          >
            <option value="invoice">Faktura</option>
            <option value="reminder">Påminnelse</option>
            <option value="authority">Myndighetsbrev</option>
            <option value="info">Info</option>
          </select>
        </FormField>
      </div>
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "1fr 1fr",
          gap: 12,
          marginBottom: 12,
        }}
      >
        <FormField label="Belopp (SEK)">
          <input
            value={amount}
            onChange={(e) => setAmount(e.target.value.replace(/[^\d.]/g, ""))}
            style={inputStyle()}
            placeholder="850"
          />
        </FormField>
        <FormField label="Förfallodatum (YYYY-MM-DD)">
          <input
            type="date"
            value={dueDate}
            onChange={(e) => setDueDate(e.target.value)}
            style={inputStyle()}
          />
        </FormField>
      </div>
      <FormField label="Ämne">
        <input
          value={subject}
          onChange={(e) => setSubject(e.target.value)}
          style={inputStyle()}
        />
      </FormField>
      <div style={{ marginTop: 12 }}>
        <FormField label="Brev-text">
          <textarea
            value={body}
            onChange={(e) => setBody(e.target.value)}
            rows={3}
            style={{
              ...inputStyle(),
              fontFamily: "Source Serif 4, Georgia, serif",
              resize: "vertical",
            }}
          />
        </FormField>
      </div>

      <div
        style={{
          marginTop: 14,
          fontFamily: "JetBrains Mono, monospace",
          fontSize: 9.5,
          color: "rgba(255,255,255,0.5)",
          letterSpacing: 0.5,
          textTransform: "uppercase",
          marginBottom: 8,
        }}
      >
        Skicka till:
      </div>
      <div style={{ display: "flex", gap: 8, marginBottom: 10 }}>
        <TargetButton
          label={`Hela klassen (${students.length})`}
          active={target === "all"}
          onClick={() => setTarget("all")}
        />
        <TargetButton
          label={`Välj manuellt (${selectedIds.size})`}
          active={target === "selected"}
          onClick={() => setTarget("selected")}
        />
      </div>
      {target === "selected" && (
        <div
          style={{
            display: "flex",
            flexWrap: "wrap",
            gap: 6,
            marginBottom: 14,
            maxHeight: 200,
            overflowY: "auto",
            padding: 8,
            background: "rgba(15,21,37,0.6)",
            border: "1px solid var(--line, rgba(255,255,255,0.1))",
            borderRadius: 6,
          }}
        >
          {students.map((stu) => {
            const on = selectedIds.has(stu.student_id);
            return (
              <button
                type="button"
                key={stu.student_id}
                onClick={() => toggleStudent(stu.student_id)}
                style={{
                  fontFamily: "JetBrains Mono, monospace",
                  fontSize: 10,
                  padding: "5px 10px",
                  borderRadius: 100,
                  border: `1px solid ${
                    on
                      ? "var(--warm, #fbbf24)"
                      : "var(--line-strong, rgba(255,255,255,0.18))"
                  }`,
                  background: on
                    ? "rgba(251,191,36,0.15)"
                    : "transparent",
                  color: on ? "var(--warm, #fbbf24)" : "rgba(255,255,255,0.7)",
                  cursor: "pointer",
                }}
              >
                {on ? "✓ " : ""}
                {stu.student_name}
              </button>
            );
          })}
        </div>
      )}

      {error && (
        <div
          style={{
            color: "#fca5a5",
            fontSize: 11,
            marginTop: 8,
            fontFamily: "JetBrains Mono, monospace",
          }}
        >
          {error}
        </div>
      )}

      <div style={{ display: "flex", gap: 10, marginTop: 14 }}>
        <button
          type="button"
          disabled={
            submitting
            || (target === "selected" && selectedIds.size === 0)
          }
          onClick={submit}
          className="larare-tb-btn solid"
          style={{ cursor: submitting ? "wait" : "pointer" }}
        >
          {submitting
            ? "Skickar…"
            : target === "all"
            ? `Skicka till alla ${students.length} →`
            : `Skicka till ${selectedIds.size} valda →`}
        </button>
        <button
          type="button"
          onClick={onClose}
          className="larare-tb-btn"
        >
          Avbryt
        </button>
      </div>
    </div>
  );
}

function FormField({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <div
        style={{
          fontFamily: "JetBrains Mono, monospace",
          fontSize: 9.5,
          color: "rgba(255,255,255,0.5)",
          letterSpacing: 0.5,
          textTransform: "uppercase",
          marginBottom: 4,
        }}
      >
        {label}
      </div>
      {children}
    </div>
  );
}

function inputStyle(): React.CSSProperties {
  return {
    width: "100%",
    background: "rgba(15,21,37,0.6)",
    border: "1px solid var(--line-strong, rgba(255,255,255,0.18))",
    color: "#fff",
    padding: "9px 12px",
    borderRadius: 6,
    fontFamily: "Inter, sans-serif",
    fontSize: 13,
  };
}

function TargetButton({
  label,
  active,
  onClick,
}: {
  label: string;
  active: boolean;
  onClick: () => void;
}) {
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
          ? "rgba(220,76,43,0.18)"
          : "rgba(255,255,255,0.05)",
        border: `1px solid ${
          active
            ? "var(--accent, #dc4c2b)"
            : "var(--line-strong, rgba(255,255,255,0.18))"
        }`,
        color: active ? "var(--accent, #dc4c2b)" : "rgba(255,255,255,0.7)",
        cursor: "pointer",
      }}
    >
      {label}
    </button>
  );
}
