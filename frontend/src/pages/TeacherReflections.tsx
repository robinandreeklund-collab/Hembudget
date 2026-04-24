import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ArrowLeft, Check, Filter, MessageSquare, User } from "lucide-react";
import { api } from "@/api/client";

type RubricCriterion = { key: string; name: string; levels: string[] };
type Reflection = {
  progress_id: number;
  student_id: number;
  student_name: string;
  class_label: string | null;
  module_id: number;
  module_title: string;
  step_id: number;
  step_title: string;
  step_question: string | null;
  reflection: string;
  completed_at: string | null;
  teacher_feedback: string | null;
  feedback_at: string | null;
  rubric: RubricCriterion[] | null;
  rubric_scores: Record<string, number> | null;
};

export default function TeacherReflections() {
  const [items, setItems] = useState<Reflection[]>([]);
  const [onlyUnread, setOnlyUnread] = useState(true);
  const [activeId, setActiveId] = useState<number | null>(null);
  const [feedback, setFeedback] = useState("");
  const [scores, setScores] = useState<Record<string, number>>({});
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function load() {
    try {
      const data = await api<Reflection[]>(
        `/teacher/reflections?needs_feedback=${onlyUnread ? "true" : "false"}`,
      );
      setItems(data);
      if (data.length > 0 && activeId == null) setActiveId(data[0].progress_id);
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    }
  }

  useEffect(() => {
    load();
  }, [onlyUnread]);

  const active = items.find((r) => r.progress_id === activeId);

  useEffect(() => {
    if (active) {
      setFeedback(active.teacher_feedback ?? "");
      setScores(active.rubric_scores ?? {});
    }
  }, [active?.progress_id]);

  async function save() {
    if (!active || !feedback.trim()) return;
    setBusy(true);
    try {
      await api(`/teacher/reflections/${active.progress_id}/feedback`, {
        method: "POST",
        body: JSON.stringify({
          feedback: feedback.trim(),
          rubric_scores: active.rubric ? scores : null,
        }),
      });
      await load();
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="min-h-screen bg-slate-50">
      <div className="max-w-6xl mx-auto p-6 space-y-4">
        <Link
          to="/teacher"
          className="text-sm text-slate-600 hover:text-brand-700 flex items-center gap-1"
        >
          <ArrowLeft className="w-4 h-4" /> Lärarpanel
        </Link>
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <MessageSquare className="w-6 h-6 text-brand-600" />
            <h1 className="text-2xl font-semibold">Elevernas reflektioner</h1>
          </div>
          <label className="text-sm flex items-center gap-2 text-slate-700">
            <Filter className="w-4 h-4 text-slate-500" />
            <input
              type="checkbox"
              checked={onlyUnread}
              onChange={(e) => setOnlyUnread(e.target.checked)}
            />
            Bara de som saknar feedback
          </label>
        </div>

        {err && (
          <div className="bg-rose-50 text-rose-700 border border-rose-200 rounded p-3 text-sm">
            {err}
          </div>
        )}

        {items.length === 0 ? (
          <div className="bg-amber-50 border border-amber-200 text-amber-800 rounded p-4 text-sm">
            Inga reflektioner {onlyUnread ? "som behöver feedback" : "än"}.
          </div>
        ) : (
          <div className="grid md:grid-cols-[320px_1fr] gap-4">
            <aside className="bg-white rounded-xl border overflow-y-auto max-h-[70vh]">
              <ul>
                {items.map((r) => (
                  <li key={r.progress_id}>
                    <button
                      onClick={() => setActiveId(r.progress_id)}
                      className={`w-full text-left p-3 border-b border-slate-100 ${
                        activeId === r.progress_id
                          ? "bg-brand-50 border-l-4 border-l-brand-500"
                          : "hover:bg-slate-50"
                      }`}
                    >
                      <div className="flex items-center gap-2 text-sm font-medium">
                        <User className="w-3.5 h-3.5 text-slate-400" />
                        {r.student_name}
                        {r.teacher_feedback && (
                          <Check className="w-4 h-4 text-emerald-600 ml-auto" />
                        )}
                      </div>
                      <div className="text-xs text-slate-500 mt-0.5 truncate">
                        {r.module_title} · {r.step_title}
                      </div>
                      <div className="text-xs text-slate-400 mt-0.5">
                        {r.completed_at
                          ? new Date(r.completed_at).toLocaleString("sv-SE", {
                              day: "2-digit", month: "2-digit",
                              hour: "2-digit", minute: "2-digit",
                            })
                          : ""}
                      </div>
                    </button>
                  </li>
                ))}
              </ul>
            </aside>

            <main className="bg-white rounded-xl border p-5 space-y-4">
              {active ? (
                <>
                  <div>
                    <div className="text-xs text-slate-500">
                      {active.student_name}
                      {active.class_label && ` · ${active.class_label}`}
                    </div>
                    <h2 className="text-lg font-semibold">{active.step_title}</h2>
                    <div className="text-xs text-slate-500">
                      I modulen {active.module_title}
                    </div>
                  </div>

                  {active.step_question && (
                    <div className="bg-slate-50 rounded p-3 text-sm text-slate-700">
                      <div className="font-semibold mb-1">Frågan:</div>
                      {active.step_question}
                    </div>
                  )}

                  <div className="bg-sky-50 border-l-4 border-sky-400 rounded p-3">
                    <div className="text-xs text-slate-600 mb-1">Elevens svar:</div>
                    <div className="text-sm text-slate-900 whitespace-pre-wrap">
                      {active.reflection}
                    </div>
                  </div>

                  {active.rubric && active.rubric.length > 0 && (
                    <div className="space-y-3 border rounded p-3 bg-slate-50">
                      <div className="text-sm font-semibold text-slate-700">
                        Bedömningskriterier:
                      </div>
                      {active.rubric.map((crit) => (
                        <div key={crit.key}>
                          <div className="text-sm font-medium text-slate-800 mb-1">
                            {crit.name}
                          </div>
                          <div className="flex flex-wrap gap-1">
                            {crit.levels.map((lvl, idx) => {
                              const sel = scores[crit.key] === idx;
                              return (
                                <button
                                  key={idx}
                                  onClick={() =>
                                    setScores({ ...scores, [crit.key]: idx })
                                  }
                                  className={`text-xs rounded px-3 py-1.5 border-2 ${
                                    sel
                                      ? "border-brand-500 bg-brand-100 text-brand-800 font-medium"
                                      : "border-slate-200 bg-white hover:border-slate-300 text-slate-700"
                                  }`}
                                >
                                  <span className="text-slate-400 mr-1">{idx + 1}.</span>
                                  {lvl}
                                </button>
                              );
                            })}
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                  <div className="space-y-2">
                    <label className="block text-sm font-medium text-slate-700">
                      Din feedback:
                    </label>
                    <textarea
                      value={feedback}
                      onChange={(e) => setFeedback(e.target.value)}
                      rows={4}
                      placeholder="Skriv uppmuntran, ställ en följdfråga, peka på något specifikt…"
                      className="w-full border rounded p-2 text-sm"
                    />
                    <button
                      onClick={save}
                      disabled={busy || !feedback.trim()}
                      className="bg-brand-600 hover:bg-brand-700 text-white rounded px-4 py-2 text-sm font-medium disabled:opacity-50"
                    >
                      {active.teacher_feedback
                        ? busy
                          ? "Uppdaterar…"
                          : "Uppdatera feedback"
                        : busy
                        ? "Skickar…"
                        : "Skicka feedback"}
                    </button>
                    {active.feedback_at && (
                      <div className="text-xs text-slate-500">
                        Senast uppdaterad{" "}
                        {new Date(active.feedback_at).toLocaleString("sv-SE")}
                      </div>
                    )}
                  </div>
                </>
              ) : (
                <div className="text-slate-500">Välj en reflektion till vänster</div>
              )}
            </main>
          </div>
        )}
      </div>
    </div>
  );
}
