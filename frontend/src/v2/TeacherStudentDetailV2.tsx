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
  type V2PentAxis,
} from "./api";
import { V2Banner } from "./V2Banner";
import { PentagonFlipCard } from "./PentagonFlipCard";
import { TeacherStudentSpelmotorPanel } from "./TeacherStudentSpelmotorPanel";
import { useAuth } from "../hooks/useAuth";
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
  const [activeAxis, setActiveAxis] = useState<V2PentAxis | null>(null);
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
          <PentagonFlipCard
            activeAxis={activeAxis}
            onClose={() => setActiveAxis(null)}
            fetchDetail={async (axis) => {
              const res = await v2Api.teacherPentagonAxisDetail(sid, axis);
              return res.detail;
            }}
            front={
              <StudentPentagon
                data={data}
                onAxisClick={setActiveAxis}
              />
            }
          />
          <StudentSideStack data={data} />
        </div>

        <CompetencyGrid competencies={data.competencies} sid={data.student_id} />

        {data.recent_events.length > 0 && (
          <RecentEvents events={data.recent_events} />
        )}

        {/* Sprint 1-6 spelmotor-panel: tick-historik + pentagon-händelser
            + snabbspola + sjuk/VAB/event-summary. */}
        <TeacherStudentSpelmotorPanel studentId={data.student_id} />
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
  const [showCreateAssignment, setShowCreateAssignment] = useState(false);
  const [showPromote, setShowPromote] = useState(false);
  const [showOverride, setShowOverride] = useState(false);
  const [createMessage, setCreateMessage] = useState<string | null>(null);
  const { impersonate } = useAuth();

  function startImpersonation() {
    impersonate(data.student_id);
    // Navigera till v2-elev-hubben i ny flik så läraren behåller
    // sin lärar-session i original-fliken.
    window.open("/v2/hub", "_blank", "noopener");
  }
  return (
    <div
      style={{
        display: "flex",
        gap: 10,
        flexWrap: "wrap",
        marginBottom: 24,
        position: "relative",
      }}
    >
      <button
        type="button"
        className="larare-tb-btn solid"
        onClick={() => setShowCreateAssignment(true)}
        style={{ background: "var(--accent, #dc4c2b)", color: "#fff" }}
      >
        + Skicka uppdrag
      </button>
      <button
        type="button"
        className="larare-tb-btn"
        onClick={startImpersonation}
        style={{
          background: "rgba(99,102,241,0.18)",
          border: "1px solid rgba(99,102,241,0.45)",
          color: "#c7d2fe",
        }}
      >
        👤 Impersonera elev →
      </button>
      {data.level_progression.target_level && (
        <button
          type="button"
          className="larare-tb-btn"
          onClick={() => setShowPromote(true)}
          style={{
            background: "rgba(110,231,183,0.10)",
            border: "1px solid rgba(110,231,183,0.45)",
            color: "#6ee7b7",
          }}
        >
          ▰▰▱ Aktivera Nivå {data.level_progression.target_level}
        </button>
      )}
      <button
        type="button"
        className="larare-tb-btn"
        onClick={() => setShowOverride(true)}
        style={{
          background: "rgba(251,191,36,0.10)",
          border: "1px solid rgba(251,191,36,0.45)",
          color: "var(--warm, #fbbf24)",
        }}
      >
        ★ Höj kompetens manuellt
      </button>
      <Link
        className="larare-tb-btn"
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

      {createMessage && (
        <div
          role="status"
          style={{
            width: "100%",
            marginTop: 6,
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
          ✓ {createMessage}
        </div>
      )}

      {showCreateAssignment && (
        <CreateAssignmentModal
          studentId={data.student_id}
          studentName={data.student_name}
          onClose={() => setShowCreateAssignment(false)}
          onCreated={(title) => {
            setCreateMessage(
              `Uppdrag "${title}" skickat till ${data.student_name.split(" ")[0]}`,
            );
            setShowCreateAssignment(false);
            window.setTimeout(() => setCreateMessage(null), 6000);
            // Soft refresh så assignments-räknaren uppdateras
            window.setTimeout(() => navigate(0), 600);
          }}
        />
      )}
      {showPromote && data.level_progression.target_level && (
        <PromoteLevelModal
          studentId={data.student_id}
          studentName={data.student_name}
          currentLevel={data.v2_level}
          targetLevel={data.level_progression.target_level}
          onClose={() => setShowPromote(false)}
          onPromoted={(newLevel) => {
            setCreateMessage(
              `${data.student_name.split(" ")[0]} är nu på Nivå ${newLevel}`,
            );
            setShowPromote(false);
            window.setTimeout(() => setCreateMessage(null), 6000);
            window.setTimeout(() => navigate(0), 600);
          }}
        />
      )}
      {showOverride && (
        <OverrideCompetencyModal
          studentId={data.student_id}
          studentName={data.student_name}
          competencies={data.competencies}
          onClose={() => setShowOverride(false)}
          onOverridden={(name, level) => {
            setCreateMessage(
              `${name} satt till ${level} för ${data.student_name.split(" ")[0]}`,
            );
            setShowOverride(false);
            window.setTimeout(() => setCreateMessage(null), 6000);
            window.setTimeout(() => navigate(0), 600);
          }}
        />
      )}
    </div>
  );
}

function OverrideCompetencyModal({
  studentId,
  studentName,
  competencies,
  onClose,
  onOverridden,
}: {
  studentId: number;
  studentName: string;
  competencies: V2StudentDetailCompetency[];
  onClose: () => void;
  onOverridden: (name: string, level: string) => void;
}) {
  const [selectedCid, setSelectedCid] = useState<number>(
    competencies[0]?.competency_id || 0,
  );
  const [level, setLevel] = useState<"B" | "G" | "F">("G");
  const [motivation, setMotivation] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  async function submit() {
    if (
      submitting
      || !selectedCid
      || motivation.trim().length < 2
    ) return;
    setSubmitting(true);
    setError(null);
    try {
      const out = await v2Api.teacherOverrideCompetency(
        studentId, selectedCid,
        { level, motivation: motivation.trim() },
      );
      onOverridden(out.competency_name, out.level);
    } catch (e) {
      setError(String((e as Error)?.message || e));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div
      role="dialog"
      aria-modal="true"
      style={{
        position: "fixed", inset: 0, zIndex: 200,
        background: "rgba(0,0,0,0.55)",
        display: "grid", placeItems: "center",
        padding: 16,
      }}
      onClick={onClose}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          width: "100%", maxWidth: 540,
          background: "rgba(15,21,37,0.98)",
          border: "1px solid var(--line-strong, rgba(255,255,255,0.18))",
          borderTop: "3px solid var(--warm, #fbbf24)",
          borderRadius: 8,
          padding: "24px 28px",
          maxHeight: "calc(100vh - 80px)",
          overflowY: "auto",
        }}
      >
        <div
          style={{
            fontFamily: "JetBrains Mono, monospace",
            fontSize: 10, fontWeight: 700, letterSpacing: 1.4,
            textTransform: "uppercase", color: "var(--warm, #fbbf24)",
            marginBottom: 6,
          }}
        >
          ★ Höj kompetens manuellt
        </div>
        <h2
          style={{
            fontFamily: "Source Serif 4, Georgia, serif",
            fontSize: 22, fontWeight: 700, color: "#fff",
            margin: "0 0 6px", letterSpacing: -0.5,
          }}
        >
          Override för{" "}
          <em style={{ color: "var(--warm)", fontStyle: "italic", fontWeight: 500 }}>
            {studentName}
          </em>
        </h2>
        <p
          style={{
            fontFamily: "Source Serif 4, Georgia, serif",
            fontSize: 13, color: "rgba(255,255,255,0.55)",
            marginTop: 0, marginBottom: 16, lineHeight: 1.5,
          }}
        >
          Din höjning vinner över mastery-beräkningen. Använd när
          eleven visat fördjupad förståelse genom samtal/klassrum
          som inte fångats av modul-stegen.
        </p>

        <FormRow label="Kompetens">
          <select
            value={selectedCid}
            onChange={(e) => setSelectedCid(Number(e.target.value))}
            style={modalInputStyle()}
          >
            {competencies.map((c) => (
              <option key={c.competency_id} value={c.competency_id}>
                {c.name} (mastery: {Math.round(c.mastery * 100)} % · {c.level})
              </option>
            ))}
          </select>
        </FormRow>

        <FormRow label="Ny nivå">
          <div style={{ display: "flex", gap: 8 }}>
            {(["B", "G", "F"] as const).map((lvl) => (
              <button
                key={lvl}
                type="button"
                onClick={() => setLevel(lvl)}
                style={{
                  flex: 1,
                  padding: "10px 14px",
                  borderRadius: 6,
                  background: level === lvl
                    ? lvl === "F"
                      ? "rgba(110,231,183,0.18)"
                      : lvl === "G"
                      ? "rgba(220,76,43,0.18)"
                      : "rgba(255,255,255,0.08)"
                    : "rgba(255,255,255,0.04)",
                  border: `1px solid ${
                    level === lvl
                      ? lvl === "F"
                        ? "#6ee7b7"
                        : lvl === "G"
                        ? "var(--accent, #dc4c2b)"
                        : "rgba(255,255,255,0.4)"
                      : "var(--line-strong, rgba(255,255,255,0.18))"
                  }`,
                  color: level === lvl
                    ? lvl === "F"
                      ? "#6ee7b7"
                      : lvl === "G"
                      ? "var(--accent, #dc4c2b)"
                      : "#fff"
                    : "rgba(255,255,255,0.7)",
                  fontFamily: "JetBrains Mono, monospace",
                  fontSize: 11,
                  fontWeight: 700,
                  letterSpacing: 1.2,
                  cursor: "pointer",
                }}
              >
                {lvl} ·{" "}
                {lvl === "F" ? "FÖRDJUPNING" : lvl === "G" ? "GRUND" : "BASIS"}
              </button>
            ))}
          </div>
        </FormRow>

        <FormRow label="Motivering (visas i elevens historik)">
          <textarea
            value={motivation}
            onChange={(e) => setMotivation(e.target.value)}
            placeholder="t.ex. Visade djup förståelse i klassrum-diskussion 14 apr"
            rows={3}
            style={{
              ...modalInputStyle(),
              fontFamily: "Source Serif 4, Georgia, serif",
              resize: "vertical",
            }}
          />
        </FormRow>

        {error && (
          <div
            style={{
              color: "#fca5a5", fontSize: 11, marginTop: 8,
              fontFamily: "JetBrains Mono, monospace",
            }}
          >
            {error}
          </div>
        )}

        <div
          style={{
            display: "flex", gap: 10, marginTop: 18,
            justifyContent: "flex-end",
          }}
        >
          <button
            type="button"
            onClick={onClose}
            className="larare-tb-btn"
          >
            Avbryt
          </button>
          <button
            type="button"
            disabled={
              submitting
              || !selectedCid
              || motivation.trim().length < 2
            }
            onClick={submit}
            className="larare-tb-btn solid"
            style={{
              cursor: submitting ? "wait" : "pointer",
              background: "var(--warm, #fbbf24)",
              color: "#422006",
              borderColor: "var(--warm, #fbbf24)",
              opacity: motivation.trim().length < 2 ? 0.5 : 1,
            }}
          >
            {submitting ? "Sparar…" : `Sätt → ${level}`}
          </button>
        </div>
      </div>
    </div>
  );
}

