import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, ArrowRight, X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { api, formatSEK } from "@/api/client";
import { CreditModal } from "@/components/CreditModal";
import type { Account } from "@/types/models";

interface BalanceRow {
  id: number;
  current_balance: number;
}

interface CreateResponse {
  ok: boolean;
  idempotent?: boolean;
  source_tx_id: number;
  destination_tx_id: number;
  amount: number;
  from_balance_after: number;
  to_balance_after: number;
  date: string;
}

interface Props {
  open: boolean;
  onClose: () => void;
  /** Förvald avsändare. */
  defaultFromId?: number;
}

/**
 * Modal för proaktiv överföring mellan elevens egna konton.
 *
 * Skickar `POST /transfers/create` som skapar två länkade Transactions.
 * Saldot räknas live på servern; vi visar bara en optimistisk preview
 * baserad på senaste balansfetch.
 */
export function NewTransferModal({ open, onClose, defaultFromId }: Props) {
  const qc = useQueryClient();
  const [fromId, setFromId] = useState<number | null>(null);
  const [toId, setToId] = useState<number | null>(null);
  const [amount, setAmount] = useState<string>("");
  const [date, setDate] = useState<string>(() => new Date().toISOString().slice(0, 10));
  const [description, setDescription] = useState<string>("");
  const [error, setError] = useState<string | null>(null);
  // När checking-saldot skulle gå minus → öppna kreditflödet i stället
  const [creditFlow, setCreditFlow] = useState<null | {
    affordability: {
      ok: boolean; current_balance: number; threshold: number;
      shortfall: number; explanation: string; account_kind: string;
      options: string[];
    };
    shortfall: number;
    depositAccountId: number;
  }>(null);
  // Stabil idempotency-key per öppnad modal — samma key skickas vid retries
  // så servern inte skapar dubbla rader om användaren råkar dubbelklicka.
  const [idemKey, setIdemKey] = useState<string>("");

  const accountsQ = useQuery({
    queryKey: ["accounts"],
    queryFn: () => api<Account[]>("/accounts"),
    enabled: open,
  });
  const balancesQ = useQuery({
    queryKey: ["balances", "today"],
    queryFn: () =>
      api<{ accounts: BalanceRow[] }>("/balances/"),
    enabled: open,
  });

  const accounts = accountsQ.data ?? [];
  const balanceMap = useMemo(() => {
    const m = new Map<number, number>();
    for (const b of balancesQ.data?.accounts ?? []) m.set(b.id, b.current_balance);
    return m;
  }, [balancesQ.data]);

  useEffect(() => {
    if (!open) return;
    setIdemKey(crypto.randomUUID());
    setError(null);
    if (defaultFromId !== undefined) setFromId(defaultFromId);
    else if (fromId === null && accounts.length > 0) setFromId(accounts[0].id);
  }, [open, defaultFromId, accounts.length]);

  const createMut = useMutation({
    mutationFn: (body: {
      from_account_id: number;
      to_account_id: number;
      amount: string;
      date: string;
      description: string;
      idempotency_key: string;
    }) =>
      api<CreateResponse>("/transfers/create", {
        method: "POST",
        body: JSON.stringify(body),
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["balances"] });
      qc.invalidateQueries({ queryKey: ["transactions"] });
      qc.invalidateQueries({ queryKey: ["transfers-paired"] });
      onClose();
    },
    onError: (e: unknown) => {
      const m = e instanceof Error ? e.message : "Kunde inte skapa överföring";
      setError(m);
    },
  });

  if (!open) return null;

  const fromAcc = accounts.find((a) => a.id === fromId);
  const toAcc = accounts.find((a) => a.id === toId);
  const amountNum = Number(amount.replace(",", "."));
  const validAmount = Number.isFinite(amountNum) && amountNum > 0;
  const sameAccount = fromId !== null && fromId === toId;
  const fromBal = fromId !== null ? balanceMap.get(fromId) ?? 0 : 0;
  const toBal = toId !== null ? balanceMap.get(toId) ?? 0 : 0;
  const fromAfter = fromBal - (validAmount ? amountNum : 0);
  const toAfter = toBal + (validAmount ? amountNum : 0);
  const wouldOverdrawSavings =
    (fromAcc?.type === "savings" || fromAcc?.type === "isk" ||
     fromAcc?.type === "pension") &&
    validAmount && fromAfter < 0;
  const wouldOverdrawChecking =
    fromAcc?.type === "checking" && validAmount && fromAfter < 0;

  const canSubmit =
    fromId !== null &&
    toId !== null &&
    !sameAccount &&
    validAmount &&
    !wouldOverdrawSavings &&
    !createMut.isPending;

  return (
    <div
      className="fixed inset-0 z-50 bg-black/40 flex items-center justify-center p-4"
      onClick={onClose}
    >
      <div
        className="bg-white rounded-xl shadow-xl w-full max-w-md p-5 space-y-4"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between">
          <h2 className="serif text-2xl">Ny överföring</h2>
          <button
            onClick={onClose}
            className="text-slate-500 hover:text-slate-800"
            aria-label="Stäng"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="space-y-2">
          <label className="text-sm font-medium">Från konto</label>
          <select
            value={fromId ?? ""}
            onChange={(e) => setFromId(Number(e.target.value))}
            className="w-full border rounded px-3 py-2"
          >
            <option value="" disabled>
              Välj konto…
            </option>
            {accounts.map((a) => (
              <option key={a.id} value={a.id}>
                {a.name} ({formatSEK(balanceMap.get(a.id) ?? 0)})
              </option>
            ))}
          </select>
        </div>

        <div className="flex items-center justify-center text-slate-400">
          <ArrowRight className="w-5 h-5" />
        </div>

        <div className="space-y-2">
          <label className="text-sm font-medium">Till konto</label>
          <select
            value={toId ?? ""}
            onChange={(e) => setToId(Number(e.target.value))}
            className="w-full border rounded px-3 py-2"
          >
            <option value="" disabled>
              Välj konto…
            </option>
            {accounts
              .filter((a) => a.id !== fromId)
              .map((a) => (
                <option key={a.id} value={a.id}>
                  {a.name} ({formatSEK(balanceMap.get(a.id) ?? 0)})
                </option>
              ))}
          </select>
        </div>

        <div className="space-y-2">
          <label className="text-sm font-medium">Belopp (kr)</label>
          <input
            type="text"
            inputMode="decimal"
            value={amount}
            onChange={(e) => setAmount(e.target.value)}
            placeholder="0,00"
            className="w-full border rounded px-3 py-2"
          />
        </div>

        <div className="grid grid-cols-2 gap-3">
          <div className="space-y-2">
            <label className="text-sm font-medium">Datum</label>
            <input
              type="date"
              value={date}
              onChange={(e) => setDate(e.target.value)}
              className="w-full border rounded px-3 py-2"
            />
          </div>
          <div className="space-y-2">
            <label className="text-sm font-medium">Beskrivning</label>
            <input
              type="text"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="(valfritt)"
              className="w-full border rounded px-3 py-2"
            />
          </div>
        </div>

        {validAmount && fromAcc && toAcc && (
          <div className="bg-slate-50 border rounded p-3 text-sm">
            <div className="font-medium mb-1">Förhandsvisning</div>
            <div className="flex items-center justify-between">
              <span>{fromAcc.name}:</span>
              <span className={fromAfter < 0 ? "text-red-600" : ""}>
                {formatSEK(fromBal)} → {formatSEK(fromAfter)}
              </span>
            </div>
            <div className="flex items-center justify-between">
              <span>{toAcc.name}:</span>
              <span>
                {formatSEK(toBal)} → {formatSEK(toAfter)}
              </span>
            </div>
          </div>
        )}

        {wouldOverdrawSavings && (
          <div className="text-sm text-red-700 bg-red-50 border border-red-200 rounded p-2">
            {fromAcc?.type === "savings" && "Sparkontot kan inte gå minus."}
            {fromAcc?.type === "isk" && "ISK-kontot kan inte gå minus."}
            {fromAcc?.type === "pension" && "Pensionskontot kan inte gå minus."}
          </div>
        )}
        {wouldOverdrawChecking && (
          <div className="text-sm text-amber-800 bg-amber-50 border border-amber-200 rounded p-2 flex items-start gap-2">
            <AlertTriangle className="w-4 h-4 mt-0.5 shrink-0" />
            <div>
              <strong>Saldot räcker inte.</strong> Du saknar{" "}
              {formatSEK(-fromAfter)}.
              {" "}Klicka "Genomför" för att se dina alternativ
              (privatlån eller avbryt).
            </div>
          </div>
        )}
        {sameAccount && (
          <div className="text-sm text-amber-700 bg-amber-50 border border-amber-200 rounded p-2">
            Du kan inte föra över till samma konto.
          </div>
        )}
        {error && (
          <div className="text-sm text-red-700 bg-red-50 border border-red-200 rounded p-2">
            {error}
          </div>
        )}

        <div className="flex gap-2 justify-end pt-2">
          <button
            onClick={onClose}
            className="px-4 py-2 rounded border bg-white hover:bg-slate-50"
          >
            Avbryt
          </button>
          <button
            onClick={() => {
              if (fromId === null || toId === null || !validAmount) return;
              if (wouldOverdrawChecking && fromAcc) {
                // Trigga kreditflödet i stället för att skicka in
                setCreditFlow({
                  affordability: {
                    ok: false,
                    current_balance: fromBal,
                    threshold: 0,
                    shortfall: -fromAfter,
                    explanation:
                      `Du har ${formatSEK(fromBal)} på ${fromAcc.name} men ` +
                      `försöker ta ut ${formatSEK(amountNum)}. Du saknar ` +
                      `${formatSEK(-fromAfter)} för att överföringen ska gå.`,
                    account_kind: fromAcc.type,
                    options: ["private_loan", "sms_loan", "cancel"],
                  },
                  shortfall: -fromAfter,
                  depositAccountId: fromAcc.id,
                });
                return;
              }
              if (!canSubmit) return;
              createMut.mutate({
                from_account_id: fromId,
                to_account_id: toId,
                amount: String(amountNum),
                date,
                description,
                idempotency_key: idemKey,
              });
            }}
            disabled={!canSubmit && !wouldOverdrawChecking}
            className="bg-brand-600 text-white px-4 py-2 rounded disabled:opacity-50"
          >
            {createMut.isPending ? "Genomför…" : "Genomför"}
          </button>
        </div>
      </div>
      {creditFlow && (
        <CreditModal
          open={true}
          onClose={() => setCreditFlow(null)}
          shortfall={creditFlow.shortfall}
          affordability={creditFlow.affordability}
          depositAccountId={creditFlow.depositAccountId}
        />
      )}
    </div>
  );
}
