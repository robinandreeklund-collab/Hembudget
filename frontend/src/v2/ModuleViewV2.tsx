/**
 * Modul-detalj v2 · /v2/moduler/:moduleId
 *
 * Nativ v2-rendering — använder samma v2-shell-klasser (v2-lan-root,
 * pill warm, actor-name, actor-sub, section-eye) som AktierV2/AvanzaV2/
 * HuvudbokV2 osv. för konsekvent grafisk profil över hela plattformen.
 *
 * Tidigare wrappade vi v1 ModuleView med CSS-skin men det gav v1-look
 * (Tailwind ljus-utility, små border-radii, mono-fonter på fel plats).
 * Nu duplicerar vi fetch-logiken och bygger sidebar + step-panel
 * nativt i v2.
 *
 * Återanvänder backend-API:erna oförändrade · ingen ändring på
 * v1 ModuleView-funktionalitet (heartbeat, AI, celebrate).
 */
import { useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, getApiBase, getToken, getAsStudent } from "@/api/client";
import { V2Banner } from "./V2Banner";
import {
  CelebrationOverlay,
  type Achievement,
} from "@/components/CelebrationOverlay";
import { AskAI } from "@/components/AskAI";


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
  peer_feedback?: { id: number; body: string; created_at: string }[];
};

type CompleteResp = {
  ok: boolean;
  data: Record<string, unknown>;
  new_achievements?: Achievement[];
};


// === Visuella konstanter · använder v2-CSS-variabler där möjligt ====

const KIND_LABEL: Record<Step["kind"], string> = {
  read: "Läs",
  watch: "Titta",
  reflect: "Svara",
  task: "Gör",
  quiz: "Quiz",
};


