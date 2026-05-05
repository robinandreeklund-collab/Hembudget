/**
 * Lärar-vy · modul-redigering (Fas 2AO).
 *
 * Routas via /teacher/v2/modul/:moduleId.
 *
 * Funktionalitet:
 * - Visa modul-info (titel, summary, system-flagga)
 * - Ändra titel/summary
 * - Lista alla steg
 * - Lägg till nytt steg (kind, titel, content, sort_order)
 * - Ändra ett steg
 * - Ta bort ett steg
 * - Knapp "Tilldela till elever" (öppnar modal)
 *
 * System-mallar är read-only — visa info-banner.
 */
import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import {
  v2Api,
  type V2RosterRow,
  type V2TeacherModuleDetail,
  type V2TeacherModuleStepKind,
  type V2TeacherModuleStepOut,
} from "./api";
import { V2Banner } from "./V2Banner";
import "./larare.css";

const STEP_KINDS: { value: V2TeacherModuleStepKind; label: string }[] = [
  { value: "read", label: "Läs (markdown-text)" },
  { value: "watch", label: "Titta (video-embed)" },
  { value: "reflect", label: "Reflektera (eleven skriver)" },
  { value: "task", label: "Uppgift (auto-bedömt via app)" },
  { value: "quiz", label: "Quiz (flerval med rätt svar)" },
];

const KIND_COLOR: Record<V2TeacherModuleStepKind, string> = {
  read: "rgba(255,255,255,0.6)",
  watch: "#a5b4fc",
  reflect: "var(--warm, #fbbf24)",
  task: "var(--accent, #dc4c2b)",
  quiz: "#6ee7b7",
};

