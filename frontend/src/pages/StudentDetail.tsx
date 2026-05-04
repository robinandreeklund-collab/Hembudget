import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import {
  Activity, ArrowLeft, BookOpenCheck, Brain, Briefcase, CheckCircle2, Eye,
  FileText, ListChecks, Loader2, Plus, Sparkles, Target, Users, XCircle,
} from "lucide-react";
import { api, ApiError, getApiBase, getToken } from "@/api/client";
import { useAuth } from "@/hooks/useAuth";
import { AssignmentList } from "@/components/AssignmentList";
import { MasteryChart } from "@/components/MasteryChart";

type Profile = {
  profession: string; employer: string;
  gross_salary_monthly: number; net_salary_monthly: number;
  personality: string; age: number; city: string;
  family_status: string; housing_type: string; housing_monthly: number;
  has_mortgage: boolean; has_car_loan: boolean; has_student_loan: boolean;
  children_ages: number[]; partner_age: number | null;
  backstory: string | null;
};

type BatchSummary = {
  id: number; year_month: string;
  artifact_count: number; imported_count: number;
};

type FacitRow = {
  tx_id: number; date: string; description: string; amount: number;
  expected_category: string; actual_category: string | null;
  is_correct: boolean; is_uncategorized: boolean;
};

type FacitOut = {
  total: number; correct: number; incorrect: number; uncategorized: number;
  year_month: string; rows: FacitRow[];
};

const ASSIGNMENT_KINDS = [
  { value: "set_budget", label: "Sätt budget" },
  { value: "import_batch", label: "Importera månadens dokument" },
  { value: "balance_month", label: "Balansera månaden (positivt resultat)" },
  { value: "review_loan", label: "Granska lån" },
  { value: "categorize_all", label: "Kategorisera alla transaktioner" },
  { value: "save_amount", label: "Spara X kr" },
  { value: "mortgage_decision", label: "Bolåne-beslut (rörlig vs bunden)" },
  { value: "link_transfer", label: "Länka överföringar (X st)" },
  { value: "add_upcoming", label: "Lägg till kommande räkningar (X st)" },
  { value: "free_text", label: "Annan uppgift (manuell)" },
];

