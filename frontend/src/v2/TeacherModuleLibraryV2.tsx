/**
 * Lärar-vy · modulbibliotek (Fas 2AN).
 *
 * Speglar v1's TeacherModules men med v2-design och full CRUD-stöd
 * direkt i lärar-v2-flödet.
 *
 * Funktionalitet:
 * - Lista alla moduler (system-mallar + lärarens egna)
 * - Skapa ny modul (titel + summary + is_template)
 * - Klona en mall till egen kopia (öppnas direkt för redigering)
 * - Tilldela till elever (single eller bulk)
 * - Öppna i edit-vyn för att lägga till/ändra/ta bort steg
 * - Ta bort egna moduler
 *
 * Routas via /teacher/v2/moduler (lista) och /teacher/v2/moduler/:id
 * (detalj/edit).
 */
import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  v2Api,
  type V2RosterRow,
  type V2TeacherModuleOut,
} from "./api";
import { V2Banner } from "./V2Banner";
import "./larare.css";

const SHORT_DATE = (iso: string | null): string => {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleDateString("sv-SE", {
    day: "numeric", month: "short", year: "numeric",
  });
};

export function TeacherModuleLibraryV2() {
  const [modules, setModules] = useState<V2TeacherModuleOut[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [showCreate, setShowCreate] = useState(false);
  const [assignTarget, setAssignTarget] = useState<V2TeacherModuleOut | null>(
    null,
  );
  const [confirmDelete, setConfirmDelete] = useState<V2TeacherModuleOut | null>(
    null,
  );
  const [message, setMessage] = useState<string | null>(null);
  const navigate = useNavigate();

  async function load() {
    try {
      const data = await v2Api.teacherListModules();
      setModules(data);
    } catch (e) {
      setError(String((e as Error)?.message || e));
    }
  }

  useEffect(() => {
    load();
  }, []);

  function flash(text: string) {
    setMessage(text);
    window.setTimeout(() => setMessage(null), 5000);
  }

  async function clone(m: V2TeacherModuleOut) {
    try {
      const cloned = await v2Api.teacherCloneModule(m.id);
      flash(`Klonad: "${cloned.title}"`);
      load();
      navigate(`/teacher/v2/moduler/${cloned.id}`);
    } catch (e) {
      setError(String((e as Error)?.message || e));
    }
  }

  async function deleteIt(m: V2TeacherModuleOut) {
    try {
      await v2Api.teacherDeleteModule(m.id);
      flash(`Modulen "${m.title}" raderad.`);
      setConfirmDelete(null);
      load();
    } catch (e) {
      setError(String((e as Error)?.message || e));
    }
  }

  if (error && !modules) {
    return (
      <div className="v2-larare-root">
        <V2Banner status={{ role: "teacher", is_super_admin: false }} />
        <div className="larare-loading">
          <div>
            <div style={{ color: "#fca5a5", marginBottom: 8 }}>
              Kunde inte ladda moduler
            </div>
            <pre style={{ fontSize: 11 }}>{error}</pre>
          </div>
        </div>
      </div>
    );
  }
  if (!modules) {
    return (
      <div className="v2-larare-root">
        <V2Banner status={{ role: "teacher", is_super_admin: false }} />
        <div className="larare-loading">Laddar modulbibliotek…</div>
      </div>
    );
  }

  const ownModules = modules.filter((m) => m.teacher_id !== null);
  const systemTemplates = modules.filter(
    (m) => m.teacher_id === null && m.is_template,
  );

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
            <span className="pill">Lärar-admin · Moduler</span>
            <h1 className="larare-head-h1">
              Modulbiblioteket — <em>{modules.length} totalt</em>.
            </h1>
            <p
              style={{
                fontFamily: "Source Serif 4, Georgia, serif",
                fontSize: 16,
                color: "rgba(255,255,255,0.6)",
                marginTop: 12,
              }}
            >
              {systemTemplates.length} systemmall
              {systemTemplates.length !== 1 ? "ar" : ""} ·{" "}
              {ownModules.length} egna moduler · klona en mall för att skapa
              egen kopia, redigera stegen och tilldela till elever.
            </p>
            <div className="larare-actions">
              <button
                type="button"
                onClick={() => setShowCreate(true)}
                className="larare-tb-btn solid"
              >
                + Skapa egen modul
              </button>
              <Link
                to="/teacher/v2/skapa"
                className="larare-tb-btn"
              >
                Skapa elev
              </Link>
            </div>
          </div>
          <div className="larare-head-meta">
            Systemmallar: <strong>{systemTemplates.length}</strong>
            <br />
            Egna moduler: <strong>{ownModules.length}</strong>
            <br />
            Totalt-steg:{" "}
            <strong>
              {modules.reduce((a, m) => a + m.step_count, 0)}
            </strong>
          </div>
        </header>

        {message && (
          <div
            role="status"
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

        {/* Egna moduler */}
        <div className="section-title">
          Egna moduler ({ownModules.length})
        </div>
        {ownModules.length === 0 ? (
          <div
            style={{
              padding: "20px 24px",
              border: "1px dashed var(--line-strong, rgba(255,255,255,0.18))",
              borderRadius: 6,
              fontFamily: "Source Serif 4, Georgia, serif",
              color: "rgba(255,255,255,0.5)",
              marginBottom: 24,
            }}
          >
            Du har inga egna moduler än. Klicka "+ Skapa egen modul" eller
            klona en systemmall.
          </div>
        ) : (
          <ModuleTable
            modules={ownModules}
            onClone={clone}
            onAssign={setAssignTarget}
            onDelete={setConfirmDelete}
          />
        )}

        {/* Systemmallar */}
        <div className="section-title" style={{ marginTop: 24 }}>
          Systemmallar ({systemTemplates.length})
        </div>
        {systemTemplates.length === 0 ? (
          <div
            style={{
              padding: "20px 24px",
              border: "1px dashed var(--line-strong, rgba(255,255,255,0.18))",
              borderRadius: 6,
              fontFamily: "Source Serif 4, Georgia, serif",
              color: "rgba(255,255,255,0.5)",
              marginBottom: 24,
            }}
          >
            Inga systemmallar tillgängliga.
          </div>
        ) : (
          <ModuleTable
            modules={systemTemplates}
            onClone={clone}
            onAssign={setAssignTarget}
            onDelete={null}
            isSystem
          />
        )}
      </div>

      {showCreate && (
        <CreateModuleModal
          onClose={() => setShowCreate(false)}
          onCreated={(m) => {
            setShowCreate(false);
            flash(`Modulen "${m.title}" skapad.`);
            navigate(`/teacher/v2/moduler/${m.id}`);
          }}
        />
      )}
      {assignTarget && (
        <AssignModuleModal
          module={assignTarget}
          onClose={() => setAssignTarget(null)}
          onAssigned={(count) => {
            flash(
              `Tilldelad till ${count} elev${count === 1 ? "" : "er"}.`,
            );
            setAssignTarget(null);
          }}
        />
      )}
      {confirmDelete && (
        <ConfirmDeleteModal
          module={confirmDelete}
          onClose={() => setConfirmDelete(null)}
          onDelete={() => deleteIt(confirmDelete)}
        />
      )}
    </div>
  );
}

function ModuleTable({
  modules,
  onClone,
  onAssign,
  onDelete,
  isSystem = false,
}: {
  modules: V2TeacherModuleOut[];
  onClone: (m: V2TeacherModuleOut) => void;
  onAssign: (m: V2TeacherModuleOut) => void;
  onDelete: ((m: V2TeacherModuleOut) => void) | null;
  isSystem?: boolean;
}) {
  return (
    <div
      style={{
        background: "rgba(15,21,37,0.7)",
        border: "1px solid var(--line, rgba(255,255,255,0.1))",
        borderRadius: 6,
        overflow: "hidden",
        marginBottom: 24,
      }}
    >
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "1.6fr 80px 110px 1fr",
          gap: 12,
          padding: "11px 16px",
          background: "rgba(0,0,0,0.15)",
          borderBottom: "1px solid var(--line, rgba(255,255,255,0.1))",
          fontFamily: "JetBrains Mono, monospace",
          fontSize: 9,
          fontWeight: 700,
          letterSpacing: 1.2,
          textTransform: "uppercase",
          color: "rgba(255,255,255,0.5)",
        }}
      >
        <span>Modul</span>
        <span>Steg</span>
        <span>Skapad</span>
        <span style={{ textAlign: "right" }}>Åtgärder</span>
      </div>
      {modules.map((m) => (
        <div
          key={m.id}
          style={{
            display: "grid",
            gridTemplateColumns: "1.6fr 80px 110px 1fr",
            gap: 12,
            padding: "12px 16px",
            borderBottom: "1px solid var(--line, rgba(255,255,255,0.05))",
            alignItems: "center",
          }}
        >
          <div>
            <Link
              to={`/teacher/v2/moduler/${m.id}`}
              style={{
                fontFamily: "Source Serif 4, Georgia, serif",
                fontSize: 14,
                color: "#fff",
                textDecoration: "none",
              }}
            >
              {m.title}
            </Link>
            {m.summary && (
              <div
                style={{
                  fontFamily: "JetBrains Mono, monospace",
                  fontSize: 9.5,
                  color: "rgba(255,255,255,0.4)",
                  marginTop: 2,
                }}
              >
                {m.summary.slice(0, 100)}
                {m.summary.length > 100 ? "…" : ""}
              </div>
            )}
          </div>
          <span
            style={{
              fontFamily: "JetBrains Mono, monospace",
              fontSize: 11,
              color: "rgba(255,255,255,0.7)",
            }}
          >
            {m.step_count}
          </span>
          <span
            style={{
              fontFamily: "JetBrains Mono, monospace",
              fontSize: 10,
              color: "rgba(255,255,255,0.5)",
            }}
          >
            {SHORT_DATE(m.created_at)}
          </span>
          <div
            style={{
              display: "flex",
              gap: 6,
              justifyContent: "flex-end",
              flexWrap: "wrap",
            }}
          >
            <Link
              to={`/teacher/v2/moduler/${m.id}`}
              className="attn-go"
              style={pillBtnStyle("#a5b4fc", "rgba(99,102,241,0.10)")}
            >
              Öppna →
            </Link>
            <button
              type="button"
              onClick={() => onAssign(m)}
              className="attn-go"
              style={pillBtnStyle("#6ee7b7", "rgba(110,231,183,0.10)")}
            >
              Tilldela
            </button>
            <button
              type="button"
              onClick={() => onClone(m)}
              className="attn-go"
              style={pillBtnStyle(
                "var(--warm, #fbbf24)",
                "rgba(251,191,36,0.10)",
              )}
            >
              Klona
            </button>
            {onDelete && (
              <button
                type="button"
                onClick={() => onDelete(m)}
                className="attn-go"
                style={pillBtnStyle(
                  "var(--accent, #dc4c2b)",
                  "rgba(220,76,43,0.08)",
                )}
              >
                Radera
              </button>
            )}
          </div>
        </div>
      ))}
      {isSystem && (
        <div
          style={{
            padding: "10px 16px",
            background: "rgba(255,255,255,0.02)",
            fontFamily: "JetBrains Mono, monospace",
            fontSize: 9,
            color: "rgba(255,255,255,0.4)",
            letterSpacing: 0.6,
          }}
        >
          Systemmallar går inte att redigera direkt. Klona för att skapa
          egen kopia.
        </div>
      )}
    </div>
  );
}

