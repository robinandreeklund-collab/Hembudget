import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { ArrowRight, CheckCircle2, Link2, Unlink2 } from "lucide-react";
import { api, formatSEK } from "@/api/client";
import { Card } from "@/components/Card";
import type { Account } from "@/types/models";

interface TxView {
  id: number;
  account_id: number;
  account_name: string | null;
  date: string;
  amount: number;
  description: string;
  is_transfer: boolean;
  transfer_pair_id: number | null;
}

interface Pair {
  source: TxView;
  destination: TxView;
}

interface Suggestion extends Pair {
  date_diff_days: number;
  amount_diff: number;
}

export default function Transfers() {
  const qc = useQueryClient();

  const pairsQ = useQuery({
    queryKey: ["transfers-paired"],
    queryFn: () => api<{ pairs: Pair[]; count: number }>("/transfers/paired"),
  });
  const unpairedQ = useQuery({
    queryKey: ["transfers-unpaired"],
    queryFn: () => api<{ transactions: TxView[]; count: number }>("/transfers/unpaired"),
  });
  const suggestionsQ = useQuery({
    queryKey: ["transfers-suggestions"],
    queryFn: () => api<{ suggestions: Suggestion[]; count: number }>("/transfers/suggestions"),
  });
  const accountsQ = useQuery({
    queryKey: ["accounts"],
    queryFn: () => api<Account[]>("/accounts"),
  });

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ["transfers-paired"] });
    qc.invalidateQueries({ queryKey: ["transfers-unpaired"] });
    qc.invalidateQueries({ queryKey: ["transfers-suggestions"] });
    qc.invalidateQueries({ queryKey: ["transactions"] });
    qc.invalidateQueries({ queryKey: ["budget"] });
    qc.invalidateQueries({ queryKey: ["balances"] });
  };

  const scanMut = useMutation({
    mutationFn: () =>
      api<{ pairs: number; ambiguous: number }>("/admin/scan-transfers", { method: "POST" }),
    onSuccess: invalidate,
  });
  const linkMut = useMutation({
    mutationFn: (p: { tx_a_id: number; tx_b_id: number }) =>
      api("/transfers/link", { method: "POST", body: JSON.stringify(p) }),
    onSuccess: invalidate,
  });
  const unlinkMut = useMutation({
    mutationFn: (id: number) => api(`/transfers/unlink/${id}`, { method: "POST" }),
    onSuccess: invalidate,
  });

  const pairs = pairsQ.data?.pairs ?? [];
  const unpaired = unpairedQ.data?.transactions ?? [];
  const suggestions = suggestionsQ.data?.suggestions ?? [];

  return (
    <div className="p-3 md:p-6 space-y-4 md:space-y-5 max-w-6xl">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold flex items-center gap-2">
            <Link2 className="w-6 h-6" />
            Överföringar
          </h1>
          <div className="text-sm text-slate-700 mt-0.5">
            Hanterar överföringar mellan dina egna konton så de inte dubbelbokförs.
          </div>
        </div>
        <button
          onClick={() => scanMut.mutate()}
          disabled={scanMut.isPending}
          className="bg-brand-600 text-white px-4 py-2 rounded-lg"
        >
          {scanMut.isPending ? "Scannar…" : "Kör om automatmatchning"}
        </button>
      </div>

      {scanMut.data && (
        <div className="text-sm text-emerald-700 bg-emerald-50 border border-emerald-200 rounded p-3">
          {scanMut.data.pairs} nya par hittade.
          {scanMut.data.ambiguous > 0 && (
            <span> {scanMut.data.ambiguous} tvetydiga — de ligger under "Förslag" nedan.</span>
          )}
        </div>
      )}

      <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-4">
        <Stat label="Parade överföringar" value={String(pairs.length)} tone="good" />
        <Stat label="Markerade utan par" value={String(unpaired.length)} tone={unpaired.length > 0 ? "warn" : "neutral"} />
        <Stat label="Föreslagna par" value={String(suggestions.length)} tone={suggestions.length > 0 ? "info" : "neutral"} />
      </div>

      {suggestions.length > 0 && (
        <Card title={`Föreslagna par (${suggestions.length})`}>
          <div className="text-sm text-slate-700 mb-2">
            Rader på olika konton med matchande belopp och nära datum. Klicka "Para ihop"
            för att bekräfta, eller strunta i dem om det är riktiga utgifter/inkomster.
          </div>
          <div className="space-y-2">
            {suggestions.slice(0, 50).map((s) => (
              <div key={`${s.source.id}-${s.destination.id}`}
                   className="border rounded-lg p-3 bg-amber-50/50 flex items-center gap-3">
                <TxRow tx={s.source} />
                <ArrowRight className="w-5 h-5 text-slate-600 shrink-0" />
                <TxRow tx={s.destination} />
                <div className="flex flex-col items-end text-xs text-slate-700 shrink-0">
                  <span>{s.date_diff_days === 0 ? "Samma dag" : `${s.date_diff_days} d isär`}</span>
                  <span>{s.amount_diff === 0 ? "Exakt belopp" : `±${formatSEK(s.amount_diff)}`}</span>
                </div>
                <button
                  onClick={() => linkMut.mutate({ tx_a_id: s.source.id, tx_b_id: s.destination.id })}
                  className="shrink-0 bg-brand-600 text-white text-sm px-3 py-1.5 rounded"
                >
                  Para ihop
                </button>
              </div>
            ))}
          </div>
        </Card>
      )}

      {unpaired.length > 0 && (
        <Card title={`Markerade som överföring men utan par (${unpaired.length})`}>
          <div className="text-sm text-slate-700 mb-2">
            Oftast för att motparten inte är importerad än (t.ex. partnerns sida
            av en överföring från hennes inkognito-konto). Välj ett konto i
            dropdownen för att skapa motsvarande transaktion där — systemet
            parar ihop dem direkt som överföring.
          </div>
          <div className="space-y-1">
            {unpaired.map((tx) => (
              <div key={tx.id} className="flex items-center gap-3 border rounded p-2 text-sm">
                <TxRow tx={tx} />
                <div className="ml-auto shrink-0 flex items-center gap-2">
                  <CreateCounterpartDropdown
                    tx={tx}
                    accounts={(accountsQ.data ?? []).filter(
                      (a) => a.id !== tx.account_id,
                    )}
                    onCreated={invalidate}
                  />
                  <button
                    onClick={() => unlinkMut.mutate(tx.id)}
                    className="flex items-center gap-1 text-slate-700 hover:text-rose-600 text-xs"
                    title="Avmarkera som överföring — räkna som vanlig transaktion"
                  >
                    <Unlink2 className="w-3.5 h-3.5" />
                    Avmarkera
                  </button>
                </div>
              </div>
            ))}
          </div>
        </Card>
      )}

      <Card title={`Parade överföringar (${pairs.length})`}>
        {pairs.length === 0 ? (
          <div className="text-sm text-slate-700">
            Inga överföringar parade ännu. Importera alla dina konton och klicka
            "Kör om automatmatchning" — då söker systemet efter matchande belopp på
            olika konton inom ±5 dagars fönster.
          </div>
        ) : (
          <div className="space-y-1">
            {pairs.map((p) => (
              <div key={p.source.id} className="flex items-center gap-3 border rounded p-2 text-sm bg-emerald-50/30">
                <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0" />
                <TxRow tx={p.source} />
                <ArrowRight className="w-4 h-4 text-slate-600 shrink-0" />
                <TxRow tx={p.destination} />
                <button
                  onClick={() => unlinkMut.mutate(p.source.id)}
                  className="ml-auto shrink-0 text-slate-600 hover:text-rose-600 text-xs"
                  title="Ta bort parningen"
                >
                  <Unlink2 className="w-3.5 h-3.5" />
                </button>
              </div>
            ))}
          </div>
        )}
      </Card>

      <Card title="Så här fungerar matchningen">
        <ul className="text-sm text-slate-600 space-y-1.5 list-disc pl-5">
          <li><strong>Kreditkort:</strong> autogiro-dragningar (t.ex. "SEB KORT AUTOGIRO") markeras som överföring via text-mönster och paras med positiv rad på kortkontot inom ±7 dagar och ±2 % belopp.</li>
          <li><strong>Mellan egna konton:</strong> scanner söker alla negativa rader och letar positiv rad på annat konto med matchande belopp (±0,5 %) inom ±5 dagar.</li>
          <li><strong>1:1-parning:</strong> när flera identiska överföringar finns samma dag (t.ex. två 5 000 kr till gemensamma) paras de i ordning istället för att flaggas som tvetydiga.</li>
          <li><strong>Parade rader räknas inte som utgift eller inkomst</strong> — de är helt utelämnade ur budget, dashboard och prognoser.</li>
        </ul>
      </Card>
    </div>
  );
}