export function TeacherModuleEditV2() {
  const { moduleId } = useParams<{ moduleId: string }>();
  const mid = moduleId ? parseInt(moduleId, 10) : 0;
  const [module, setModule] = useState<V2TeacherModuleDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [editingMeta, setEditingMeta] = useState(false);
  const [showAddStep, setShowAddStep] = useState(false);
  const [editingStepId, setEditingStepId] = useState<number | null>(null);
  const [showAssign, setShowAssign] = useState(false);
  const [confirmDeleteStep, setConfirmDeleteStep] = useState<
    V2TeacherModuleStepOut | null
  >(null);
  const [message, setMessage] = useState<string | null>(null);
  const navigate = useNavigate();

  async function load() {
    try {
      const data = await v2Api.teacherGetModule(mid);
      setModule(data);
    } catch (e) {
      setError(String((e as Error)?.message || e));
    }
  }

  useEffect(() => {
    if (!mid) return;
    load();
  }, [mid]);

  function flash(text: string) {
    setMessage(text);
    window.setTimeout(() => setMessage(null), 5000);
  }

  if (error && !module) {
    return (
      <div className="v2-larare-root">
        <V2Banner status={{ role: "teacher", is_super_admin: false }} />
        <div className="larare-loading">
          <div>
            <div style={{ color: "#fca5a5", marginBottom: 8 }}>
              Kunde inte ladda modulen
            </div>
            <pre style={{ fontSize: 11 }}>{error}</pre>
          </div>
        </div>
      </div>
    );
  }
  if (!module) {
    return (
      <div className="v2-larare-root">
        <V2Banner status={{ role: "teacher", is_super_admin: false }} />
        <div className="larare-loading">Laddar modulen…</div>
      </div>
    );
  }

  const isOwn = module.teacher_id !== null;

  return (
    <div className="v2-larare-root">
      <V2Banner status={{ role: "teacher", is_super_admin: false }} />

      <div className="shell">
        <a
          className="attn-go"
          onClick={(e) => {
            e.preventDefault();
            navigate("/teacher/v2/moduler");
          }}
          href="#"
          style={{ marginBottom: 22, display: "inline-block" }}
        >
          ← Tillbaka till modulbiblioteket
        </a>

        <header className="larare-head">
          <div>
            <span className="pill">
              {isOwn ? "Egen modul" : "Systemmall · skrivskyddad"}
            </span>
            <h1 className="larare-head-h1">
              {module.title}
              {module.is_template && isOwn && (
                <em
                  style={{
                    fontSize: "0.45em",
                    marginLeft: 12,
                    fontFamily: "JetBrains Mono",
                    color: "var(--warm)",
                    fontStyle: "normal",
                    letterSpacing: 1.4,
                    fontWeight: 400,
                  }}
                >
                  · MALL
                </em>
              )}
            </h1>
            {module.summary && (
              <p
                style={{
                  fontFamily: "Source Serif 4, Georgia, serif",
                  fontSize: 16,
                  color: "rgba(255,255,255,0.7)",
                  marginTop: 12,
                  lineHeight: 1.55,
                }}
              >
                {module.summary}
              </p>
            )}
            <div className="larare-actions">
              {isOwn && (
                <button
                  type="button"
                  onClick={() => setEditingMeta(true)}
                  className="larare-tb-btn"
                >
                  Redigera info
                </button>
              )}
              {isOwn && (
                <button
                  type="button"
                  onClick={() => setShowAddStep(true)}
                  className="larare-tb-btn solid"
                >
                  + Lägg till steg
                </button>
              )}
              <button
                type="button"
                onClick={() => setShowAssign(true)}
                className="larare-tb-btn"
                style={{
                  background: "rgba(110,231,183,0.10)",
                  color: "#6ee7b7",
                  borderColor: "rgba(110,231,183,0.4)",
                }}
              >
                Tilldela till elever
              </button>
              {!isOwn && (
                <button
                  type="button"
                  onClick={async () => {
                    try {
                      const cloned = await v2Api.teacherCloneModule(module.id);
                      navigate(`/teacher/v2/moduler/${cloned.id}`);
                    } catch (e) {
                      setError(String((e as Error)?.message || e));
                    }
                  }}
                  className="larare-tb-btn"
                  style={{
                    background: "rgba(251,191,36,0.10)",
                    color: "var(--warm)",
                    borderColor: "rgba(251,191,36,0.4)",
                  }}
                >
                  Klona för redigering
                </button>
              )}
            </div>
          </div>
          <div className="larare-head-meta">
            Antal steg: <strong>{module.steps.length}</strong>
            <br />
            Skapad:{" "}
            <strong>
              {new Date(module.created_at).toLocaleDateString("sv-SE")}
            </strong>
            <br />
            Typ:{" "}
            <strong>{isOwn ? "egen" : "system"}</strong>
          </div>
        </header>

        {!isOwn && (
          <div
            style={{
              padding: "12px 16px",
              background: "rgba(99,102,241,0.06)",
              border: "1px solid rgba(99,102,241,0.25)",
              borderLeft: "3px solid #818cf8",
              borderRadius: 6,
              fontFamily: "JetBrains Mono, monospace",
              fontSize: 11,
              color: "#c7d2fe",
              letterSpacing: 0.6,
              marginBottom: 18,
            }}
          >
            🔒 Detta är en systemmall — ej redigerbar. Använd "Klona för
            redigering" för att skapa egen kopia.
          </div>
        )}

        {message && (
          <div
            style={{
              padding: "10px 14px",
              background: "rgba(110,231,183,0.10)",
              border: "1px solid rgba(110,231,183,0.35)",
              borderRadius: 6,
              fontFamily: "JetBrains Mono, monospace",
              fontSize: 11,
              color: "#6ee7b7",
              letterSpacing: 0.6,
              marginBottom: 16,
            }}
          >
            ✓ {message}
          </div>
        )}

        {/* Steg-tabell */}
        <div className="section-title">
          Steg ({module.steps.length}) ·{" "}
          {isOwn ? "klick för att redigera" : "klick för att förhandsgranska"}
        </div>
        {module.steps.length === 0 ? (
          <div
            style={{
              padding: "24px 28px",
              border: "1px dashed var(--line-strong, rgba(255,255,255,0.18))",
              borderRadius: 6,
              fontFamily: "Source Serif 4, Georgia, serif",
              color: "rgba(255,255,255,0.55)",
              marginBottom: 22,
            }}
          >
            {isOwn
              ? "Modulen har inga steg än. Klicka \"+ Lägg till steg\" för att börja."
              : "Modulen har inga steg."}
          </div>
        ) : (
          <div
            style={{
              background: "rgba(15,21,37,0.7)",
              border: "1px solid var(--line, rgba(255,255,255,0.1))",
              borderRadius: 6,
              overflow: "hidden",
              marginBottom: 22,
            }}
          >
            {module.steps
              .sort((a, b) => a.sort_order - b.sort_order)
              .map((s, idx) => (
                <div
                  key={s.id}
                  style={{
                    display: "grid",
                    gridTemplateColumns: "30px 80px 1fr auto",
                    gap: 12,
                    padding: "14px 18px",
                    borderBottom:
                      "1px solid var(--line, rgba(255,255,255,0.05))",
                    alignItems: "center",
                  }}
                >
                  <span
                    style={{
                      fontFamily: "JetBrains Mono, monospace",
                      fontSize: 10,
                      color: "rgba(255,255,255,0.4)",
                    }}
                  >
                    {idx + 1}
                  </span>
                  <span
                    style={{
                      fontFamily: "JetBrains Mono, monospace",
                      fontSize: 9.5,
                      color: KIND_COLOR[s.kind],
                      letterSpacing: 1,
                      textTransform: "uppercase",
                      fontWeight: 700,
                    }}
                  >
                    {s.kind}
                  </span>
                  <div>
                    <div
                      style={{
                        fontFamily: "Source Serif 4, Georgia, serif",
                        fontSize: 14,
                        color: "#fff",
                      }}
                    >
                      {s.title}
                    </div>
                    {s.content && (
                      <div
                        style={{
                          fontFamily: "JetBrains Mono, monospace",
                          fontSize: 9.5,
                          color: "rgba(255,255,255,0.4)",
                          marginTop: 2,
                        }}
                      >
                        {s.content.slice(0, 110)}
                        {s.content.length > 110 ? "…" : ""}
                      </div>
                    )}
                  </div>
                  {isOwn && (
                    <div style={{ display: "flex", gap: 6 }}>
                      <button
                        type="button"
                        onClick={() => setEditingStepId(s.id)}
                        className="attn-go"
                        style={pillBtn(
                          "var(--warm, #fbbf24)",
                          "rgba(251,191,36,0.10)",
                        )}
                      >
                        Ändra
                      </button>
                      <button
                        type="button"
                        onClick={() => setConfirmDeleteStep(s)}
                        className="attn-go"
                        style={pillBtn(
                          "var(--accent, #dc4c2b)",
                          "rgba(220,76,43,0.08)",
                        )}
                      >
                        Radera
                      </button>
                    </div>
                  )}
                </div>
              ))}
          </div>
        )}

        <Link
          to="/teacher/v2/moduler"
          className="larare-tb-btn"
          style={{ display: "inline-block" }}
        >
          ← Modulbiblioteket
        </Link>
      </div>

      {editingMeta && (
        <EditMetaModal
          module={module}
          onClose={() => setEditingMeta(false)}
          onSaved={() => {
            setEditingMeta(false);
            flash("Modul-info sparat");
            load();
          }}
        />
      )}
      {showAddStep && (
        <StepModal
          mode="add"
          moduleId={module.id}
          step={null}
          nextSortOrder={
            (module.steps.reduce((a, s) => Math.max(a, s.sort_order), -1)
              + 10)
          }
          onClose={() => setShowAddStep(false)}
          onSaved={() => {
            setShowAddStep(false);
            flash("Steg tillagt");
            load();
          }}
        />
      )}
      {editingStepId !== null && (
        <StepModal
          mode="edit"
          moduleId={module.id}
          step={module.steps.find((s) => s.id === editingStepId) || null}
          nextSortOrder={0}
          onClose={() => setEditingStepId(null)}
          onSaved={() => {
            setEditingStepId(null);
            flash("Steg uppdaterat");
            load();
          }}
        />
      )}
      {confirmDeleteStep && (
        <ConfirmDeleteStepModal
          moduleId={module.id}
          step={confirmDeleteStep}
          onClose={() => setConfirmDeleteStep(null)}
          onDeleted={() => {
            setConfirmDeleteStep(null);
            flash("Steget raderat");
            load();
          }}
        />
      )}
      {showAssign && (
        <AssignModuleModal
          moduleId={module.id}
          moduleTitle={module.title}
          onClose={() => setShowAssign(false)}
          onAssigned={(count) => {
            setShowAssign(false);
            flash(
              `Tilldelad till ${count} elev${count === 1 ? "" : "er"}`,
            );
          }}
        />
      )}
    </div>
  );
}

