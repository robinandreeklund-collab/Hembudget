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
  const [newAcc, setNewAcc] = useState<{
    name: string; bank: string; type: string; account_number: string;
  }>({ name: "", bank: "nordea", type: "checking", account_number: "" });

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

  const deleteAccMut = useMutation({
    mutationFn: (p: { id: number; force: boolean }) =>
      api<{ deleted: number; deleted_transactions: number }>(
        `/accounts/${p.id}?force=${p.force}`,
        { method: "DELETE" },
      ),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["accounts"] });
      qc.invalidateQueries({ queryKey: ["balances"] });
      qc.invalidateQueries({ queryKey: ["transactions"] });
    },
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
    <div className="p-3 md:p-6 space-y-4 md:space-y-5 max-w-3xl">
      <h1 className="text-2xl font-semibold">Importera CSV</h1>

      {accounts.length > 0 && (
        <Card title="Konto-inställningar">
          <div className="text-sm text-slate-500 mb-3">
            Kontonummer används för auto-koppling av fakturor (vision AI). Ingående
            saldo + startdatum gör att systemet kan räkna ut nuvarande saldo.
            Lämna saldo-fälten tomma om du inte har startat spåra kontot än.
          </div>
          <div className="space-y-2">
            {accounts.map((a) => (
              <AccountSetupRow
                key={a.id}
                account={a}
                onSave={(updates) =>
                  patchAccount(a.id, updates).then(() =>
                    qc.invalidateQueries({ queryKey: ["accounts"] }),
                  )
                }
                onDelete={(force) =>
                  deleteAccMut.mutate({ id: a.id, force })
                }
              />
            ))}
          </div>
          {deleteAccMut.isError && (
            <div className="mt-2 text-sm text-rose-600">
              {(deleteAccMut.error as Error).message}
            </div>
          )}
          {deleteAccMut.data && (
            <div className="mt-2 text-sm text-emerald-700">
              Raderade konto och {deleteAccMut.data.deleted_transactions} transaktioner.
            </div>
          )}
        </Card>
      )}

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
        <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
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
          <input
            className="border rounded px-2 py-1.5 col-span-4"
            placeholder="Kontonummer (t.ex. 1709 20 72840) — används för att auto-koppla fakturor"
            value={newAcc.account_number}
            onChange={(e) => setNewAcc({ ...newAcc, account_number: e.target.value })}
          />
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

function AccountSetupRow({
  account,
  onSave,
  onDelete,
}: {
  account: Account;
  onSave: (updates: Partial<Account>) => Promise<unknown>;
  onDelete: (force: boolean) => void;
}) {
  const [num, setNum] = useState(account.account_number ?? "");
  const [ob, setOb] = useState(
    account.opening_balance != null ? String(account.opening_balance) : "",
  );
  const [obDate, setObDate] = useState(account.opening_balance_date ?? "");
  const [creditLimit, setCreditLimit] = useState(
    account.credit_limit != null ? String(account.credit_limit) : "",
  );
  const [bg, setBg] = useState(account.bankgiro ?? "");

  const isCredit = account.type === "credit";

  function saveIfChanged(
    field:
      | "account_number"
      | "opening_balance"
      | "opening_balance_date"
      | "credit_limit"
      | "bankgiro",
    value: string,
  ) {
    const current =
      field === "account_number"
        ? account.account_number ?? ""
        : field === "opening_balance"
        ? (account.opening_balance != null ? String(account.opening_balance) : "")
        : field === "opening_balance_date"
        ? account.opening_balance_date ?? ""
        : field === "credit_limit"
        ? (account.credit_limit != null ? String(account.credit_limit) : "")
        : account.bankgiro ?? "";
    if (value === current) return;
    const updates: Partial<Account> = {};
    if (field === "account_number") updates.account_number = value || null;
    else if (field === "opening_balance")
      updates.opening_balance = value ? (Number(value) as unknown as Account["opening_balance"]) : null;
    else if (field === "opening_balance_date")
      updates.opening_balance_date = value || null;
    else if (field === "credit_limit")
      updates.credit_limit = value ? (Number(value) as unknown as Account["credit_limit"]) : null;
    else updates.bankgiro = value || null;
    onSave(updates);
  }

  return (
    <div className="border rounded p-2 text-sm space-y-2">
      <div className="flex items-start gap-2">
        <div className="flex-1">
          <div className="font-medium truncate">{account.name}</div>
          <div className="text-xs text-slate-500">{account.bank} · {account.type}</div>
        </div>
        <button
          onClick={() => {
            const msg =
              "Radera kontot '" +
              account.name +
              "'?\n\nOm kontot har transaktioner raderas även alla transaktioner, splits och loan-länkar. Detta kan inte ångras.";
            if (confirm(msg)) onDelete(true);
          }}
          className="text-xs text-rose-600 hover:text-rose-800 hover:bg-rose-50 px-2 py-1 rounded"
          title="Radera kontot"
        >
          Radera
        </button>
      </div>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
        <label>
          <div className="text-xs text-slate-500">Kontonummer</div>
          <input
            value={num}
            onChange={(e) => setNum(e.target.value)}
            onBlur={() => saveIfChanged("account_number", num)}
            placeholder="1709 20 72840"
            className="border rounded px-2 py-1 w-full font-mono text-xs"
          />
        </label>
        {isCredit ? (
          <label>
            <div className="text-xs text-slate-500">Kreditgräns (kr)</div>
            <input
              type="number"
              step="1000"
              value={creditLimit}
              onChange={(e) => setCreditLimit(e.target.value)}
              onBlur={() => saveIfChanged("credit_limit", creditLimit)}
              placeholder="150000"
              className="border rounded px-2 py-1 w-full text-right"
            />
          </label>
        ) : (
          <label>
            <div className="text-xs text-slate-500">Ingående saldo</div>
            <input
              type="number"
              step="0.01"
              value={ob}
              onChange={(e) => setOb(e.target.value)}
              onBlur={() => saveIfChanged("opening_balance", ob)}
              placeholder="0"
              className="border rounded px-2 py-1 w-full text-right"
            />
          </label>
        )}
        {isCredit ? (
          <label>
            <div className="text-xs text-slate-500">Bankgiro (för autogiro-match)</div>
            <input
              value={bg}
              onChange={(e) => setBg(e.target.value)}
              onBlur={() => saveIfChanged("bankgiro", bg)}
              placeholder="5127-5477"
              className="border rounded px-2 py-1 w-full font-mono text-xs"
            />
          </label>
        ) : (
          <label>
            <div className="text-xs text-slate-500">Startdatum</div>
            <input
              type="date"
              value={obDate}
              onChange={(e) => setObDate(e.target.value)}
              onBlur={() => saveIfChanged("opening_balance_date", obDate)}
              className="border rounded px-2 py-1 w-full text-xs"
            />
          </label>
        )}
        {isCredit && (
          <label>
            <div className="text-xs text-slate-500">Skuld (negativt saldo)</div>
            <input
              type="number"
              step="0.01"
              value={ob}
              onChange={(e) => setOb(e.target.value)}
              onBlur={() => saveIfChanged("opening_balance", ob)}
              placeholder="-39683.78"
              className="border rounded px-2 py-1 w-full text-right"
            />
          </label>
        )}
      </div>
    </div>
  );
}
