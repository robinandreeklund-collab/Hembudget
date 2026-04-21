import { useState } from "react";
import { Server } from "lucide-react";
import { setApiBaseOverride, getApiBase } from "@/api/client";

export function BackendSetup({ error }: { error?: string }) {
  const [url, setUrl] = useState("");
  const [probing, setProbing] = useState(false);
  const [probeError, setProbeError] = useState<string | null>(null);

  async function save() {
    if (!url.trim()) return;
    setProbing(true);
    setProbeError(null);
    const normalized = url.trim().replace(/\/$/, "");
    const withScheme = /^https?:\/\//i.test(normalized)
      ? normalized
      : `https://${normalized}`;
    try {
      const res = await fetch(`${withScheme}/healthz`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      await res.json();
    } catch (e) {
      setProbeError(
        `Kunde inte nå ${withScheme}/healthz: ${e instanceof Error ? e.message : e}`,
      );
      setProbing(false);
      return;
    }
    setApiBaseOverride(withScheme);
    window.location.reload();
  }

  return (
    <div className="h-full grid place-items-center bg-gradient-to-br from-slate-50 to-brand-50 p-6">
      <div className="bg-white rounded-2xl shadow-lg p-8 w-[32rem] max-w-full space-y-4 border border-slate-200">
        <div className="flex items-center gap-2 text-brand-600">
          <Server className="w-5 h-5" />
          <h1 className="text-xl font-semibold">Koppla mot backend</h1>
        </div>
        <p className="text-sm text-slate-600">
          Frontenden behöver veta var backend-servern finns. Den här rutan
          dyker bara upp när automatisk upptäckt misslyckas — brukar bero på
          att VITE_API_BASE inte var ifyllt när frontend byggdes på Render.
        </p>
        {error && (
          <div className="text-xs bg-rose-50 border border-rose-200 rounded p-2 text-rose-700">
            Senaste fel: {error}
          </div>
        )}
        <div>
          <label className="text-sm font-medium">Backend-URL</label>
          <input
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            placeholder="hembudget-backend-xxxx.onrender.com"
            autoFocus
            className="w-full mt-1 px-3 py-2 border rounded-lg border-slate-300 font-mono text-sm"
          />
          <div className="text-xs text-slate-500 mt-1">
            Från Render-dashboarden: hitta "hembudget-backend"-tjänsten och
            kopiera URL:en (t.ex. <code>hembudget-backend-abc.onrender.com</code>).
            Jag lägger till <code>https://</code> automatiskt.
          </div>
        </div>
        {probeError && (
          <div className="text-sm text-rose-600">{probeError}</div>
        )}
        <div className="text-xs text-slate-500">
          Nuvarande försök: <code className="bg-slate-100 px-1 rounded">{getApiBase()}</code>
        </div>
        <button
          onClick={save}
          disabled={!url.trim() || probing}
          className="w-full bg-brand-600 text-white rounded-lg py-2 font-medium disabled:opacity-50"
        >
          {probing ? "Testar…" : "Spara och anslut"}
        </button>
      </div>
    </div>
  );
}
