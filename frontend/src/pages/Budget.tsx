import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
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

  return (
    <div className="p-6 space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Budget</h1>
        <input
          type="month"
          value={month}
          onChange={(e) => setMonth(e.target.value)}
          className="border rounded px-2 py-1"
        />
      </div>

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
