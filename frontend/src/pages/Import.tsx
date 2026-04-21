import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api, uploadFile } from "@/api/client";
import { Card } from "@/components/Card";
import { ACCOUNT_TYPES, accountTypeLabel, isPayer } from "@/lib/accountTypes";
import type { Account } from "@/types/models";

async function patchAccount(id: number, payload: Partial<Account>): Promise<Account> {
  return api<Account>(`/accounts/${id}`, { method: "PATCH", body: JSON.stringify(payload) });
}

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

  const linkPayerMut = useMutation({
    mutationFn: (p: { account_id: number; pays_credit_account_id: number | null }) =>
      patchAccount(p.account_id, { pays_credit_account_id: p.pays_credit_account_id }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["accounts"] }),
  });

  const accounts = accountsQ.data ?? [];
  const creditAccounts = accounts.filter((a) => a.type === "credit");
  const payerAccounts = accounts.filter((a) => isPayer(a.type));

  return (
    <div className="p-6 space-y-5 max-w-3xl">
      <h1 className="text-2xl font-semibold">Importera CSV</h1>

      {creditAccounts.length > 0 && payerAccounts.length > 0 && (
        <Card title="Kreditkorts-koppling">
          <div className="text-sm text-slate-600 mb-3">
            Välj vilket konto som betalar fakturan för varje kreditkort. Oftast
            det gemensamma kontot. Då markeras autogiro-dragningen som
            <em> Överföring</em> och räknas inte som en utgift (detaljerna
            finns ju redan i kortets transaktioner).
          </div>
          <div className="space-y-2">
            {creditAccounts.map((cc) => (
              <div key={cc.id} className="flex items-center gap-3 text-sm">
                <div className="w-48 font-medium">{cc.name}</div>
                <span className="text-slate-400">betalas från</span>
                <select
                  value={cc.pays_credit_account_id ?? ""}
                  onChange={(e) =>
                    linkPayerMut.mutate({
                      account_id: cc.id,
                      pays_credit_account_id: e.target.value ? Number(e.target.value) : null,
                    })
                  }
                  className="border rounded px-2 py-1"
                >
                  <option value="">—</option>
                  {payerAccounts.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.name} ({accountTypeLabel(c.type)})
                    </option>
                  ))}
                </select>
              </div>
            ))}
          </div>
        </Card>
      )}

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
            {ACCOUNT_TYPES.map((t) => (
              <option key={t.value} value={t.value}>{t.label}</option>
            ))}
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
                {a.name} — {accountTypeLabel(a.type)} ({a.bank})
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
            accept=".csv,text/csv,.xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
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
