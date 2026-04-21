import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { ArrowLeftRight } from "lucide-react";
import { api, formatSEK } from "@/api/client";
import { Card } from "@/components/Card";
import type { Category, Transaction } from "@/types/models";

export default function Transactions() {
  const qc = useQueryClient();
  const [uncategorizedOnly, setUncategorizedOnly] = useState(false);
  const [hideTransfers, setHideTransfers] = useState(true);

  const txsQ = useQuery({
    queryKey: ["transactions", { uncategorizedOnly }],
    queryFn: () =>
      api<Transaction[]>(
        `/transactions?limit=500${uncategorizedOnly ? "&uncategorized=true" : ""}`,
      ),
  });
  const catsQ = useQuery({ queryKey: ["categories"], queryFn: () => api<Category[]>("/categories") });

  const updateMut = useMutation({
    mutationFn: (p: { id: number; category_id: number }) =>
      api<Transaction>(`/transactions/${p.id}`, {
        method: "PATCH",
        body: JSON.stringify({ category_id: p.category_id, create_rule: true }),
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["transactions"] }),
  });

  const toggleTransferMut = useMutation({
    mutationFn: (p: { id: number; is_transfer: boolean }) =>
      api<Transaction>(`/transactions/${p.id}`, {
        method: "PATCH",
        body: JSON.stringify({ is_transfer: p.is_transfer }),
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["transactions"] });
      qc.invalidateQueries({ queryKey: ["budget"] });
    },
  });

  const cats = catsQ.data ?? [];

  return (
    <div className="p-6 space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Transaktioner</h1>
        <div className="flex items-center gap-4 text-sm">
          <label className="flex items-center gap-2">
            <input
              type="checkbox"
              checked={uncategorizedOnly}
              onChange={(e) => setUncategorizedOnly(e.target.checked)}
            />
            Visa bara okategoriserade
          </label>
          <label className="flex items-center gap-2">
            <input
              type="checkbox"
              checked={hideTransfers}
              onChange={(e) => setHideTransfers(e.target.checked)}
            />
            Dölj överföringar
          </label>
        </div>
      </div>

      <Card>
        {txsQ.isLoading ? (
          <div className="text-sm text-slate-500">Laddar…</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs uppercase text-slate-500 border-b">
                  <th className="py-2 pr-4">Datum</th>
                  <th className="py-2 pr-4">Beskrivning</th>
                  <th className="py-2 pr-4 text-right">Belopp</th>
                  <th className="py-2 pr-4">Kategori</th>
                </tr>
              </thead>
              <tbody>
                {(txsQ.data ?? [])
                  .filter((tx) => (hideTransfers ? !tx.is_transfer : true))
                  .map((tx) => (
                  <tr
                    key={tx.id}
                    className={`border-b last:border-0 hover:bg-slate-50 ${
                      tx.is_transfer ? "opacity-60" : ""
                    }`}
                  >
                    <td className="py-2 pr-4 text-slate-500">{tx.date}</td>
                    <td className="py-2 pr-4">
                      <div className="font-medium flex items-center gap-2">
                        {tx.normalized_merchant ?? tx.raw_description}
                        {tx.is_transfer && (
                          <span className="inline-flex items-center gap-1 text-xs bg-blue-100 text-blue-700 px-1.5 py-0.5 rounded">
                            <ArrowLeftRight className="w-3 h-3" /> Överföring
                          </span>
                        )}
                      </div>
                      {tx.normalized_merchant && (
                        <div className="text-xs text-slate-400">{tx.raw_description}</div>
                      )}
                    </td>
                    <td
                      className={`py-2 pr-4 text-right font-medium ${
                        tx.is_transfer
                          ? "text-slate-400"
                          : tx.amount < 0
                          ? "text-rose-600"
                          : "text-emerald-600"
                      }`}
                    >
                      {formatSEK(tx.amount)}
                    </td>
                    <td className="py-2 pr-4">
                      {tx.is_transfer ? (
                        <button
                          onClick={() => toggleTransferMut.mutate({ id: tx.id, is_transfer: false })}
                          className="text-xs text-slate-500 hover:text-slate-700 underline"
                        >
                          Markera som utgift
                        </button>
                      ) : (
                        <div className="flex items-center gap-2">
                          <select
                            value={tx.category_id ?? ""}
                            onChange={(e) =>
                              updateMut.mutate({ id: tx.id, category_id: Number(e.target.value) })
                            }
                            className="border rounded px-2 py-1 text-sm bg-white"
                          >
                            <option value="">—</option>
                            {cats.map((c) => (
                              <option key={c.id} value={c.id}>
                                {c.name}
                              </option>
                            ))}
                          </select>
                          {!tx.user_verified && tx.category_id && (
                            <span className="text-xs text-slate-400">
                              AI ({Math.round((tx.ai_confidence ?? 0) * 100)} %)
                            </span>
                          )}
                          <button
                            onClick={() => toggleTransferMut.mutate({ id: tx.id, is_transfer: true })}
                            className="text-xs text-slate-400 hover:text-blue-600"
                            title="Markera som överföring"
                          >
                            ↔
                          </button>
                        </div>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <div className="mt-3 text-xs text-slate-500">
          Tips: när du byter kategori skapas en regel automatiskt så att framtida liknande
          transaktioner kategoriseras rätt.
        </div>
      </Card>
      <div className="text-xs text-slate-500">{(txsQ.data ?? []).length} rader. Kategorier tillgängliga: {cats.length}.</div>
    </div>
  );
}
