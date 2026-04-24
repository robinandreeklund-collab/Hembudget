import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
  ArrowLeft, BookOpen, CheckCircle2, Circle, FileText, HelpCircle,
  PlayCircle, Send,
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
  title: string;
  summary: string | null;
  steps: Step[];
};

type StepProgress = {
  step: Step;
  completed_at: string | null;
  data: Record<string, unknown> | null;
  teacher_feedback: string | null;
};

export default function ModuleView() {
  const { moduleId } = useParams<{ moduleId: string }>();
  const mid = parseInt(moduleId || "0", 10);
  const [mod, setMod] = useState<ModuleDetail | null>(null);
  const [progressByStep, setProgressByStep] = useState<Record<number, StepProgress>>({});
  const [activeStepId, setActiveStepId] = useState<number | null>(null);
  const [err, setErr] = useState<string | null>(null);

  async function loadAll() {
    try {
      const m = await api<ModuleDetail>(`/student/modules/${mid}`);
      setMod(m);
      // Hämta progress för varje steg
      const progresses: Record<number, StepProgress> = {};
      for (const st of m.steps) {
        try {
          const p = await api<StepProgress>(`/student/steps/${st.id}/progress`);
          progresses[st.id] = p;
        } catch {
          /* ignore */
        }
      }
      setProgressByStep(progresses);
      // Välj första okomplettera steget
      const firstUndone = m.steps.find(
        (s) => !progresses[s.id]?.completed_at,
      );
      setActiveStepId(firstUndone?.id ?? m.steps[0]?.id ?? null);
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    }
  }

  useEffect(() => {
    loadAll();
  }, [mid]);

  if (err) {
    return (
      <div className="p-6">
        <div className="bg-rose-50 text-rose-700 border border-rose-200 rounded p-3">
          {err}
        </div>
      </div>
    );
  }
  if (!mod) return <div className="p-6 text-slate-500">Laddar…</div>;

  const completedCount = mod.steps.filter(
    (s) => progressByStep[s.id]?.completed_at,
  ).length;

  return (
    <div className="min-h-screen bg-slate-50">
      <div className="max-w-5xl mx-auto p-6 grid md:grid-cols-[280px_1fr] gap-6">
        {/* Sidomeny med alla steg */}
        <aside className="space-y-3">
          <Link
            to="/modules"
            className="text-sm text-slate-600 hover:text-brand-700 flex items-center gap-1"
          >
            <ArrowLeft className="w-4 h-4" /> Din kursplan
          </Link>
          <div className="bg-white border rounded-xl p-4">
            <h2 className="font-semibold text-slate-900 mb-1">{mod.title}</h2>
            {mod.summary && (
              <p className="text-xs text-slate-600 mb-3">{mod.summary}</p>
            )}
            <div className="text-xs text-slate-500 mb-3">
              {completedCount} / {mod.steps.length} klara
            </div>
            <ul className="space-y-1">
              {mod.steps.map((s, i) => {
                const done = !!progressByStep[s.id]?.completed_at;
                const isActive = s.id === activeStepId;
                return (
                  <li key={s.id}>
                    <button
                      onClick={() => setActiveStepId(s.id)}
                      className={`w-full text-left flex items-center gap-2 rounded px-2 py-1.5 text-sm ${
                        isActive
                          ? "bg-brand-100 text-brand-800 font-medium"
                          : "hover:bg-slate-100 text-slate-700"
                      }`}
                    >
                      {done ? (
                        <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0" />
                      ) : (
                        <Circle className="w-4 h-4 text-slate-300 shrink-0" />
                      )}
                      <span className="truncate">
                        <span className="text-slate-400 mr-1">{i + 1}.</span>
                        {s.title}
                      </span>
                      <StepKindBadge kind={s.kind} />
                    </button>
                  </li>
                );
              })}
            </ul>
          </div>
        </aside>

        {/* Aktivt steg */}
        <main>
          {activeStepId != null && (
            <StepPanel
              step={mod.steps.find((s) => s.id === activeStepId)!}
              progress={progressByStep[activeStepId] ?? null}
              onDone={async () => {
                await loadAll();
                // Hoppa till nästa oklara steg om det finns
                const idx = mod.steps.findIndex((s) => s.id === activeStepId);
                const next = mod.steps.slice(idx + 1).find(
                  (s) => !progressByStep[s.id]?.completed_at,
                );
                if (next) setActiveStepId(next.id);
              }}
            />
          )}
        </main>
      </div>
    </div>
  );
}

