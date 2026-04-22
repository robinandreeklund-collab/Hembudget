import { useMutation, useQuery } from "@tanstack/react-query";
import { api, formatSEK } from "@/api/client";
import { Card } from "@/components/Card";
import { useAuth } from "@/hooks/useAuth";

interface SubHealth {
  id: number;
  merchant: string;
  amount: number;
  interval_days: number;
  last_seen: string | null;
  days_since: number | null;
  is_stale: boolean;
  annual_cost: number;
}

interface SubHealthResp {
  stale_days: number;
  subscriptions: SubHealth[];
  stale_annual_cost: number;
  total_annual_cost: number;
}

export default function Settings() {
  const { logout } = useAuth();
  const statusQ = useQuery({
    queryKey: ["status"],
    queryFn: () =>
      api<{ initialized: boolean; db_path: string; lm_studio: string }>("/status"),
  });
  const lmQ = useQuery({
    queryKey: ["lm-status"],
    queryFn: () => api<{ alive: boolean; base_url: string; model: string }>("/chat/lm-studio-status"),
  });

  const detectSubsMut = useMutation({
    mutationFn: () =>
      api<{ count: number; subscriptions: unknown[] }>("/budget/subscriptions/detect", {
        method: "POST",
      }),
  });

  const subHealthQ = useQuery({
    queryKey: ["subs-health"],
    queryFn: () =>
      api<SubHealthResp>("/budget/subscriptions/health?stale_days=60"),
  });

  const scanTransfersMut = useMutation({
    mutationFn: () =>
      api<{ pairs: number; ambiguous: number; details: [number, number][] }>(
        "/admin/scan-transfers",
        { method: "POST" },
      ),
  });

  const recategorizeMut = useMutation({
    mutationFn: () =>
      api<{
        seed_rules_removed: number;
        txs_processed: number;
        categorized: number;
        still_uncategorized: number;
      }>("/admin/recategorize", { method: "POST" }),
  });

  return (
    <div className="p-3 md:p-6 space-y-4 md:space-y-4 max-w-2xl">
      <h1 className="text-2xl font-semibold">Inställningar</h1>

      <Card title="System">
        <div className="text-sm space-y-1">
          <div>DB: <code className="bg-slate-100 px-1 rounded">{statusQ.data?.db_path}</code></div>
          <div>LM Studio: <code className="bg-slate-100 px-1 rounded">{statusQ.data?.lm_studio}</code></div>
          <div>
            Status:{" "}
            <span className={lmQ.data?.alive ? "text-emerald-600" : "text-rose-600"}>
              {lmQ.data?.alive ? "ansluten" : "ej ansluten"}
            </span>
          </div>
          <div>Modell: {lmQ.data?.model}</div>
        </div>
      </Card>

      <Card
        title="Prenumerationer — hälsokoll"
        action={
          subHealthQ.data && (
            <span className="text-xs text-slate-700">
              Totalt {formatSEK(subHealthQ.data.total_annual_cost)}/år
            </span>
          )
        }
      >
        {subHealthQ.isLoading ? (
          <div className="text-sm text-slate-700">Analyserar…</div>
        ) : !subHealthQ.data || subHealthQ.data.subscriptions.length === 0 ? (
          <div className="text-sm text-slate-700">
            Inga aktiva prenumerationer registrerade. Klicka "Hitta prenumerationer nu" nedan.
          </div>
        ) : (
          <>
            {subHealthQ.data.stale_annual_cost > 0 && (
              <div className="bg-amber-50 border border-amber-200 text-amber-800 rounded px-3 py-2 text-sm mb-3">
                Du har {formatSEK(subHealthQ.data.stale_annual_cost)}/år i
                prenumerationer som inte dragits senaste{" "}
                {subHealthQ.data.stale_days} dagarna — överväg att säga upp.
              </div>
            )}
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs uppercase text-slate-700 border-b">
                  <th className="py-1.5 pr-3">Tjänst</th>
                  <th className="py-1.5 pr-3 text-right">Pris</th>
                  <th className="py-1.5 pr-3 text-right">Senast dragen</th>
                  <th className="py-1.5 pr-3 text-right">Per år</th>
                </tr>
              </thead>
              <tbody>
                {subHealthQ.data.subscriptions.map((s) => (
                  <tr
                    key={s.id}
                    className={`border-b last:border-0 ${
                      s.is_stale ? "bg-amber-50" : ""
                    }`}
                  >
                    <td className="py-1.5 pr-3">
                      <div className="font-medium">{s.merchant}</div>
                      <div className="text-xs text-slate-700">
                        var {s.interval_days}:e dag
                      </div>
                    </td>
                    <td className="py-1.5 pr-3 text-right">
                      {formatSEK(s.amount)}
                    </td>
                    <td
                      className={`py-1.5 pr-3 text-right text-xs ${
                        s.is_stale ? "text-amber-700 font-semibold" : "text-slate-700"
                      }`}
                    >
                      {s.last_seen
                        ? `${s.last_seen} (${s.days_since}d sedan)`
                        : "— aldrig sedd"}
                    </td>
                    <td className="py-1.5 pr-3 text-right font-semibold">
                      {formatSEK(s.annual_cost)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </>
        )}
      </Card>

      <Card title="Automatik">
        <div className="space-y-3">
          <div>
            <button
              className="bg-brand-600 text-white px-4 py-2 rounded"
              onClick={() => detectSubsMut.mutate()}
              disabled={detectSubsMut.isPending}
            >
              {detectSubsMut.isPending ? "Analyserar…" : "Hitta prenumerationer nu"}
            </button>
            {detectSubsMut.data && (
              <pre className="mt-2 bg-slate-900 text-slate-100 text-xs p-3 rounded overflow-x-auto">
                {JSON.stringify(detectSubsMut.data, null, 2)}
              </pre>
            )}
          </div>

          <div>
            <button
              className="bg-brand-600 text-white px-4 py-2 rounded"
              onClick={() => scanTransfersMut.mutate()}
              disabled={scanTransfersMut.isPending}
            >
              {scanTransfersMut.isPending ? "Skannar…" : "Hitta överföringar mellan konton"}
            </button>
            <div className="text-xs text-slate-700 mt-1">
              Matchar transaktioner med motsatt belopp mellan dina konton (±0,5 %, ±3 dagar).
              Körs automatiskt efter varje import, men kan köras om manuellt.
            </div>
            {scanTransfersMut.data && (
              <div className="mt-2 text-sm">
                <strong>{scanTransfersMut.data.pairs}</strong> nya par hittade.
                {scanTransfersMut.data.ambiguous > 0 && (
                  <span className="text-amber-700 ml-2">
                    {scanTransfersMut.data.ambiguous} tvetydiga (behöver manuell granskning).
                  </span>
                )}
              </div>
            )}
          </div>

          <div>
            <button
              className="bg-slate-800 text-white px-4 py-2 rounded"
              onClick={() => recategorizeMut.mutate()}
              disabled={recategorizeMut.isPending}
            >
              {recategorizeMut.isPending ? "Kör om…" : "Omseeda regler + omkategorisera"}
            </button>
            <div className="text-xs text-slate-700 mt-1">
              Tar bort inbyggda seed-regler, lägger till de senaste från koden och
              kör om kategoriseringen på alla transaktioner som du inte själv har
              rättat. Dina egna rättningar behålls.
            </div>
            {recategorizeMut.data && (
              <div className="mt-2 text-sm">
                <strong>{recategorizeMut.data.categorized}</strong> av{" "}
                {recategorizeMut.data.txs_processed} transaktioner kategoriserade.
                {" "}
                ({recategorizeMut.data.seed_rules_removed} gamla seed-regler ersatta,
                {" "}{recategorizeMut.data.still_uncategorized} kvar okategoriserade — de
                hamnar hos LLM:en vid nästa import.)
              </div>
            )}
          </div>
        </div>
      </Card>

      <Card title="Session">
        <button className="bg-rose-600 text-white px-4 py-2 rounded" onClick={logout}>
          Logga ut
        </button>
      </Card>
    </div>
  );
}
