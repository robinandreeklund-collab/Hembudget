/**
 * StudentPedagogyCards — pedagogiska elev-vy-element som tidigare bara
 * fanns i den separata EkoDashboard. Vi monterar dem nu överst i den
 * gemensamma Dashboard så ATT eleven OCH läraren-via-impersonation ser
 * samma sak — annars blir det förvirrande att vyn skiljer sig beroende
 * på roll.
 *
 * Innehåll (top-down):
 *  - Inactivity-nudge (om eleven varit borta länge)
 *  - "Hej {namn}" + profession
 *  - Budget denna månad (progressbars per kategori)
 *  - Oväntade utgifter denna månad
 *  - Uppdrag-summary (AssignmentList)
 *  - Streak + prestationer (badges)
 *  - Färdighets-mastery (radar)
 *
 * KPIs (Inkomst/Utgifter/Sparande/Sparkvot) lämnas till Dashboard
 * eftersom de redan finns där och är mer detaljerade.
 */
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  AlertTriangle,
  BookOpenCheck,
  Download,
  Flame,
} from "lucide-react";
import { api, getApiBase, getToken } from "@/api/client";
import { AssignmentList } from "@/components/AssignmentList";
import { InfoBanner } from "@/components/Tooltip";
import { MasteryChart } from "@/components/MasteryChart";

type DashboardRow = { category: string; budget: number; spent: number; pct: number };
type Overshoot = {
  date: string;
  description: string;
  amount: number;
  category_hint: string | null;
};

type Dashboard = {
  year_month: string;
  net_income: number;
  total_spent: number;
  balance: number;
  savings_done: number;
  savings_goal: number | null;
  category_rows: DashboardRow[];
  recent_overshoots: Overshoot[];
  assignments_done: number;
  assignments_total: number;
  personality: string;
  profession: string;
  display_name: string;
  inactivity_nudge: { days_away: number; last_active: string } | null;
};

type MasteryRow = {
  competency: { id: number; name: string; level: string; description?: string | null };
  mastery: number;
  evidence_count: number;
};

const formatKr = (n: number): string =>
  n.toLocaleString("sv-SE") + " kr";

interface Props {
  /** YYYY-MM. Driver budget-/oväntade-utgifter-vyerna. */
  month: string;
}

