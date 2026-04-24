import { useEffect, useState } from "react";
import {
  CheckCircle2, CircleDashed, ListTodo, Trash2, Hourglass,
} from "lucide-react";
import { api } from "@/api/client";

export type AssignmentStatus = {
  id: number;
  title: string;
  description: string;
  kind: string;
  status: "not_started" | "in_progress" | "completed";
  progress: string;
  target_year_month: string | null;
  student_id: number | null;
};

export function AssignmentList({
  studentId,
  asTeacher = false,
}: {
  studentId?: number;
  asTeacher?: boolean;
}) {
  const [items, setItems] = useState<AssignmentStatus[]>([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);

  async function reload() {
    setLoading(true);
    try {
      const path = asTeacher
        ? `/teacher/assignments${studentId ? `?student_id=${studentId}` : ""}`
        : "/student/assignments";
      const list = await api<AssignmentStatus[]>(path);
      setItems(list);
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }

  async function remove(id: number) {
    if (!confirm("Ta bort uppdraget?")) return;
    await api(`/teacher/assignments/${id}`, { method: "DELETE" });
    reload();
  }

  useEffect(() => {
    reload();
  }, [studentId, asTeacher]);

  if (loading) return <div className="text-sm text-slate-500">Laddar uppdrag…</div>;
  if (err) return <div className="text-sm text-rose-600">{err}</div>;

  if (items.length === 0) {
    return (
      <div className="text-sm text-slate-500 py-4 text-center bg-slate-50 rounded">
        Inga uppdrag {asTeacher ? "till denna elev" : "än"}.
      </div>
    );
  }

  return (
    <ul className="divide-y divide-slate-200">
      {items.map((a) => (
        <li key={a.id} className="py-3 flex items-start gap-3">
          {a.status === "completed" ? (
            <CheckCircle2 className="w-5 h-5 text-emerald-600 mt-0.5" />
          ) : a.status === "in_progress" ? (
            <Hourglass className="w-5 h-5 text-amber-500 mt-0.5" />
          ) : (
            <CircleDashed className="w-5 h-5 text-slate-400 mt-0.5" />
          )}
          <div className="flex-1">
            <div className="font-medium">{a.title}</div>
            <div className="text-sm text-slate-600">{a.description}</div>
            <div className="text-xs mt-1">
              <span
                className={`px-2 py-0.5 rounded ${
                  a.status === "completed"
                    ? "bg-emerald-100 text-emerald-700"
                    : a.status === "in_progress"
                    ? "bg-amber-100 text-amber-700"
                    : "bg-slate-100 text-slate-600"
                }`}
              >
                {a.progress}
              </span>
              {a.target_year_month && (
                <span className="ml-2 text-slate-500">
                  Månad: {a.target_year_month}
                </span>
              )}
            </div>
          </div>
          {asTeacher && (
            <button
              onClick={() => remove(a.id)}
              className="p-1 text-slate-400 hover:text-rose-600"
              title="Ta bort"
            >
              <Trash2 className="w-4 h-4" />
            </button>
          )}
        </li>
      ))}
    </ul>
  );
}

export function AssignmentSummary({ studentId }: { studentId: number }) {
  const [items, setItems] = useState<AssignmentStatus[]>([]);
  useEffect(() => {
    api<AssignmentStatus[]>(`/teacher/assignments?student_id=${studentId}`)
      .then(setItems)
      .catch(() => setItems([]));
  }, [studentId]);
  if (items.length === 0) return null;
  const done = items.filter((a) => a.status === "completed").length;
  const wip = items.filter((a) => a.status === "in_progress").length;
  return (
    <span className="text-xs">
      <ListTodo className="inline w-3 h-3 mr-0.5" />
      {done}/{items.length} klara
      {wip > 0 && (
        <span className="text-amber-700"> · {wip} pågår</span>
      )}
    </span>
  );
}
