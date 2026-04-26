import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  BookOpen, CheckCircle2, ChevronRight, GraduationCap, Play, Sparkles,
} from "lucide-react";
import { api } from "@/api/client";

type Mod = {
  id: number;
  module_id: number;
  module_title: string;
  module_summary: string | null;
  sort_order: number;
  started_at: string | null;
  completed_at: string | null;
  step_count: number;
  completed_step_count: number;
};

type Recommendation = {
  module_id: number;
  title: string;
  summary: string | null;
  step_count: number;
  reason: string;
  weak_competencies: string[];
};

export default function MyModules() {
  const [mods, setMods] = useState<Mod[]>([]);
  const [recs, setRecs] = useState<Recommendation[]>([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    api<Mod[]>("/student/modules")
      .then(setMods)
      .catch((e) => setErr(e instanceof Error ? e.message : String(e)))
      .finally(() => setLoading(false));
    api<Recommendation[]>("/student/recommendations")
      .then(setRecs)
      .catch(() => setRecs([]));
  }, []);

  return (
    <div className="p-4 md:p-6 max-w-4xl mx-auto space-y-6">
      <div className="flex items-center gap-2">
        <GraduationCap className="w-6 h-6 text-brand-600" />
        <h1 className="serif text-3xl leading-tight">Din kursplan</h1>
      </div>
      <p className="text-sm text-slate-700">
        Gå igenom modulerna i ordning — läs, reflektera, svara på frågor
        och gör uppdrag. Din lärare ser när du är klar.
      </p>
      {err && (
        <div className="text-sm text-[#b91c1c] border-l-2 border-[#b91c1c] pl-3 py-1">
          {err}
        </div>
      )}
      {recs.length > 0 && (
        <section className="bg-gradient-to-br from-brand-50 to-white border border-brand-200 rounded-xl p-4 space-y-3">
          <div className="flex items-center gap-2">
            <Sparkles className="w-5 h-5 text-brand-600" />
            <h2 className="font-semibold text-slate-900">
              Rekommenderat för dig
            </h2>
          </div>
          <p className="text-sm text-slate-600">
            Baserat på dina färdigheter — be din lärare att tilldela dig
            dessa moduler.
          </p>
          <ul className="space-y-2">
            {recs.slice(0, 3).map((r) => (
              <li
                key={r.module_id}
                className="bg-white border border-slate-200 rounded p-3"
              >
                <div className="font-medium text-slate-900">{r.title}</div>
                {r.summary && (
                  <div className="text-sm text-slate-600 mt-0.5">
                    {r.summary}
                  </div>
                )}
                <div className="text-xs text-brand-700 mt-1">
                  💡 {r.reason}
                </div>
              </li>
            ))}
          </ul>
        </section>
      )}

      {loading ? (
        <div className="text-slate-500">Laddar…</div>
      ) : mods.length === 0 ? (
        <div className="bg-amber-50 border border-amber-200 text-amber-800 rounded-lg p-4">
          Inga moduler tilldelade än. Fråga din lärare om hen planerat en
          kursplan åt dig.
        </div>
      ) : (
        <ul className="space-y-3">
          {mods.map((m, i) => {
            const pct = m.step_count > 0
              ? Math.round((m.completed_step_count / m.step_count) * 100)
              : 0;
            const isDone = m.completed_at != null;
            const isStarted = m.started_at != null;
            return (
              <li key={m.id}>
                <Link
                  to={`/modules/${m.module_id}`}
                  className="block bg-white rounded-xl border border-slate-200 hover:border-brand-400 hover:shadow-md transition-all p-5"
                >
                  <div className="flex items-start gap-4">
                    <div
                      className={`w-10 h-10 rounded-full flex items-center justify-center shrink-0 ${
                        isDone
                          ? "bg-emerald-100 text-emerald-700"
                          : isStarted
                          ? "bg-amber-100 text-amber-700"
                          : "bg-slate-100 text-slate-500"
                      }`}
                    >
                      {isDone ? (
                        <CheckCircle2 className="w-5 h-5" />
                      ) : isStarted ? (
                        <Play className="w-4 h-4" />
                      ) : (
                        <span className="text-sm font-semibold">{i + 1}</span>
                      )}
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center justify-between gap-2">
                        <h2 className="font-semibold text-slate-900">
                          {m.module_title}
                        </h2>
                        <ChevronRight className="w-4 h-4 text-slate-400 shrink-0" />
                      </div>
                      {m.module_summary && (
                        <p className="text-sm text-slate-600 mt-1">
                          {m.module_summary}
                        </p>
                      )}
                      <div className="mt-3 flex items-center gap-2 text-xs">
                        <div className="flex-1 h-1.5 bg-slate-100 rounded-full overflow-hidden">
                          <div
                            className={`h-full ${
                              isDone
                                ? "bg-emerald-500"
                                : pct > 0
                                ? "bg-amber-500"
                                : "bg-slate-300"
                            }`}
                            style={{ width: `${Math.max(pct, 2)}%` }}
                          />
                        </div>
                        <span className="text-slate-500 whitespace-nowrap">
                          <BookOpen className="inline w-3 h-3 mr-1" />
                          {m.completed_step_count} / {m.step_count} steg
                        </span>
                      </div>
                    </div>
                  </div>
                </Link>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
