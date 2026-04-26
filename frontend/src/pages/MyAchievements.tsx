import { useEffect, useState } from "react";
import { Flame } from "lucide-react";
import { api } from "@/api/client";

type AchievementItem = {
  key: string;
  title: string;
  emoji: string;
  description: string;
  earned?: boolean;
  earned_at?: string;
};

type AchievementsResp = {
  earned: AchievementItem[];
  available: AchievementItem[];
  streak: { current: number; longest: number };
};

export default function MyAchievements() {
  const [data, setData] = useState<AchievementsResp | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    api<AchievementsResp>("/student/achievements")
      .then(setData)
      .catch((e) => setErr(e instanceof Error ? e.message : String(e)));
  }, []);

  if (err) {
    return (
      <div className="p-6 text-rose-600 bg-rose-50 border border-rose-200 rounded">
        {err}
      </div>
    );
  }
  if (!data) return <div className="p-6 text-slate-500">Laddar…</div>;

  const earnedKeys = new Set(data.earned.map((e) => e.key));

  return (
    <div className="max-w-3xl mx-auto p-6 space-y-6">
      <h1 className="serif text-3xl leading-tight">Mina prestationer</h1>

      <div className="bg-gradient-to-br from-amber-50 to-rose-50 border border-amber-200 rounded-xl p-5 flex items-center gap-4">
        <Flame className="w-10 h-10 text-amber-500" />
        <div>
          <div className="text-sm text-slate-600">Aktuell serie</div>
          <div className="text-2xl font-bold text-slate-900">
            {data.streak.current}{" "}
            {data.streak.current === 1 ? "dag" : "dagar"}
          </div>
          <div className="text-xs text-slate-500">
            Längsta: {data.streak.longest} dagar i rad
          </div>
        </div>
      </div>

      <div>
        <h2 className="font-semibold text-slate-800 mb-3">
          Tjänade ({data.earned.length} / {data.available.length})
        </h2>
        <ul className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          {data.available.map((a) => {
            const earned = earnedKeys.has(a.key);
            return (
              <li
                key={a.key}
                className={`rounded-xl p-4 border flex items-center gap-3 ${
                  earned
                    ? "bg-white border-amber-200"
                    : "bg-slate-50 border-slate-200 opacity-60"
                }`}
              >
                <div className="text-3xl">{earned ? a.emoji : "🔒"}</div>
                <div>
                  <div className="font-semibold text-slate-900">{a.title}</div>
                  <div className="text-xs text-slate-600">{a.description}</div>
                </div>
              </li>
            );
          })}
        </ul>
      </div>
    </div>
  );
}