function PromoteLevelModal({
  studentId,
  studentName,
  currentLevel,
  targetLevel,
  onClose,
  onPromoted,
}: {
  studentId: number;
  studentName: string;
  currentLevel: number;
  targetLevel: number;
  onClose: () => void;
  onPromoted: (newLevel: number) => void;
}) {
  const [motivation, setMotivation] = useState("");
  const [spendProfile, setSpendProfile] = useState<
    "auto" | "sparsam" | "balanserad" | "slosa"
  >("auto");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  async function submit() {
    if (submitting) return;
    setSubmitting(true);
    setError(null);
    try {
      const body: {
        target_level: number;
        new_spend_profile?: "sparsam" | "balanserad" | "slosa";
        motivation?: string;
      } = { target_level: targetLevel };
      if (spendProfile !== "auto") body.new_spend_profile = spendProfile;
      if (motivation.trim().length > 0) body.motivation = motivation.trim();
      await v2Api.teacherPromoteStudentLevel(studentId, body);
      onPromoted(targetLevel);
    } catch (e) {
      setError(String((e as Error)?.message || e));
    } finally {
      setSubmitting(false);
    }
  }

  const levelLabel = ["", "Sparsam", "Balanserad", "Slösa"][targetLevel] || "?";

  return (
    <div
      role="dialog"
      aria-modal="true"
      style={{
        position: "fixed", inset: 0, zIndex: 200,
        background: "rgba(0,0,0,0.55)",
        display: "grid", placeItems: "center",
        padding: 16,
      }}
      onClick={onClose}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          width: "100%", maxWidth: 540,
          background: "rgba(15,21,37,0.98)",
          border: "1px solid var(--line-strong, rgba(255,255,255,0.18))",
          borderTop: "3px solid #6ee7b7",
          borderRadius: 8,
          padding: "24px 28px",
          maxHeight: "calc(100vh - 80px)",
          overflowY: "auto",
        }}
      >
        <div
          style={{
            fontFamily: "JetBrains Mono, monospace",
            fontSize: 10, fontWeight: 700, letterSpacing: 1.4,
            textTransform: "uppercase", color: "#6ee7b7",
            marginBottom: 6,
          }}
        >
          ● Aktivera nivå
        </div>
        <h2
          style={{
            fontFamily: "Source Serif 4, Georgia, serif",
            fontSize: 24, fontWeight: 700, color: "#fff",
            margin: "0 0 6px", letterSpacing: -0.6,
          }}
        >
          Bumpa{" "}
          <em style={{ color: "var(--warm)", fontStyle: "italic", fontWeight: 500 }}>
            {studentName}
          </em>{" "}
          → Nivå {targetLevel}
        </h2>
        <p
          style={{
            fontFamily: "Source Serif 4, Georgia, serif",
            fontSize: 13, color: "rgba(255,255,255,0.55)",
            marginTop: 0, marginBottom: 16, lineHeight: 1.5,
          }}
        >
          Eleven hoppar från Nivå {currentLevel} →{" "}
          <strong style={{ color: "#6ee7b7" }}>
            Nivå {targetLevel} · {levelLabel}
          </strong>
          . Karaktären behålls men ekonomin blir svårare:
          fler oväntade brev, svårare att budgetera, mer komplexa
          val. Spendprofilen byts (kan överridas nedan).
        </p>

        <FormRow label="Ny spendprofil">
          <select
            value={spendProfile}
            onChange={(e) =>
              setSpendProfile(e.target.value as typeof spendProfile)
            }
            style={modalInputStyle()}
          >
            <option value="auto">
              Auto från nivån (
              {targetLevel === 2 ? "balanserad" : "slösa"})
            </option>
            <option value="sparsam">Sparsam</option>
            <option value="balanserad">Balanserad</option>
            <option value="slosa">Slösa</option>
          </select>
        </FormRow>
        <FormRow label="Motivering (visas i historik)">
          <textarea
            value={motivation}
            onChange={(e) => setMotivation(e.target.value)}
            placeholder="t.ex. 12 v på Nivå 1, 3 G-kompetenser, 2 av 3 moduler klara"
            rows={3}
            style={{
              ...modalInputStyle(),
              fontFamily: "Source Serif 4, Georgia, serif",
              resize: "vertical",
            }}
          />
        </FormRow>

        {error && (
          <div
            style={{
              color: "#fca5a5", fontSize: 11, marginTop: 8,
              fontFamily: "JetBrains Mono, monospace",
            }}
          >
            {error}
          </div>
        )}

        <div
          style={{
            display: "flex", gap: 10, marginTop: 18,
            justifyContent: "flex-end",
          }}
        >
          <button
            type="button"
            onClick={onClose}
            className="larare-tb-btn"
          >
            Avbryt
          </button>
          <button
            type="button"
            disabled={submitting}
            onClick={submit}
            className="larare-tb-btn solid"
            style={{
              cursor: submitting ? "wait" : "pointer",
              background: "#6ee7b7",
              color: "#064e3b",
              borderColor: "#6ee7b7",
            }}
          >
            {submitting
              ? "Aktiverar…"
              : `Aktivera Nivå ${targetLevel} →`}
          </button>
        </div>
      </div>
    </div>
  );
}

