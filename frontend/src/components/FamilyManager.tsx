import { useEffect, useState } from "react";
import { Plus, Trash2, Users } from "lucide-react";
import { api } from "@/api/client";

export type Family = {
  id: number;
  name: string;
  member_count: number;
};

export function FamilyManager({
  onChange,
}: { onChange?: () => void }) {
  const [families, setFamilies] = useState<Family[]>([]);
  const [newName, setNewName] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function reload() {
    try {
      setFamilies(await api<Family[]>("/teacher/families"));
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    }
  }

  useEffect(() => {
    reload();
  }, []);

  async function create() {
    if (!newName.trim()) return;
    setBusy(true);
    try {
      await api("/teacher/families", {
        method: "POST",
        body: JSON.stringify({ name: newName.trim() }),
      });
      setNewName("");
      reload();
      onChange?.();
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function remove(id: number) {
    if (!confirm("Lös upp familjen? Eleverna blir solo igen.")) return;
    await api(`/teacher/families/${id}`, { method: "DELETE" });
    reload();
    onChange?.();
  }

  return (
    <div className="bg-white rounded-xl border p-4 space-y-3">
      <h2 className="font-semibold flex items-center gap-2">
        <Users className="w-5 h-5 text-brand-600" />
        Familjer ({families.length})
      </h2>
      {err && <div className="text-sm text-rose-600">{err}</div>}
      <div className="flex gap-2">
        <input
          type="text"
          value={newName}
          onChange={(e) => setNewName(e.target.value)}
          placeholder="Familjenamn (t.ex. Familjen Andersson)"
          className="flex-1 border rounded px-3 py-1.5 text-sm"
        />
        <button
          onClick={create}
          disabled={busy || !newName.trim()}
          className="btn-dark rounded-md px-3 py-1.5 text-sm flex items-center gap-1 disabled:opacity-50"
        >
          <Plus className="w-4 h-4" /> Skapa
        </button>
      </div>
      {families.length > 0 && (
        <ul className="text-sm divide-y">
          {families.map((f) => (
            <li key={f.id} className="py-2 flex items-center justify-between">
              <span>
                <strong>{f.name}</strong>{" "}
                <span className="text-slate-500">
                  ({f.member_count} medlem{f.member_count === 1 ? "" : "mar"})
                </span>
              </span>
              <button
                onClick={() => remove(f.id)}
                className="text-rose-500 hover:bg-rose-50 p-1 rounded"
              >
                <Trash2 className="w-4 h-4" />
              </button>
            </li>
          ))}
        </ul>
      )}
      <p className="text-xs text-slate-500">
        Familjemedlemmar delar bankkonto, transaktioner och budget — bra för
        att simulera ett hushåll med två vuxna.
      </p>
    </div>
  );
}