function CreateModuleModal({
  onClose, onCreated,
}: {
  onClose: () => void;
  onCreated: (m: V2TeacherModuleOut) => void;
}) {
  const [title, setTitle] = useState("");
  const [summary, setSummary] = useState("");
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
    if (submitting || title.trim().length < 1) return;
    setSubmitting(true);
    setError(null);
    try {
      const m = await v2Api.teacherCreateModule({
        title: title.trim(),
        summary: summary.trim() || undefined,
        is_template: false,
      });
      onCreated(m);
    } catch (e) {
      setError(String((e as Error)?.message || e));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <ModalShell title="Skapa egen modul" eye="● Ny modul" onClose={onClose}>
      <FormRow label="Titel">
        <input
          autoFocus
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          placeholder="ex: Bolån för 2,4 Mkr"
          maxLength={200}
          style={modalInputStyle()}
        />
      </FormRow>
      <FormRow label="Sammanfattning (valfri)">
        <textarea
          value={summary}
          onChange={(e) => setSummary(e.target.value)}
          placeholder="Kort beskrivning som visas för eleven"
          rows={3}
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
        onSubmit={submit}
        submitLabel={submitting ? "Skapar…" : "Skapa →"}
        disabled={submitting || title.trim().length < 1}
      />
    </ModalShell>
  );
}

