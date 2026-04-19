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
        <button
          className="bg-brand-600 text-white px-4 py-2 rounded"
          onClick={() => detectSubsMut.mutate()}
          disabled={detectSubsMut.isPending}
        >
          {detectSubsMut.isPending ? "Analyserar…" : "Hitta prenumerationer nu"}
        </button>
        {detectSubsMut.data && (
          <pre className="mt-3 bg-slate-900 text-slate-100 text-xs p-3 rounded overflow-x-auto">
            {JSON.stringify(detectSubsMut.data, null, 2)}
          </pre>
        )}
      </Card>

      <Card title="Session">
        <button className="bg-rose-600 text-white px-4 py-2 rounded" onClick={logout}>
          Logga ut
        </button>
      </Card>
    </div>
  );
}
