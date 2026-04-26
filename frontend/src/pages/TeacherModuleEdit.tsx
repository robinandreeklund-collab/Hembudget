import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
  ArrowLeft, BookOpen, CheckCircle2, FileText, HelpCircle,
  PlayCircle, Plus, Save, Trash2, UserPlus,
} from "lucide-react";
import { api } from "@/api/client";

type Step = {
  id: number;
  module_id: number;
  sort_order: number;
  kind: "read" | "watch" | "reflect" | "task" | "quiz";
  title: string;
  content: string | null;
  params: Record<string, unknown> | null;
};

type ModuleDetail = {
  id: number;
  teacher_id: number | null;
  title: string;
  summary: string | null;
  is_template: boolean;
  steps: Step[];
};

type Student = { id: number; display_name: string; class_label: string | null };

const KIND_LABELS: Record<Step["kind"], { label: string; icon: React.ReactNode }> = {
  read: { label: "Läs (markdown-text)", icon: <BookOpen className="w-4 h-4" /> },
  watch: { label: "Titta (video)", icon: <PlayCircle className="w-4 h-4" /> },
  reflect: { label: "Reflektera (öppen fråga)", icon: <FileText className="w-4 h-4" /> },
  quiz: { label: "Quiz (flerval)", icon: <HelpCircle className="w-4 h-4" /> },
  task: { label: "Uppdrag (task)", icon: <CheckCircle2 className="w-4 h-4" /> },
};