export function ModuleViewV2() {
  const { moduleId } = useParams<{ moduleId: string }>();
  const mid = parseInt(moduleId || "0", 10);
  const [mod, setMod] = useState<ModuleDetail | null>(null);
  const [progressByStep, setProgressByStep] =
    useState<Record<number, StepProgress>>({});
  const [activeStepId, setActiveStepId] = useState<number | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [celebration, setCelebration] = useState<Achievement[]>([]);

  async function loadAll() {
    try {
      const m = await api<ModuleDetail>(`/student/modules/${mid}`);
      setMod(m);
      const progresses: Record<number, StepProgress> = {};
      for (const st of m.steps) {
        try {
          const p = await api<StepProgress>(
            `/student/steps/${st.id}/progress`,
          );
          progresses[st.id] = p;
        } catch {
          /* ignore · steg kan sakna progress innan första interaktionen */
        }
      }
      setProgressByStep(progresses);
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
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mid]);

  // Heartbeat-pings medan eleven har steget öppet · lärarstatistik
  useEffect(() => {
    if (activeStepId == null) return;
    let cancelled = false;
    const send = () => {
      if (cancelled) return;
      api("/student/step-heartbeat", {
        method: "POST",
        body: JSON.stringify({ step_id: activeStepId }),
      }).catch(() => undefined);
    };
    send();
    const id = window.setInterval(send, 30_000);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, [activeStepId]);

  if (err) {
    return (
      <div className="v2-lan-root">
        <V2Banner status={{ role: "student", is_super_admin: false }} />
        <div className="shell">
          <Link className="actor-back" to="/v2/moduler">
            Tillbaka till mina moduler
          </Link>
          <div
            style={{
              padding: "32px 28px",
              border: "1px solid rgba(220,76,43,0.4)",
              borderRadius: 6,
              color: "#fca5a5",
              fontFamily: "var(--serif)",
              marginTop: 20,
            }}
          >
            <div
              style={{
                fontFamily: "var(--mono)",
                fontSize: 10,
                letterSpacing: 1.4,
                textTransform: "uppercase",
                marginBottom: 8,
              }}
            >
              Kunde inte ladda modulen
            </div>
            <pre style={{ fontSize: 12 }}>{err}</pre>
          </div>
        </div>
      </div>
    );
  }

  if (!mod) {
    return (
      <div className="v2-lan-root">
        <V2Banner status={{ role: "student", is_super_admin: false }} />
        <div className="bank-loading">Laddar modulen…</div>
      </div>
    );
  }

  const completedCount = mod.steps.filter(
    (s) => !!progressByStep[s.id]?.completed_at,
  ).length;
  const activeStep = mod.steps.find((s) => s.id === activeStepId) ?? null;

  return (
    <div className="v2-lan-root">
      <V2Banner status={{ role: "student", is_super_admin: false }} />

      <div className="shell">
        <Link className="actor-back" to="/v2/moduler">
          Tillbaka till mina moduler
        </Link>

        <header className="actor-head">
          <div>
            <span className="pill warm">Skola · Modul</span>
            <h1 className="actor-name" style={{ marginTop: 14 }}>
              {mod.title}
            </h1>
            {mod.summary && (
              <p className="actor-sub">{mod.summary}</p>
            )}
          </div>
          <div className="actor-meta">
            Framsteg{" "}
            <strong>
              {completedCount} / {mod.steps.length}
            </strong>
            <br />
            Status{" "}
            <strong>
              {completedCount === mod.steps.length
                ? "klar"
                : completedCount === 0
                ? "ej påbörjad"
                : "pågående"}
            </strong>
          </div>
        </header>

        <div
          style={{
            display: "grid",
            gridTemplateColumns: "280px 1fr",
            gap: 28,
            alignItems: "start",
          }}
        >
          {/* Sidebar · stegmeny */}
          <aside>
            <div className="section-eye" style={{ marginBottom: 12 }}>
              Steg · {completedCount}/{mod.steps.length} klara
            </div>
            <div
              style={{
                border: "1px solid var(--line)",
                borderRadius: 8,
                overflow: "hidden",
              }}
            >
              {mod.steps.map((s, i) => {
                const done = !!progressByStep[s.id]?.completed_at;
                const isActive = s.id === activeStepId;
                return (
                  <button
                    key={s.id}
                    onClick={() => setActiveStepId(s.id)}
                    style={{
                      width: "100%",
                      textAlign: "left",
                      display: "flex",
                      alignItems: "center",
                      gap: 10,
                      padding: "12px 14px",
                      background: isActive
                        ? "rgba(220, 76, 43, 0.12)"
                        : "transparent",
                      borderLeft: isActive
                        ? "3px solid var(--accent)"
                        : "3px solid transparent",
                      borderTop: i === 0
                        ? "none"
                        : "1px solid var(--line)",
                      borderRight: "none",
                      borderBottom: "none",
                      color: isActive
                        ? "var(--text)"
                        : "var(--text-mid)",
                      cursor: "pointer",
                      transition: "background 120ms",
                      fontFamily: "inherit",
                    }}
                  >
                    <span
                      aria-hidden
                      style={{
                        width: 16,
                        height: 16,
                        borderRadius: 999,
                        background: done
                          ? "rgba(110, 231, 183, 0.9)"
                          : "transparent",
                        border: done
                          ? "none"
                          : "1.5px solid var(--line-strong)",
                        flexShrink: 0,
                        display: "inline-flex",
                        alignItems: "center",
                        justifyContent: "center",
                        fontSize: 10,
                        color: "#063",
                      }}
                    >
                      {done ? "✓" : ""}
                    </span>
                    <div
                      style={{
                        flex: 1,
                        minWidth: 0,
                        overflow: "hidden",
                      }}
                    >
                      <div
                        style={{
                          fontSize: 13,
                          fontWeight: isActive ? 600 : 400,
                          whiteSpace: "nowrap",
                          textOverflow: "ellipsis",
                          overflow: "hidden",
                        }}
                      >
                        <span
                          style={{
                            color: "var(--text-dim)",
                            marginRight: 4,
                          }}
                        >
                          {i + 1}.
                        </span>
                        {s.title}
                      </div>
                    </div>
                    <span
                      style={{
                        fontFamily: "var(--mono)",
                        fontSize: 9,
                        letterSpacing: 1.2,
                        textTransform: "uppercase",
                        color: "var(--text-dim)",
                        flexShrink: 0,
                      }}
                    >
                      {KIND_LABEL[s.kind]}
                    </span>
                  </button>
                );
              })}
            </div>
          </aside>

          {/* Main · aktivt steg */}
          <main>
            {activeStep && (
              <StepCardV2
                step={activeStep}
                progress={progressByStep[activeStep.id] ?? null}
                onCelebrate={(a) => {
                  if (a.length > 0) setCelebration(a);
                }}
                onDone={async () => {
                  await loadAll();
                  const idx = mod.steps.findIndex(
                    (s) => s.id === activeStep.id,
                  );
                  const next = mod.steps.slice(idx + 1).find(
                    (s) => !progressByStep[s.id]?.completed_at,
                  );
                  if (next) setActiveStepId(next.id);
                }}
              />
            )}
          </main>
        </div>

        {celebration.length > 0 && (
          <CelebrationOverlay
            items={celebration}
            onClose={() => setCelebration([])}
          />
        )}
        <AskAI
          moduleId={mid}
          stepId={activeStepId ?? undefined}
          contextLabel={
            activeStep
              ? `Du jobbar med: ${activeStep.title}`
              : `Modul: ${mod.title}`
          }
        />
      </div>
    </div>
  );
}


// =====================================================================
// StepCardV2 · rendering av aktivt steg i v2-stil
// =====================================================================

type StepCardProps = {
  step: Step;
  progress: StepProgress | null;
  onDone: () => void;
  onCelebrate: (items: Achievement[]) => void;
};

function StepCardV2({ step, progress, onDone, onCelebrate }: StepCardProps) {
  const done = !!progress?.completed_at;
  return (
    <div
      style={{
        border: "1px solid var(--line)",
        borderRadius: 8,
        padding: "24px 28px",
        background: "rgba(15, 21, 37, 0.4)",
      }}
    >
      <div
        style={{
          fontFamily: "var(--mono)",
          fontSize: 10,
          letterSpacing: 1.4,
          textTransform: "uppercase",
          color: "var(--accent)",
          marginBottom: 8,
        }}
      >
        ● Steg · {KIND_LABEL[step.kind]}
        {done && " · klart ✓"}
      </div>
      <h2
        style={{
          fontFamily: "var(--serif)",
          fontSize: "1.6rem",
          fontWeight: 600,
          margin: "0 0 16px",
          color: "#fff",
        }}
      >
        {step.title}
      </h2>

      {step.content && (
        <div
          style={{
            color: "var(--text)",
            fontSize: 15,
            lineHeight: 1.6,
            whiteSpace: "pre-wrap",
            marginBottom: 20,
            fontFamily: "var(--serif)",
          }}
        >
          {step.content}
        </div>
      )}

      {step.kind === "watch" && Boolean(step.params?.url) && (
        <VideoEmbed url={String(step.params?.url)} />
      )}

      {step.kind === "read" || step.kind === "watch" ? (
        <ReadWatchPanel step={step} progress={progress}
          onDone={onDone} onCelebrate={onCelebrate} />
      ) : step.kind === "reflect" ? (
        <ReflectPanel step={step} progress={progress}
          onDone={onDone} onCelebrate={onCelebrate} />
      ) : step.kind === "quiz" ? (
        <QuizPanel step={step} progress={progress}
          onDone={onDone} onCelebrate={onCelebrate} />
      ) : step.kind === "task" ? (
        <TaskPanel step={step} progress={progress}
          onDone={onDone} onCelebrate={onCelebrate} />
      ) : null}

      {progress?.teacher_feedback && (
        <div
          style={{
            marginTop: 16,
            padding: "12px 14px",
            borderLeft: "3px solid rgba(99, 102, 241, 0.6)",
            background: "rgba(99, 102, 241, 0.08)",
            borderRadius: 4,
            fontSize: 13,
            color: "#c7d2fe",
            whiteSpace: "pre-wrap",
          }}
        >
          <div
            style={{
              fontFamily: "var(--mono)",
              fontSize: 9,
              letterSpacing: 1.4,
              textTransform: "uppercase",
              marginBottom: 4,
              opacity: 0.8,
            }}
          >
            Feedback från läraren
          </div>
          {progress.teacher_feedback}
        </div>
      )}

      {progress?.peer_feedback && progress.peer_feedback.length > 0 && (
        <div
          style={{
            marginTop: 12,
            padding: "12px 14px",
            borderLeft: "3px solid rgba(167, 139, 250, 0.6)",
            background: "rgba(167, 139, 250, 0.08)",
            borderRadius: 4,
            fontSize: 13,
            color: "rgba(196,181,253,0.95)",
          }}
        >
          <div
            style={{
              fontFamily: "var(--mono)",
              fontSize: 9,
              letterSpacing: 1.4,
              textTransform: "uppercase",
              marginBottom: 6,
              opacity: 0.8,
            }}
          >
            Kamrater har sagt · {progress.peer_feedback.length}
          </div>
          {progress.peer_feedback.map((pf) => (
            <div
              key={pf.id}
              style={{ marginBottom: 4, whiteSpace: "pre-wrap" }}
            >
              "{pf.body}"
            </div>
          ))}
        </div>
      )}
    </div>
  );
}


function VideoEmbed({ url }: { url: string }) {
  const id = extractYouTubeId(url);
  if (id) {
    return (
      <div
        style={{
          aspectRatio: "16 / 9",
          borderRadius: 6,
          overflow: "hidden",
          background: "#000",
          marginBottom: 20,
        }}
      >
        <iframe
          style={{ width: "100%", height: "100%", border: "none" }}
          src={`https://www.youtube.com/embed/${id}`}
          allowFullScreen
          title="video"
        />
      </div>
    );
  }
  return (
    <a
      href={url} target="_blank" rel="noreferrer"
      style={{
        color: "var(--accent)",
        textDecoration: "underline",
        marginBottom: 16,
        display: "inline-block",
      }}
    >
      Öppna video: {url}
    </a>
  );
}

function extractYouTubeId(url: string): string | null {
  const m = url.match(
    /(?:youtube\.com\/watch\?v=|youtu\.be\/)([a-zA-Z0-9_-]{11})/,
  );
  return m ? m[1] : null;
}


// === V2 CTA-knapp (orange accent) ====================================

function V2Button({
  onClick, disabled, children, variant = "primary",
}: {
  onClick?: () => void | Promise<void>;
  disabled?: boolean;
  children: React.ReactNode;
  variant?: "primary" | "ghost";
}) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      style={{
        padding: "10px 22px",
        borderRadius: 999,
        fontFamily: "var(--mono)",
        fontSize: 11,
        fontWeight: 700,
        letterSpacing: 1.4,
        textTransform: "uppercase",
        cursor: disabled ? "not-allowed" : "pointer",
        border: variant === "primary"
          ? "1px solid var(--accent)"
          : "1px solid var(--line-strong)",
        background: disabled
          ? "rgba(255,255,255,0.06)"
          : variant === "primary"
          ? "var(--accent)"
          : "transparent",
        color: disabled
          ? "var(--text-dim)"
          : variant === "primary"
          ? "#fff"
          : "var(--text)",
        opacity: disabled ? 0.6 : 1,
        transition: "all 120ms",
      }}
    >
      {children}
    </button>
  );
}


