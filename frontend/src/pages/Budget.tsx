import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Sparkles } from "lucide-react";
import { api, formatSEK } from "@/api/client";
import { Card } from "@/components/Card";
import type { Category, MonthSummary } from "@/types/models";

function defaultMonth(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

export default function Budget() {
  const qc = useQueryClient();
  const [month, setMonth] = useState(defaultMonth());
  const summaryQ = useQuery({
    queryKey: ["budget", month],
    queryFn: () => api<MonthSummary>(`/budget/${month}`),
  });
  const catsQ = useQuery({ queryKey: ["categories"], queryFn: () => api<Category[]>("/categories") });

  const setMut = useMutation({
    mutationFn: (p: { category_id: number; planned_amount: number }) =>
      api("/budget/", {
        method: "POST",
        body: JSON.stringify({ month, category_id: p.category_id, planned_amount: p.planned_amount }),
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["budget", month] }),
  });

  const autoMut = useMutation({
    mutationFn: (opts: { overwrite: boolean }) =>
      api<{ updated: number; budgets: unknown[] }>(
        `/budget/auto?month=${month}&lookback_months=6&overwrite=${opts.overwrite}`,
        { method: "POST" },
      ),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["budget", month] }),
  });

  return (
    <div className="p-3 md:p-6 space-y-4 md:space-y-4">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <h1 className="text-2xl font-semibold">Budget</h1>
        <div className="flex items-center gap-2 flex-wrap">
          <button
            onClick={() => autoMut.mutate({ overwrite: false })}
            disabled={autoMut.isPending}
            className="inline-flex items-center gap-1.5 text-sm bg-brand-50 text-brand-700 border border-brand-200 rounded-lg px-3 py-1.5 hover:bg-brand-100 disabled:opacity-50"
            title="Fyll i tomma budgetrader från medianen av de senaste 6 månaderna"
          >
            <Sparkles className="w-4 h-4" />
            {autoMut.isPending ? "Räknar…" : "Auto-fyll budget"}
          </button>
          <button
            onClick={() => {
              if (confirm("Ersätter ALLA budgetrader för denna månad med historiskt snitt. Fortsätta?")) {
                autoMut.mutate({ overwrite: true });
              }
            }}
            disabled={autoMut.isPending}
            className="text-xs text-slate-500 hover:text-slate-700"
            title="Ersätt även befintliga manuella värden"
          >
            (ersätt allt)
          </button>
          <input
            type="month"
            value={month}
            onChange={(e) => setMonth(e.target.value)}
            className="border rounded px-2 py-1"
          />
        </div>
      </div>

      {autoMut.data && (
        <div className="bg-emerald-50 border border-emerald-200 rounded-lg px-3 py-2 text-sm text-emerald-800">
          Uppdaterade {autoMut.data.updated} budgetrader från historiskt
          snitt.
        </div>
      )}

      <Card title={`Budget vs utfall — ${month}`}>
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-xs uppercase text-slate-500 border-b">
              <th className="py-2 pr-4">Kategori</th>
              <th className="py-2 pr-4 text-right">Budgeterat</th>
              <th className="py-2 pr-4 text-right">Faktiskt</th>
              <th className="py-2 pr-4 text-right">Diff</th>
            </tr>
          </thead>
          <tbody>
            {(summaryQ.data?.lines ?? []).map((l) => (
              <tr key={l.category_id} className="border-b last:border-0">
                <td className="py-2 pr-4">{l.category}</td>
                <td className="py-2 pr-4 text-right">
                  <input
                    type="number"
                    defaultValue={l.planned}
                    onBlur={(e) => {
                      const v = Number(e.target.value);
                      if (v !== l.planned) setMut.mutate({ category_id: l.category_id, planned_amount: v });
                    }}
                    className="w-28 border rounded px-2 py-0.5 text-right"
                  />
                </td>
                <td className="py-2 pr-4 text-right">{formatSEK(l.actual)}</td>
                <td
                  className={`py-2 pr-4 text-right ${
                    l.diff < 0 ? "text-rose-600" : "text-emerald-600"
                  }`}
                >
                  {formatSEK(l.diff)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
      <div className="text-xs text-slate-500">{catsQ.data?.length ?? 0} kategorier totalt.</div>
    </div>
  );
}