export default function TeacherModuleEdit() {
  const { moduleId } = useParams<{ moduleId: string }>();
  const mid = parseInt(moduleId || "0", 10);
  const [mod, setMod] = useState<ModuleDetail | null>(null);
  const [activeStepId, setActiveStepId] = useState<number | null>(null);
  const [students, setStudents] = useState<Student[]>([]);
  const [showAssign, setShowAssign] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function load() {
    try {
      setMod(await api<ModuleDetail>(`/teacher/modules/${mid}`));
      setStudents(await api<Student[]>("/teacher/students"));
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    }
  }
  useEffect(() => {
    load();
  }, [mid]);

  async function saveModule(m: ModuleDetail) {
    await api(`/teacher/modules/${mid}`, {
      method: "PATCH",
      body: JSON.stringify({
        title: m.title,
        summary: m.summary,
        is_template: m.is_template,
      }),
    });
  }

  async function addStep(kind: Step["kind"]) {
    await api(`/teacher/modules/${mid}/steps`, {
      method: "POST",
      body: JSON.stringify({
        kind,
        title: "Nytt steg",
        content: kind === "read" ? "Skriv innehållet här…" : null,
        params:
          kind === "quiz"
            ? {
                question: "Fråga?",
                options: ["Alternativ 1", "Alternativ 2"],
                correct_index: 0,
                explanation: "Förklaring…",
              }
            : kind === "watch"
            ? { video_url: "" }
            : null,
      }),
    });
    await load();
  }

  async function saveStep(st: Step) {
    await api(`/teacher/modules/${mid}/steps/${st.id}`, {
      method: "PATCH",
      body: JSON.stringify({
        kind: st.kind, title: st.title,
        content: st.content, params: st.params,
        sort_order: st.sort_order,
      }),
    });
    await load();
  }

  async function removeStep(step_id: number) {
    if (!confirm("Ta bort steget?")) return;
    await api(`/teacher/modules/${mid}/steps/${step_id}`, { method: "DELETE" });
    await load();
  }

  async function assign(studentIds: number[]) {
    await api(`/teacher/modules/${mid}/assign`, {
      method: "POST",
      body: JSON.stringify({ student_ids: studentIds }),
    });
    setShowAssign(false);
  }

  if (err) return <div className="p-6 text-rose-600">{err}</div>;
  if (!mod) return <div className="p-6 text-slate-500">Laddar…</div>;

  const active = mod.steps.find((s) => s.id === activeStepId);

  return (
    <div className="min-h-screen bg-slate-50 p-6">
      <div className="max-w-6xl mx-auto space-y-4">
        <Link
          to="/teacher/modules"
          className="text-sm text-slate-600 hover:text-ink flex items-center gap-1"
        >
          <ArrowLeft className="w-4 h-4" /> Alla moduler
        </Link>

        {/* Modul-header */}
        <div className="bg-white border-[1.5px] border-rule p-5 space-y-3">
          <input
            value={mod.title}
            onChange={(e) => setMod({ ...mod, title: e.target.value })}
            onBlur={() => saveModule(mod)}
            className="w-full text-2xl font-bold border-0 outline-none bg-transparent"
          />
          <textarea
            value={mod.summary ?? ""}
            onChange={(e) => setMod({ ...mod, summary: e.target.value })}
            onBlur={() => saveModule(mod)}
            placeholder="Kort beskrivning…"
            rows={2}
            className="w-full border rounded px-2 py-1 text-sm"
          />
          <div className="flex items-center gap-3 text-xs text-slate-600">
            <label className="flex items-center gap-1.5">
              <input
                type="checkbox"
                checked={mod.is_template}
                onChange={async (e) => {
                  const m = { ...mod, is_template: e.target.checked };
                  setMod(m);
                  await saveModule(m);
                }}
              />
              Spara som mall
            </label>
            <button
              onClick={() => setShowAssign(true)}
              className="ml-auto inline-flex items-center gap-1 bg-emerald-600 hover:bg-emerald-700 text-white rounded px-3 py-1.5 text-sm"
            >
              <UserPlus className="w-4 h-4" /> Tilldela elever
            </button>
          </div>
        </div>

        {/* Steg-editor */}
        <div className="grid md:grid-cols-[260px_1fr] gap-4">
          <aside className="bg-white border-[1.5px] border-rule p-3 h-fit">
            <div className="font-semibold text-sm mb-2 text-slate-700">
              Steg ({mod.steps.length})
            </div>
            <ul className="space-y-1">
              {mod.steps.map((s, i) => (
                <li key={s.id}>
                  <button
                    onClick={() => setActiveStepId(s.id)}
                    className={`w-full text-left rounded px-2 py-1.5 text-sm flex items-center gap-2 ${
                      activeStepId === s.id
                        ? "bg-brand-100 text-brand-800 font-medium"
                        : "hover:bg-slate-100"
                    }`}
                  >
                    <span className="text-slate-400 text-xs w-4">{i + 1}.</span>
                    <span className="flex items-center gap-1 text-slate-400">
                      {KIND_LABELS[s.kind].icon}
                    </span>
                    <span className="truncate flex-1">{s.title}</span>
                  </button>
                </li>
              ))}
            </ul>
            <div className="mt-3 pt-3 border-t space-y-1">
              <div className="text-xs text-slate-500 mb-1">Lägg till steg:</div>
              {(Object.keys(KIND_LABELS) as Step["kind"][]).map((k) => (
                <button
                  key={k}
                  onClick={() => addStep(k)}
                  className="w-full text-left text-sm px-2 py-1 rounded hover:bg-slate-100 flex items-center gap-2 text-slate-700"
                >
                  <Plus className="w-3.5 h-3.5" /> {KIND_LABELS[k].label}
                </button>
              ))}
            </div>
          </aside>

          <main>
            {active ? (
              <StepEditor
                step={active}
                onSave={saveStep}
                onDelete={() => removeStep(active.id)}
              />
            ) : (
              <div className="bg-white border-[1.5px] border-rule p-8 text-center text-slate-500">
                Välj ett steg i listan eller lägg till ett nytt.
              </div>
            )}
          </main>
        </div>
      </div>

      {showAssign && (
        <AssignModal
          students={students}
          onClose={() => setShowAssign(false)}
          onAssign={assign}
        />
      )}
    </div>
  );
}