function AssignModuleModal({
  module: m,
  onClose,
  onAssigned,
}: {
  module: V2TeacherModuleOut;
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

  function selectAll() {
    if (!students) return;
    setSelected(new Set(students.map((s) => s.student_id)));
  }

  async function submit() {
    if (submitting || selected.size === 0) return;
    setSubmitting(true);
    setError(null);
    try {
      const res = await v2Api.teacherAssignModule(
        m.id, Array.from(selected),
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
      title={`Tilldela "${m.title}"`}
      eye="● Tilldela modul"
      onClose={onClose}
    >
      <p
        style={{
          fontFamily: "Source Serif 4, Georgia, serif",
          fontSize: 13,
          color: "rgba(255,255,255,0.55)",
          marginTop: 0,
          marginBottom: 14,
        }}
      >
        Välj elever som ska få modulen. Elever som redan har den hoppas
        över. Task-steg med assignment_kind blir automatiskt egna uppdrag.
      </p>
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
        <div
          style={{
            padding: 16,
            color: "rgba(255,255,255,0.5)",
            fontFamily: "Source Serif 4, Georgia, serif",
            fontSize: 13,
          }}
        >
          Du har inga elever att tilldela till. Skapa elever först.
        </div>
      ) : (
        <>
          <div
            style={{
              display: "flex",
              gap: 8,
              marginBottom: 10,
            }}
          >
            <button
              type="button"
              onClick={selectAll}
              className="attn-go"
              style={pillBtnStyle(
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
              style={pillBtnStyle(
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
                    border: `1px solid ${on
                      ? "var(--warm, #fbbf24)"
                      : "var(--line-strong, rgba(255,255,255,0.18))"
                    }`,
                    background: on
                      ? "rgba(251,191,36,0.15)"
                      : "transparent",
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
            : `Tilldela till ${selected.size}${
                selected.size === 1 ? " elev" : " elever"
              } →`
        }
        disabled={submitting || selected.size === 0}
      />
    </ModalShell>
  );
}

function ConfirmDeleteModal({
  module: m, onClose, onDelete,
}: {
  module: V2TeacherModuleOut;
  onClose: () => void;
  onDelete: () => void;
}) {
  return (
    <ModalShell
      title={`Radera "${m.title}"?`}
      eye="● Bekräfta radering"
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
        Detta tar bort modulen och alla {m.step_count} steg. Elever som
        har modulen tilldelad förlorar progressen. Det går INTE att ångra.
      </p>
      <ModalFooter
        onClose={onClose}
        onSubmit={onDelete}
        submitLabel="Ja, radera"
        submitColor="var(--accent, #dc4c2b)"
      />
    </ModalShell>
  );
}

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
          maxWidth: 560,
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
      <button
        type="button"
        onClick={onClose}
        className="larare-tb-btn"
      >
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

function pillBtnStyle(color: string, bg: string): React.CSSProperties {
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