function EditMetaModal({
  module: m, onClose, onSaved,
}: {
  module: V2TeacherModuleDetail;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [title, setTitle] = useState(m.title);
  const [summary, setSummary] = useState(m.summary || "");
  const [isTemplate, setIsTemplate] = useState(m.is_template);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  async function save() {
    if (submitting || title.trim().length === 0) return;
    setSubmitting(true);
    setError(null);
    try {
      await v2Api.teacherUpdateModule(m.id, {
        title: title.trim(),
        summary: summary.trim() || undefined,
        is_template: isTemplate,
      });
      onSaved();
    } catch (e) {
      setError(String((e as Error)?.message || e));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <ModalShell title="Redigera modul-info" eye="● Modul-info" onClose={onClose}>
      <FormRow label="Titel">
        <input
          autoFocus
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          maxLength={200}
          style={modalInputStyle()}
        />
      </FormRow>
      <FormRow label="Sammanfattning">
        <textarea
          value={summary}
          onChange={(e) => setSummary(e.target.value)}
          rows={3}
          style={{
            ...modalInputStyle(),
            fontFamily: "Source Serif 4, Georgia, serif",
            resize: "vertical",
          }}
        />
      </FormRow>
      <FormRow label="Mallstatus">
        <label
          style={{
            display: "flex",
            gap: 10,
            alignItems: "center",
            fontFamily: "JetBrains Mono, monospace",
            fontSize: 11,
            color: "rgba(255,255,255,0.7)",
            cursor: "pointer",
            padding: "8px 10px",
            background: "rgba(255,255,255,0.04)",
            borderRadius: 6,
            border: "1px solid var(--line-strong, rgba(255,255,255,0.18))",
          }}
        >
          <input
            type="checkbox"
            checked={isTemplate}
            onChange={(e) => setIsTemplate(e.target.checked)}
          />
          Mall (kan användas som utgångspunkt för andra)
        </label>
      </FormRow>
      {error && <ErrorBox text={error} />}
      <ModalFooter
        onClose={onClose}
        onSubmit={save}
        submitLabel={submitting ? "Sparar…" : "Spara"}
        disabled={submitting || title.trim().length === 0}
      />
    </ModalShell>
  );
}

function StepModal({
  mode, moduleId, step, nextSortOrder, onClose, onSaved,
}: {
  mode: "add" | "edit";
  moduleId: number;
  step: V2TeacherModuleStepOut | null;
  nextSortOrder: number;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [kind, setKind] = useState<V2TeacherModuleStepKind>(
    step?.kind || "read",
  );
  const [title, setTitle] = useState(step?.title || "");
  const [content, setContent] = useState(step?.content || "");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  async function save() {
    if (submitting || title.trim().length === 0) return;
    setSubmitting(true);
    setError(null);
    try {
      const body = {
        kind,
        title: title.trim(),
        content: content.trim() || undefined,
        sort_order: step?.sort_order ?? nextSortOrder,
      };
      if (mode === "add") {
        await v2Api.teacherCreateModuleStep(moduleId, body);
      } else if (step) {
        await v2Api.teacherUpdateModuleStep(moduleId, step.id, body);
      }
      onSaved();
    } catch (e) {
      setError(String((e as Error)?.message || e));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <ModalShell
      title={mode === "add" ? "Nytt steg" : "Ändra steg"}
      eye="● Modul-steg"
      onClose={onClose}
    >
      <FormRow label="Typ">
        <select
          value={kind}
          onChange={(e) =>
            setKind(e.target.value as V2TeacherModuleStepKind)
          }
          style={modalInputStyle()}
        >
          {STEP_KINDS.map((k) => (
            <option key={k.value} value={k.value}>
              {k.label}
            </option>
          ))}
        </select>
      </FormRow>
      <FormRow label="Titel">
        <input
          autoFocus
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          placeholder="ex: Räkna KALP för 2,4 Mkr"
          maxLength={200}
          style={modalInputStyle()}
        />
      </FormRow>
      <FormRow label="Innehåll (markdown / instruktioner)">
        <textarea
          value={content}
          onChange={(e) => setContent(e.target.value)}
          placeholder={
            kind === "reflect"
              ? "Skriv frågan eleven ska reflektera över…"
              : kind === "quiz"
              ? "Skriv frågan + lägg svars-alternativ i params (avancerat)"
              : kind === "task"
              ? "Vad ska eleven göra konkret?"
              : "Markdown-text eller video-URL beroende på typ"
          }
          rows={6}
          style={{
            ...modalInputStyle(),
            fontFamily: "Source Serif 4, Georgia, serif",
            resize: "vertical",
          }}
        />
      </FormRow>
      {error && <ErrorBox text={error} />}
      <ModalFooter
        onClose={onClose}
        onSubmit={save}
        submitLabel={
          submitting
            ? "Sparar…"
            : mode === "add"
            ? "Lägg till steg"
            : "Spara ändringar"
        }
        disabled={submitting || title.trim().length === 0}
      />
    </ModalShell>
  );
}

function ConfirmDeleteStepModal({
  moduleId, step, onClose, onDeleted,
}: {
  moduleId: number;
  step: V2TeacherModuleStepOut;
  onClose: () => void;
  onDeleted: () => void;
}) {
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function deleteIt() {
    if (submitting) return;
    setSubmitting(true);
    setError(null);
    try {
      await v2Api.teacherDeleteModuleStep(moduleId, step.id);
      onDeleted();
    } catch (e) {
      setError(String((e as Error)?.message || e));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <ModalShell
      title={`Radera "${step.title}"?`}
      eye="● Bekräfta"
      borderColor="var(--accent, #dc4c2b)"
      onClose={onClose}
    >
      <p
        style={{
          fontFamily: "Source Serif 4, Georgia, serif",
          fontSize: 14,
          color: "rgba(255,255,255,0.85)",
          marginTop: 0,
          marginBottom: 14,
          lineHeight: 1.5,
        }}
      >
        Steget tas bort permanent. Elever som redan markerat det som klart
        behåller sin progress, men raderingen går inte att ångra.
      </p>
      {error && <ErrorBox text={error} />}
      <ModalFooter
        onClose={onClose}
        onSubmit={deleteIt}
        submitLabel={submitting ? "Raderar…" : "Ja, radera"}
        submitColor="var(--accent, #dc4c2b)"
        disabled={submitting}
      />
    </ModalShell>
  );
}

function AssignModuleModal({
  moduleId, moduleTitle, onClose, onAssigned,
}: {
  moduleId: number;
  moduleTitle: string;
  onClose: () => void;
  onAssigned: (count: number) => void;
}) {
  const [students, setStudents] = useState<V2RosterRow[] | null>(null);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    v2Api
      .roster()
      .then(setStudents)
      .catch((e) => setError(String((e as Error)?.message || e)));
  }, []);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  function toggle(id: number) {
    setSelected((s) => {
      const next = new Set(s);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  async function submit() {
    if (submitting || selected.size === 0) return;
    setSubmitting(true);
    setError(null);
    try {
      const res = await v2Api.teacherAssignModule(
        moduleId, Array.from(selected),
      );
      onAssigned(res.assigned);
    } catch (e) {
      setError(String((e as Error)?.message || e));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <ModalShell
      title={`Tilldela "${moduleTitle}"`}
      eye="● Tilldela modul"
      onClose={onClose}
    >
      {!students ? (
        <div
          style={{
            padding: 16,
            color: "rgba(255,255,255,0.5)",
            fontFamily: "JetBrains Mono, monospace",
            fontSize: 11,
          }}
        >
          Laddar elev-listan…
        </div>
      ) : students.length === 0 ? (
        <p
          style={{
            color: "rgba(255,255,255,0.5)",
            fontFamily: "Source Serif 4",
            fontSize: 13,
          }}
        >
          Du har inga elever att tilldela till.
        </p>
      ) : (
        <>
          <div style={{ display: "flex", gap: 8, marginBottom: 10 }}>
            <button
              type="button"
              onClick={() =>
                setSelected(new Set(students.map((s) => s.student_id)))
              }
              className="attn-go"
              style={pillBtn(
                "var(--warm, #fbbf24)",
                "rgba(251,191,36,0.10)",
              )}
            >
              Välj alla ({students.length})
            </button>
            <button
              type="button"
              onClick={() => setSelected(new Set())}
              className="attn-go"
              style={pillBtn(
                "rgba(255,255,255,0.5)",
                "rgba(255,255,255,0.04)",
              )}
            >
              Rensa
            </button>
            <span
              style={{
                marginLeft: "auto",
                alignSelf: "center",
                fontFamily: "JetBrains Mono, monospace",
                fontSize: 10,
                color: "rgba(255,255,255,0.5)",
              }}
            >
              {selected.size} valda
            </span>
          </div>
          <div
            style={{
              display: "flex",
              flexWrap: "wrap",
              gap: 6,
              maxHeight: 240,
              overflowY: "auto",
              padding: 8,
              background: "rgba(15,21,37,0.6)",
              border: "1px solid var(--line, rgba(255,255,255,0.1))",
              borderRadius: 6,
              marginBottom: 12,
            }}
          >
            {students.map((s) => {
              const on = selected.has(s.student_id);
              return (
                <button
                  key={s.student_id}
                  type="button"
                  onClick={() => toggle(s.student_id)}
                  style={{
                    fontFamily: "JetBrains Mono, monospace",
                    fontSize: 10,
                    padding: "6px 12px",
                    borderRadius: 100,
                    border: `1px solid ${
                      on
                        ? "var(--warm, #fbbf24)"
                        : "var(--line-strong, rgba(255,255,255,0.18))"
                    }`,
                    background: on ? "rgba(251,191,36,0.15)" : "transparent",
                    color: on
                      ? "var(--warm, #fbbf24)"
                      : "rgba(255,255,255,0.7)",
                    cursor: "pointer",
                  }}
                >
                  {on ? "✓ " : ""}{s.display_name}
                </button>
              );
            })}
          </div>
        </>
      )}
      {error && <ErrorBox text={error} />}
      <ModalFooter
        onClose={onClose}
        onSubmit={submit}
        submitLabel={
          submitting
            ? "Tilldelar…"
            : `Tilldela ${selected.size}${
                selected.size === 1 ? " elev" : " elever"
              } →`
        }
        disabled={submitting || selected.size === 0}
      />
    </ModalShell>
  );
}

// === Shared helpers (samma som i TeacherModuleLibraryV2) ===

function ModalShell({
  title, eye, borderColor, onClose, children,
}: {
  title: string;
  eye: string;
  borderColor?: string;
  onClose: () => void;
  children: React.ReactNode;
}) {
  return (
    <div
      role="dialog"
      aria-modal="true"
      onClick={onClose}
      style={{
        position: "fixed",
        inset: 0,
        zIndex: 200,
        background: "rgba(0,0,0,0.55)",
        display: "grid",
        placeItems: "center",
        padding: 16,
      }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          width: "100%",
          maxWidth: 640,
          background: "rgba(15,21,37,0.98)",
          border: "1px solid var(--line-strong, rgba(255,255,255,0.18))",
          borderTop: `3px solid ${borderColor || "var(--warm, #fbbf24)"}`,
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
            color: borderColor || "var(--warm, #fbbf24)",
            marginBottom: 6,
          }}
        >
          {eye}
        </div>
        <h2
          style={{
            fontFamily: "Source Serif 4, Georgia, serif",
            fontSize: 22,
            fontWeight: 700,
            color: "#fff",
            margin: "0 0 14px",
            letterSpacing: -0.4,
          }}
        >
          {title}
        </h2>
        {children}
      </div>
    </div>
  );
}

function ModalFooter({
  onClose, onSubmit, submitLabel, disabled = false, submitColor,
}: {
  onClose: () => void;
  onSubmit: () => void;
  submitLabel: string;
  disabled?: boolean;
  submitColor?: string;
}) {
  return (
    <div
      style={{
        display: "flex",
        gap: 10,
        marginTop: 18,
        justifyContent: "flex-end",
      }}
    >
      <button type="button" onClick={onClose} className="larare-tb-btn">
        Avbryt
      </button>
      <button
        type="button"
        disabled={disabled}
        onClick={onSubmit}
        className="larare-tb-btn solid"
        style={{
          background: submitColor || "var(--warm, #fbbf24)",
          color: submitColor ? "#fff" : "#422006",
          borderColor: submitColor || "var(--warm, #fbbf24)",
          opacity: disabled ? 0.5 : 1,
          cursor: disabled ? "not-allowed" : "pointer",
        }}
      >
        {submitLabel}
      </button>
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

function ErrorBox({ text }: { text: string }) {
  return (
    <div
      style={{
        color: "#fca5a5",
        fontSize: 11,
        marginTop: 8,
        fontFamily: "JetBrains Mono, monospace",
      }}
    >
      {text}
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

function pillBtn(color: string, bg: string): React.CSSProperties {
  return {
    fontFamily: "JetBrains Mono, monospace",
    fontSize: 9.5,
    fontWeight: 700,
    letterSpacing: 1,
    textTransform: "uppercase",
    padding: "6px 11px",
    borderRadius: 100,
    background: bg,
    border: `1px solid ${color}`,
    color,
    cursor: "pointer",
    textDecoration: "none",
  };
}
