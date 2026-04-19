import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api, uploadFile } from "@/api/client";
import { Card } from "@/components/Card";
import type { Account } from "@/types/models";

const BANKS = [
  { value: "", label: "Auto-detektera" },
  { value: "amex", label: "American Express (Eurobonus)" },
  { value: "nordea", label: "Nordea" },
  { value: "seb_kort", label: "SEB Kort (Mastercard)" },
];

export default function ImportPage() {
  const qc = useQueryClient();
  const accountsQ = useQuery({ queryKey: ["accounts"], queryFn: () => api<Account[]>("/accounts") });
  const [file, setFile] = useState<File | null>(null);
  const [accountId, setAccountId] = useState<number | null>(null);
  const [bank, setBank] = useState<string>("");
  const [result, setResult] = useState<unknown>(null);
  const [newAcc, setNewAcc] = useState({ name: "", bank: "nordea", type: "checking" });

  const createAccMut = useMutation({
    mutationFn: () =>
      api<Account>("/accounts", { method: "POST", body: JSON.stringify(newAcc) }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["accounts"] }),
  });

  const importMut = useMutation({
    mutationFn: async () => {
      if (!file || !accountId) throw new Error("Välj konto och fil");
      const form = new FormData();
      form.append("file", file);
      form.append("account_id", String(accountId));
      if (bank) form.append("bank", bank);
      return uploadFile("/import/csv", form);
    },
    onSuccess: (data) => {
      setResult(data);
      qc.invalidateQueries({ queryKey: ["transactions"] });
    },
    onError: (err: Error) => setResult({ error: err.message }),
  });

  return (
    <div className="p-6 space-y-5 max-w-3xl">
      <h1 className="text-2xl font-semibold">Importera CSV</h1>

      <Card title="Nytt konto">
        <div className="grid grid-cols-4 gap-2">
          <input
            className="border rounded px-2 py-1.5 col-span-2"
            placeholder="Namn (t.ex. Privat lönekonto)"
            value={newAcc.name}
            onChange={(e) => setNewAcc({ ...newAcc, name: e.target.value })}
          />
          <select
            className="border rounded px-2 py-1.5"
            value={newAcc.bank}
            onChange={(e) => setNewAcc({ ...newAcc, bank: e.target.value })}
          >
            <option value="nordea">Nordea</option>
            <option value="amex">Amex</option>
            <option value="seb_kort">SEB Kort</option>
          </select>
          <select
            className="border rounded px-2 py-1.5"
            value={newAcc.type}
            onChange={(e) => setNewAcc({ ...newAcc, type: e.target.value })}
          >
            <option value="checking">Lönekonto</option>
            <option value="credit">Kreditkort</option>
            <option value="savings">Sparkonto</option>
            <option value="isk">ISK</option>
          </select>
        </div>
        <button
          className="mt-3 bg-slate-800 text-white px-3 py-1.5 rounded"
          onClick={() => createAccMut.mutate()}
          disabled={!newAcc.name}
        >
          Lägg till konto
        </button>
      </Card>

      <Card title="Ladda upp CSV">
        <div className="space-y-3">
          <select
            className="border rounded px-2 py-1.5 w-full"
            value={accountId ?? ""}
            onChange={(e) => setAccountId(Number(e.target.value) || null)}
          >
            <option value="">Välj konto…</option>
            {(accountsQ.data ?? []).map((a) => (
              <option key={a.id} value={a.id}>
                {a.name} ({a.bank})
              </option>
            ))}
          </select>
          <select
            className="border rounded px-2 py-1.5 w-full"
            value={bank}
            onChange={(e) => setBank(e.target.value)}
          >
            {BANKS.map((b) => (
              <option key={b.value} value={b.value}>{b.label}</option>
            ))}
          </select>
          <input
            type="file"
            accept=".csv,text/csv"
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
          />
          <button
            className="bg-brand-600 text-white px-4 py-2 rounded disabled:opacity-50"
            disabled={!file || !accountId || importMut.isPending}
            onClick={() => importMut.mutate()}
          >
            {importMut.isPending ? "Importerar…" : "Importera"}
          </button>
          {result !== null && (
            <pre className="bg-slate-900 text-slate-100 text-xs p-3 rounded overflow-x-auto">
              {JSON.stringify(result, null, 2)}
            </pre>
          )}
        </div>
      </Card>
    </div>
  );
}
