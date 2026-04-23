import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import {
  ArrowRight, CheckCircle2, ChevronDown, ChevronRight, Link2, Unlink2,
} from "lucide-react";
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
  const bulkLinkMut = useMutation({
    mutationFn: (pairs: Array<{ tx_a_id: number; tx_b_id: number }>) =>
      api<{ linked: number; skipped: number; errors: unknown[] }>(
        "/transfers/link-bulk",
        { method: "POST", body: JSON.stringify({ pairs }) },
      ),
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
          {(() => {
            // "Säkra par" = exakt belopp + samma dag. Typiska kreditkorts-
            // betalningar och autogiro mellan checking och kortkonto. Risk
            // för falska positiver är minimal — om beloppet matchar på en
            // krona och samma dag är det nästan alltid en transfer.
            const safe = suggestions.filter(
              (s) => s.date_diff_days === 0 && s.amount_diff === 0,
            );
            if (safe.length === 0) return null;
            return (
              <div className="mb-3 flex items-center gap-2 bg-emerald-50 border border-emerald-200 rounded p-2 text-sm">
                <span className="flex-1">
                  <strong>{safe.length} förslag</strong> med exakt samma
                  belopp och samma dag — typiskt kreditkorts-betalningar.
                  Para ihop alla med ett klick:
                </span>
                <button
                  onClick={() => {
                    if (
                      confirm(
                        `Para ihop alla ${safe.length} säkra förslag (samma dag + exakt belopp)?\n\nDu kan ångra dem individuellt under "Parade överföringar" om något blev fel.`,
                      )
                    ) {
                      bulkLinkMut.mutate(
                        safe.map((s) => ({
                          tx_a_id: s.source.id,
                          tx_b_id: s.destination.id,
                        })),
                      );
                    }
                  }}
                  disabled={bulkLinkMut.isPending}
                  className="bg-emerald-600 text-white px-3 py-1.5 rounded text-sm disabled:opacity-50"
                >
                  {bulkLinkMut.isPending
                    ? "Parar…"
                    : `Para alla ${safe.length} säkra`}
                </button>
              </div>
            );
          })()}
          {bulkLinkMut.data && (
            <div className="mb-3 text-sm text-emerald-700 bg-emerald-50 rounded p-2">
              ✓ {bulkLinkMut.data.linked} par hopparade.
              {bulkLinkMut.data.skipped > 0 &&
                ` ${bulkLinkMut.data.skipped} hoppades över (redan parade).`}
            </div>
          )}
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
          <BatchCounterpartSection
            count={unpaired.length}
            accounts={accountsQ.data ?? []}
            onDone={invalidate}
          />
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
          <PairsByMonth pairs={pairs} onUnlink={(id) => unlinkMut.mutate(id)} />
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

function BatchCounterpartSection({
  count,
  accounts,
  onDone,
}: {
  count: number;
  accounts: Account[];
  onDone: () => void;
}) {
  const [targetId, setTargetId] = useState<string>("");
  const [message, setMessage] = useState<string | null>(null);
  const mut = useMutation({
    mutationFn: (id: number) =>
      api<{ orphans_processed: number; counterparts_created: number }>(
        "/transfers/batch-create-counterparts",
        {
          method: "POST",
          body: JSON.stringify({ target_account_id: id }),
        },
      ),
    onSuccess: (data) => {
      setMessage(
        `Skapade ${data.counterparts_created} motsvarande transaktioner av ${data.orphans_processed} orphans.`,
      );
      setTargetId("");
      onDone();
    },
    onError: (e: Error) => setMessage("Fel: " + e.message),
  });

  const sorted = [...accounts].sort((a, b) => {
    const rank = (acc: Account) => (acc.incognito ? -1 : 0);
    return rank(a) - rank(b);
  });

  return (
    <div className="mb-3 p-3 bg-brand-50 border border-brand-100 rounded text-sm">
      <div className="font-medium text-brand-800 mb-1">
        Fixa alla {count} på en gång
      </div>
      <div className="text-xs text-slate-700 mb-2">
        Välj ett konto (typiskt partnerns inkognito) så skapas motsvarande
        transaktion på det kontot för varje orphan. Alla paras ihop som
        överföringar automatiskt.
      </div>
      <div className="flex gap-2 items-center">
        <select
          value={targetId}
          onChange={(e) => setTargetId(e.target.value)}
          className="border rounded px-2 py-1 bg-white text-sm flex-1"
        >
          <option value="">Välj målkonto…</option>
          {sorted.map((a) => (
            <option key={a.id} value={a.id}>
              {a.name} {a.incognito ? "(inkognito)" : ""}
            </option>
          ))}
        </select>
        <button
          onClick={() => targetId && mut.mutate(Number(targetId))}
          disabled={!targetId || mut.isPending}
          className="bg-brand-600 text-white text-sm px-3 py-1.5 rounded disabled:opacity-50"
        >
          {mut.isPending ? "Kör…" : "Skapa motsvarande för alla"}
        </button>
      </div>
      {message && (
        <div
          className={`mt-2 text-xs ${
            message.startsWith("Fel") ? "text-rose-600" : "text-emerald-700"
          }`}
        >
          {message}
        </div>
      )}
    </div>
  );
}

const SV_MONTHS = [
  "januari", "februari", "mars", "april", "maj", "juni",
  "juli", "augusti", "september", "oktober", "november", "december",
];

function formatMonthLabel(ym: string): string {
  const [y, m] = ym.split("-").map(Number);
  if (!y || !m) return ym;
  return `${SV_MONTHS[m - 1]} ${y}`;
}

function PairsByMonth({
  pairs,
  onUnlink,
}: {
  pairs: Pair[];
  onUnlink: (tx_id: number) => void;
}) {
  // Gruppera per YYYY-MM (baserat på source-tx:s datum)
  const byMonth: Record<string, Pair[]> = {};
  for (const p of pairs) {
    const ym = p.source.date.slice(0, 7);
    (byMonth[ym] = byMonth[ym] || []).push(p);
  }
  const months = Object.keys(byMonth).sort().reverse();
  // De 2 senaste månaderna öppna som default, resten kollapsade
  const initiallyOpen = new Set(months.slice(0, 2));

  return (
    <div className="space-y-2">
      {months.map((ym) => (
        <PairsMonthSection
          key={ym}
          month={ym}
          pairs={byMonth[ym]}
          initiallyOpen={initiallyOpen.has(ym)}
          onUnlink={onUnlink}
        />
      ))}
    </div>
  );
}

function PairsMonthSection({
  month,
  pairs,
  initiallyOpen,
  onUnlink,
}: {
  month: string;
  pairs: Pair[];
  initiallyOpen: boolean;
  onUnlink: (tx_id: number) => void;
}) {
  const [open, setOpen] = useState(initiallyOpen);
  const total = pairs.reduce(
    (s, p) => s + Math.abs(Number(p.source.amount)), 0,
  );

  return (
    <div className="border rounded-lg overflow-hidden">
      <button
        onClick={() => setOpen((o) => !o)}
        className="w-full flex items-center gap-3 px-3 py-2 hover:bg-slate-50 text-left"
      >
        {open ? (
          <ChevronDown className="w-4 h-4 text-slate-600 shrink-0" />
        ) : (
          <ChevronRight className="w-4 h-4 text-slate-600 shrink-0" />
        )}
        <div className="flex-1 min-w-0">
          <div className="font-medium capitalize">{formatMonthLabel(month)}</div>
          <div className="text-xs text-slate-700">
            {pairs.length} par
          </div>
        </div>
        <div className="text-right shrink-0 text-sm font-semibold">
          {formatSEK(total)}
        </div>
      </button>
      {open && (
        <div className="border-t p-2 space-y-1 bg-slate-50/40">
          {pairs.map((p) => (
            <div key={p.source.id} className="flex items-center gap-3 border rounded p-2 text-sm bg-emerald-50/30">
              <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0" />
              <TxRow tx={p.source} />
              <ArrowRight className="w-4 h-4 text-slate-600 shrink-0" />
              <TxRow tx={p.destination} />
              <button
                onClick={() => onUnlink(p.source.id)}
                className="ml-auto shrink-0 text-slate-600 hover:text-rose-600 text-xs"
                title="Ta bort parningen"
              >
                <Unlink2 className="w-3.5 h-3.5" />
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
