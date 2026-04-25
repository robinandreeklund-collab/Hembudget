import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  ArrowLeft, BookOpen, ChevronRight, Copy, Edit2, Library, Loader2,
  Plus, Sparkles, Trash2,
} from "lucide-react";
import { api, ApiError } from "@/api/client";

type Module = {
  id: number;
  teacher_id: number | null;
  title: string;
  summary: string | null;
  is_template: boolean;
  sort_order: number;
  step_count: number;
};

type AIStepDraft = {
  kind: "read" | "watch" | "reflect" | "task" | "quiz";
  title: string;
  body?: string;
  sort_order?: number;
};

type AIModuleDraft = {
  title: string;
  summary: string;
  steps: AIStepDraft[];
};

export default function TeacherModules() {
  const nav = useNavigate();
  const [mods, setMods] = useState<Module[]>([]);
  const [showCreate, setShowCreate] = useState(false);
  const [newTitle, setNewTitle] = useState("");
  const [newSummary, setNewSummary] = useState("");
  const [err, setErr] = useState<string | null>(null);

  const [templates, setTemplates] = useState<Module[]>([]);
  const [aiEnabled, setAiEnabled] = useState(false);
  const [showAI, setShowAI] = useState(false);
  const [aiPrompt, setAiPrompt] = useState("");
  const [aiBusy, setAiBusy] = useState(false);
  const [aiDraft, setAiDraft] = useState<AIModuleDraft | null>(null);
  const [aiErr, setAiErr] = useState<string | null>(null);

  useEffect(() => {
    api<{ ai_enabled: boolean }>("/admin/ai/me")
      .then((r) => setAiEnabled(Boolean(r.ai_enabled)))
      .catch(() => setAiEnabled(false));
  }, []);

  async function load() {
    try {
      setMods(await api<Module[]>("/teacher/modules"));
      const lib = await api<Module[]>("/library/modules");
      // Bara system-mallar (teacher_id=null), inte dina egna
      setTemplates(lib.filter((m) => m.teacher_id == null));
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    }
  }

  async function clone(id: number) {
    await api(`/teacher/modules/${id}/clone`, { method: "POST" });
    await load();
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

  async function aiGenerate() {
    if (!aiPrompt.trim()) return;
    setAiBusy(true);
    setAiErr(null);
    setAiDraft(null);
    try {
      const res = await api<{ parsed: AIModuleDraft | null; raw: string }>(
        "/ai/modules/generate",
        { method: "POST", body: JSON.stringify({ prompt: aiPrompt.trim() }) },
      );
      if (!res.parsed || !Array.isArray(res.parsed.steps)) {
        setAiErr(
          "AI-svaret kunde inte tolkas som modul. Prova en annan formulering.",
        );
        return;
      }
      setAiDraft(res.parsed);
    } catch (e) {
      if (e instanceof ApiError && e.status === 503) {
        setAiErr("AI-funktioner är inte aktiverade på ditt konto.");
      } else {
        setAiErr(e instanceof Error ? e.message : String(e));
      }
    } finally {
      setAiBusy(false);
    }
  }

  async function acceptAiDraft() {
    if (!aiDraft) return;
    setAiBusy(true);
    try {
      const mod = await api<Module>("/teacher/modules", {
        method: "POST",
        body: JSON.stringify({
          title: aiDraft.title,
          summary: aiDraft.summary || null,
        }),
      });
      let order = 0;
      for (const st of aiDraft.steps) {
        if (!st.kind || !st.title) continue;
        await api(`/teacher/modules/${mod.id}/steps`, {
          method: "POST",
          body: JSON.stringify({
            kind: st.kind,
            title: st.title,
            content: st.body || null,
            sort_order: st.sort_order ?? order,
            params: null,
          }),
        });
        order += 1;
      }
      setShowAI(false);
      setAiDraft(null);
      setAiPrompt("");
      nav(`/teacher/modules/${mod.id}`);
    } catch (e) {
      setAiErr(e instanceof Error ? e.message : String(e));
    } finally {
      setAiBusy(false);
    }
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
        <div className="flex gap-2">
          {aiEnabled && (
            <button
              onClick={() => setShowAI(true)}
              className="bg-purple-600 hover:bg-purple-700 text-white rounded-lg px-4 py-2 flex items-center gap-2"
              title="Låt AI skissa en modul"
            >
              <Sparkles className="w-4 h-4" /> AI-skiss
            </button>
          )}
          <button
            onClick={() => setShowCreate(true)}
            className="btn-dark rounded-md px-4 py-2 flex items-center gap-2"
          >
            <Plus className="w-4 h-4" /> Ny modul
          </button>
        </div>
      </div>
      {err && (
        <div className="text-sm text-[#b91c1c] border-l-2 border-[#b91c1c] pl-3 py-1">
          {err}
        </div>
      )}

      {templates.length > 0 && (
        <section className="bg-slate-100 rounded-xl p-4 space-y-3">
          <div className="flex items-center gap-2 text-sm font-semibold text-slate-700">
            <Library className="w-4 h-4" /> Bibliotek — färdiga mallar
          </div>
          <ul className="space-y-2">
            {templates.map((t) => (
              <li
                key={t.id}
                className="bg-white border rounded-lg p-3 flex items-center gap-3"
              >
                <BookOpen className="w-5 h-5 text-brand-600 shrink-0" />
                <div className="flex-1 min-w-0">
                  <div className="font-medium text-slate-800">{t.title}</div>
                  {t.summary && (
                    <div className="text-xs text-slate-600 truncate">{t.summary}</div>
                  )}
                  <div className="text-xs text-slate-500 mt-0.5">
                    {t.step_count} steg
                  </div>
                </div>
                <button
                  onClick={() => clone(t.id)}
                  className="btn-dark rounded-md px-3 py-1.5 text-sm flex items-center gap-1"
                >
                  <Copy className="w-3.5 h-3.5" /> Använd mall
                </button>
              </li>
            ))}
          </ul>
        </section>
      )}

      {mods.length === 0 ? (
        <div className="bg-amber-50 border border-amber-200 text-amber-900 rounded p-4 text-sm">
          Inga egna moduler än. Skapa din första eller använd en mall ovan.
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

      {/* AI-skiss-modal */}
      {showAI && (
        <div
          className="fixed inset-0 bg-black/40 grid place-items-center z-50 p-4"
          onClick={() => !aiBusy && setShowAI(false)}
        >
          <div
            className="bg-white rounded-xl shadow-xl p-6 w-full max-w-2xl max-h-[85vh] overflow-y-auto space-y-3"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center gap-2">
              <Sparkles className="w-5 h-5 text-purple-600" />
              <h2 className="font-semibold text-lg">AI-skissad modul</h2>
            </div>
            <p className="text-xs text-slate-600">
              Beskriv temat — gärna målgrupp, lärandemål och eventuella
              begränsningar. AI:n skissar 4–7 steg. Du kan redigera allt
              innan du godkänner.
            </p>
            <textarea
              value={aiPrompt}
              onChange={(e) => setAiPrompt(e.target.value)}
              placeholder="Ex: 'En modul om att göra sin första månadsbudget. Målgrupp 17-åringar. Ska ha en reflektion om behov/önskemål och ett quiz.'"
              rows={4}
              className="w-full border rounded px-3 py-2 text-sm"
              disabled={aiBusy}
            />
            {aiErr && (
              <div className="bg-rose-50 border border-rose-200 text-rose-700 rounded p-2 text-sm">
                {aiErr}
              </div>
            )}
            {aiDraft && (
              <div className="bg-purple-50 border border-purple-200 rounded p-3 space-y-2">
                <div className="font-semibold text-slate-900">
                  {aiDraft.title}
                </div>
                {aiDraft.summary && (
                  <div className="text-sm text-slate-700">
                    {aiDraft.summary}
                  </div>
                )}
                <ol className="space-y-1 text-sm text-slate-700">
                  {aiDraft.steps.map((st, i) => (
                    <li key={i} className="flex gap-2">
                      <span className="text-slate-500 font-mono text-xs mt-0.5">
                        {i + 1}.
                      </span>
                      <div>
                        <span className="inline-block text-xs bg-white border border-slate-200 rounded px-1.5 py-0.5 mr-2">
                          {st.kind}
                        </span>
                        <span className="font-medium">{st.title}</span>
                        {st.body && (
                          <div className="text-xs text-slate-600 mt-0.5">
                            {st.body.slice(0, 200)}
                            {st.body.length > 200 ? "…" : ""}
                          </div>
                        )}
                      </div>
                    </li>
                  ))}
                </ol>
              </div>
            )}
            <div className="flex justify-end gap-2 pt-2">
              <button
                onClick={() => !aiBusy && setShowAI(false)}
                className="px-3 py-2 text-slate-600 hover:bg-slate-100 rounded"
                disabled={aiBusy}
              >
                Avbryt
              </button>
              {aiDraft ? (
                <>
                  <button
                    onClick={() => setAiDraft(null)}
                    className="px-3 py-2 text-slate-600 hover:bg-slate-100 rounded"
                    disabled={aiBusy}
                  >
                    Skissa om
                  </button>
                  <button
                    onClick={acceptAiDraft}
                    disabled={aiBusy}
                    className="btn-dark rounded-md px-4 py-2 flex items-center gap-2 disabled:opacity-50"
                  >
                    {aiBusy && <Loader2 className="w-4 h-4 animate-spin" />}
                    Skapa modulen
                  </button>
                </>
              ) : (
                <button
                  onClick={aiGenerate}
                  disabled={aiBusy || !aiPrompt.trim()}
                  className="bg-purple-600 hover:bg-purple-700 text-white rounded px-4 py-2 flex items-center gap-2 disabled:opacity-50"
                >
                  {aiBusy ? (
                    <Loader2 className="w-4 h-4 animate-spin" />
                  ) : (
                    <Sparkles className="w-4 h-4" />
                  )}
                  Skissa modul
                </button>
              )}
            </div>
          </div>
        </div>
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
