import { useEffect, useState } from "react";
import { Copy, Plus, Share2, Trash2 } from "lucide-react";
import { api } from "@/api/client";

type Criterion = {
  key: string;
  name: string;
  levels: string[];
};

type Template = {
  id: number;
  teacher_id: number | null;
  owner_name: string | null;
  name: string;
  description: string | null;
  criteria: Criterion[];
  is_shared: boolean;
  is_mine: boolean;
  created_at: string;
};

const EMPTY: Template = {
  id: 0, teacher_id: null, owner_name: null,
  name: "", description: "",
  criteria: [{ key: "c1", name: "Kriterium 1", levels: ["Låg", "Medel", "Hög"] }],
  is_shared: false, is_mine: true, created_at: "",
};

export default function TeacherRubrics() {
  const [templates, setTemplates] = useState<Template[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const [editing, setEditing] = useState<Template | null>(null);

  async function load() {
    try {
      setTemplates(await api<Template[]>("/teacher/rubric-templates"));
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    }
  }
  useEffect(() => {
    load();
  }, []);

  async function save(t: Template) {
    const body = {
      name: t.name,
      description: t.description,
      criteria: t.criteria,
      is_shared: t.is_shared,
    };
    if (t.id === 0) {
      await api("/teacher/rubric-templates", {
        method: "POST", body: JSON.stringify(body),
      });
    } else {
      await api(`/teacher/rubric-templates/${t.id}`, {
        method: "PATCH", body: JSON.stringify(body),
      });
    }
    setEditing(null);
    load();
  }

  async function remove(id: number) {
    if (!confirm("Radera mallen?")) return;
    await api(`/teacher/rubric-templates/${id}`, { method: "DELETE" });
    load();
  }

  async function clone(id: number) {
    await api(`/teacher/rubric-templates/${id}/clone`, { method: "POST" });
    load();
  }

  return (
    <div className="max-w-4xl mx-auto p-6 space-y-5">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold text-slate-900">Rubric-mallar</h1>
        <button
          onClick={() => setEditing({ ...EMPTY })}
          className="bg-brand-600 hover:bg-brand-700 text-white rounded-lg px-4 py-2 text-sm font-medium flex items-center gap-2"
        >
          <Plus className="w-4 h-4" /> Ny mall
        </button>
      </div>

      {err && (
        <div className="bg-rose-50 border border-rose-200 text-rose-700 text-sm rounded p-3">
          {err}
        </div>
      )}

      <ul className="divide-y divide-slate-200 border rounded-xl bg-white">
        {templates.length === 0 && (
          <li className="p-4 text-sm text-slate-500">
            Inga mallar än. Skapa en som du kan återanvända på reflect-steg.
          </li>
        )}
        {templates.map((t) => (
          <li key={t.id} className="p-4 flex items-start gap-3">
            <div className="flex-1">
              <div className="flex items-center gap-2">
                <div className="font-semibold text-slate-900">{t.name}</div>
                {t.is_shared && (
                  <span className="inline-flex items-center gap-0.5 text-xs bg-emerald-100 text-emerald-700 rounded px-1.5 py-0.5">
                    <Share2 className="w-3 h-3" /> Delad
                  </span>
                )}
                {!t.is_mine && (
                  <span className="text-xs text-slate-500">
                    av {t.owner_name ?? "system"}
                  </span>
                )}
              </div>
              {t.description && (
                <div className="text-sm text-slate-600 mt-0.5">
                  {t.description}
                </div>
              )}
              <div className="text-xs text-slate-500 mt-1">
                {t.criteria.length} kriterier ·{" "}
                {t.criteria.map((c) => c.name).join(", ")}
              </div>
            </div>
            <div className="flex gap-1">
              {t.is_mine ? (
                <>
                  <button
                    onClick={() => setEditing(t)}
                    className="text-xs px-2 py-1 border rounded hover:bg-slate-50"
                  >
                    Redigera
                  </button>
                  <button
                    onClick={() => remove(t.id)}
                    className="p-1 text-slate-400 hover:text-rose-600"
                    title="Radera"
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                </>
              ) : (
                <button
                  onClick={() => clone(t.id)}
                  className="text-xs px-2 py-1 border rounded hover:bg-slate-50 flex items-center gap-1"
                >
                  <Copy className="w-3 h-3" /> Klona
                </button>
              )}
            </div>
          </li>
        ))}
      </ul>

      {editing && (
        <TemplateEditor
          initial={editing}
          onClose={() => setEditing(null)}
          onSave={save}
        />
      )}
    </div>
  );
}

function TemplateEditor({
  initial, onClose, onSave,
}: { initial: Template; onClose: () => void; onSave: (t: Template) => void }) {
  const [t, setT] = useState<Template>(initial);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  function updateCrit(i: number, patch: Partial<Criterion>) {
    const n = [...t.criteria];
    n[i] = { ...n[i], ...patch };
    setT({ ...t, criteria: n });
  }

  return (
    <div
      onClick={onClose}
      className="fixed inset-0 z-30 bg-slate-900/40 flex items-center justify-center p-4"
    >
      <div
        onClick={(e) => e.stopPropagation()}
        className="bg-white rounded-xl shadow-xl p-6 w-full max-w-2xl space-y-4 max-h-[90vh] overflow-y-auto"
      >
        <h2 className="text-lg font-semibold">
          {t.id === 0 ? "Skapa mall" : "Redigera mall"}
        </h2>
        <input
          type="text"
          value={t.name}
          onChange={(e) => setT({ ...t, name: e.target.value })}
          placeholder="Mallens namn"
          className="w-full px-3 py-2 border rounded-lg"
        />
        <textarea
          value={t.description ?? ""}
          onChange={(e) => setT({ ...t, description: e.target.value })}
          rows={2}
          placeholder="Beskrivning (valfri)"
          className="w-full px-3 py-2 border rounded-lg text-sm"
        />
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={t.is_shared}
            onChange={(e) => setT({ ...t, is_shared: e.target.checked })}
          />
          Dela med andra lärare (de kan klona men inte ändra)
        </label>

        <div>
          <div className="font-semibold mb-2">Kriterier</div>
          <ul className="space-y-3">
            {t.criteria.map((c, i) => (
              <li key={i} className="border rounded p-3 space-y-2">
                <div className="flex gap-2">
                  <input
                    type="text"
                    value={c.key}
                    onChange={(e) => updateCrit(i, { key: e.target.value })}
                    placeholder="nyckel"
                    className="w-32 px-2 py-1 border rounded text-sm"
                  />
                  <input
                    type="text"
                    value={c.name}
                    onChange={(e) => updateCrit(i, { name: e.target.value })}
                    placeholder="Namn"
                    className="flex-1 px-2 py-1 border rounded text-sm"
                  />
                  <button
                    onClick={() =>
                      setT({
                        ...t,
                        criteria: t.criteria.filter((_, j) => j !== i),
                      })
                    }
                    className="text-slate-400 hover:text-rose-600"
                    title="Ta bort kriterium"
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                </div>
                <div className="space-y-1">
                  {c.levels.map((lvl, li) => (
                    <div key={li} className="flex gap-2 items-center">
                      <span className="text-xs text-slate-500 w-4">{li}</span>
                      <input
                        type="text"
                        value={lvl}
                        onChange={(e) => {
                          const levels = [...c.levels];
                          levels[li] = e.target.value;
                          updateCrit(i, { levels });
                        }}
                        className="flex-1 px-2 py-1 border rounded text-sm"
                      />
                      {c.levels.length > 2 && (
                        <button
                          onClick={() =>
                            updateCrit(i, {
                              levels: c.levels.filter((_, j) => j !== li),
                            })
                          }
                          className="text-slate-400 hover:text-rose-600 text-xs"
                        >
                          ×
                        </button>
                      )}
                    </div>
                  ))}
                  {c.levels.length < 6 && (
                    <button
                      onClick={() =>
                        updateCrit(i, { levels: [...c.levels, ""] })
                      }
                      className="text-xs nav-link"
                    >
                      + lägg till nivå
                    </button>
                  )}
                </div>
              </li>
            ))}
          </ul>
          <button
            onClick={() =>
              setT({
                ...t,
                criteria: [
                  ...t.criteria,
                  {
                    key: `c${t.criteria.length + 1}`,
                    name: `Kriterium ${t.criteria.length + 1}`,
                    levels: ["Låg", "Medel", "Hög"],
                  },
                ],
              })
            }
            className="mt-2 text-sm nav-link"
          >
            + lägg till kriterium
          </button>
        </div>

        {err && <div className="text-sm text-rose-600">{err}</div>}
        <div className="flex justify-end gap-2">
          <button
            onClick={onClose}
            className="px-4 py-2 text-sm border rounded hover:bg-slate-50"
          >
            Avbryt
          </button>
          <button
            onClick={async () => {
              setErr(null);
              if (!t.name.trim())
                return setErr("Mallen behöver ett namn.");
              setBusy(true);
              try {
                await onSave(t);
              } catch (e) {
                setErr(e instanceof Error ? e.message : String(e));
              } finally {
                setBusy(false);
              }
            }}
            disabled={busy}
            className="px-4 py-2 text-sm bg-brand-600 hover:bg-brand-700 text-white rounded disabled:opacity-50"
          >
            {busy ? "Sparar…" : "Spara"}
          </button>
        </div>
      </div>
    </div>
  );
}
