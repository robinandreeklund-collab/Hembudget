import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { ExternalLink, Key, LogOut, RefreshCw } from "lucide-react";
import { api } from "@/api/client";
import { Card } from "@/components/Card";

interface TibberHome {
  id: string;
  address: string;
  currency: string;
  has_pulse: boolean;
}

interface OAuthStatus {
  configured: boolean;
  authorized: boolean;
  client_id: string;
  redirect_uri: string;
  scope: string;
  expires_at: string | null;
}

export default function TibberSettings({
  onSync,
}: {
  onSync?: () => void;
}) {
  const qc = useQueryClient();
  const statusQ = useQuery({
    queryKey: ["tibber-oauth-status"],
    queryFn: () => api<OAuthStatus>("/utility/tibber/oauth/status"),
  });
  const status = statusQ.data;

  return (
    <Card title="Tibber-integration (OAuth)">
      <div className="text-sm text-slate-700 mb-3">
        Koppla ditt Tibber-utvecklarkonto för att hämta hem-data och
        realtidsförbrukning. Skapa en klient på{" "}
        <a
          href="https://thewall.tibber.com"
          target="_blank"
          rel="noreferrer"
          className="text-brand-600 underline"
        >
          thewall.tibber.com
        </a>
        {" "}med redirect-URL{" "}
        <code className="bg-slate-100 px-1 rounded text-xs">
          http://localhost:1420/Callback
        </code>{" "}
        och scopes{" "}
        <code className="bg-slate-100 px-1 rounded text-xs">
          data-api-homes-read
        </code>
        ,{" "}
        <code className="bg-slate-100 px-1 rounded text-xs">
          data-api-user-read
        </code>
        .
      </div>

      {!status || statusQ.isLoading ? (
        <div className="text-sm text-slate-700">Laddar status…</div>
      ) : !status.configured ? (
        <OAuthConfigForm
          onSaved={() => qc.invalidateQueries({ queryKey: ["tibber-oauth-status"] })}
        />
      ) : !status.authorized ? (
        <OAuthAuthorizeStep
          status={status}
          onChangeConfig={() => qc.invalidateQueries({ queryKey: ["tibber-oauth-status"] })}
        />
      ) : (
        <OAuthAuthorizedView
          status={status}
          onSync={onSync}
          onLogout={() => qc.invalidateQueries({ queryKey: ["tibber-oauth-status"] })}
        />
      )}
    </Card>
  );
}

// ----- Steg 1: spara client_id + client_secret -----

function OAuthConfigForm({ onSaved }: { onSaved: () => void }) {
  const [clientId, setClientId] = useState("");
  const [clientSecret, setClientSecret] = useState("");
  const [redirectUri, setRedirectUri] = useState(
    "http://localhost:1420/Callback",
  );

  const saveMut = useMutation({
    mutationFn: (p: { client_id: string; client_secret: string; redirect_uri: string }) =>
      api("/utility/tibber/oauth/config", {
        method: "PUT",
        body: JSON.stringify(p),
      }),
    onSuccess: onSaved,
  });

  return (
    <div className="space-y-2 text-sm">
      <div>
        <label className="text-xs text-slate-700">Client ID</label>
        <input
          value={clientId}
          onChange={(e) => setClientId(e.target.value)}
          placeholder="065182F9DE16AD7B9D85196A…"
          className="border rounded px-2 py-1 w-full font-mono text-xs"
        />
      </div>
      <div>
        <label className="text-xs text-slate-700">Client Secret</label>
        <input
          type="password"
          value={clientSecret}
          onChange={(e) => setClientSecret(e.target.value)}
          placeholder="(från Tibber developer-konsolen)"
          className="border rounded px-2 py-1 w-full font-mono text-xs"
        />
      </div>
      <div>
        <label className="text-xs text-slate-700">Redirect URI</label>
        <input
          value={redirectUri}
          onChange={(e) => setRedirectUri(e.target.value)}
          className="border rounded px-2 py-1 w-full font-mono text-xs"
        />
        <div className="text-[10px] text-slate-500">
          Måste matcha exakt det du registrerade hos Tibber.
        </div>
      </div>
      <button
        onClick={() =>
          clientId.trim() &&
          clientSecret.trim() &&
          saveMut.mutate({
            client_id: clientId.trim(),
            client_secret: clientSecret.trim(),
            redirect_uri: redirectUri.trim(),
          })
        }
        disabled={!clientId.trim() || !clientSecret.trim() || saveMut.isPending}
        className="bg-brand-600 text-white px-3 py-1.5 rounded text-sm disabled:opacity-50"
      >
        {saveMut.isPending ? "Sparar…" : "Spara & gå vidare"}
      </button>
      {saveMut.isError && (
        <div className="text-xs text-rose-700">
          {(saveMut.error as Error).message}
        </div>
      )}
    </div>
  );
}

