import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  ArrowLeft, Brain, Check, Key, Loader2, ShieldCheck, Trash2, X, Zap,
} from "lucide-react";
import { api, ApiError } from "@/api/client";

type TeacherRow = {
  id: number;
  email: string;
  name: string;
  active: boolean;
  is_super_admin: boolean;
  is_demo: boolean;
  ai_enabled: boolean;
  ai_requests_count: number;
  ai_input_tokens: number;
  ai_output_tokens: number;
};

type Status = { client_available: boolean };

type ApiKeyStatus = {
  configured: boolean;
  source: string; // "db" | "env" | ""
  preview: string;
  client_available: boolean;
};

export default function AdminAI() {
  const [status, setStatus] = useState<Status | null>(null);
  const [rows, setRows] = useState<TeacherRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);
  const [toggling, setToggling] = useState<string | null>(null);
  const [apiKey, setApiKey] = useState<ApiKeyStatus | null>(null);
  const [newKey, setNewKey] = useState("");
  const [keyBusy, setKeyBusy] = useState(false);
  const [keyMsg, setKeyMsg] = useState<string | null>(null);

  async function reload() {
    setLoading(true);
    setErr(null);
    try {
      const [st, list, key] = await Promise.all([
        api<Status>("/admin/ai/status"),
        api<TeacherRow[]>("/admin/ai/teachers"),
        api<ApiKeyStatus>("/admin/ai/api-key"),
      ]);
      setStatus(st);
      setRows(list);
      setApiKey(key);
    } catch (e) {
      if (e instanceof ApiError && e.status === 403) {
        setErr("Endast super-admin kan se denna sida.");
      } else {
        setErr(e instanceof Error ? e.message : String(e));
      }
    } finally {
      setLoading(false);
    }
  }

  async function saveKey() {
    if (!newKey.trim() || newKey.trim().length < 20) {
      setKeyMsg("Nyckeln ser för kort ut. Klistra in hela sk-ant-…");
      return;
    }
    setKeyBusy(true);
    setKeyMsg(null);
    try {
      const res = await api<ApiKeyStatus>("/admin/ai/api-key", {
        method: "POST",
        body: JSON.stringify({ key: newKey.trim() }),
      });
      setApiKey(res);
      setNewKey("");
      setKeyMsg(
        res.client_available
          ? "Nyckeln är sparad och klienten är uppkopplad."
          : "Sparad — men klienten kunde inte initieras. Kontrollera att nyckeln är giltig.",
      );
      // Uppdatera toggle-sektionens status också
      const st = await api<Status>("/admin/ai/status");
      setStatus(st);
    } catch (e) {
      setKeyMsg(e instanceof Error ? e.message : String(e));
    } finally {
      setKeyBusy(false);
    }
  }

  async function deleteKey() {
    if (!confirm(
      "Radera den sparade nyckeln? AI-funktionerna stängs av för alla " +
      "lärare tills en ny nyckel läggs in (eller ANTHROPIC_API_KEY är " +
      "satt i Cloud Run-env).",
    )) return;
    setKeyBusy(true);
    setKeyMsg(null);
    try {
      const res = await api<ApiKeyStatus>("/admin/ai/api-key", {
        method: "DELETE",
      });
      setApiKey(res);
      setKeyMsg("Nyckeln raderad.");
      const st = await api<Status>("/admin/ai/status");
      setStatus(st);
    } catch (e) {
      setKeyMsg(e instanceof Error ? e.message : String(e));
    } finally {
      setKeyBusy(false);
    }
  }

  useEffect(() => {
    reload();
  }, []);

  async function toggleAi(t: TeacherRow) {
    const key = `ai-${t.id}`;
    setToggling(key);
    try {
      const updated = await api<TeacherRow>(
        `/admin/ai/teachers/${t.id}/ai`,
        {
          method: "POST",
          body: JSON.stringify({ enabled: !t.ai_enabled }),
        },
      );
      setRows((prev) => prev.map((r) => (r.id === updated.id ? updated : r)));
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setToggling(null);
    }
  }

  async function toggleSuper(t: TeacherRow) {
    const key = `super-${t.id}`;
    setToggling(key);
    try {
      const updated = await api<TeacherRow>(
        `/admin/ai/teachers/${t.id}/super`,
        {
          method: "POST",
          body: JSON.stringify({ enabled: !t.is_super_admin }),
        },
      );
      setRows((prev) => prev.map((r) => (r.id === updated.id ? updated : r)));
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setToggling(null);
    }
  }

  if (loading) {
    return (
      <div className="p-6 text-slate-500 flex items-center gap-2">
        <Loader2 className="w-4 h-4 animate-spin" /> Laddar …
      </div>
    );
  }
  if (err) {
    return (
      <div className="p-6 max-w-3xl mx-auto space-y-3">
        <Link
          to="/teacher"
          className="text-sm text-brand-600 hover:underline flex items-center gap-1"
        >
          <ArrowLeft className="w-4 h-4" /> Tillbaka
        </Link>
        <div className="bg-rose-50 border border-rose-200 text-rose-700 rounded p-4">
          {err}
        </div>
      </div>
    );
  }

  const totalIn = rows.reduce((s, r) => s + r.ai_input_tokens, 0);
  const totalOut = rows.reduce((s, r) => s + r.ai_output_tokens, 0);
  const totalReq = rows.reduce((s, r) => s + r.ai_requests_count, 0);

  return (
    <div className="p-6 max-w-5xl mx-auto space-y-6">
      <div>
        <Link
          to="/teacher"
          className="text-sm text-brand-600 hover:underline flex items-center gap-1"
        >
          <ArrowLeft className="w-4 h-4" /> Tillbaka till lärarvyn
        </Link>
        <h1 className="text-2xl font-semibold mt-2 flex items-center gap-2">
          <Brain className="w-6 h-6 text-brand-600" />
          AI-administration
        </h1>
        <p className="text-sm text-slate-600 mt-1">
          Här tilldelar du AI-åtkomst per lärarkonto. AI är av som default
          — tänd bara för lärare du litar på, eftersom varje anrop kostar
          pengar på Anthropic-kontot.
        </p>
      </div>

      <div
        className={`rounded-lg border px-4 py-3 text-sm ${
          status?.client_available
            ? "bg-emerald-50 border-emerald-200 text-emerald-800"
            : "bg-amber-50 border-amber-200 text-amber-800"
        }`}
      >
        {status?.client_available ? (
          <>
            <Zap className="inline w-4 h-4 mr-1" />
            Claude-klient är uppkopplad. AI-endpoints fungerar för lärare
            som är påslagna nedan.
          </>
        ) : (
          <>
            ⚠ Ingen giltig API-nyckel — klienten kan inte starta. Lägg in
            en nyckel nedan.
          </>
        )}
      </div>

      {/* API-nyckel-sektion */}
      <section className="bg-white rounded-xl border border-slate-200 p-5 space-y-4">
        <div className="flex items-center gap-2">
          <Key className="w-5 h-5 text-brand-600" />
          <h2 className="font-medium">Anthropic API-nyckel</h2>
        </div>
        <div className="text-sm text-slate-700 space-y-1">
          <div>
            Status:{" "}
            {apiKey?.configured ? (
              <span className="font-medium text-emerald-700">
                Konfigurerad {apiKey.preview && `(${apiKey.preview})`}
              </span>
            ) : (
              <span className="font-medium text-amber-700">Saknas</span>
            )}
          </div>
          {apiKey?.source && (
            <div className="text-xs text-slate-500">
              Källa:{" "}
              {apiKey.source === "db"
                ? "sparad via detta formulär"
                : "HEMBUDGET_API_KEY (miljövariabel)"}
            </div>
          )}
        </div>
        <div className="space-y-2">
          <label className="block text-xs font-medium text-slate-600">
            {apiKey?.configured ? "Byt nyckel" : "Lägg in nyckel"}
          </label>
          <div className="flex gap-2">
            <input
              type="password"
              value={newKey}
              onChange={(e) => setNewKey(e.target.value)}
              placeholder="sk-ant-api03-…"
              className="flex-1 border border-slate-300 rounded px-3 py-2 text-sm font-mono"
              disabled={keyBusy}
              autoComplete="off"
              spellCheck={false}
            />
            <button
              onClick={saveKey}
              disabled={keyBusy || !newKey.trim()}
              className="bg-brand-600 hover:bg-brand-700 text-white rounded px-4 py-2 text-sm font-medium disabled:opacity-50 flex items-center gap-2"
            >
              {keyBusy ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : (
                <Check className="w-4 h-4" />
              )}
              Spara
            </button>
          </div>
          <p className="text-xs text-slate-500">
            Nyckeln lagras i master-DB:n och används direkt av alla
            AI-endpoints. Den skrivs inte till loggar och visas aldrig
            i klartext efter att du sparat den.
          </p>
          {apiKey?.source === "db" && (
            <button
              onClick={deleteKey}
              disabled={keyBusy}
              className="text-xs text-rose-600 hover:text-rose-800 flex items-center gap-1 disabled:opacity-50"
            >
              <Trash2 className="w-3 h-3" />
              Radera sparad nyckel
            </button>
          )}
          {keyMsg && (
            <div className="text-xs bg-slate-50 border border-slate-200 rounded p-2 text-slate-700">
              {keyMsg}
            </div>
          )}
        </div>
      </section>

      <div className="grid grid-cols-3 gap-3">
        <Stat label="Totalt antal anrop" value={totalReq.toLocaleString("sv-SE")} />
        <Stat label="In-tokens" value={totalIn.toLocaleString("sv-SE")} />
        <Stat label="Ut-tokens" value={totalOut.toLocaleString("sv-SE")} />
      </div>

      <section className="bg-white rounded-xl border border-slate-200">
        <div className="px-4 py-3 border-b border-slate-100 flex items-center justify-between">
          <h2 className="font-medium">Lärarkonton</h2>
          <span className="text-xs text-slate-500">{rows.length} st</span>
        </div>
        <table className="w-full text-sm">
          <thead className="text-xs text-slate-500 bg-slate-50">
            <tr>
              <th className="text-left px-4 py-2">Lärare</th>
              <th className="text-left px-4 py-2">E-post</th>
              <th className="text-right px-4 py-2">Anrop</th>
              <th className="text-right px-4 py-2">In / Ut</th>
              <th className="text-center px-4 py-2">AI</th>
              <th className="text-center px-4 py-2">Super</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((t) => (
              <tr key={t.id} className="border-t border-slate-100">
                <td className="px-4 py-2">
                  <div className="font-medium">{t.name}</div>
                  {t.is_demo && (
                    <span className="inline-block text-xs bg-amber-100 text-amber-800 px-1.5 py-0.5 rounded mt-0.5">
                      demo
                    </span>
                  )}
                </td>
                <td className="px-4 py-2 text-slate-600">{t.email}</td>
                <td className="px-4 py-2 text-right tabular-nums">
                  {t.ai_requests_count.toLocaleString("sv-SE")}
                </td>
                <td className="px-4 py-2 text-right tabular-nums text-xs text-slate-600">
                  {t.ai_input_tokens.toLocaleString("sv-SE")} /{" "}
                  {t.ai_output_tokens.toLocaleString("sv-SE")}
                </td>
                <td className="px-4 py-2 text-center">
                  <ToggleButton
                    active={t.ai_enabled}
                    loading={toggling === `ai-${t.id}`}
                    onClick={() => toggleAi(t)}
                    labelOn="AI på"
                    labelOff="AI av"
                  />
                </td>
                <td className="px-4 py-2 text-center">
                  <ToggleButton
                    active={t.is_super_admin}
                    loading={toggling === `super-${t.id}`}
                    onClick={() => toggleSuper(t)}
                    labelOn={<ShieldCheck className="w-3.5 h-3.5 inline" />}
                    labelOff={<span className="text-slate-400">—</span>}
                  />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <div className="text-xs text-slate-500 leading-relaxed">
        <p>
          <strong>AI-toggel:</strong> Styr om lärarens elever får
          AI-feedback, Q&A och lärarens egna AI-verktyg (rubric-förslag,
          modulgenerering).
        </p>
        <p className="mt-1">
          <strong>Super-admin:</strong> Får se och toggla AI åt andra
          lärare. Din egen super-status kan du inte ta bort själv.
        </p>
      </div>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="bg-white rounded-lg border border-slate-200 p-4">
      <div className="text-xs text-slate-500">{label}</div>
      <div className="text-2xl font-semibold tabular-nums mt-1">{value}</div>
    </div>
  );
}

function ToggleButton({
  active, loading, onClick, labelOn, labelOff,
}: {
  active: boolean;
  loading: boolean;
  onClick: () => void;
  labelOn: React.ReactNode;
  labelOff: React.ReactNode;
}) {
  return (
    <button
      onClick={onClick}
      disabled={loading}
      className={`inline-flex items-center gap-1 px-2.5 py-1 rounded text-xs font-medium transition-colors ${
        active
          ? "bg-emerald-100 text-emerald-700 hover:bg-emerald-200"
          : "bg-slate-100 text-slate-600 hover:bg-slate-200"
      } ${loading ? "opacity-50" : ""}`}
    >
      {loading ? (
        <Loader2 className="w-3 h-3 animate-spin" />
      ) : active ? (
        <Check className="w-3 h-3" />
      ) : (
        <X className="w-3 h-3" />
      )}
      {active ? labelOn : labelOff}
    </button>
  );
}