export default function StudentDetail() {
  const { studentId } = useParams<{ studentId: string }>();
  const navigate = useNavigate();
  const { impersonate } = useAuth();
  const sid = parseInt(studentId || "0", 10);

  const [profile, setProfile] = useState<Profile | null>(null);
  const [batches, setBatches] = useState<BatchSummary[]>([]);
  const [facitMonth, setFacitMonth] = useState("");
  const [facit, setFacit] = useState<FacitOut | null>(null);
  const [mastery, setMastery] = useState<Array<{
    competency: { id: number; name: string; level: string };
    mastery: number;
    evidence_count: number;
  }>>([]);
  const [recommendations, setRecommendations] = useState<Array<{
    module_id: number;
    title: string;
    summary: string | null;
    reason: string;
    step_count: number;
  }>>([]);
  const [moduleProgress, setModuleProgress] = useState<Array<{
    id: number;
    module_id: number;
    module_title: string;
    module_summary: string | null;
    started_at: string | null;
    completed_at: string | null;
    step_count: number;
    completed_step_count: number;
    steps: Array<{
      id: number; sort_order: number; kind: string; title: string;
      completed_at: string | null;
      auto_status: "not_started" | "in_progress" | "completed" | null;
      auto_progress: string | null;
    }>;
  }>>([]);
  const [showCreate, setShowCreate] = useState(false);
  const [newKind, setNewKind] = useState("free_text");
  const [newTitle, setNewTitle] = useState("");
  const [newDesc, setNewDesc] = useState("");
  const [newMonth, setNewMonth] = useState("");
  const [newAmount, setNewAmount] = useState("");
  const [newMortgagePrincipal, setNewMortgagePrincipal] = useState("2000000");
  const [newMortgageHorizon, setNewMortgageHorizon] = useState("36");
  const [reloadKey, setReloadKey] = useState(0);
  const [aiEnabled, setAiEnabled] = useState(false);
  const [aiChecks, setAiChecks] = useState<Record<number, {
    is_match: boolean; confidence: number; explanation: string;
  }>>({});
  const [aiBusyRow, setAiBusyRow] = useState<number | null>(null);
  const [aiThreads, setAiThreads] = useState<Array<{
    id: number; title: string | null; module_id: number | null;
    created_at: string; updated_at: string; message_count: number;
  }>>([]);
  const [openThread, setOpenThread] = useState<{
    id: number; title: string | null; messages: Array<{
      id: number; role: string; content: string; created_at: string;
    }>;
  } | null>(null);
  const [activity, setActivity] = useState<Array<{
    id: number; kind: string; summary: string;
    payload: Record<string, unknown> | null;
    occurred_at: string;
  }>>([]);

  useEffect(() => {
    api<{ ai_enabled: boolean }>("/admin/ai/me")
      .then((r) => setAiEnabled(Boolean(r.ai_enabled)))
      .catch(() => setAiEnabled(false));
  }, []);

  async function recheckRow(r: FacitRow) {
    if (!r.actual_category || !r.expected_category) return;
    setAiBusyRow(r.tx_id);
    try {
      const res = await api<{
        is_match: boolean; confidence: number; explanation: string;
      }>("/ai/category/check", {
        method: "POST",
        body: JSON.stringify({
          merchant: r.description,
          amount: r.amount,
          student_category: r.actual_category,
          facit_category: r.expected_category,
        }),
      });
      setAiChecks((prev) => ({ ...prev, [r.tx_id]: res }));
    } catch (e) {
      if (e instanceof ApiError && e.status !== 503) {
        console.error(e);
      }
    } finally {
      setAiBusyRow(null);
    }
  }

  async function reload() {
    const p = await api<Profile>(`/teacher/students/${sid}/profile`);
    setProfile(p);
    const b = await api<BatchSummary[]>(`/teacher/students/${sid}/batches`);
    setBatches(b);
    if (b.length > 0 && !facitMonth) {
      setFacitMonth(b[0].year_month);
    }
  }

  async function loadFacit(ym: string) {
    try {
      const f = await api<FacitOut>(
        `/teacher/students/${sid}/facit/${ym}`,
      );
      setFacit(f);
    } catch {
      setFacit(null);
    }
  }

  useEffect(() => {
    reload();
    api<typeof mastery>(`/teacher/students/${sid}/mastery`)
      .then((m) => setMastery(m.filter((r) => r.evidence_count > 0)))
      .catch(() => setMastery([]));
    api<typeof recommendations>(`/teacher/students/${sid}/recommendations`)
      .then(setRecommendations)
      .catch(() => setRecommendations([]));
    api<typeof moduleProgress>(`/teacher/students/${sid}/modules`)
      .then(setModuleProgress)
      .catch(() => setModuleProgress([]));
    api<typeof aiThreads>(`/ai/teacher/students/${sid}/threads`)
      .then(setAiThreads)
      .catch(() => setAiThreads([]));
    api<{ items: typeof activity }>(`/teacher/students/${sid}/activity?limit=30`)
      .then((r) => setActivity(r.items))
      .catch(() => setActivity([]));
  }, [sid]);

  async function openAiThread(id: number) {
    try {
      const t = await api<{
        id: number; title: string | null;
        messages: Array<{ id: number; role: string; content: string; created_at: string }>;
      }>(`/ai/teacher/students/${sid}/threads/${id}`);
      setOpenThread(t);
    } catch {
      setOpenThread(null);
    }
  }

  async function assignRec(moduleId: number) {
    await api(`/teacher/modules/${moduleId}/assign`, {
      method: "POST",
      body: JSON.stringify({ student_ids: [sid] }),
    });
    api<typeof recommendations>(`/teacher/students/${sid}/recommendations`)
      .then(setRecommendations)
      .catch(() => setRecommendations([]));
  }

  useEffect(() => {
    if (facitMonth) loadFacit(facitMonth);
  }, [facitMonth]);

  async function createAssignment() {
    if (!newTitle.trim()) return;
    await api("/teacher/assignments", {
      method: "POST",
      body: JSON.stringify({
        title: newTitle, description: newDesc || newTitle,
        kind: newKind, student_id: sid,
        target_year_month: newMonth || null,
        params: newKind === "save_amount" && newAmount
          ? { amount: parseInt(newAmount, 10) }
          : newKind === "mortgage_decision"
          ? {
              decision_month: newMonth,
              principal: parseInt(newMortgagePrincipal, 10),
              horizon_months: parseInt(newMortgageHorizon, 10),
            }
          : (newKind === "link_transfer" || newKind === "add_upcoming")
            && newAmount
          ? { target_count: parseInt(newAmount, 10) }
          : null,
      }),
    });
    setNewTitle(""); setNewDesc(""); setNewMonth(""); setNewAmount("");
    setShowCreate(false);
    setReloadKey(reloadKey + 1);
  }

  function viewAs() {
    impersonate(sid);
    window.location.href = "/dashboard";
  }

  async function downloadPortfolio() {
    const tok = getToken();
    const res = await fetch(
      `${getApiBase()}/teacher/students/${sid}/portfolio.pdf`,
      { headers: tok ? { Authorization: `Bearer ${tok}` } : undefined },
    );
    if (!res.ok) {
      setMastery((v) => v);
      return;
    }
    const blob = await res.blob();
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `portfolio_${sid}.pdf`;
    document.body.appendChild(a);
    a.click();
    a.remove();
  }

  if (!profile) {
    return <div className="p-6">Laddar elev…</div>;
  }

  return (
    <div className="p-4 md:p-6 max-w-5xl mx-auto space-y-6">
      <button
        onClick={() => navigate("/teacher")}
        className="text-sm text-slate-600 hover:text-ink flex items-center gap-1"
      >
        <ArrowLeft className="w-4 h-4" /> Tillbaka till elevlistan
      </button>

      <div className="flex items-center justify-between">
        <h1 className="serif text-3xl leading-tight">
          <Users className="w-6 h-6 text-brand-600" />
          Elev #{sid}
        </h1>
        <div className="flex gap-2">
          <button
            onClick={downloadPortfolio}
            className="bg-white border border-slate-300 hover:bg-slate-50 rounded px-4 py-2 flex items-center gap-2 text-slate-700"
          >
            📄 Portfolio PDF
          </button>
          <button
            onClick={viewAs}
            className="btn-dark rounded-md px-4 py-2 flex items-center gap-2"
          >
            <Eye className="w-4 h-4" /> Titta som denna elev
          </button>
        </div>
      </div>

      {/* Profil */}
      <section className="bg-white border rounded-xl p-4 space-y-3">
        <h2 className="font-semibold text-lg flex items-center gap-2">
          <Briefcase className="w-5 h-5 text-brand-600" /> Profil
        </h2>
        <div className="text-sm text-slate-700 italic">{profile.backstory}</div>
        <div className="grid grid-cols-2 md:grid-cols-3 gap-3 text-sm">
          <Stat label="Yrke" value={profile.profession} />
          <Stat label="Arbetsgivare" value={profile.employer} />
          <Stat label="Personlighet" value={profile.personality} />
          <Stat label="Ålder" value={`${profile.age} år`} />
          <Stat label="Bruttolön" value={`${profile.gross_salary_monthly.toLocaleString("sv-SE")} kr`} />
          <Stat label="Nettolön" value={`${profile.net_salary_monthly.toLocaleString("sv-SE")} kr`} />
          <Stat
            label="Familj"
            value={
              profile.family_status === "ensam" ? "Ensam"
              : profile.family_status === "sambo" ? "Sambo"
              : `Barn (${profile.children_ages.join(", ")} år)`
            }
          />
          <Stat label="Stad" value={profile.city} />
          <Stat
            label="Boende"
            value={`${profile.housing_type} – ${profile.housing_monthly.toLocaleString("sv-SE")} kr`}
          />
        </div>
      </section>

      <EmployerStatusCard studentId={sid} onView={viewAs} />

      {/* Rekommendationer */}
      {recommendations.length > 0 && (
        <section className="bg-gradient-to-br from-brand-50 to-white border border-brand-200 rounded-xl p-4 space-y-3">
          <h2 className="font-semibold text-lg flex items-center gap-2">
            <Sparkles className="w-5 h-5 text-brand-600" /> Rekommenderade moduler
          </h2>
          <p className="text-sm text-slate-600">
            Baserat på elevens mastery — dessa moduler tränar svagaste områdena.
          </p>
          <ul className="space-y-2">
            {recommendations.slice(0, 3).map((r) => (
              <li
                key={r.module_id}
                className="bg-white border rounded p-3 flex items-center gap-3"
              >
                <div className="flex-1">
                  <div className="font-medium">{r.title}</div>
                  {r.summary && (
                    <div className="text-sm text-slate-600">{r.summary}</div>
                  )}
                  <div className="text-xs text-brand-700 mt-1">💡 {r.reason}</div>
                </div>
                <button
                  onClick={() => assignRec(r.module_id)}
                  className="btn-dark rounded-md px-3 py-1.5 text-sm"
                >
                  Tilldela
                </button>
              </li>
            ))}
          </ul>
        </section>
      )}

      {/* AI-sammanfattning */}
      <AiStudentSummarySection studentId={sid} />

      {/* Mastery */}
      {mastery.length > 0 && (
        <section className="bg-white border rounded-xl p-4 space-y-3">
          <h2 className="font-semibold text-lg flex items-center gap-2">
            <Target className="w-5 h-5 text-brand-600" /> Färdigheter
          </h2>
          <MasteryChart data={mastery} compact />
        </section>
      )}

      {/* Modul-progression — task-steg auto-spårade mot scope-DB */}
      {moduleProgress.length > 0 && (
        <section className="bg-white border border-rule rounded-xl p-4 space-y-3">
          <h2 className="font-semibold text-lg flex items-center gap-2">
            <ListChecks className="w-5 h-5 text-ink" /> Modul-progression
          </h2>
          <p className="text-sm text-[#666]">
            Task-steg utvärderas live mot elevens huvudbok. Du ser
            samma status som eleven utan att eleven behöver klicka klar.
          </p>
          <ul className="space-y-3">
            {moduleProgress.map((m) => {
              const pct = m.step_count > 0
                ? Math.round((m.completed_step_count / m.step_count) * 100)
                : 0;
              return (
                <li
                  key={m.id}
                  className="border border-rule rounded-md p-3 space-y-2"
                >
                  <div className="flex items-center justify-between gap-3">
                    <div className="flex-1 min-w-0">
                      <div className="font-medium truncate">
                        {m.module_title}
                      </div>
                      <div className="text-xs text-[#666] mt-0.5">
                        {m.completed_step_count}/{m.step_count} steg klara
                        {m.completed_at ? " · klar" : m.started_at ? " · pågår" : " · ej påbörjad"}
                      </div>
                    </div>
                    <div className="text-sm tabular-nums text-[#444] shrink-0">
                      {pct}%
                    </div>
                  </div>
                  <div className="h-1.5 bg-paper rounded overflow-hidden">
                    <div
                      className="h-full bg-ink"
                      style={{ width: `${pct}%` }}
                    />
                  </div>
                  <ul className="text-xs space-y-1 mt-2">
                    {m.steps.map((s) => {
                      const dotColor = s.completed_at
                        ? "bg-emerald-600"
                        : s.auto_status === "in_progress"
                        ? "bg-amber-500"
                        : "bg-rule";
                      return (
                        <li
                          key={s.id}
                          className="flex items-center gap-2"
                        >
                          <span
                            className={
                              "inline-block w-2 h-2 rounded-full " + dotColor
                            }
                          />
                          <span className="truncate flex-1">
                            <span className="text-[#999] mr-1">
                              [{s.kind}]
                            </span>
                            {s.title}
                          </span>
                          {s.kind === "task" && s.auto_progress && (
                            <span className="text-[#666] shrink-0">
                              {s.auto_progress}
                            </span>
                          )}
                        </li>
                      );
                    })}
                  </ul>
                </li>
              );
            })}
          </ul>
        </section>
      )}

      {/* AI-konversationer — vad eleven har frågat Claude */}
      {aiThreads.length > 0 && (
        <section className="bg-white border border-rule rounded-xl p-4 space-y-3">
          <h2 className="font-semibold text-lg flex items-center gap-2">
            <Brain className="w-5 h-5 text-ink" /> AI-konversationer
          </h2>
          <p className="text-sm text-[#666]">
            Vad eleven har frågat AI:n. Klicka på en tråd för att läsa
            hela konversationen — viktigt för bedömning och
            missbruksskydd.
          </p>
          <ul className="space-y-1.5">
            {aiThreads.map((t) => (
              <li
                key={t.id}
                className="border border-rule rounded-md px-3 py-2 flex items-center gap-3 hover:bg-paper cursor-pointer"
                onClick={() => openAiThread(t.id)}
              >
                <div className="flex-1 min-w-0">
                  <div className="text-sm font-medium truncate">
                    {t.title || "(utan titel)"}
                  </div>
                  <div className="text-xs text-[#666]">
                    {new Date(t.updated_at).toLocaleString("sv-SE")} ·
                    {" "}{t.message_count} meddelanden
                  </div>
                </div>
                <Eye className="w-4 h-4 text-[#888] shrink-0" />
              </li>
            ))}
          </ul>
        </section>
      )}

      {/* Modal: full AI-tråd */}
      {openThread && (
        <div
          className="fixed inset-0 z-50 bg-ink/50 flex items-center justify-center p-4"
          onClick={() => setOpenThread(null)}
        >
          <div
            className="bg-white border border-rule rounded-xl max-w-2xl w-full max-h-[80vh] overflow-y-auto p-5 space-y-3"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between gap-3 border-b border-rule pb-3">
              <h3 className="font-semibold text-lg">
                {openThread.title || "(utan titel)"}
              </h3>
              <button
                onClick={() => setOpenThread(null)}
                className="text-[#666] hover:text-ink text-xl leading-none"
                aria-label="Stäng"
              >
                ×
              </button>
            </div>
            <div className="space-y-3">
              {openThread.messages.map((m) => (
                <div
                  key={m.id}
                  className={
                    "border rounded-md p-3 text-sm whitespace-pre-wrap " +
                    (m.role === "user"
                      ? "border-rule bg-paper"
                      : "border-rule bg-white")
                  }
                >
                  <div className="text-xs eyebrow mb-1">
                    {m.role === "user" ? "Eleven" : "AI"} ·
                    {" "}{new Date(m.created_at).toLocaleString("sv-SE")}
                  </div>
                  <div className="text-ink">{m.content}</div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* Aktivitetsflöde — vad eleven gjort i scope-DB:n */}
      {activity.length > 0 && (
        <section className="bg-white border border-rule rounded-xl p-4 space-y-3">
          <h2 className="font-semibold text-lg flex items-center gap-2">
            <Activity className="w-5 h-5 text-ink" /> Senaste aktivitet
          </h2>
          <p className="text-sm text-[#666]">
            Tidslinje över elevens handlingar — transaktioner, budget, lån
            och kategorisering. Fångas automatiskt utan att eleven behöver
            rapportera.
          </p>
          <ul className="space-y-1.5 max-h-80 overflow-y-auto">
            {activity.map((a) => (
              <li
                key={a.id}
                className="flex items-start gap-3 border-b border-rule/50 pb-1.5 last:border-0"
              >
                <span className="text-xs eyebrow shrink-0 mt-0.5 w-28">
                  {new Date(a.occurred_at).toLocaleString("sv-SE", {
                    month: "2-digit", day: "2-digit",
                    hour: "2-digit", minute: "2-digit",
                  })}
                </span>
                <span className="text-sm flex-1">{a.summary}</span>
                <span className="text-xs text-[#999] shrink-0">{a.kind}</span>
              </li>
            ))}
          </ul>
        </section>
      )}

      {/* Uppdrag */}
      <section className="bg-white border rounded-xl p-4 space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="font-semibold text-lg flex items-center gap-2">
            <BookOpenCheck className="w-5 h-5 text-brand-600" /> Uppdrag
          </h2>
          <button
            onClick={() => setShowCreate(!showCreate)}
            className="text-sm btn-dark rounded-md px-3 py-1.5 flex items-center gap-1"
          >
            <Plus className="w-4 h-4" /> Nytt uppdrag
          </button>
        </div>
        {showCreate && (
          <div className="bg-slate-50 rounded p-3 space-y-2 text-sm">
            <div className="grid grid-cols-2 gap-2">
              <select
                value={newKind}
                onChange={(e) => setNewKind(e.target.value)}
                className="border rounded px-2 py-1.5"
              >
                {ASSIGNMENT_KINDS.map((k) => (
                  <option key={k.value} value={k.value}>{k.label}</option>
                ))}
              </select>
              <input
                type="month"
                value={newMonth}
                onChange={(e) => setNewMonth(e.target.value)}
                placeholder="Månad (valfri)"
                className="border rounded px-2 py-1.5"
              />
            </div>
            <input
              value={newTitle}
              onChange={(e) => setNewTitle(e.target.value)}
              placeholder="Titel"
              className="w-full border rounded px-2 py-1.5"
            />
            <textarea
              value={newDesc}
              onChange={(e) => setNewDesc(e.target.value)}
              placeholder="Beskrivning"
              className="w-full border rounded px-2 py-1.5"
              rows={2}
            />
            {newKind === "save_amount" && (
              <input
                type="number"
                value={newAmount}
                onChange={(e) => setNewAmount(e.target.value)}
                placeholder="Belopp att spara (kr)"
                className="w-full border rounded px-2 py-1.5"
              />
            )}
            {(newKind === "link_transfer" || newKind === "add_upcoming") && (
              <input
                type="number"
                value={newAmount}
                onChange={(e) => setNewAmount(e.target.value)}
                placeholder={
                  newKind === "link_transfer"
                    ? "Antal överföringar att länka"
                    : "Antal kommande räkningar"
                }
                className="w-full border rounded px-2 py-1.5"
              />
            )}
            {newKind === "mortgage_decision" && (
              <div className="grid grid-cols-2 gap-2">
                <input
                  type="number"
                  value={newMortgagePrincipal}
                  onChange={(e) => setNewMortgagePrincipal(e.target.value)}
                  placeholder="Lånebelopp (kr)"
                  className="border rounded px-2 py-1.5"
                />
                <input
                  type="number"
                  value={newMortgageHorizon}
                  onChange={(e) => setNewMortgageHorizon(e.target.value)}
                  placeholder="Horisont (månader)"
                  className="border rounded px-2 py-1.5"
                />
                <p className="col-span-2 text-xs text-amber-700">
                  Använd Månad-fältet som beslutsmånad — välj gärna en
                  historisk månad (t.ex. 2022-06) så eleven kan se facit.
                </p>
              </div>
            )}
            <div className="flex justify-end gap-2">
              <button
                onClick={() => setShowCreate(false)}
                className="text-slate-600 hover:bg-slate-200 rounded px-3 py-1.5"
              >
                Avbryt
              </button>
              <button
                onClick={createAssignment}
                className="bg-brand-600 text-white rounded px-3 py-1.5"
              >
                Skapa
              </button>
            </div>
          </div>
        )}
        <AssignmentList key={reloadKey} studentId={sid} asTeacher />
      </section>

      {/* Facit för kategorisering */}
      <section className="bg-white border rounded-xl p-4 space-y-3">
        <div className="flex items-center justify-between flex-wrap gap-2">
          <h2 className="font-semibold text-lg flex items-center gap-2">
            <ListChecks className="w-5 h-5 text-brand-600" /> Kategori-facit
          </h2>
          {batches.length > 0 && (
            <select
              value={facitMonth}
              onChange={(e) => setFacitMonth(e.target.value)}
              className="text-sm border rounded px-2 py-1"
            >
              {batches.map((b) => (
                <option key={b.year_month} value={b.year_month}>
                  {b.year_month}
                </option>
              ))}
            </select>
          )}
        </div>
        {!facit ? (
          <div className="text-sm text-slate-500">
            Inga transaktioner att kontrollera ännu.
          </div>
        ) : (
          <>
            <div className="grid grid-cols-3 gap-3 text-sm">
              <div className="bg-emerald-50 rounded p-2">
                <div className="text-xs text-slate-600">Rätt</div>
                <div className="text-xl font-bold text-emerald-700">
                  {facit.correct} / {facit.total}
                </div>
              </div>
              <div className="bg-rose-50 rounded p-2">
                <div className="text-xs text-slate-600">Fel</div>
                <div className="text-xl font-bold text-rose-700">
                  {facit.incorrect}
                </div>
              </div>
              <div className="bg-slate-100 rounded p-2">
                <div className="text-xs text-slate-600">Okategoriserade</div>
                <div className="text-xl font-bold text-slate-600">
                  {facit.uncategorized}
                </div>
              </div>
            </div>
            {facit.rows.length > 0 && (
              <details className="text-sm">
                <summary className="cursor-pointer text-slate-600 hover:text-ink">
                  Visa alla ({facit.rows.length} transaktioner)
                </summary>
                <div className="overflow-x-auto -mx-2 md:mx-0 mt-2">
                <table className="w-full text-xs min-w-[640px]">
                  <thead>
                    <tr className="text-slate-500 text-left">
                      <th className="py-1">Datum</th>
                      <th>Transaktion</th>
                      <th>Facit</th>
                      <th>Elevens val</th>
                      <th></th>
                      <th></th>
                    </tr>
                  </thead>
                  <tbody>
                    {facit.rows.map((r) => {
                      const ai = aiChecks[r.tx_id];
                      const canRecheck =
                        aiEnabled && !r.is_correct && !r.is_uncategorized;
                      return (
                        <tr key={r.tx_id} className="border-t align-top">
                          <td className="py-1 text-slate-500">{r.date}</td>
                          <td>{r.description}</td>
                          <td className="font-medium">{r.expected_category}</td>
                          <td className={
                            r.is_correct || ai?.is_match
                              ? "text-emerald-700"
                              : r.is_uncategorized
                              ? "text-slate-400"
                              : "text-rose-600"
                          }>
                            {r.actual_category ?? "—"}
                            {ai && (
                              <div className="text-[10px] mt-0.5 text-slate-600 italic leading-tight">
                                AI: {ai.is_match ? "godkänt" : "inte samma"}
                                {" "}({Math.round(ai.confidence * 100)}%)
                                {ai.explanation && <> — {ai.explanation}</>}
                              </div>
                            )}
                          </td>
                          <td>
                            {r.is_correct ? (
                              <CheckCircle2 className="w-4 h-4 text-emerald-600" />
                            ) : r.is_uncategorized ? (
                              <span className="text-slate-400">?</span>
                            ) : ai?.is_match ? (
                              <CheckCircle2 className="w-4 h-4 text-emerald-600" />
                            ) : (
                              <XCircle className="w-4 h-4 text-rose-500" />
                            )}
                          </td>
                          <td>
                            {canRecheck && !ai && (
                              <button
                                onClick={() => recheckRow(r)}
                                disabled={aiBusyRow === r.tx_id}
                                className="text-[10px] text-purple-600 hover:text-purple-800 flex items-center gap-0.5 disabled:opacity-50"
                                title="Fråga AI om synonymerna stämmer"
                              >
                                {aiBusyRow === r.tx_id ? (
                                  <Loader2 className="w-3 h-3 animate-spin" />
                                ) : (
                                  <Brain className="w-3 h-3" />
                                )}
                                AI
                              </button>
                            )}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
                </div>
              </details>
            )}
          </>
        )}
      </section>

      {/* Batches */}
      <section className="bg-white border rounded-xl p-4 space-y-3">
        <h2 className="font-semibold text-lg flex items-center gap-2">
          <FileText className="w-5 h-5 text-brand-600" /> Utskickade dokument
        </h2>
        {batches.length === 0 ? (
          <div className="text-sm text-slate-500">
            Inga batches utdelade än. Gå tillbaka till lärarpanelen och tryck
            "Generera" för att skapa månadens dokument.
          </div>
        ) : (
          <ul className="divide-y divide-slate-200">
            {batches.map((b) => (
              <li
                key={b.id}
                className="py-2 flex items-center justify-between text-sm"
              >
                <span>
                  <strong>{b.year_month}</strong> – {b.artifact_count} dokument
                </span>
                <span className="text-xs text-slate-500">
                  {b.imported_count}/{b.artifact_count} importerade
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-xs text-slate-500">{label}</div>
      <div className="font-medium">{value}</div>
    </div>
  );
}


type SummaryOut = {
  student_id: number;
  strengths: string;
  gaps: string;
  next_steps: string;
  model: string;
  input_tokens: number;
  output_tokens: number;
};

function AiStudentSummarySection({ studentId }: { studentId: number }) {
  const [aiEnabled, setAiEnabled] = useState(false);
  const [summary, setSummary] = useState<SummaryOut | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    api<{ ai_enabled: boolean }>("/admin/ai/me")
      .then((r) => setAiEnabled(Boolean(r.ai_enabled)))
      .catch(() => setAiEnabled(false));
  }, []);

  async function run() {
    setBusy(true); setErr(null);
    try {
      const s = await api<SummaryOut>(
        `/ai/teacher/students/${studentId}/summary`,
        { method: "POST" },
      );
      setSummary(s);
    } catch (e) {
      if (e instanceof ApiError && e.status === 503)
        setErr("AI-funktioner är inte påslagna för ditt konto.");
      else setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  if (!aiEnabled) return null;

  return (
    <section className="bg-gradient-to-br from-purple-50 to-slate-50 border border-purple-200 rounded-xl p-4 space-y-3">
      <div className="flex items-center justify-between">
        <h2 className="font-semibold text-lg text-slate-900 flex items-center gap-2">
          <Sparkles className="w-5 h-5 text-purple-600" />
          AI-lägesbild
        </h2>
        <button
          onClick={run}
          disabled={busy}
          className="text-sm bg-purple-600 hover:bg-purple-700 text-white rounded px-3 py-1.5 flex items-center gap-1 disabled:opacity-50"
        >
          {busy ? (
            <Loader2 className="w-4 h-4 animate-spin" />
          ) : (
            <Sparkles className="w-4 h-4" />
          )}
          {summary ? "Generera ny" : "Generera lägesbild"}
        </button>
      </div>
      {err && (
        <div className="bg-rose-50 border border-rose-200 text-rose-700 text-sm rounded p-2">
          {err}
        </div>
      )}
      {summary && (
        <div className="space-y-3 text-sm text-slate-800">
          <div>
            <div className="font-semibold text-emerald-800 mb-0.5">Styrkor</div>
            <div className="whitespace-pre-wrap">{summary.strengths}</div>
          </div>
          <div>
            <div className="font-semibold text-amber-800 mb-0.5">Gap</div>
            <div className="whitespace-pre-wrap">{summary.gaps}</div>
          </div>
          <div>
            <div className="font-semibold text-brand-800 mb-0.5">Nästa steg</div>
            <div className="whitespace-pre-wrap">{summary.next_steps}</div>
          </div>
          <div className="text-xs text-slate-500">
            Genererad med Claude Sonnet · {summary.input_tokens} in /{" "}
            {summary.output_tokens} ut tokens
          </div>
        </div>
      )}
      {!summary && !err && !busy && (
        <p className="text-sm text-slate-600">
          AI-genererad lägesbild över elevens styrkor, gap och föreslagna
          nästa steg. Baserad på mastery, reflektioner och uppdrag.
        </p>
      )}
    </section>
  );
}


interface ClassEmployerRow {
  student_id: number;
  display_name: string;
  score: number;
  trend: "rising" | "falling" | "stable";
  agreement_code: string | null;
  flag: "low" | "critical" | null;
}


function EmployerStatusCard({
  studentId,
  onView,
}: {
  studentId: number;
  onView: () => void;
}) {
  const q = useQuery({
    queryKey: ["teacher-employer-class"],
    queryFn: () => api<{ rows: ClassEmployerRow[] }>(
      "/teacher/employer/class",
    ),
  });
  const row = q.data?.rows.find((r) => r.student_id === studentId);
  if (q.isLoading) {
    return (
      <section className="bg-white border rounded-xl p-4">
        <div className="text-sm text-slate-600">Laddar arbetsgivar-status…</div>
      </section>
    );
  }
  if (!row) {
    return null; // ingen status än, eller fel — tyst
  }
  const tone = row.flag === "critical"
    ? "border-rose-300 bg-rose-50/50"
    : row.flag === "low"
      ? "border-amber-300 bg-amber-50/50"
      : "border-slate-200 bg-white";
  const trendArrow =
    row.trend === "rising" ? "↑" :
    row.trend === "falling" ? "↓" : "→";
  return (
    <section className={`border rounded-xl p-4 ${tone}`}>
      <div className="flex items-start justify-between gap-3">
        <div>
          <h2 className="font-semibold text-lg flex items-center gap-2">
            🏢 Arbetsgivar-nöjdhet
          </h2>
          <div className="text-sm text-slate-600 mt-0.5">
            {row.agreement_code
              ? <>Avtal: <code className="bg-white border px-1 rounded">{row.agreement_code}</code></>
              : "Småföretag utan avtal"}
          </div>
        </div>
        <div className="text-right">
          <div className="text-3xl serif font-semibold">{row.score}</div>
          <div className="text-xs text-slate-500">
            {trendArrow} {row.trend}
          </div>
        </div>
      </div>
      {row.flag && (
        <div className={`text-xs mt-2 ${
          row.flag === "critical" ? "text-rose-700" : "text-amber-700"
        }`}>
          {row.flag === "critical"
            ? "Kritisk nivå — boka uppföljningssamtal"
            : "Låg nivå — håll utkik"}
        </div>
      )}
      <div className="mt-3">
        <button
          onClick={onView}
          className="text-xs text-brand-700 hover:underline"
        >
          Öppna /arbetsgivare som denna elev →
        </button>
      </div>
    </section>
  );
}