// ----- Steg 2: auktorisera -----

function OAuthAuthorizeStep({
  status, onChangeConfig,
}: {
  status: OAuthStatus;
  onChangeConfig: () => void;
}) {
  const startMut = useMutation({
    mutationFn: () =>
      api<{ authorize_url: string; state: string }>(
        "/utility/tibber/oauth/start",
        { method: "POST" },
      ),
    onSuccess: (res) => {
      window.location.href = res.authorize_url;
    },
  });

  return (
    <div className="space-y-3 text-sm">
      <div className="bg-slate-50 border rounded p-2">
        <div className="text-xs text-slate-700">
          Client ID: <code className="font-mono">{status.client_id.slice(0, 16)}…</code>
        </div>
        <div className="text-xs text-slate-700">
          Redirect: <code className="font-mono">{status.redirect_uri}</code>
        </div>
      </div>
      <button
        onClick={() => startMut.mutate()}
        disabled={startMut.isPending}
        className="bg-brand-600 text-white px-4 py-2 rounded inline-flex items-center gap-2 disabled:opacity-50"
      >
        <ExternalLink className="w-4 h-4" />
        {startMut.isPending ? "Startar…" : "Anslut Tibber-kontot"}
      </button>
      <button
        onClick={() => {
          if (confirm("Ändra OAuth-config? Sparade tokens nollställs.")) {
            onChangeConfig();
          }
        }}
        className="ml-2 text-xs text-slate-700 hover:underline"
      >
        Ändra client-inställningar
      </button>
      {startMut.isError && (
        <div className="text-xs text-rose-700">
          {(startMut.error as Error).message}
        </div>
      )}
    </div>
  );
}

// ----- Steg 3: autentiserad -----

function OAuthAuthorizedView({
  status, onSync, onLogout,
}: {
  status: OAuthStatus;
  onSync?: () => void;
  onLogout: () => void;
}) {
  const qc = useQueryClient();
  const [homes, setHomes] = useState<TibberHome[]>([]);
  const [testError, setTestError] = useState<string | null>(null);

  const testMut = useMutation({
    mutationFn: () =>
      api<{ homes: TibberHome[]; auth: string }>(
        "/utility/tibber/test",
        { method: "POST" },
      ),
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
  const logoutMut = useMutation({
    mutationFn: () =>
      api("/utility/tibber/oauth/logout", { method: "POST" }),
    onSuccess: onLogout,
  });

  return (
    <div className="space-y-3 text-sm">
      <div className="flex items-center gap-2">
        <Key className="w-4 h-4 text-emerald-600" />
        <span className="text-emerald-700">Ansluten</span>
        <span className="text-xs text-slate-500">
          · Scopes: {status.scope.split(" ").filter(Boolean).length}
        </span>
        {status.expires_at && (
          <span className="text-xs text-slate-500">
            · Giltig till {new Date(status.expires_at).toLocaleString("sv-SE")}
          </span>
        )}
        <button
          onClick={() => {
            if (confirm("Koppla från Tibber? Du behöver auktorisera på nytt.")) {
              logoutMut.mutate();
            }
          }}
          className="text-xs text-rose-600 hover:underline ml-auto inline-flex items-center gap-1"
        >
          <LogOut className="w-3 h-3" />
          Koppla från
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
      {testError && <div className="text-xs text-rose-700">{testError}</div>}
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
  );
}
