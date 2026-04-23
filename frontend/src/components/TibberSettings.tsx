import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Key, RefreshCw } from "lucide-react";
import { api } from "@/api/client";
import { Card } from "@/components/Card";

interface TibberHome {
  id: string;
  address: string;
  currency: string;
  has_pulse: boolean;
}

export default function TibberSettings({
  onSync,
}: {
  onSync?: () => void;
}) {
  const qc = useQueryClient();
  const tokenQ = useQuery({
    queryKey: ["setting", "tibber_api_token"],
    queryFn: async () => {
      try {
        const r = await api<{ value: string | null }>(
          "/settings/tibber_api_token",
        );
        return r.value ?? "";
      } catch {
        return "";
      }
    },
  });
  const [tokenInput, setTokenInput] = useState("");
  const [homes, setHomes] = useState<TibberHome[]>([]);
  const [testError, setTestError] = useState<string | null>(null);

  const setMut = useMutation({
    mutationFn: (value: string) =>
      api(`/settings/tibber_api_token`, {
        method: "PUT",
        body: JSON.stringify({ value }),
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["setting", "tibber_api_token"] });
      setTokenInput("");
    },
  });
  const testMut = useMutation({
    mutationFn: () =>
      api<{ homes: TibberHome[] }>("/utility/tibber/test", { method: "POST" }),
    onSuccess: (data) => {
      setHomes(data.homes ?? []);
      setTestError(null);
    },
    onError: (e: Error) => {
      setTestError(e.message);
      setHomes([]);
    },
  });
  const syncMut = useMutation({
    mutationFn: () =>
      api<{ saved: number; updated: number; home_address: string }>(
        "/utility/tibber/sync?months=24",
        { method: "POST" },
      ),
    onSuccess: () => {
      onSync?.();
      qc.invalidateQueries({ queryKey: ["utility"] });
    },
  });

  const hasToken = (tokenQ.data ?? "").length > 0;

  return (
    <Card title="Tibber-integration">
      <div className="text-sm text-slate-700 mb-3">
        Synka månadsförbrukning + realtidspris från ditt Tibber-konto.
        Generera en token på{" "}
        <a
          href="https://developer.tibber.com/settings/access-token"
          target="_blank"
          rel="noreferrer"
          className="text-brand-600 underline"
        >
          developer.tibber.com
        </a>
        . När tokenen är sparad visas realtidsgrafen automatiskt på
        /förbrukning.
      </div>
      {!hasToken ? (
        <div className="flex gap-2 text-sm">
          <div className="flex-1 relative">
            <Key className="w-4 h-4 absolute left-2 top-1/2 -translate-y-1/2 text-slate-600" />
            <input
              type="password"
              value={tokenInput}
              onChange={(e) => setTokenInput(e.target.value)}
              placeholder="Tibber API-token (sha-256-sträng)"
              className="border rounded pl-8 pr-2 py-1.5 w-full font-mono text-xs"
            />
          </div>
          <button
            onClick={() => tokenInput.trim() && setMut.mutate(tokenInput.trim())}
            disabled={!tokenInput.trim() || setMut.isPending}
            className="bg-brand-600 text-white px-4 py-1.5 rounded text-sm disabled:opacity-50"
          >
            Spara token
          </button>
        </div>
      ) : (
        <div className="space-y-2 text-sm">
          <div className="flex items-center gap-2">
            <Key className="w-4 h-4 text-emerald-600" />
            <span className="text-emerald-700">Token sparad</span>
            <button
              onClick={() => {
                if (confirm("Ta bort token?")) {
                  setMut.mutate("");
                  setHomes([]);
                }
              }}
              className="text-xs text-rose-600 hover:underline ml-auto"
            >
              Ta bort
            </button>
          </div>
          <div className="flex gap-2">
            <button
              onClick={() => testMut.mutate()}
              disabled={testMut.isPending}
              className="bg-slate-700 text-white px-3 py-1.5 rounded text-xs disabled:opacity-50"
            >
              {testMut.isPending ? "Testar…" : "Testa + hämta hem"}
            </button>
            <button
              onClick={() => syncMut.mutate()}
              disabled={syncMut.isPending}
              className="bg-brand-600 text-white px-3 py-1.5 rounded text-xs disabled:opacity-50 inline-flex items-center gap-1.5"
            >
              <RefreshCw
                className={"w-3.5 h-3.5 " + (syncMut.isPending ? "animate-spin" : "")}
              />
              {syncMut.isPending ? "Synkar…" : "Synka 24 månader"}
            </button>
          </div>
          {testError && (
            <div className="text-xs text-rose-600">{testError}</div>
          )}
          {syncMut.data && (
            <div className="text-xs text-emerald-700">
              ✓ {syncMut.data.saved} nya + {syncMut.data.updated} uppdaterade
              läsningar från {syncMut.data.home_address}
            </div>
          )}
          {homes.length > 0 && (
            <div className="mt-2 text-xs">
              <div className="text-slate-700 font-medium mb-1">Dina hem:</div>
              {homes.map((h) => (
                <div key={h.id} className="border rounded p-2 mb-1 bg-slate-50">
                  <div>{h.address}</div>
                  <div className="text-slate-600">
                    {h.has_pulse ? "✓ Pulse aktiv (realtid)" : "Pulse saknas"} ·{" "}
                    {h.currency}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </Card>
  );
}