// === Step-panels =====================================================

function ReadWatchPanel({ progress, onDone, onCelebrate, step }: StepCardProps) {
  const done = !!progress?.completed_at;
  const [busy, setBusy] = useState(false);
  async function markDone() {
    setBusy(true);
    try {
      const res = await api<CompleteResp>(
        `/student/steps/${step.id}/complete`,
        { method: "POST", body: JSON.stringify({}) },
      );
      if (res.new_achievements?.length) onCelebrate(res.new_achievements);
      onDone();
    } finally {
      setBusy(false);
    }
  }
  return (
    <V2Button onClick={markDone} disabled={done || busy}>
      {done ? "Klart ✓" : busy ? "Sparar…" : "Jag har läst klart"}
    </V2Button>
  );
}


function ReflectPanel({ step, progress, onDone, onCelebrate }: StepCardProps) {
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
      const res = await api<CompleteResp>(
        `/student/steps/${step.id}/complete`,
        {
          method: "POST",
          body: JSON.stringify({ data: { reflection: text.trim() } }),
        },
      );
      if (res.new_achievements?.length) onCelebrate(res.new_achievements);
      onDone();
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <textarea
        value={text}
        onChange={(e) => setText(e.target.value)}
        rows={5}
        placeholder="Skriv din reflektion här…"
        style={{
          width: "100%",
          background: "rgba(15, 21, 37, 0.7)",
          border: "1px solid var(--line-strong)",
          borderRadius: 6,
          padding: 14,
          color: "var(--text)",
          fontSize: 14,
          fontFamily: "var(--serif)",
          resize: "vertical",
        }}
      />
      <div
        style={{
          display: "flex", justifyContent: "space-between",
          alignItems: "center", marginTop: 8,
        }}
      >
        <span
          style={{
            fontFamily: "var(--mono)",
            fontSize: 10,
            color: "var(--text-dim)",
            letterSpacing: 1.2,
          }}
        >
          {text.trim().length} tecken
        </span>
        <V2Button onClick={save} disabled={busy}>
          {progress?.completed_at ? "Spara ny version" : "Skicka"}
        </V2Button>
      </div>
      {err && (
        <div
          style={{
            color: "#fca5a5", fontSize: 13, marginTop: 8,
          }}
        >
          {err}
        </div>
      )}
    </div>
  );
}