function StepEditor({
  step, onSave, onDelete,
}: {
  step: Step;
  onSave: (st: Step) => void | Promise<void>;
  onDelete: () => void;
}) {
  const [local, setLocal] = useState<Step>(step);
  useEffect(() => setLocal(step), [step.id]);

  async function save() {
    await onSave(local);
  }

  return (
    <div className="bg-white border-[1.5px] border-rule p-5 space-y-4">
      <div className="flex items-center gap-2">
        <span className="inline-flex items-center gap-1 text-xs bg-slate-100 text-slate-600 rounded px-2 py-1">
          {KIND_LABELS[local.kind].icon} {KIND_LABELS[local.kind].label}
        </span>
        <button
          onClick={onDelete}
          className="ml-auto text-rose-500 hover:bg-rose-50 rounded p-1.5"
          title="Ta bort"
        >
          <Trash2 className="w-4 h-4" />
        </button>
      </div>

      <label className="block">
        <span className="text-xs text-slate-500">Titel</span>
        <input
          value={local.title}
          onChange={(e) => setLocal({ ...local, title: e.target.value })}
          className="w-full border rounded px-2 py-1.5 mt-1"
        />
      </label>

      {(local.kind === "read" || local.kind === "reflect") && (
        <label className="block">
          <span className="text-xs text-slate-500">
            {local.kind === "read" ? "Text eleven läser (markdown stödjs inte än)" : "Fråga till eleven"}
          </span>
          <textarea
            value={local.content ?? ""}
            onChange={(e) => setLocal({ ...local, content: e.target.value })}
            rows={local.kind === "read" ? 10 : 4}
            className="w-full border rounded px-2 py-1.5 mt-1 font-mono text-sm"
          />
        </label>
      )}
      {local.kind === "reflect" && (
        <>
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={!!local.params?.peer_review}
              onChange={(e) =>
                setLocal({
                  ...local,
                  params: {
                    ...(local.params ?? {}),
                    peer_review: e.target.checked,
                  },
                })
              }
            />
            Aktivera kamratrespons för detta steg (eleverna får läsa och
            kommentera varandras reflektioner anonymt)
          </label>
          <RubricEditor local={local} setLocal={setLocal} />
        </>
      )}

      {local.kind === "watch" && (
        <>
          <label className="block">
            <span className="text-xs text-slate-500">
              Text före videon (valfritt)
            </span>
            <textarea
              value={local.content ?? ""}
              onChange={(e) => setLocal({ ...local, content: e.target.value })}
              rows={3}
              className="w-full border rounded px-2 py-1.5 mt-1"
            />
          </label>
          <label className="block">
            <span className="text-xs text-slate-500">Video-URL (YouTube)</span>
            <input
              value={(local.params?.video_url as string) ?? ""}
              onChange={(e) =>
                setLocal({
                  ...local,
                  params: { ...(local.params ?? {}), video_url: e.target.value },
                })
              }
              placeholder="https://www.youtube.com/watch?v=…"
              className="w-full border rounded px-2 py-1.5 mt-1"
            />
          </label>
        </>
      )}

      {local.kind === "quiz" && <QuizEditor local={local} setLocal={setLocal} />}

      {local.kind === "task" && (
        <label className="block">
          <span className="text-xs text-slate-500">Instruktioner till eleven</span>
          <textarea
            value={local.content ?? ""}
            onChange={(e) => setLocal({ ...local, content: e.target.value })}
            rows={3}
            className="w-full border rounded px-2 py-1.5 mt-1"
          />
        </label>
      )}

      <button
        onClick={save}
        className="btn-dark rounded-md px-4 py-2 inline-flex items-center gap-1"
      >
        <Save className="w-4 h-4" /> Spara
      </button>
    </div>
  );
}