function CreateAssignmentModal({
  studentId,
  studentName,
  onClose,
  onCreated,
}: {
  studentId: number;
  studentName: string;
  onClose: () => void;
  onCreated: (title: string) => void;
}) {
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [kind, setKind] = useState<string>("free_text");
  const [dueDate, setDueDate] = useState<string>("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Esc stänger modalen
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  async function submit() {
    if (submitting || title.trim().length < 2 || description.trim().length < 2) return;
    setSubmitting(true);
    setError(null);
    try {
      const due_date = dueDate
        ? new Date(`${dueDate}T23:59:59`).toISOString()
        : null;
      await v2Api.teacherCreateAssignment(studentId, {
        title: title.trim(),
        description: description.trim(),
        kind,
        due_date,
      });
      onCreated(title.trim());
    } catch (e) {
      setError(String((e as Error)?.message || e));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div
      role="dialog"
      aria-modal="true"
      style={{
        position: "fixed",
        inset: 0,
        zIndex: 200,
        background: "rgba(0,0,0,0.55)",
        display: "grid",
        placeItems: "center",
        padding: 16,
      }}
      onClick={onClose}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          width: "100%",
          maxWidth: 560,
          background: "rgba(15,21,37,0.98)",
          border: "1px solid var(--line-strong, rgba(255,255,255,0.18))",
          borderTop: "3px solid var(--accent, #dc4c2b)",
          borderRadius: 8,
          padding: "24px 28px",
          maxHeight: "calc(100vh - 80px)",
          overflowY: "auto",
        }}
      >
        <div
          style={{
            fontFamily: "JetBrains Mono, monospace",
            fontSize: 10,
            fontWeight: 700,
            letterSpacing: 1.4,
            textTransform: "uppercase",
            color: "var(--accent, #dc4c2b)",
            marginBottom: 6,
          }}
        >
          ● Skicka uppdrag
        </div>
        <h2
          style={{
            fontFamily: "Source Serif 4, Georgia, serif",
            fontSize: 24,
            fontWeight: 700,
            color: "#fff",
            margin: "0 0 6px",
            letterSpacing: -0.6,
          }}
        >
          Nytt uppdrag till{" "}
          <em
            style={{
              fontStyle: "italic",
              color: "var(--warm, #fbbf24)",
              fontWeight: 500,
            }}
          >
            {studentName}
          </em>
        </h2>
        <p
          style={{
            fontFamily: "Source Serif 4, Georgia, serif",
            fontSize: 13,
            color: "rgba(255,255,255,0.55)",
            marginTop: 0,
            marginBottom: 16,
          }}
        >
          Eleven får uppdraget direkt i sin /v2/uppdrag-vy med deadline +
          status. Free_text bedöms manuellt — andra kind:s utvärderas
          automatiskt av appen.
        </p>

        <FormRow label="Titel">
          <input
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="ex: Räkna KALP för 2,4 Mkr-bolån"
            maxLength={200}
            style={modalInputStyle()}
          />
        </FormRow>

        <FormRow label="Beskrivning">
          <textarea
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="Vad ska eleven göra? Hänvisa gärna till relevanta verktyg…"
            rows={4}
            style={{
              ...modalInputStyle(),
              fontFamily: "Source Serif 4, Georgia, serif",
              resize: "vertical",
            }}
          />
        </FormRow>

        <div
          style={{
            display: "grid",
            gridTemplateColumns: "1fr 1fr",
            gap: 12,
          }}
        >
          <FormRow label="Bedömnings-typ">
            <select
              value={kind}
              onChange={(e) => setKind(e.target.value)}
              style={modalInputStyle()}
            >
              <option value="free_text">
                Reflektion (manuellt bedömt)
              </option>
              <option value="set_budget">Budget (auto)</option>
              <option value="balance_month">Bokslut (auto)</option>
              <option value="categorize_all">Klassa alla tx (auto)</option>
              <option value="save_amount">Spara belopp (auto)</option>
              <option value="mortgage_decision">Bolåne-beslut (auto)</option>
            </select>
          </FormRow>
          <FormRow label="Deadline (valfritt)">
            <input
              type="date"
              value={dueDate}
              onChange={(e) => setDueDate(e.target.value)}
              style={modalInputStyle()}
            />
          </FormRow>
        </div>

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

        <div
          style={{
            display: "flex",
            gap: 10,
            marginTop: 18,
            justifyContent: "flex-end",
          }}
        >
          <button
            type="button"
            onClick={onClose}
            className="larare-tb-btn"
          >
            Avbryt
          </button>
          <button
            type="button"
            disabled={
              submitting
              || title.trim().length < 2
              || description.trim().length < 2
            }
            onClick={submit}
            className="larare-tb-btn solid"
            style={{
              cursor: submitting ? "wait" : "pointer",
              background: "var(--accent, #dc4c2b)",
              color: "#fff",
              borderColor: "var(--accent, #dc4c2b)",
              opacity:
                title.trim().length < 2 || description.trim().length < 2
                  ? 0.5
                  : 1,
            }}
          >
            {submitting ? "Skickar…" : "Skicka uppdrag →"}
          </button>
        </div>
      </div>
    </div>
  );
}