function QuizPanel({ step, progress, onDone, onCelebrate }: StepCardProps) {
  const p = step.params ?? {};
  const options = (p.options as string[]) ?? [];
  const correctIdx = p.correct_index as number | undefined;
  const correctIndices = p.correct_indices as number[] | undefined;
  const isMulti = Array.isArray(correctIndices);
  const explanation = p.explanation as string | undefined;

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
  const [lastCorrect, setLastCorrect] = useState<boolean | null>(
    progress?.data?.correct != null
      ? (progress.data.correct as boolean) : null,
  );
  const [showResult, setShowResult] = useState(!!progress?.completed_at);
  const [busy, setBusy] = useState(false);
  const [aiEnabled, setAiEnabled] = useState(false);
  const [aiText, setAiText] = useState("");
  const [aiBusy, setAiBusy] = useState(false);
  const [aiErr, setAiErr] = useState<string | null>(null);
  const aiAbortRef = useRef<AbortController | null>(null);
  const question = (p.question as string) || "";

  useEffect(() => {
    api<{ ai_enabled: boolean }>("/admin/ai/me")
      .then((r) => setAiEnabled(Boolean(r.ai_enabled)))
      .catch(() => setAiEnabled(false));
  }, []);

  async function submit() {
    setBusy(true);
    setAiText("");
    setAiErr(null);
    try {
      const body = isMulti
        ? { data: { answers: [...multiSelected].sort((a, b) => a - b) } }
        : { data: { answer: singleSelected } };
      const res = await api<CompleteResp>(
        `/student/steps/${step.id}/complete`,
        { method: "POST", body: JSON.stringify(body) },
      );
      setLastCorrect(!!res.data.correct);
      setShowResult(true);
      if (res.new_achievements?.length) onCelebrate(res.new_achievements);
      // Auto-gå till nästa step efter framgångsrikt svar — annars
      // står eleven kvar och måste klicka manuellt.
      if (res.data.correct) {
        window.setTimeout(() => onDone(), 1500);
      }
    } finally {
      setBusy(false);
    }
  }

  function retry() {
    setShowResult(false);
    setSingleSelected(null);
    setMultiSelected(new Set());
    setAiText("");
    setAiErr(null);
    aiAbortRef.current?.abort();
  }

  async function explainWithAi() {
    aiAbortRef.current?.abort();
    const ctrl = new AbortController();
    aiAbortRef.current = ctrl;
    setAiBusy(true);
    setAiErr(null);
    setAiText("");
    try {
      const token = getToken();
      const asStudent = getAsStudent();
      const headers: Record<string, string> = {
        "Content-Type": "application/json",
      };
      if (token) headers.Authorization = `Bearer ${token}`;
      if (asStudent) headers["X-As-Student"] = String(asStudent);
      const res = await fetch(
        `${getApiBase()}/ai/student/quiz-explain/stream`,
        {
          method: "POST",
          headers,
          body: JSON.stringify({ step_id: step.id }),
          signal: ctrl.signal,
        },
      );
      if (!res.ok || !res.body) {
        if (res.status === 503)
          throw new Error("AI-hjälpen är inte tillgänglig just nu.");
        throw new Error(`HTTP ${res.status}`);
      }
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const parts = buffer.split("\n\n");
        buffer = parts.pop() ?? "";
        for (const part of parts) {
          const line = part.trim();
          if (!line.startsWith("data:")) continue;
          try {
            const payload = JSON.parse(line.slice(5).trim());
            if (payload.text) {
              setAiText((t) => t + (payload.text as string));
            }
          } catch {
            /* ignore malformed SSE chunk */
          }
        }
      }
    } catch (e) {
      if ((e as Error).name !== "AbortError") {
        setAiErr(e instanceof Error ? e.message : String(e));
      }
    } finally {
      setAiBusy(false);
    }
  }

  const canSubmit = isMulti
    ? multiSelected.size > 0 : singleSelected !== null;

  return (
    <div>
      {question && (
        <div
          style={{
            fontFamily: "var(--serif)",
            fontSize: 16,
            color: "var(--text)",
            marginBottom: 16,
            fontWeight: 500,
          }}
        >
          {question}
        </div>
      )}
      {isMulti && !showResult && (
        <div
          style={{
            fontFamily: "var(--mono)",
            fontSize: 10,
            letterSpacing: 1.2,
            color: "var(--text-dim)",
            marginBottom: 10,
            textTransform: "uppercase",
          }}
        >
          Flera svar kan vara rätt — bocka alla du tror
        </div>
      )}

      <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
        {options.map((opt, i) => {
          const isSelected = isMulti
            ? multiSelected.has(i) : singleSelected === i;
          const isCorrectAnswer = isMulti
            ? (correctIndices ?? []).includes(i) : correctIdx === i;
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
              style={{
                width: "100%",
                textAlign: "left",
                padding: "14px 16px",
                borderRadius: 6,
                border: showCorrect
                  ? "1.5px solid rgba(110, 231, 183, 0.7)"
                  : showWrong
                  ? "1.5px solid rgba(220, 76, 43, 0.7)"
                  : isSelected
                  ? "1.5px solid var(--accent)"
                  : "1px solid var(--line-strong)",
                background: showCorrect
                  ? "rgba(110, 231, 183, 0.10)"
                  : showWrong
                  ? "rgba(220, 76, 43, 0.10)"
                  : isSelected
                  ? "rgba(220, 76, 43, 0.10)"
                  : "rgba(15, 21, 37, 0.4)",
                color: "var(--text)",
                fontSize: 14,
                fontFamily: "var(--serif)",
                cursor: showResult ? "default" : "pointer",
                transition: "all 120ms",
                display: "flex",
                alignItems: "center",
                gap: 12,
              }}
            >
              {isMulti && !showResult && (
                <span
                  style={{
                    width: 18, height: 18,
                    border: "1.5px solid var(--line-strong)",
                    borderRadius: 4,
                    display: "inline-flex",
                    alignItems: "center", justifyContent: "center",
                    color: "var(--accent)",
                    fontSize: 12,
                    flexShrink: 0,
                  }}
                >
                  {isSelected ? "✓" : ""}
                </span>
              )}
              <span style={{ flex: 1 }}>{opt}</span>
              {showCorrect && (
                <span style={{ color: "#6ee7b7", fontSize: 12 }}>
                  ✓ rätt
                </span>
              )}
              {showWrong && (
                <span style={{ color: "#fda594", fontSize: 12 }}>
                  ✗ fel
                </span>
              )}
            </button>
          );
        })}
      </div>

      <div style={{ display: "flex", gap: 10, marginTop: 16 }}>
        {!showResult ? (
          <V2Button onClick={submit} disabled={!canSubmit || busy}>
            {busy ? "Skickar…" : "Svara"}
          </V2Button>
        ) : (
          <>
            <V2Button onClick={retry} variant="ghost">
              Försök igen
            </V2Button>
            {aiEnabled && !lastCorrect && (
              <V2Button onClick={explainWithAi} disabled={aiBusy}>
                {aiBusy ? "AI förklarar…" : "AI förklarar"}
              </V2Button>
            )}
          </>
        )}
      </div>

      {showResult && explanation && (
        <div
          style={{
            marginTop: 16,
            padding: "12px 14px",
            background: "rgba(99, 102, 241, 0.08)",
            borderLeft: "3px solid rgba(99, 102, 241, 0.6)",
            borderRadius: 4,
            fontSize: 13,
            color: "#c7d2fe",
            whiteSpace: "pre-wrap",
          }}
        >
          <div
            style={{
              fontFamily: "var(--mono)",
              fontSize: 9,
              letterSpacing: 1.4,
              textTransform: "uppercase",
              marginBottom: 4,
              opacity: 0.8,
            }}
          >
            Förklaring
          </div>
          {explanation}
        </div>
      )}

      {aiText && (
        <div
          style={{
            marginTop: 12,
            padding: "12px 14px",
            background: "rgba(167, 139, 250, 0.08)",
            borderLeft: "3px solid rgba(167, 139, 250, 0.6)",
            borderRadius: 4,
            fontSize: 13,
            color: "rgba(196,181,253,0.95)",
            whiteSpace: "pre-wrap",
          }}
        >
          <div
            style={{
              fontFamily: "var(--mono)",
              fontSize: 9,
              letterSpacing: 1.4,
              textTransform: "uppercase",
              marginBottom: 4,
              opacity: 0.8,
            }}
          >
            AI-förklaring
          </div>
          {aiText}
        </div>
      )}
      {aiErr && (
        <div
          style={{
            color: "#fca5a5", fontSize: 13, marginTop: 8,
          }}
        >
          {aiErr}
        </div>
      )}
    </div>
  );
}


function TaskPanel({ step, progress, onDone, onCelebrate }: StepCardProps) {
  const done = !!progress?.completed_at;
  const [busy, setBusy] = useState(false);
  const taskHint = (step.params?.hint as string) || "";

  async function markDone() {
    setBusy(true);
    try {
      const res = await api<CompleteResp>(
        `/student/steps/${step.id}/complete`,
        { method: "POST", body: JSON.stringify({}) },
      );
      if (res.new_achievements?.length) onCelebrate(res.new_achievements);
      onDone();
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      {taskHint && (
        <div
          style={{
            padding: "12px 14px",
            background: "rgba(15, 21, 37, 0.6)",
            border: "1px solid var(--line)",
            borderRadius: 6,
            fontSize: 13,
            color: "var(--text)",
            marginBottom: 14,
            whiteSpace: "pre-wrap",
            fontFamily: "var(--serif)",
          }}
        >
          {taskHint}
        </div>
      )}
      <V2Button onClick={markDone} disabled={done || busy}>
        {done ? "Klart ✓" : busy ? "Sparar…" : "Markera som klar"}
      </V2Button>
    </div>
  );
}