function QuizEditor({
  local, setLocal,
}: { local: Step; setLocal: (s: Step) => void }) {
  const params = local.params ?? {};
  const options = ((params.options as string[]) ?? []).slice();
  const isMulti = Array.isArray(params.correct_indices);
  const correct = (params.correct_index as number) ?? 0;
  const correctSet = new Set((params.correct_indices as number[]) ?? []);

  function setMode(multi: boolean) {
    if (multi) {
      const next = { ...params };
      next.correct_indices = correct != null ? [correct] : [];
      delete next.correct_index;
      setLocal({ ...local, params: next });
    } else {
      const next = { ...params };
      next.correct_index = correctSet.size > 0 ? Math.min(...correctSet) : 0;
      delete next.correct_indices;
      setLocal({ ...local, params: next });
    }
  }

  return (
    <div className="space-y-2">
      <label className="block">
        <span className="text-xs text-slate-500">Fråga</span>
        <input
          value={(params.question as string) ?? ""}
          onChange={(e) =>
            setLocal({
              ...local,
              params: { ...params, question: e.target.value },
            })
          }
          className="w-full border rounded px-2 py-1.5 mt-1"
        />
      </label>

      <div className="flex gap-1 text-xs bg-slate-100 rounded p-1">
        <button
          onClick={() => setMode(false)}
          className={`flex-1 rounded py-1 ${
            !isMulti ? "bg-white shadow text-brand-700 font-medium" : "text-slate-600"
          }`}
        >
          Ett rätt svar
        </button>
        <button
          onClick={() => setMode(true)}
          className={`flex-1 rounded py-1 ${
            isMulti ? "bg-white shadow text-brand-700 font-medium" : "text-slate-600"
          }`}
        >
          Flera rätt svar
        </button>
      </div>

      <div className="space-y-1">
        <div className="text-xs text-slate-500">
          Svarsalternativ ({isMulti ? "bocka ALLA rätta" : "välj det rätta"})
        </div>
        {options.map((opt, i) => (
          <div key={i} className="flex items-center gap-2">
            {isMulti ? (
              <input
                type="checkbox"
                checked={correctSet.has(i)}
                onChange={(e) => {
                  const next = new Set(correctSet);
                  if (e.target.checked) next.add(i); else next.delete(i);
                  setLocal({
                    ...local,
                    params: { ...params, correct_indices: [...next].sort() },
                  });
                }}
              />
            ) : (
              <input
                type="radio"
                checked={correct === i}
                onChange={() =>
                  setLocal({
                    ...local,
                    params: { ...params, correct_index: i },
                  })
                }
              />
            )}
            <input
              value={opt}
              onChange={(e) => {
                const next = [...options];
                next[i] = e.target.value;
                setLocal({ ...local, params: { ...params, options: next } });
              }}
              className="flex-1 border rounded px-2 py-1 text-sm"
            />
            <button
              onClick={() => {
                const next = options.filter((_, j) => j !== i);
                const nextParams: Record<string, unknown> = {
                  ...params, options: next,
                };
                if (isMulti) {
                  nextParams.correct_indices = [...correctSet]
                    .filter((c) => c !== i)
                    .map((c) => (c > i ? c - 1 : c));
                } else {
                  nextParams.correct_index = Math.min(correct, next.length - 1);
                }
                setLocal({ ...local, params: nextParams });
              }}
              className="text-rose-500 hover:text-rose-700 text-xs"
            >
              Ta bort
            </button>
          </div>
        ))}
        <button
          onClick={() =>
            setLocal({
              ...local,
              params: {
                ...params,
                options: [...options, `Alternativ ${options.length + 1}`],
              },
            })
          }
          className="text-sm nav-link"
        >
          + Lägg till alternativ
        </button>
      </div>
      <label className="block">
        <span className="text-xs text-slate-500">
          Förklaring (visas efter svar)
        </span>
        <textarea
          value={(params.explanation as string) ?? ""}
          onChange={(e) =>
            setLocal({
              ...local,
              params: { ...params, explanation: e.target.value },
            })
          }
          rows={2}
          className="w-full border rounded px-2 py-1.5 mt-1 text-sm"
        />
      </label>
    </div>
  );
}