function StepKindBadge({ kind }: { kind: Step["kind"] }) {
  const map: Record<Step["kind"], { icon: React.ReactNode; label: string }> = {
    read: { icon: <BookOpen className="w-3 h-3" />, label: "Läs" },
    watch: { icon: <PlayCircle className="w-3 h-3" />, label: "Titta" },
    reflect: { icon: <FileText className="w-3 h-3" />, label: "Svara" },
    task: { icon: <CheckCircle2 className="w-3 h-3" />, label: "Gör" },
    quiz: { icon: <HelpCircle className="w-3 h-3" />, label: "Quiz" },
  };
  const m = map[kind];
  return (
    <span className="ml-auto inline-flex items-center gap-0.5 text-[10px] text-slate-500">
      {m.icon} {m.label}
    </span>
  );
}

function StepPanel({
  step, progress, onDone,
}: {
  step: Step;
  progress: StepProgress | null;
  onDone: () => void;
}) {
  return (
    <div className="bg-white rounded-xl border border-slate-200 p-6 space-y-4">
      <div className="flex items-center gap-2">
        <StepKindBadge kind={step.kind} />
        <h1 className="text-xl font-semibold text-slate-900">{step.title}</h1>
        {progress?.completed_at && (
          <CheckCircle2 className="w-5 h-5 text-emerald-600 ml-auto" />
        )}
      </div>

      {step.content && (
        <div className="prose prose-slate max-w-none whitespace-pre-wrap text-slate-700">
          {step.content}
        </div>
      )}

      {step.kind === "watch" && !!step.params?.video_url && (
        <VideoEmbed url={String(step.params.video_url)} />
      )}

      {step.kind === "read" || step.kind === "watch" ? (
        <ReadWatchPanel step={step} progress={progress} onDone={onDone} />
      ) : step.kind === "reflect" ? (
        <ReflectPanel step={step} progress={progress} onDone={onDone} />
      ) : step.kind === "quiz" ? (
        <QuizPanel step={step} progress={progress} onDone={onDone} />
      ) : step.kind === "task" ? (
        <TaskPanel step={step} progress={progress} onDone={onDone} />
      ) : null}

      {progress?.teacher_feedback && (
        <div className="bg-sky-50 border-l-4 border-sky-400 rounded p-3 text-sm">
          <div className="font-semibold text-sky-900 mb-1">
            Feedback från läraren:
          </div>
          <div className="text-sky-900 whitespace-pre-wrap">
            {progress.teacher_feedback}
          </div>
        </div>
      )}
    </div>
  );
}

function VideoEmbed({ url }: { url: string }) {
  // Enkel YouTube-embed
  const id = extractYouTubeId(url);
  if (id) {
    return (
      <div className="aspect-video rounded overflow-hidden bg-black">
        <iframe
          className="w-full h-full"
          src={`https://www.youtube.com/embed/${id}`}
          allowFullScreen
          title="video"
        />
      </div>
    );
  }
  return (
    <a href={url} target="_blank" rel="noreferrer" className="text-brand-600 underline">
      Öppna video: {url}
    </a>
  );
}

function extractYouTubeId(url: string): string | null {
  const m = url.match(/(?:youtube\.com\/watch\?v=|youtu\.be\/)([a-zA-Z0-9_-]{11})/);
  return m ? m[1] : null;
}

function ReadWatchPanel({
  step: _step, progress, onDone,
}: { step: Step; progress: StepProgress | null; onDone: () => void }) {
  const done = !!progress?.completed_at;
  const [busy, setBusy] = useState(false);
  async function markDone() {
    setBusy(true);
    try {
      await api(`/student/steps/${_step.id}/complete`, {
        method: "POST",
        body: JSON.stringify({}),
      });
      onDone();
    } finally {
      setBusy(false);
    }
  }
  return (
    <div>
      <button
        onClick={markDone}
        disabled={done || busy}
        className="bg-brand-600 hover:bg-brand-700 text-white rounded-lg px-5 py-2 font-medium disabled:bg-slate-300"
      >
        {done ? "Klar ✓" : busy ? "Sparar…" : "Jag har läst klart"}
      </button>
    </div>
  );
}

