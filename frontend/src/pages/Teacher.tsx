import { useEffect, useState } from "react";
import { api } from "@/api/client";
import { useAuth } from "@/hooks/useAuth";
import {
  Eye,
  Loader2,
  Play,
  Plus,
  RotateCcw,
  Trash2,
  Users,
} from "lucide-react";

type Student = {
  id: number;
  display_name: string;
  class_label: string | null;
  login_code: string;
  active: boolean;
  last_login_at: string | null;
  created_at: string;
  months_generated: string[];
};

type GenerateRow = {
  student_id: number;
  display_name: string;
  year_month: string;
  status: string;
  seed?: number;
  stats?: Record<string, number>;
  error?: string;
};

function thisMonth(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

export default function Teacher() {
  const { impersonate } = useAuth();
  const [students, setStudents] = useState<Student[]>([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [newName, setNewName] = useState("");
  const [newClass, setNewClass] = useState("");
  const [ym, setYm] = useState(thisMonth());
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [overwrite, setOverwrite] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [lastRun, setLastRun] = useState<GenerateRow[] | null>(null);
  const [err, setErr] = useState<string | null>(null);

  async function reload() {
    setLoading(true);
    try {
      const list = await api<Student[]>("/teacher/students");
      setStudents(list);
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    reload();
  }, []);

  async function createStudent() {
    if (!newName.trim()) return;
    try {
      await api("/teacher/students", {
        method: "POST",
        body: JSON.stringify({
          display_name: newName.trim(),
          class_label: newClass.trim() || null,
        }),
      });
      setNewName("");
      setNewClass("");
      setShowCreate(false);
      reload();
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    }
  }

  async function deleteStudent(id: number) {
    if (!confirm("Ta bort eleven och all data?")) return;
    await api(`/teacher/students/${id}`, { method: "DELETE" });
    reload();
  }

  async function resetStudent(id: number) {
    if (!confirm("Nollställ all data för eleven? (behåller själva kontot)")) return;
    await api(`/teacher/students/${id}/reset`, { method: "POST" });
    reload();
  }

  function toggleSelect(id: number) {
    const next = new Set(selected);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    setSelected(next);
  }

  function selectAll() {
    if (selected.size === students.length) setSelected(new Set());
    else setSelected(new Set(students.map((s) => s.id)));
  }

  async function runGenerate() {
    setGenerating(true);
    setErr(null);
    setLastRun(null);
    try {
      const body = {
        year_month: ym,
        student_ids: selected.size > 0 ? [...selected] : null,
        overwrite,
      };
      const res = await api<GenerateRow[]>("/teacher/generate", {
        method: "POST",
        body: JSON.stringify(body),
      });
      setLastRun(res);
      reload();
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setGenerating(false);
    }
  }

  function viewAs(id: number) {
    impersonate(id);
    window.location.href = "/dashboard";
  }

  return (
    <div className="p-6 max-w-6xl mx-auto space-y-6">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Users className="w-6 h-6 text-brand-600" />
          <h1 className="text-2xl font-semibold">Lärarpanel</h1>
        </div>
        <button
          onClick={() => setShowCreate(true)}
          className="bg-brand-600 hover:bg-brand-700 text-white rounded-lg px-4 py-2 flex items-center gap-2"
        >
          <Plus className="w-4 h-4" /> Ny elev
        </button>
      </div>

      {err && (
        <div className="bg-rose-50 text-rose-700 border border-rose-200 rounded p-3 text-sm">
          {err}
        </div>
      )}

      {/* Generator-panel */}
      <div className="bg-white rounded-xl shadow-sm border p-4 space-y-3">
        <div className="flex items-center gap-2">
          <Play className="w-5 h-5 text-emerald-600" />
          <h2 className="font-semibold">Generera exempeldata för månad</h2>
        </div>
        <div className="flex flex-wrap items-end gap-3">
          <label className="text-sm">
            <div className="text-slate-600 mb-1">Månad</div>
            <input
              type="month"
              value={ym}
              onChange={(e) => setYm(e.target.value)}
              className="border rounded px-2 py-1.5"
            />
          </label>
          <label className="text-sm flex items-center gap-2">
            <input
              type="checkbox"
              checked={overwrite}
              onChange={(e) => setOverwrite(e.target.checked)}
            />
            Skriv över befintlig månadsdata
          </label>
          <div className="text-sm text-slate-600">
            {selected.size === 0
              ? "Genererar för alla elever"
              : `Genererar för ${selected.size} valda`}
          </div>
          <button
            onClick={runGenerate}
            disabled={generating || students.length === 0}
            className="ml-auto bg-emerald-600 hover:bg-emerald-700 text-white rounded-lg px-4 py-2 flex items-center gap-2 disabled:opacity-50"
          >
            {generating ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <Play className="w-4 h-4" />
            )}
            Generera
          </button>
        </div>

        {lastRun && (
          <div className="text-sm border-t pt-3">
            <div className="font-medium mb-2">Resultat:</div>
            <ul className="space-y-1">
              {lastRun.map((r) => (
                <li key={r.student_id} className="flex gap-3">
                  <span className="font-medium w-40">{r.display_name}</span>
                  <span
                    className={`px-2 rounded text-xs ${
                      r.status === "created"
                        ? "bg-emerald-100 text-emerald-700"
                        : r.status === "overwritten"
                        ? "bg-amber-100 text-amber-700"
                        : r.status === "skipped"
                        ? "bg-slate-100 text-slate-600"
                        : "bg-rose-100 text-rose-700"
                    }`}
                  >
                    {r.status}
                  </span>
                  <span className="text-slate-600 text-xs">
                    {r.stats
                      ? Object.entries(r.stats)
                          .map(([k, v]) => `${k.replace("_created", "")}:${v}`)
                          .join(" · ")
                      : r.error}
                  </span>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>

      {/* Elevlista */}
      <div className="bg-white rounded-xl shadow-sm border overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-left">
            <tr>
              <th className="p-3 w-8">
                <input
                  type="checkbox"
                  checked={
                    selected.size === students.length && students.length > 0
                  }
                  onChange={selectAll}
                />
              </th>
              <th className="p-3">Namn</th>
              <th className="p-3">Klass</th>
              <th className="p-3">Kod</th>
              <th className="p-3">Genererade månader</th>
              <th className="p-3">Senast inloggad</th>
              <th className="p-3 w-40 text-right">Åtgärder</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr>
                <td colSpan={7} className="p-6 text-center text-slate-500">
                  Laddar…
                </td>
              </tr>
            ) : students.length === 0 ? (
              <tr>
                <td colSpan={7} className="p-6 text-center text-slate-500">
                  Inga elever ännu. Skapa din första med "Ny elev".
                </td>
              </tr>
            ) : (
              students.map((s) => (
                <tr key={s.id} className="border-t hover:bg-slate-50">
                  <td className="p-3">
                    <input
                      type="checkbox"
                      checked={selected.has(s.id)}
                      onChange={() => toggleSelect(s.id)}
                    />
                  </td>
                  <td className="p-3 font-medium">{s.display_name}</td>
                  <td className="p-3 text-slate-600">{s.class_label || "—"}</td>
                  <td className="p-3 font-mono text-brand-600 bg-brand-50 inline-block px-2 rounded">
                    {s.login_code}
                  </td>
                  <td className="p-3 text-xs">
                    {s.months_generated.length === 0
                      ? "—"
                      : s.months_generated.join(", ")}
                  </td>
                  <td className="p-3 text-xs text-slate-600">
                    {s.last_login_at
                      ? new Date(s.last_login_at).toLocaleDateString("sv-SE")
                      : "Aldrig"}
                  </td>
                  <td className="p-3 text-right space-x-1">
                    <button
                      onClick={() => viewAs(s.id)}
                      title="Titta som elev"
                      className="p-1.5 hover:bg-brand-100 rounded text-brand-600"
                    >
                      <Eye className="w-4 h-4" />
                    </button>
                    <button
                      onClick={() => resetStudent(s.id)}
                      title="Nollställ elevens data"
                      className="p-1.5 hover:bg-amber-100 rounded text-amber-600"
                    >
                      <RotateCcw className="w-4 h-4" />
                    </button>
                    <button
                      onClick={() => deleteStudent(s.id)}
                      title="Ta bort elev"
                      className="p-1.5 hover:bg-rose-100 rounded text-rose-600"
                    >
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* Create modal */}
      {showCreate && (
        <div
          className="fixed inset-0 bg-black/40 grid place-items-center z-50"
          onClick={() => setShowCreate(false)}
        >
          <div
            className="bg-white rounded-xl shadow-xl p-6 w-96 space-y-3"
            onClick={(e) => e.stopPropagation()}
          >
            <h2 className="font-semibold text-lg">Ny elev</h2>
            <input
              type="text"
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              placeholder="Namn"
              className="w-full px-3 py-2 border rounded-lg"
              autoFocus
            />
            <input
              type="text"
              value={newClass}
              onChange={(e) => setNewClass(e.target.value)}
              placeholder="Klass (valfritt, t.ex. 9A)"
              className="w-full px-3 py-2 border rounded-lg"
            />
            <div className="flex gap-2 justify-end pt-2">
              <button
                onClick={() => setShowCreate(false)}
                className="px-4 py-2 rounded text-slate-600 hover:bg-slate-100"
              >
                Avbryt
              </button>
              <button
                onClick={createStudent}
                className="px-4 py-2 rounded bg-brand-600 text-white hover:bg-brand-700"
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
