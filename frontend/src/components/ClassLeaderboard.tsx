/**
 * ClassLeaderboard — anonymiserad rangordning för eleven.
 *
 * Visar bara om läraren slagit på class_list_enabled. Eleven ser sin
 * egen plats + topp + klassgenomsnitt. Andra elever är 'Anonym A/B/C…'.
 *
 * Pedagogisk princip: jämförelse kan motivera utan att skuldbelägga.
 * Aldrig namn på andra (förrän opt-in i V2).
 */
import { useQuery } from "@tanstack/react-query";
import { Trophy, Users } from "lucide-react";
import { api } from "@/api/client";
import { Card } from "@/components/Card";

interface Entry {
  rank: number;
  is_me: boolean;
  display_label: string;
  total_score: number;
  social: number;
  events_accepted: number;
}

interface LeaderboardResp {
  enabled: boolean;
  entries: Entry[];
  aggregate: {
    class_avg: number;
    my_rank: number | null;
    my_total: number | null;
    diff_from_avg: number;
    total_students: number;
  } | null;
}

export function ClassLeaderboard() {
  const q = useQuery({
    queryKey: ["class-leaderboard"],
    queryFn: () => api<LeaderboardResp>("/class/leaderboard"),
    refetchInterval: 5 * 60_000,  // 5 min — räcker
  });

  const data = q.data;
  if (!data || !data.enabled) {
    return null;
  }

  const agg = data.aggregate;

  // Visa topp 5 + jag själv + 1 ovan + 1 under (om jag inte redan är topp)
  const myIdx = data.entries.findIndex((e) => e.is_me);
  const top5 = data.entries.slice(0, 5);
  const myContext: Entry[] = [];
  if (myIdx >= 5) {
    if (myIdx > 0) myContext.push(data.entries[myIdx - 1]);
    myContext.push(data.entries[myIdx]);
    if (myIdx + 1 < data.entries.length) myContext.push(data.entries[myIdx + 1]);
  }

  return (
    <Card title="Klassens Wellbeing (anonym rangordning)">
      <div className="text-xs text-slate-600 mb-2 italic">
        Bara du själv visas under namn. Andra elever är anonymiserade.
      </div>

      {agg && (
        <div className="grid grid-cols-3 gap-2 mb-3 text-sm">
          <div className="bg-slate-50 border rounded p-2 text-center">
            <div className="text-xs text-slate-600">Klassens snitt</div>
            <div className="font-semibold">{agg.class_avg}</div>
          </div>
          <div className="bg-slate-50 border rounded p-2 text-center">
            <div className="text-xs text-slate-600">Din placering</div>
            <div className="font-semibold">
              {agg.my_rank ?? "—"} / {agg.total_students}
            </div>
          </div>
          <div
            className={`border rounded p-2 text-center ${
              agg.diff_from_avg >= 0
                ? "bg-emerald-50"
                : "bg-amber-50"
            }`}
          >
            <div className="text-xs text-slate-600">Mot snitt</div>
            <div className="font-semibold">
              {agg.diff_from_avg >= 0 ? "+" : ""}
              {agg.diff_from_avg}
            </div>
          </div>
        </div>
      )}

      <div className="space-y-1">
        <div className="flex items-center gap-1 text-xs font-medium text-slate-600">
          <Trophy className="w-3 h-3 text-amber-500" />
          Topp 5
        </div>
        {top5.map((e) => (
          <Row key={e.rank} entry={e} />
        ))}

        {myContext.length > 0 && (
          <>
            <div className="text-xs text-slate-400 text-center py-1">…</div>
            <div className="flex items-center gap-1 text-xs font-medium text-slate-600">
              <Users className="w-3 h-3" />
              Din position
            </div>
            {myContext.map((e) => (
              <Row key={e.rank} entry={e} />
            ))}
          </>
        )}
      </div>
    </Card>
  );
}

function Row({ entry }: { entry: Entry }) {
  return (
    <div
      className={`flex items-center gap-2 p-1.5 rounded ${
        entry.is_me
          ? "bg-emerald-50 border border-emerald-200"
          : "bg-slate-50/50"
      }`}
    >
      <span
        className={`text-xs font-mono w-7 text-center ${
          entry.rank === 1 ? "text-amber-600 font-bold" :
          entry.rank === 2 ? "text-slate-500 font-bold" :
          entry.rank === 3 ? "text-orange-700 font-bold" :
          "text-slate-500"
        }`}
      >
        #{entry.rank}
      </span>
      <span className={`flex-1 text-sm ${entry.is_me ? "font-semibold" : ""}`}>
        {entry.display_label}
      </span>
      <span className="text-sm font-mono">{entry.total_score}</span>
      <span className="text-xs text-slate-500" title={`Social: ${entry.social}`}>
        S: {entry.social}
      </span>
    </div>
  );
}
