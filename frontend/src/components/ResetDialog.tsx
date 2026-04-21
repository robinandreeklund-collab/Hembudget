import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { AlertTriangle, X } from "lucide-react";
import { api } from "@/api/client";

const CONFIRM_PHRASE = "NOLLSTÄLL";

interface Stats {
  accounts: number;
  transactions: number;
  imports: number;
  budgets: number;
  rules: number;
  subscriptions: number;
  scenarios: number;
  chat_messages: number;
  tax_events: number;
  goals: number;
  loans: number;
  loan_payments: number;
}

export function ResetDialog({ onClose }: { onClose: () => void }) {
  const qc = useQueryClient();
  const [typed, setTyped] = useState("");
  const [keepRules, setKeepRules] = useState(false);

  const statsQ = useQuery({
    queryKey: ["admin-stats"],
    queryFn: () => api<Stats>("/admin/stats"),
  });

  const resetMut = useMutation({
    mutationFn: () =>
      api<{ ok: boolean; deleted: Record<string, number> }>("/admin/reset", {
        method: "POST",
        body: JSON.stringify({
          confirm: CONFIRM_PHRASE,
          keep_rules: keepRules,
        }),
      }),
    onSuccess: () => {
      qc.clear();
      onClose();
      window.location.reload();
    },
  });

  const stats = statsQ.data;
  const canConfirm = typed === CONFIRM_PHRASE && !resetMut.isPending;

  return (
    <div className="fixed inset-0 bg-slate-900/60 grid place-items-center z-50 p-4">
      <div className="bg-white rounded-xl shadow-xl w-[32rem] max-w-full">
        <div className="flex items-start justify-between p-5 border-b">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 bg-rose-100 rounded-full grid place-items-center">
              <AlertTriangle className="w-5 h-5 text-rose-600" />
            </div>
            <div>
              <h3 className="text-lg font-semibold">Nollställ data</h3>
              <div className="text-xs text-slate-500">Denna åtgärd kan inte ångras.</div>
            </div>
          </div>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-700">
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="p-5 space-y-4 text-sm">
          {stats && (
            <div className="bg-slate-50 rounded-lg p-3 grid grid-cols-2 gap-y-1 gap-x-4 text-xs">
              <div className="flex justify-between"><span className="text-slate-500">Transaktioner</span><span className="font-medium">{stats.transactions}</span></div>
              <div className="flex justify-between"><span className="text-slate-500">Konton</span><span className="font-medium">{stats.accounts}</span></div>
              <div className="flex justify-between"><span className="text-slate-500">Imports</span><span className="font-medium">{stats.imports}</span></div>
              <div className="flex justify-between"><span className="text-slate-500">Budgetar</span><span className="font-medium">{stats.budgets}</span></div>
              <div className="flex justify-between"><span className="text-slate-500">Regler</span><span className="font-medium">{stats.rules}</span></div>
              <div className="flex justify-between"><span className="text-slate-500">Abonnemang</span><span className="font-medium">{stats.subscriptions}</span></div>
              <div className="flex justify-between"><span className="text-slate-500">Scenarion</span><span className="font-medium">{stats.scenarios}</span></div>
              <div className="flex justify-between"><span className="text-slate-500">Chatt-rader</span><span className="font-medium">{stats.chat_messages}</span></div>
            </div>
          )}

          <div className="bg-emerald-50 border border-emerald-200 text-emerald-900 rounded-lg p-3 text-xs">
            <strong>Alltid bevarat:</strong> konton ({stats?.accounts ?? "?"}),
            lån ({stats?.loans ?? "?"}) och lånescheman. Radera dessa manuellt
            en i taget från respektive sida om du vill rensa dem.
          </div>
          <div className="space-y-2">
            <label className="flex items-center gap-2">
              <input
                type="checkbox"
                checked={keepRules}
                onChange={(e) => setKeepRules(e.target.checked)}
              />
              <span>Behåll egna kategoriseringsregler</span>
            </label>
          </div>

          <div>
            <label className="block text-slate-600 mb-1">
              Skriv <code className="bg-slate-100 px-1.5 py-0.5 rounded font-mono">{CONFIRM_PHRASE}</code> för att bekräfta:
            </label>
            <input
              value={typed}
              onChange={(e) => setTyped(e.target.value)}
              className="w-full border rounded-lg px-3 py-2 font-mono"
              placeholder={CONFIRM_PHRASE}
              autoFocus
            />
          </div>

          <div className="text-xs text-slate-500">
            Master-lösenordet och kategoriträdet behålls. Standardreglerna seedas om på nytt
            om du inte väljer att behålla egna regler.
          </div>

          {resetMut.isError && (
            <div className="text-sm text-rose-600">
              Fel: {(resetMut.error as Error).message}
            </div>
          )}
        </div>

        <div className="flex justify-end gap-2 p-5 border-t bg-slate-50 rounded-b-xl">
          <button
            onClick={onClose}
            className="px-4 py-2 rounded-lg border border-slate-300 bg-white"
          >
            Avbryt
          </button>
          <button
            onClick={() => resetMut.mutate()}
            disabled={!canConfirm}
            className="px-4 py-2 rounded-lg bg-rose-600 text-white disabled:opacity-40 disabled:cursor-not-allowed"
          >
            {resetMut.isPending ? "Nollställer…" : "Nollställ nu"}
          </button>
        </div>
      </div>
    </div>
  );
}