export function StudentPedagogyCards({ month }: Props) {
  const [data, setData] = useState<Dashboard | null>(null);
  const [mastery, setMastery] = useState<MasteryRow[]>([]);
  const [achievements, setAchievements] = useState<{
    earned: { key: string; title: string; emoji: string }[];
    streak: { current: number; longest: number };
  } | null>(null);

  useEffect(() => {
    api<Dashboard>(`/student/dashboard?year_month=${month}`)
      .then(setData)
      .catch(() => setData(null));
  }, [month]);

  useEffect(() => {
    api<MasteryRow[]>("/student/mastery")
      .then((m) => setMastery(m.filter((r) => r.evidence_count > 0)))
      .catch(() => setMastery([]));
    api<{
      earned: { key: string; title: string; emoji: string }[];
      streak: { current: number; longest: number };
    }>("/student/achievements")
      .then(setAchievements)
      .catch(() => setAchievements(null));
  }, []);

  async function downloadPortfolio() {
    const tok = getToken();
    const res = await fetch(`${getApiBase()}/student/portfolio.pdf`, {
      headers: tok ? { Authorization: `Bearer ${tok}` } : undefined,
    });
    if (!res.ok) return;
    const blob = await res.blob();
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = "portfolio.pdf";
    document.body.appendChild(a);
    a.click();
    a.remove();
  }

  // Om endpointen inte är tillgänglig (t.ex. ingen scope eller fel
  // konfig) — rendera ingenting tyst i stället för att haverera vyn.
  if (!data) return null;

  const overBudgetCount = data.category_rows.filter((r) => r.pct > 100).length;

  return (
    <>
      {data.inactivity_nudge && (
        <div className="bg-sky-50 border-l-4 border-sky-400 rounded p-4 flex items-start gap-3">
          <div className="text-2xl">👋</div>
          <div className="flex-1">
            <div className="font-semibold text-sky-900">
              Välkommen tillbaka!
            </div>
            <p className="text-sm text-sky-800">
              Det var {data.inactivity_nudge.days_away} dagar sedan du gjorde
              ett steg. Klicka på "Din kursplan" så fortsätter vi där du var.
            </p>
          </div>
          <Link
            to="/modules"
            className="text-sm bg-sky-600 hover:bg-sky-700 text-white rounded px-3 py-1.5 font-medium"
          >
            Till kursplanen
          </Link>
        </div>
      )}

      <div>
        <h1 className="serif text-2xl leading-tight">
          Hej {data.display_name.split(" ")[0]}!
        </h1>
        <p className="text-sm text-slate-600">
          Du är {data.profession.toLowerCase()} — {data.personality} typ.
        </p>
      </div>

      {data.assignments_total > 0 && data.assignments_done === 0 && (
        <InfoBanner title="Kom igång">
          Du har {data.assignments_total} uppdrag att jobba med. Kolla
          längst ner på sidan — där ser du allt du behöver göra.
        </InfoBanner>
      )}

      {/* Budget denna månad */}
      <section className="bg-white border-[1.5px] border-rule p-4 space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="font-semibold text-lg">Budget denna månad</h2>
          {overBudgetCount > 0 && (
            <span className="text-xs text-rose-600 flex items-center gap-1">
              <AlertTriangle className="w-4 h-4" />
              {overBudgetCount} överskridna
            </span>
          )}
        </div>
        {data.category_rows.length === 0 ? (
          <p className="text-sm text-slate-500">
            Ingen budget satt för denna månad.
          </p>
        ) : (
          <ul className="space-y-2">
            {data.category_rows.map((r) => (
              <li key={r.category} className="text-sm">
                <div className="flex items-center justify-between mb-0.5">
                  <span>{r.category}</span>
                  <span
                    className={
                      r.pct > 100
                        ? "text-rose-600 font-medium"
                        : r.pct > 80
                        ? "text-amber-600"
                        : "text-slate-600"
                    }
                  >
                    {formatKr(r.spent)} / {formatKr(r.budget)} ({r.pct}%)
                  </span>
                </div>
                <div className="h-2 bg-slate-100 rounded">
                  <div
                    className={`h-full rounded ${
                      r.pct > 100
                        ? "bg-rose-500"
                        : r.pct > 80
                        ? "bg-amber-500"
                        : "bg-emerald-500"
                    }`}
                    style={{ width: `${Math.min(r.pct, 100)}%` }}
                  />
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>

      {/* Oväntade utgifter */}
      {data.recent_overshoots.length > 0 && (
        <section className="bg-white border-[1.5px] border-rule p-4 space-y-3">
          <h2 className="font-semibold text-lg flex items-center gap-2">
            <Flame className="w-5 h-5 text-amber-500" />
            Oväntade utgifter denna månad
          </h2>
          <p className="text-sm text-slate-600">
            Livet händer! Så här har det sett ut:
          </p>
          <ul className="divide-y">
            {data.recent_overshoots.map((o, i) => (
              <li key={i} className="py-2 flex items-center justify-between text-sm">
                <span>
                  <span className="text-slate-500 text-xs mr-2">{o.date}</span>
                  {o.description}
                </span>
                <span className="font-semibold text-rose-600">
                  -{formatKr(o.amount)}
                </span>
              </li>
            ))}
          </ul>
        </section>
      )}

      {/* Uppdrag */}
      <section className="bg-white border-[1.5px] border-rule p-4 space-y-3">
        <h2 className="font-semibold text-lg flex items-center gap-2">
          <BookOpenCheck className="w-5 h-5 text-brand-600" />
          Uppdrag ({data.assignments_done}/{data.assignments_total} klara)
        </h2>
        <AssignmentList />
      </section>

      {/* Prestationer + streak */}
      {achievements && (achievements.earned.length > 0 || achievements.streak.current > 0) && (
        <section className="bg-gradient-to-br from-amber-50 to-rose-50 border border-amber-200 rounded-xl p-4">
          <div className="flex items-center justify-between gap-3 flex-wrap">
            <div className="flex items-center gap-4">
              <div>
                <div className="text-xs text-slate-600">Aktuell serie</div>
                <div className="text-2xl font-bold text-slate-900 flex items-center gap-1">
                  🔥 {achievements.streak.current}{" "}
                  <span className="text-sm font-normal text-slate-600">
                    {achievements.streak.current === 1 ? "dag" : "dagar"}
                  </span>
                </div>
              </div>
              <div className="flex items-center gap-1 flex-wrap">
                {achievements.earned.slice(0, 5).map((a) => (
                  <span
                    key={a.key}
                    title={a.title}
                    className="text-2xl bg-white border border-amber-200 rounded-full w-10 h-10 flex items-center justify-center shadow-sm"
                  >
                    {a.emoji}
                  </span>
                ))}
              </div>
            </div>
            <Link
              to="/achievements"
              className="text-sm text-brand-700 hover:text-brand-800 font-medium"
            >
              Se alla prestationer →
            </Link>
          </div>
        </section>
      )}

      {/* Mastery */}
      {mastery.length > 0 && (
        <section className="bg-white border-[1.5px] border-rule p-4 space-y-3">
          <div className="flex items-center justify-between">
            <h2 className="font-semibold text-lg">Dina färdigheter</h2>
            <button
              onClick={downloadPortfolio}
              className="text-sm btn-dark rounded-md px-3 py-1.5 flex items-center gap-1"
              title="Ladda ner din portfolio som PDF"
            >
              <Download className="w-4 h-4" /> Portfolio PDF
            </button>
          </div>
          <p className="text-sm text-slate-600">
            Baserat på dina svar i modulerna. Ju fler bevis, desto
            säkrare bedömning.
          </p>
          <MasteryChart data={mastery} />
        </section>
      )}
    </>
  );
}