function FormRow({
  label, children,
}: { label: string; children: React.ReactNode }) {
  return (
    <div style={{ marginBottom: 12 }}>
      <div
        style={{
          fontFamily: "JetBrains Mono, monospace",
          fontSize: 9.5,
          color: "rgba(255,255,255,0.5)",
          letterSpacing: 1,
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

function modalInputStyle(): React.CSSProperties {
  return {
    width: "100%",
    background: "rgba(255,255,255,0.04)",
    border: "1px solid var(--line-strong, rgba(255,255,255,0.18))",
    color: "#fff",
    padding: "9px 12px",
    borderRadius: 6,
    fontFamily: "Inter, sans-serif",
    fontSize: 13,
  };
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

function StudentPentagon({
  data,
  onAxisClick,
}: {
  data: V2TeacherStudentDetail;
  onAxisClick: (axis: V2PentAxis) => void;
}) {
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
        <button
          type="button"
          className="axis-clickable"
          onClick={() => onAxisClick("economy")}
          style={axisTagStyle()}
        >
          Ekonomi
          <strong>{p.economy}</strong>
        </button>
        <button
          type="button"
          className="axis-clickable"
          onClick={() => onAxisClick("safety")}
          style={axisTagStyle()}
        >
          Karriär
          <strong>{p.safety}</strong>
        </button>
        <button
          type="button"
          className="axis-clickable"
          onClick={() => onAxisClick("health")}
          style={axisTagStyle()}
        >
          Hälsa
          <strong>{p.health}</strong>
        </button>
        <button
          type="button"
          className="axis-clickable"
          onClick={() => onAxisClick("social")}
          style={axisTagStyle()}
        >
          Relation
          <strong>{p.social}</strong>
        </button>
        <button
          type="button"
          className="axis-clickable"
          onClick={() => onAxisClick("leisure")}
          style={axisTagStyle()}
        >
          Fritid
          <strong>{p.leisure}</strong>
        </button>
      </div>
    </article>
  );
}

function axisTagStyle(): React.CSSProperties {
  return {
    padding: "8px 6px",
    background: "rgba(255,255,255,0.03)",
    borderRadius: 4,
    border: "1px solid var(--line, rgba(255,255,255,0.1))",
    fontFamily: "JetBrains Mono, monospace",
    fontSize: 10,
    letterSpacing: 0.6,
    textTransform: "uppercase",
    color: "rgba(255,255,255,0.6)",
    textAlign: "center",
    cursor: "pointer",
  };
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
