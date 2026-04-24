import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  ArrowLeft, BookOpen, ChevronRight, Edit2, Library, Plus, Trash2,
} from "lucide-react";
import { api } from "@/api/client";

type Module = {
  id: number;
  teacher_id: number | null;
  title: string;
  summary: string | null;
  is_template: boolean;
  sort_order: number;
  step_count: number;
};

export default function TeacherModules() {
  const nav = useNavigate();
  const [mods, setMods] = useState<Module[]>([]);
  const [showCreate, setShowCreate] = useState(false);
  const [newTitle, setNewTitle] = useState("");
  const [newSummary, setNewSummary] = useState("");
  const [err, setErr] = useState<string | null>(null);

  async function load() {
    try {
      setMods(await api<Module[]>("/teacher/modules"));
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    }
  }

  useEffect(() => {
    load();
  }, []);

  async function create() {
    if (!newTitle.trim()) return;
    const m = await api<Module & { steps: unknown[] }>("/teacher/modules", {
      method: "POST",
      body: JSON.stringify({
        title: newTitle.trim(), summary: newSummary.trim() || null,
      }),
    });
    setShowCreate(false);
    setNewTitle(""); setNewSummary("");
    nav(`/teacher/modules/${m.id}`);
  }

  async function remove(id: number) {
    if (!confirm("Ta bort modulen och alla dess steg?")) return;
    await api(`/teacher/modules/${id}`, { method: "DELETE" });
    load();
  }

  return (
    <div className="p-6 max-w-4xl mx-auto space-y-6">
      <Link
        to="/teacher"
        className="text-sm text-slate-600 hover:text-brand-700 flex items-center gap-1"
      >
        <ArrowLeft className="w-4 h-4" /> Lärarpanel
      </Link>
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Library className="w-6 h-6 text-brand-600" />
          <h1 className="text-2xl font-semibold">Kursmoduler</h1>
        </div>
        <button
          onClick={() => setShowCreate(true)}
          className="bg-brand-600 hover:bg-brand-700 text-white rounded-lg px-4 py-2 flex items-center gap-2"
        >
          <Plus className="w-4 h-4" /> Ny modul
        </button>
      </div>
      {err && (
        <div className="bg-rose-50 text-rose-700 border border-rose-200 rounded p-3 text-sm">
          {err}
        </div>
      )}

      {mods.length === 0 ? (
        <div className="bg-amber-50 border border-amber-200 text-amber-900 rounded p-4 text-sm">
          Inga moduler än. Skapa din första för att börja bygga en kursplan.
        </div>
      ) : (
        <ul className="space-y-2">
          {mods.map((m) => (
            <li
              key={m.id}
              className="bg-white border rounded-xl p-4 flex items-center gap-3 hover:shadow-md transition-shadow"
            >
              <BookOpen className="w-5 h-5 text-brand-600 shrink-0" />
              <div className="flex-1 min-w-0">
                <Link
                  to={`/teacher/modules/${m.id}`}
                  className="font-semibold text-slate-900 hover:underline"
                >
                  {m.title}
                </Link>
                {m.is_template && (
                  <span className="ml-2 text-xs bg-amber-100 text-amber-800 rounded px-1.5 py-0.5">
                    mall
                  </span>
                )}
                {m.summary && (
                  <p className="text-sm text-slate-600 truncate">{m.summary}</p>
                )}
                <div className="text-xs text-slate-500 mt-1">
                  {m.step_count} steg
                </div>
              </div>
              <Link
                to={`/teacher/modules/${m.id}`}
                className="p-2 text-slate-500 hover:text-brand-700"
                title="Redigera"
              >
                <Edit2 className="w-4 h-4" />
              </Link>
              {m.teacher_id != null && (
                <button
                  onClick={() => remove(m.id)}
                  className="p-2 text-slate-400 hover:text-rose-600"
                  title="Ta bort"
                >
                  <Trash2 className="w-4 h-4" />
                </button>
              )}
              <ChevronRight className="w-4 h-4 text-slate-300" />
            </li>
          ))}
        </ul>
      )}

      {/* Skapa-modal */}
      {showCreate && (
        <div
          className="fixed inset-0 bg-black/40 grid place-items-center z-50"
          onClick={() => setShowCreate(false)}
        >
          <div
            className="bg-white rounded-xl shadow-xl p-6 w-[28rem] space-y-3"
            onClick={(e) => e.stopPropagation()}
          >
            <h2 className="font-semibold text-lg">Ny modul</h2>
            <input
              value={newTitle}
              onChange={(e) => setNewTitle(e.target.value)}
              placeholder="Titel"
              className="w-full border rounded px-3 py-2"
              autoFocus
            />
            <textarea
              value={newSummary}
              onChange={(e) => setNewSummary(e.target.value)}
              placeholder="Kort beskrivning (valfritt)"
              rows={3}
              className="w-full border rounded px-3 py-2"
            />
            <div className="flex justify-end gap-2 pt-2">
              <button
                onClick={() => setShowCreate(false)}
                className="px-3 py-2 text-slate-600 hover:bg-slate-100 rounded"
              >
                Avbryt
              </button>
              <button
                onClick={create}
                disabled={!newTitle.trim()}
                className="bg-brand-600 text-white rounded px-4 py-2 disabled:opacity-50"
              >
                Skapa
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