function TxRow({ tx }: { tx: TxView }) {
  const isNegative = tx.amount < 0;
  return (
    <div className="flex-1 min-w-0">
      <div className="flex gap-2 items-baseline">
        <span className={`font-semibold shrink-0 ${isNegative ? "text-rose-600" : "text-emerald-600"}`}>
          {formatSEK(tx.amount)}
        </span>
        <span className="text-slate-700 text-xs shrink-0">{tx.date}</span>
        <span className="text-slate-700 text-xs truncate">
          {tx.account_name ?? `Konto #${tx.account_id}`}
        </span>
      </div>
      <div className="text-xs text-slate-600 truncate">{tx.description}</div>
    </div>
  );
}

function Stat({ label, value, tone }: { label: string; value: string; tone: "good" | "warn" | "info" | "neutral" }) {
  const color =
    tone === "good" ? "text-emerald-600"
    : tone === "warn" ? "text-amber-600"
    : tone === "info" ? "text-brand-600"
    : "text-slate-700";
  return (
    <div className="bg-white border border-slate-200 rounded-xl p-4">
      <div className="text-xs uppercase text-slate-700">{label}</div>
      <div className={`text-2xl font-semibold mt-1 ${color}`}>{value}</div>
    </div>
  );
}

function CreateCounterpartDropdown({
  tx,
  accounts,
  onCreated,
}: {
  tx: TxView;
  accounts: Account[];
  onCreated: () => void;
}) {
  const [_pick, setPick] = useState<string>("");
  const mut = useMutation({
    mutationFn: (accountId: number) =>
      api(`/transfers/${tx.id}/create-counterpart`, {
        method: "POST",
        body: JSON.stringify({
          account_id: accountId,
          description: `Motpart till ${tx.description}`,
        }),
      }),
    onSuccess: onCreated,
  });

  const sorted = [...accounts].sort((a, b) => {
    const rank = (acc: Account) => (acc.incognito ? -1 : 0);
    return rank(a) - rank(b);
  });

  return (
    <select
      value=""
      onChange={(e) => {
        const v = Number(e.target.value);
        if (v) mut.mutate(v);
        setPick("");
      }}
      disabled={mut.isPending}
      className="text-xs border rounded px-1.5 py-1 bg-white"
      title="Skapa motsvarande transaktion på valt konto (motsatt tecken) och para ihop som överföring"
    >
      <option value="">
        {mut.isPending ? "Skapar…" : "Skapa motsvarande…"}
      </option>
      {sorted.map((a) => (
        <option key={a.id} value={a.id}>
          {a.name} {a.incognito ? "(inkognito)" : ""}
        </option>
      ))}
    </select>
  );
}