function ReflectPanel({
  step, progress, onDone,
}: { step: Step; progress: StepProgress | null; onDone: () => void }) {
  const existing = (progress?.data?.reflection as string) ?? "";
  const [text, setText] = useState(existing);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function save() {
    setErr(null);
    if (text.trim().length < 10) {
      setErr("Skriv minst 10 tecken så läraren ser vad du menar.");
      return;
    }
    setBusy(true);
    try {
      await api(`/student/steps/${step.id}/complete`, {
        method: "POST",
        body: JSON.stringify({ data: { reflection: text.trim() } }),
      });
      onDone();
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-2">
      <textarea
        value={text}
        onChange={(e) => setText(e.target.value)}
        rows={5}
        placeholder="Skriv din reflektion här…"
        className="w-full border rounded p-3 text-sm"
      />
      <div className="flex items-center justify-between">
        <span className="text-xs text-slate-500">
          {text.trim().length} tecken
        </span>
        <button
          onClick={save}
          disabled={busy}
          className="bg-brand-600 hover:bg-brand-700 text-white rounded-lg px-5 py-2 font-medium disabled:opacity-50"
        >
          <Send className="w-4 h-4 inline mr-1" />
          {progress?.completed_at ? "Spara ny version" : "Skicka"}
        </button>
      </div>
      {err && <div className="text-sm text-rose-600">{err}</div>}
    </div>
  );
}

function QuizPanel({
  step, progress, onDone,
}: { step: Step; progress: StepProgress | null; onDone: () => void }) {
  const p = step.params ?? {};
  const options = (p.options as string[]) ?? [];
  const correctIdx = (p.correct_index as number | undefined);
  const correctIndices = (p.correct_indices as number[] | undefined);
  const isMulti = Array.isArray(correctIndices);
  const explanation = p.explanation as string | undefined;

  // Flerval: Set, enkel: null | index
  const [multiSelected, setMultiSelected] = useState<Set<number>>(
    new Set(
      isMulti && Array.isArray(progress?.data?.answers)
        ? (progress?.data?.answers as number[])
        : [],
    ),
  );
  const [singleSelected, setSingleSelected] = useState<number | null>(
    !isMulti && progress?.data?.answer != null
      ? (progress?.data?.answer as number)
      : null,
  );
  const [lastSubmittedCorrect, setLastSubmittedCorrect] = useState<boolean | null>(
    progress?.data?.correct != null ? (progress.data.correct as boolean) : null,
  );
  const [showResult, setShowResult] = useState(!!progress?.completed_at);
  const [attempts, setAttempts] = useState<number>(
    (progress?.data?.attempts as number) ?? 0,
  );
  const [busy, setBusy] = useState(false);

  const firstCorrect = (progress?.data?.first_correct as boolean | undefined);

  async function submit() {
    setBusy(true);
    try {
      const body = isMulti
        ? { data: { answers: [...multiSelected].sort((a, b) => a - b) } }
        : { data: { answer: singleSelected } };
      const res = await api<{ data: Record<string, unknown> }>(
        `/student/steps/${step.id}/complete`,
        { method: "POST", body: JSON.stringify(body) },
      );
      setLastSubmittedCorrect(!!res.data.correct);
      setAttempts((res.data.attempts as number) ?? attempts + 1);
      setShowResult(true);
    } finally {
      setBusy(false);
    }
  }

  function retry() {
    setShowResult(false);
    setSingleSelected(null);
    setMultiSelected(new Set());
  }

  return (
    <div className="space-y-3">
      {!!p.question && (
        <div className="font-medium text-slate-800">{String(p.question)}</div>
      )}
      {isMulti && !showResult && (
        <div className="text-xs text-slate-500">
          (Flera svar kan vara rätt — bocka alla du tror)
        </div>
      )}
      <div className="space-y-2">
        {options.map((opt, i) => {
          const isSelected = isMulti
            ? multiSelected.has(i)
            : singleSelected === i;
          const isCorrectAnswer = isMulti
            ? (correctIndices ?? []).includes(i)
            : correctIdx === i;
          const showCorrect = showResult && isCorrectAnswer;
          const showWrong = showResult && isSelected && !isCorrectAnswer;
          return (
            <button
              key={i}
              onClick={() => {
                if (showResult) return;
                if (isMulti) {
                  const n = new Set(multiSelected);
                  if (n.has(i)) n.delete(i); else n.add(i);
                  setMultiSelected(n);
                } else {
                  setSingleSelected(i);
                }
              }}
              disabled={showResult}
              className={`w-full text-left rounded-lg border-2 p-3 text-sm transition ${
                showCorrect
                  ? "border-emerald-500 bg-emerald-50"
                  : showWrong
                  ? "border-rose-500 bg-rose-50"
                  : isSelected
                  ? "border-brand-500 bg-brand-50"
                  : "border-slate-200 bg-white hover:border-slate-300"
              }`}
            >
              {isMulti && !showResult && (
                <span className="inline-block w-4 h-4 border border-slate-400 rounded mr-2 align-middle">
                  {isSelected ? "✓" : ""}
                </span>
              )}
              {opt}
              {showCorrect && <span className="ml-2 text-emerald-600">✓ rätt</span>}
              {showWrong && <span className="ml-2 text-rose-600">✗ fel</span>}
            </button>
          );
        })}
      </div>

      {!showResult ? (
        <button
          onClick={submit}
          disabled={
            busy ||
            (isMulti ? multiSelected.size === 0 : singleSelected == null)
          }
          className="bg-brand-600 hover:bg-brand-700 text-white rounded-lg px-5 py-2 font-medium disabled:opacity-50"
        >
          Svara
        </button>
      ) : (
        <>
          <div
            className={`rounded p-3 text-sm ${
              lastSubmittedCorrect
                ? "bg-emerald-50 border-l-4 border-emerald-500 text-emerald-900"
                : "bg-amber-50 border-l-4 border-amber-500 text-amber-900"
            }`}
          >
            <strong>
              {lastSubmittedCorrect
                ? "Rätt!"
                : "Inte riktigt — titta på förklaringen och prova igen."}
            </strong>
            {explanation && (
              <div className="mt-1 text-slate-800">
                <em>Förklaring:</em> {explanation}
              </div>
            )}
            {attempts > 1 && (
              <div className="text-xs text-slate-500 mt-1">
                Försök #{attempts}
                {firstCorrect === false && (
                  <span className="ml-2 text-slate-600">
                    (mastery räknar första försöket)
                  </span>
                )}
              </div>
            )}
          </div>
          <div className="flex gap-2">
            {!lastSubmittedCorrect && (
              <button
                onClick={retry}
                className="bg-amber-500 hover:bg-amber-600 text-white rounded-lg px-5 py-2 font-medium"
              >
                Prova igen
              </button>
            )}
            <button
              onClick={onDone}
              className="bg-brand-600 hover:bg-brand-700 text-white rounded-lg px-5 py-2 font-medium"
            >
              Nästa steg →
            </button>
          </div>
        </>
      )}
    </div>
  );
}

function TaskPanel({
  step: _step, progress, onDone,
}: { step: Step; progress: StepProgress | null; onDone: () => void }) {
  const assignmentId = (_step.params?.assignment_id as number) ?? null;
  const [busy, setBusy] = useState(false);
  const done = !!progress?.completed_at;

  async function markDone() {
    setBusy(true);
    try {
      await api(`/student/steps/${_step.id}/complete`, {
        method: "POST",
        body: JSON.stringify({}),
      });
      onDone();
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-3">
      {assignmentId && (
        <Link
          to={`/mortgage/${assignmentId}`}
          className="inline-block bg-brand-50 border border-brand-300 text-brand-800 rounded-lg px-4 py-2 text-sm hover:bg-brand-100"
        >
          Öppna kopplat uppdrag →
        </Link>
      )}
      <div>
        <button
          onClick={markDone}
          disabled={done || busy}
          className="bg-emerald-600 hover:bg-emerald-700 text-white rounded-lg px-5 py-2 font-medium disabled:bg-slate-300"
        >
          {done ? "Markerad som klar ✓" : busy ? "Sparar…" : "Jag har gjort uppdraget"}
        </button>
      </div>
    </div>
  );
}