function RubricEditor({
  local, setLocal,
}: { local: Step; setLocal: (s: Step) => void }) {
  const rubric = ((local.params?.rubric as Array<{
    key: string; name: string; levels: string[];
  }>) ?? []).slice();

  function setRubric(next: typeof rubric) {
    setLocal({
      ...local,
      params: { ...(local.params ?? {}), rubric: next },
    });
  }

  function addCrit() {
    setRubric([
      ...rubric,
      {
        key: `crit_${rubric.length + 1}`,
        name: "Nytt kriterium",
        levels: ["Grundläggande", "Skicklig", "Utmärkt"],
      },
    ]);
  }

  return (
    <div className="border rounded p-3 bg-slate-50 space-y-3">
      <div className="flex items-center justify-between">
        <div className="text-xs font-semibold text-slate-700 uppercase tracking-wide">
          Bedömningsmatris (rubric) — valfritt
        </div>
        <button
          onClick={addCrit}
          className="text-xs nav-link"
        >
          + Lägg till kriterium
        </button>
      </div>
      {rubric.length === 0 && (
        <p className="text-xs text-slate-500">
          Lägg till kriterier om du vill bedöma kvaliteten på elevens svar
          med en matris. T.ex. "Djup" / "Struktur" / "Reflektionsförmåga".
        </p>
      )}
      {rubric.map((crit, i) => (
        <div key={i} className="bg-white rounded border p-3 space-y-2">
          <div className="flex items-center gap-2">
            <input
              value={crit.name}
              onChange={(e) => {
                const n = [...rubric];
                n[i] = { ...crit, name: e.target.value };
                setRubric(n);
              }}
              className="flex-1 border rounded px-2 py-1 text-sm font-medium"
            />
            <button
              onClick={() => setRubric(rubric.filter((_, j) => j !== i))}
              className="text-rose-500 hover:text-rose-700 text-xs"
            >
              Ta bort
            </button>
          </div>
          <div className="text-xs text-slate-500">Nivåer (från lägst till högst):</div>
          {crit.levels.map((lvl, j) => (
            <div key={j} className="flex items-center gap-2">
              <span className="text-xs text-slate-400 w-4">{j + 1}.</span>
              <input
                value={lvl}
                onChange={(e) => {
                  const n = [...rubric];
                  const levs = [...crit.levels];
                  levs[j] = e.target.value;
                  n[i] = { ...crit, levels: levs };
                  setRubric(n);
                }}
                className="flex-1 border rounded px-2 py-1 text-xs"
              />
              <button
                onClick={() => {
                  const n = [...rubric];
                  n[i] = {
                    ...crit,
                    levels: crit.levels.filter((_, k) => k !== j),
                  };
                  setRubric(n);
                }}
                className="text-rose-400 hover:text-rose-600 text-xs"
              >
                ×
              </button>
            </div>
          ))}
          <button
            onClick={() => {
              const n = [...rubric];
              n[i] = {
                ...crit,
                levels: [...crit.levels, `Nivå ${crit.levels.length + 1}`],
              };
              setRubric(n);
            }}
            className="text-xs nav-link"
          >
            + Lägg till nivå
          </button>
        </div>
      ))}
    </div>
  );
}


function AssignModal({
  students, onClose, onAssign,
}: {
  students: Student[];
  onClose: () => void;
  onAssign: (ids: number[]) => Promise<void>;
}) {
  const [selected, setSelected] = useState<Set<number>>(new Set());
  return (
    <div className="fixed inset-0 bg-black/40 grid place-items-center z-50" onClick={onClose}>
      <div
        className="bg-white rounded-xl p-5 w-[28rem] max-h-[80vh] overflow-y-auto space-y-3"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 className="font-semibold">Tilldela modulen</h2>
        {students.length === 0 ? (
          <div className="text-sm text-slate-500">Inga elever.</div>
        ) : (
          <ul className="space-y-1">
            {students.map((s) => (
              <li key={s.id}>
                <label className="flex items-center gap-2 py-1">
                  <input
                    type="checkbox"
                    checked={selected.has(s.id)}
                    onChange={(e) => {
                      const n = new Set(selected);
                      if (e.target.checked) n.add(s.id);
                      else n.delete(s.id);
                      setSelected(n);
                    }}
                  />
                  <span className="text-sm">
                    {s.display_name}
                    {s.class_label && (
                      <span className="text-slate-400 ml-2">{s.class_label}</span>
                    )}
                  </span>
                </label>
              </li>
            ))}
          </ul>
        )}
        <div className="flex justify-end gap-2 pt-3 border-t">
          <button onClick={onClose} className="px-3 py-1.5 text-slate-600 hover:bg-slate-100 rounded">
            Avbryt
          </button>
          <button
            onClick={() => onAssign([...selected])}
            disabled={selected.size === 0}
            className="bg-emerald-600 hover:bg-emerald-700 text-white rounded px-4 py-1.5 disabled:opacity-50"
          >
            Tilldela {selected.size} elever
          </button>
        </div>
      </div>
    </div>
  );
}
