import { useEffect, useState } from "react";
import {
  CheckCircle2, Check, CircleDashed, ListTodo, MessageSquare,
  Trash2, Hourglass,
} from "lucide-react";
import { Link } from "react-router-dom";
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
  teacher_feedback?: string | null;
  teacher_feedback_at?: string | null;
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
        <li key={a.id} className="py-3 space-y-2">
          <div className="flex items-start gap-3">
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
          {!asTeacher && a.kind === "mortgage_decision" && (
            <Link
              to={`/mortgage/${a.id}`}
              className="text-xs btn-dark rounded-md px-2 py-1"
            >
              Öppna
            </Link>
          )}
          {asTeacher && (
            <div className="flex gap-1">
              <FeedbackButton
                assignmentId={a.id}
                hasExisting={!!a.teacher_feedback}
                onDone={reload}
              />
              {a.status !== "completed" && (
                <button
                  onClick={async () => {
                    await api(`/teacher/assignments/${a.id}/complete`, {
                      method: "POST",
                    });
                    reload();
                  }}
                  className="p-1 text-emerald-600 hover:bg-emerald-50 rounded"
                  title="Markera som klar"
                >
                  <Check className="w-4 h-4" />
                </button>
              )}
              <button
                onClick={() => remove(a.id)}
                className="p-1 text-slate-400 hover:text-rose-600"
                title="Ta bort"
              >
                <Trash2 className="w-4 h-4" />
              </button>
            </div>
          )}
          </div>
          {a.teacher_feedback && (
            <div className="ml-8 bg-sky-50 border-l-4 border-sky-400 rounded p-2 text-sm">
              <div className="font-semibold text-sky-900 text-xs mb-0.5">
                Lärarens feedback:
              </div>
              <div className="text-sky-900 whitespace-pre-wrap">
                {a.teacher_feedback}
              </div>
            </div>
          )}
        </li>
      ))}
    </ul>
  );
}

function FeedbackButton({
  assignmentId, hasExisting, onDone,
}: { assignmentId: number; hasExisting: boolean; onDone: () => void }) {
  const [open, setOpen] = useState(false);
  const [text, setText] = useState("");
  const [retry, setRetry] = useState(false);
  const [busy, setBusy] = useState(false);

  async function save() {
    if (!text.trim()) return;
    setBusy(true);
    try {
      await api(`/teacher/assignments/${assignmentId}/feedback`, {
        method: "POST",
        body: JSON.stringify({
          body: text.trim(), request_retry: retry,
        }),
      });
      setOpen(false); setText(""); setRetry(false);
      onDone();
    } finally {
      setBusy(false);
    }
  }

  if (!open) {
    return (
      <button
        onClick={() => setOpen(true)}
        className={`p-1 rounded ${
          hasExisting
            ? "text-brand-700 hover:bg-brand-50"
            : "text-slate-500 hover:text-brand-700"
        }`}
        title={hasExisting ? "Redigera återkoppling" : "Ge återkoppling"}
      >
        <MessageSquare className="w-4 h-4" />
      </button>
    );
  }
  return (
    <div
      onClick={(e) => e.stopPropagation()}
      className="fixed inset-0 z-30 bg-slate-900/40 flex items-center justify-center p-4"
    >
      <div className="bg-white rounded-xl shadow-xl p-5 w-full max-w-md space-y-3">
        <div className="font-semibold">Lämna återkoppling</div>
        <textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          rows={4}
          placeholder="Skriv feedback till eleven…"
          className="w-full border rounded p-2 text-sm"
          autoFocus
        />
        <label className="flex items-center gap-2 text-sm text-slate-700">
          <input
            type="checkbox"
            checked={retry}
            onChange={(e) => setRetry(e.target.checked)}
          />
          Be eleven försöka igen (nollar markering-som-klar)
        </label>
        <div className="flex gap-2 justify-end">
          <button
            onClick={() => setOpen(false)}
            className="px-3 py-1.5 text-sm text-slate-600 hover:bg-slate-100 rounded"
          >
            Avbryt
          </button>
          <button
            onClick={save}
            disabled={busy || !text.trim()}
            className="px-4 py-1.5 text-sm bg-brand-600 hover:bg-brand-700 text-white rounded disabled:opacity-50"
          >
            {busy ? "Sparar…" : "Skicka"}
          </button>
        </div>
      </div>
    </div>
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
