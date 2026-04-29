/**
 * /teacher/wellbeing — klassöversikt över Wellbeing per elev.
 *
 * Lärar-vy med fullständigt namn + per-dimension Wellbeing + rödflaggor.
 * Pedagogiskt: läraren ska kunna se vilka elever som mår sämre och
 * prata med dem. Inga betyg, bara signaler.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, Calendar, Heart, Info, Send } from "lucide-react";
import { useState } from "react";
import { api, formatSEK } from "@/api/client";
import { Card } from "@/components/Card";

interface ClassRow {
  student_id: number;
  display_name: string;
  class_label: string | null;
  total_score: number;
  economy: number;
  health: number;
  social: number;
  leisure: number;
  safety: number;
  events_accepted: number;
  events_declined: number;
  budget_violations: number;
  decline_streak: number;
  flags: string[];
}

interface OverviewResponse {
  rows: ClassRow[];
  aggregate: {
    students: number;
    avg_total_score: number;
    avg_economy: number;
    avg_social: number;
    students_with_flags: number;
  };
}

const FLAG_INFO: Record<string, { label: string; color: string }> = {
  social_low: { label: "Sociala band lågt", color: "bg-amber-100 text-amber-800 border-amber-200" },
  budget_underfed: { label: "Budget underfed", color: "bg-orange-100 text-orange-800 border-orange-200" },
  economy_critical: { label: "Ekonomi kritisk", color: "bg-red-100 text-red-800 border-red-200" },
  buffer_low: { label: "Ingen buffert", color: "bg-rose-100 text-rose-800 border-rose-200" },
  decline_streak_high: { label: "Många nej", color: "bg-amber-100 text-amber-800 border-amber-200" },
  overall_low: { label: "Wellbeing lågt", color: "bg-red-100 text-red-800 border-red-200" },
  data_error: { label: "Data-fel", color: "bg-slate-100 text-slate-800 border-slate-200" },
};

function ScoreBar({ value, label }: { value: number; label: string }) {
  const color =
    value >= 70 ? "bg-emerald-500" :
    value >= 50 ? "bg-amber-400" :
    value >= 30 ? "bg-orange-500" :
    "bg-red-500";
  return (
    <div className="flex items-center gap-1.5 text-xs" title={`${label}: ${value}/100`}>
      <span className="w-14 text-slate-600">{label}</span>
      <div className="flex-1 bg-slate-100 rounded-full h-1.5 overflow-hidden">
        <div className={`h-full rounded-full ${color}`} style={{ width: `${value}%` }} />
      </div>
      <span className="font-mono w-7 text-right">{value}</span>
    </div>
  );
}

export default function TeacherWellbeing() {
  const overviewQ = useQuery({
    queryKey: ["teacher-wellbeing-overview"],
    queryFn: () => api<OverviewResponse>("/teacher/class/wellbeing"),
    refetchInterval: 60_000,
  });

  const data = overviewQ.data;

  return (
    <div className="p-3 md:p-6 space-y-4 max-w-6xl">
      <div>
        <h1 className="serif text-3xl flex items-center gap-2">
          <Heart className="w-7 h-7 text-rose-500" />
          Wellbeing — klassöversikt
        </h1>
        <div className="text-sm text-slate-700 mt-1">
          Hur mår eleverna? Wellbeing över 5 dimensioner + rödflaggor.
          <br />
          <span className="text-xs italic">
            Pedagogiskt syfte: signal, inte betyg. Använd för att veta vem
            du behöver fråga "hur har du det?".
          </span>
        </div>
      </div>

      {data && (
        <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
          <Card title="Elever">
            <div className="text-2xl serif">{data.aggregate.students}</div>
          </Card>
          <Card title="Klassens snitt-Wellbeing">
            <div className="text-2xl serif">{data.aggregate.avg_total_score}</div>
            <div className="text-xs text-slate-600">av 100</div>
          </Card>
          <Card title="Snitt sociala band">
            <div className="text-2xl serif">{data.aggregate.avg_social}</div>
          </Card>
          <Card title="Elever med rödflagg">
            <div className={`text-2xl serif ${
              data.aggregate.students_with_flags > 0 ? "text-amber-700" : ""
            }`}>
              {data.aggregate.students_with_flags}
            </div>
            <div className="text-xs text-slate-600">behöver kanske check-in</div>
          </Card>
        </div>
      )}

      <ClassEventsSection />

      <Card title={`Elever (${data?.rows.length ?? 0})`}>
        <div className="text-xs text-slate-600 mb-3 flex items-start gap-1">
          <Info className="w-3 h-3 mt-0.5 shrink-0" />
          <span>
            Wellbeing-faktorerna är transparenta: sätt en låg matbudget och
            'Mat &amp; hälsa' sjunker; nekas alla sociala events och 'Sociala
            band' rasar. Lär eleven att se sambandet — det är pedagogiken.
          </span>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="text-left text-slate-600 border-b">
              <tr>
                <th className="py-2">Elev</th>
                <th>Klass</th>
                <th>Total</th>
                <th colSpan={5}>Dimensioner</th>
                <th>Events ja/nej</th>
                <th>Streak</th>
                <th>Flaggor</th>
              </tr>
            </thead>
            <tbody>
              {data?.rows.map((r) => (
                <tr
                  key={r.student_id}
                  className={`border-b last:border-0 hover:bg-slate-50 ${
                    r.flags.includes("overall_low") || r.flags.includes("economy_critical")
                      ? "bg-red-50"
                      : r.flags.length > 0
                        ? "bg-amber-50/40"
                        : ""
                  }`}
                >
                  <td className="py-2 font-medium">{r.display_name}</td>
                  <td>{r.class_label ?? "—"}</td>
                  <td className="font-mono font-semibold">
                    <span className={
                      r.total_score >= 70 ? "text-emerald-700" :
                      r.total_score >= 50 ? "text-amber-700" :
                      r.total_score >= 30 ? "text-orange-700" :
                      "text-red-700"
                    }>
                      {r.total_score}
                    </span>
                  </td>
                  <td colSpan={5}>
                    <div className="space-y-0.5 max-w-xs">
                      <ScoreBar value={r.economy} label="Ekonomi" />
                      <ScoreBar value={r.health} label="Hälsa" />
                      <ScoreBar value={r.social} label="Social" />
                      <ScoreBar value={r.leisure} label="Fritid" />
                      <ScoreBar value={r.safety} label="Trygghet" />
                    </div>
                  </td>
                  <td className="text-xs">
                    <span className="text-emerald-700">{r.events_accepted}</span>
                    {" / "}
                    <span className="text-slate-500">{r.events_declined}</span>
                    {r.budget_violations > 0 && (
                      <div className="text-[10px] text-orange-700 mt-0.5">
                        {r.budget_violations} budget-violations
                      </div>
                    )}
                  </td>
                  <td className="text-center">
                    <span className={
                      r.decline_streak >= 5 ? "text-red-700 font-bold" :
                      r.decline_streak >= 3 ? "text-amber-700 font-medium" :
                      "text-slate-500"
                    }>
                      {r.decline_streak}
                    </span>
                  </td>
                  <td>
                    <div className="flex flex-wrap gap-1">
                      {r.flags.map((f) => {
                        const info = FLAG_INFO[f] ?? FLAG_INFO.data_error;
                        return (
                          <span
                            key={f}
                            className={`text-[10px] px-1.5 py-0.5 rounded border ${info.color}`}
                            title={f}
                          >
                            <AlertTriangle className="inline w-2 h-2 mr-0.5" />
                            {info.label}
                          </span>
                        );
                      })}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}

// ---------- Klassgemensamma events (Fas 7) ----------

interface TeacherClassEvent {
  id: number;
  teacher_id: number;
  class_label: string | null;
  title: string;
  description: string;
  category: string;
  cost: number;
  proposed_date: string | null;
  deadline: string;
  impact_economy: number;
  impact_health: number;
  impact_social: number;
  impact_leisure: number;
  impact_safety: number;
  status: string;
  distributed_at: string | null;
  created_at: string;
}

function ClassEventsSection() {
  const qc = useQueryClient();
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({
    title: "Klassresan till Berlin",
    description: "Tre dagar i Berlin med klassen — gemensamt boende.",
    category: "culture",
    cost: 4500,
    proposed_date: "",
    deadline: "",
    class_label: "",
    impact_economy: -2,
    impact_health: 0,
    impact_social: 6,
    impact_leisure: 6,
    impact_safety: 0,
  });
  const [error, setError] = useState<string | null>(null);

  const eventsQ = useQuery({
    queryKey: ["teacher-class-events"],
    queryFn: () =>
      api<{ events: TeacherClassEvent[]; count: number }>("/teacher/class-events"),
  });

  const createMut = useMutation({
    mutationFn: (body: typeof form) =>
      api<TeacherClassEvent>("/teacher/class-events", {
        method: "POST",
        body: JSON.stringify({
          ...body,
          class_label: body.class_label || null,
          proposed_date: body.proposed_date || null,
        }),
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["teacher-class-events"] });
      setShowForm(false);
      setError(null);
    },
    onError: (e: unknown) => {
      setError(e instanceof Error ? e.message : "Kunde inte skapa");
    },
  });

  const distributeMut = useMutation({
    mutationFn: (eventId: number) =>
      api<{ students_targeted: number; student_events_created: number }>(
        `/teacher/class-events/${eventId}/distribute`,
        { method: "POST" },
      ),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["teacher-class-events"] });
    },
  });

  const events = eventsQ.data?.events ?? [];

  return (
    <Card title={`Klassgemensamma events (${events.length})`}>
      <div className="text-xs text-slate-600 mb-3 italic">
        Skapa events som tilldelas hela klassen — t.ex. klassresan, fika
        i fredag, friluftsdagen. Eleverna ser dem i sin Dashboard och
        accepterar/nekar som vanliga events.
      </div>

      {!showForm && (
        <button
          onClick={() => setShowForm(true)}
          className="bg-rose-600 text-white px-3 py-1.5 rounded text-sm flex items-center gap-1 mb-3"
        >
          <Calendar className="w-3 h-3" />
          Skapa nytt klassevent
        </button>
      )}

      {showForm && (
        <div className="border rounded p-3 mb-3 space-y-2 bg-slate-50">
          <input
            type="text"
            value={form.title}
            onChange={(e) => setForm({ ...form, title: e.target.value })}
            placeholder="Titel"
            className="w-full border rounded px-2 py-1.5 text-sm"
          />
          <textarea
            value={form.description}
            onChange={(e) => setForm({ ...form, description: e.target.value })}
            placeholder="Beskrivning"
            rows={2}
            className="w-full border rounded px-2 py-1.5 text-sm"
          />
          <div className="grid grid-cols-2 gap-2">
            <label className="text-xs">
              Kostnad/elev (kr)
              <input
                type="number"
                value={form.cost}
                onChange={(e) =>
                  setForm({ ...form, cost: parseFloat(e.target.value) || 0 })
                }
                className="w-full border rounded px-2 py-1 text-sm mt-0.5"
              />
            </label>
            <label className="text-xs">
              Deadline (YYYY-MM-DD)
              <input
                type="date"
                value={form.deadline}
                onChange={(e) => setForm({ ...form, deadline: e.target.value })}
                className="w-full border rounded px-2 py-1 text-sm mt-0.5"
              />
            </label>
            <label className="text-xs">
              Föreslaget datum
              <input
                type="date"
                value={form.proposed_date}
                onChange={(e) => setForm({ ...form, proposed_date: e.target.value })}
                className="w-full border rounded px-2 py-1 text-sm mt-0.5"
              />
            </label>
            <label className="text-xs">
              Klass-label (valfri)
              <input
                type="text"
                value={form.class_label}
                onChange={(e) => setForm({ ...form, class_label: e.target.value })}
                placeholder="t.ex. NA22"
                className="w-full border rounded px-2 py-1 text-sm mt-0.5"
              />
            </label>
          </div>
          <div className="text-xs font-medium mt-2">Wellbeing-impact vid accept</div>
          <div className="grid grid-cols-5 gap-1">
            {(["economy", "health", "social", "leisure", "safety"] as const).map((dim) => (
              <label key={dim} className="text-[10px] text-slate-600">
                {dim}
                <input
                  type="number"
                  min={-10}
                  max={10}
                  value={form[`impact_${dim}` as const]}
                  onChange={(e) =>
                    setForm({
                      ...form,
                      [`impact_${dim}`]: parseInt(e.target.value) || 0,
                    })
                  }
                  className="w-full border rounded px-1 py-0.5 text-xs mt-0.5"
                />
              </label>
            ))}
          </div>
          {error && (
            <div className="text-xs text-red-700 bg-red-50 border border-red-200 rounded p-1.5">
              {error}
            </div>
          )}
          <div className="flex gap-2 justify-end">
            <button
              onClick={() => {
                setShowForm(false);
                setError(null);
              }}
              className="px-3 py-1.5 rounded border text-sm"
            >
              Avbryt
            </button>
            <button
              onClick={() => createMut.mutate(form)}
              disabled={
                createMut.isPending ||
                !form.title ||
                !form.deadline
              }
              className="bg-rose-600 text-white px-3 py-1.5 rounded text-sm disabled:opacity-50"
            >
              {createMut.isPending ? "Skapar…" : "Skapa (draft)"}
            </button>
          </div>
        </div>
      )}

      <div className="space-y-2">
        {events.length === 0 && (
          <div className="text-sm text-slate-500 italic">
            Inga klassevent än.
          </div>
        )}
        {events.map((e) => (
          <div key={e.id} className="border rounded p-2.5 text-sm">
            <div className="flex items-start justify-between gap-2">
              <div className="flex-1 min-w-0">
                <div className="font-medium">{e.title}</div>
                <div className="text-xs text-slate-600 mt-0.5">{e.description}</div>
                <div className="text-xs text-slate-500 mt-1">
                  {formatSEK(e.cost)} ·{" "}
                  Deadline {new Date(e.deadline).toLocaleDateString("sv-SE")}
                  {e.class_label && ` · ${e.class_label}`}
                </div>
              </div>
              <div className="text-right shrink-0">
                <span
                  className={`inline-block text-[10px] px-1.5 py-0.5 rounded ${
                    e.status === "draft"
                      ? "bg-slate-100 text-slate-700"
                      : e.status === "distributed"
                      ? "bg-emerald-100 text-emerald-800"
                      : "bg-amber-100 text-amber-800"
                  }`}
                >
                  {e.status}
                </span>
                {e.status === "draft" && (
                  <button
                    onClick={() => distributeMut.mutate(e.id)}
                    disabled={distributeMut.isPending}
                    className="block bg-rose-600 text-white px-2 py-1 rounded text-xs mt-1 disabled:opacity-50"
                  >
                    <Send className="inline w-3 h-3 mr-0.5" />
                    Distribuera
                  </button>
                )}
              </div>
            </div>
          </div>
        ))}
      </div>

      {distributeMut.data && (
        <div className="text-xs bg-emerald-50 border border-emerald-200 rounded p-2 mt-2">
          ✓ Distribuerat till {distributeMut.data.students_targeted} elever
          ({distributeMut.data.student_events_created} event-rader skapade).
        </div>
      )}
    </Card>
  );
}
