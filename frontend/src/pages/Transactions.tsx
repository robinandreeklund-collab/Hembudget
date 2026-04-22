import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { ArrowLeftRight } from "lucide-react";
import { api, formatSEK } from "@/api/client";
import { Card } from "@/components/Card";
import type { Account, Category, Transaction } from "@/types/models";

const NEW_CATEGORY_SENTINEL = "__new__";
const ALL_ACCOUNTS = "__all__";

export default function Transactions() {
  const qc = useQueryClient();
  const [uncategorizedOnly, setUncategorizedOnly] = useState(false);
  const [hideTransfers, setHideTransfers] = useState(true);
  const [newCatFor, setNewCatFor] = useState<number | null>(null);
  const [accountFilter, setAccountFilter] = useState<string>(
    () => localStorage.getItem("tx_account_filter") || ALL_ACCOUNTS,
  );

  const accountsQ = useQuery({
    queryKey: ["accounts"],
    queryFn: () => api<Account[]>("/accounts"),
  });

  const txsQ = useQuery({
    queryKey: ["transactions", { uncategorizedOnly, accountFilter }],
    queryFn: () => {
      const params = new URLSearchParams({ limit: "500" });
      if (uncategorizedOnly) params.set("uncategorized", "true");
      if (accountFilter !== ALL_ACCOUNTS) {
        params.set("account_id", accountFilter);
      }
      return api<Transaction[]>(`/transactions?${params.toString()}`);
    },
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

  const createCategoryMut = useMutation({
    mutationFn: (p: { name: string; parent_id: number | null; txId: number }) =>
      api<Category>("/categories", {
        method: "POST",
        body: JSON.stringify({ name: p.name, parent_id: p.parent_id }),
      }),
    onSuccess: async (newCat, variables) => {
      await qc.invalidateQueries({ queryKey: ["categories"] });
      updateMut.mutate({ id: variables.txId, category_id: newCat.id });
      setNewCatFor(null);
    },
  });

  const cats = catsQ.data ?? [];

  return (
    <div className="p-3 md:p-6 space-y-4">
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-2">
        <h1 className="text-xl md:text-2xl font-semibold">Transaktioner</h1>
        <div className="flex flex-wrap items-center gap-3 md:gap-4 text-sm">
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

      {/* Konto-flikar — ett klick för att filtrera */}
      <div className="flex flex-wrap gap-2 items-center">
        <button
          onClick={() => {
            setAccountFilter(ALL_ACCOUNTS);
            localStorage.setItem("tx_account_filter", ALL_ACCOUNTS);
          }}
          className={`px-3 py-1.5 rounded-full text-sm font-medium border transition ${
            accountFilter === ALL_ACCOUNTS
              ? "bg-brand-600 text-white border-brand-600"
              : "bg-white text-slate-700 border-slate-300 hover:border-brand-400"
          }`}
        >
          Alla konton
        </button>
        {(accountsQ.data ?? []).map((a) => {
          const active = accountFilter === String(a.id);
          return (
            <button
              key={a.id}
              onClick={() => {
                setAccountFilter(String(a.id));
                localStorage.setItem("tx_account_filter", String(a.id));
              }}
              className={`px-3 py-1.5 rounded-full text-sm font-medium border transition ${
                active
                  ? "bg-brand-600 text-white border-brand-600"
                  : "bg-white text-slate-700 border-slate-300 hover:border-brand-400"
              }`}
              title={`${a.bank} · ${a.type}`}
            >
              {a.name}
              <span className={`ml-1.5 text-xs ${active ? "text-brand-100" : "text-slate-600"}`}>
                {a.bank}
              </span>
            </button>
          );
        })}
        {(accountsQ.data ?? []).length === 0 && (
          <span className="text-xs text-slate-600">
            (Inga konton hittades — gå till Importera för att sätta upp dem)
          </span>
        )}
      </div>

      <Card>
        {txsQ.isLoading ? (
          <div className="text-sm text-slate-700">Laddar…</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs uppercase text-slate-700 border-b">
                  <th className="py-2 pr-4">Datum</th>
                  {accountFilter === ALL_ACCOUNTS && (
                    <th className="py-2 pr-4">Konto</th>
                  )}
                  <th className="py-2 pr-4">Beskrivning</th>
                  <th className="py-2 pr-4 text-right">Belopp</th>
                  <th className="py-2 pr-4">Kategori</th>
                </tr>
              </thead>
              <tbody>
                {(txsQ.data ?? [])
                  .filter((tx) => (hideTransfers ? !tx.is_transfer : true))
                  .map((tx) => {
                    const acc = (accountsQ.data ?? []).find((a) => a.id === tx.account_id);
                    return (
                  <tr
                    key={tx.id}
                    className={`border-b last:border-0 hover:bg-slate-50 ${
                      tx.is_transfer ? "opacity-60" : ""
                    }`}
                  >
                    <td className="py-2 pr-4 text-slate-700">{tx.date}</td>
                    {accountFilter === ALL_ACCOUNTS && (
                      <td className="py-2 pr-4 text-slate-600 text-xs">
                        {acc ? acc.name : `#${tx.account_id}`}
                      </td>
                    )}
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
                        <div className="text-xs text-slate-600">{tx.raw_description}</div>
                      )}
                    </td>
                    <td
                      className={`py-2 pr-4 text-right font-medium ${
                        tx.is_transfer
                          ? "text-slate-600"
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
                          className="text-xs text-slate-700 hover:text-slate-700 underline"
                        >
                          Markera som utgift
                        </button>
                      ) : newCatFor === tx.id ? (
                        <NewCategoryInline
                          cats={cats}
                          busy={createCategoryMut.isPending}
                          error={createCategoryMut.error as Error | null}
                          onCancel={() => setNewCatFor(null)}
                          onSave={(name, parent_id) =>
                            createCategoryMut.mutate({ name, parent_id, txId: tx.id })
                          }
                        />
                      ) : (
                        <div className="flex items-center gap-2">
                          <select
                            value={tx.category_id ?? ""}
                            onChange={(e) => {
                              if (e.target.value === NEW_CATEGORY_SENTINEL) {
                                setNewCatFor(tx.id);
                                return;
                              }
                              updateMut.mutate({ id: tx.id, category_id: Number(e.target.value) });
                            }}
                            className="border rounded px-2 py-1 text-sm bg-white"
                          >
                            <option value="">—</option>
                            {cats.map((c) => (
                              <option key={c.id} value={c.id}>
                                {c.name}
                              </option>
                            ))}
                            <option value={NEW_CATEGORY_SENTINEL}>➕ Ny kategori…</option>
                          </select>
                          {!tx.user_verified && tx.category_id && (
                            <span className="text-xs text-slate-600">
                              AI ({Math.round((tx.ai_confidence ?? 0) * 100)} %)
                            </span>
                          )}
                          <button
                            onClick={() => toggleTransferMut.mutate({ id: tx.id, is_transfer: true })}
                            className="text-xs text-slate-600 hover:text-blue-600"
                            title="Markera som överföring"
                          >
                            ↔
                          </button>
                        </div>
                      )}
                    </td>
                  </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
        <div className="mt-3 text-xs text-slate-700">
          Tips: när du byter kategori skapas en regel automatiskt så att framtida liknande
          transaktioner kategoriseras rätt. Välj <strong>➕ Ny kategori…</strong> i dropdownen
          för att skapa en egen kategori på flugan — t.ex. "Online-spel" eller "Barn-prenumerationer".
        </div>
      </Card>
      <div className="text-xs text-slate-700">{(txsQ.data ?? []).length} rader. Kategorier tillgängliga: {cats.length}.</div>
    </div>
  );
}

function NewCategoryInline({
  cats,
  busy,
  error,
  onSave,
  onCancel,
}: {
  cats: Category[];
  busy: boolean;
  error: Error | null;
  onSave: (name: string, parent_id: number | null) => void;
  onCancel: () => void;
}) {
  const [name, setName] = useState("");
  const [parentId, setParentId] = useState<number | "">("");
  // Föräldrar = bara top-level (utan parent)
  const topLevel = cats.filter((c) => c.parent_id == null);

  return (
    <div className="flex flex-col gap-1 bg-slate-50 border border-slate-200 rounded p-2">
      <div className="flex items-center gap-2">
        <input
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="Kategorinamn (t.ex. Online-spel)"
          autoFocus
          className="border rounded px-2 py-1 text-sm flex-1"
        />
        <select
          value={parentId}
          onChange={(e) => setParentId(e.target.value === "" ? "" : Number(e.target.value))}
          className="border rounded px-2 py-1 text-sm bg-white"
        >
          <option value="">Toppkategori</option>
          {topLevel.map((c) => (
            <option key={c.id} value={c.id}>
              Under {c.name}
            </option>
          ))}
        </select>
        <button
          disabled={!name.trim() || busy}
          onClick={() => onSave(name.trim(), parentId === "" ? null : parentId)}
          className="bg-brand-600 text-white text-xs px-3 py-1 rounded disabled:opacity-40"
        >
          {busy ? "Skapar…" : "Skapa"}
        </button>
        <button
          onClick={onCancel}
          className="text-slate-600 hover:text-slate-700 text-xs px-1"
        >
          Avbryt
        </button>
      </div>
      {error && <div className="text-xs text-rose-600">{error.message}</div>}
    </div>
  );
}
