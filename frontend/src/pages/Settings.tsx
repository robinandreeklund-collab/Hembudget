import { useMutation, useQuery } from "@tanstack/react-query";
import { api } from "@/api/client";
import { Card } from "@/components/Card";
import { useAuth } from "@/hooks/useAuth";

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
    <div className="p-6 space-y-4 max-w-2xl">
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
            <div className="text-xs text-slate-500 mt-1">
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
            <div className="text-xs text-slate-500 mt-1">
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
