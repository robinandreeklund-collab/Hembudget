import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  ArrowLeft, Brain, Check, Database, Image, Key, Loader2, Mail, Send, ShieldCheck,
  Trash2, Upload, Wrench, X, Zap,
} from "lucide-react";
import { api, ApiError, getApiBase, getToken } from "@/api/client";

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
      <div className="p-4 md:p-6 max-w-3xl mx-auto space-y-3">
        <Link
          to="/teacher"
          className="text-sm nav-link flex items-center gap-1"
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
    <div className="p-4 md:p-6 max-w-5xl mx-auto space-y-6">
      <div>
        <Link
          to="/teacher"
          className="text-sm nav-link flex items-center gap-1"
        >
          <ArrowLeft className="w-4 h-4" /> Tillbaka till lärarvyn
        </Link>
        <h1 className="serif text-3xl leading-tight mt-2">
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
              className="btn-dark rounded-md px-4 py-2 text-sm font-medium disabled:opacity-50 flex items-center gap-2"
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

      {/* Finnhub-nyckel för aktiekurser */}
      <FinnhubSection />

      {/* Klassdisplay-toggles per lärare */}
      <ClassDisplaySection />

      {/* SMTP-konfiguration */}
      <SmtpSection />

      {/* Landningssidans skärmdumpar */}
      <LandingGallerySection />

      {/* Landningssidans variant (A/B-test) */}
      <LandingVariantSection />

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

      <DbMigrationsCard />

      <StocksDiagnosticsCard />
    </div>
  );
}


function StocksDiagnosticsCard() {
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState<Record<string, unknown> | null>(null);
  const [pollResult, setPollResult] = useState<Record<string, unknown> | null>(null);
  const [err, setErr] = useState<string | null>(null);

  async function loadStatus() {
    setBusy(true);
    setErr(null);
    try {
      const res = await api<Record<string, unknown>>("/admin/ai/db/stocks-status");
      setStatus(res);
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function pollNow() {
    setBusy(true);
    setErr(null);
    setPollResult(null);
    try {
      const res = await api<Record<string, unknown>>("/admin/ai/db/stocks-poll-now", {
        method: "POST",
      });
      setPollResult(res);
      await loadStatus();
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="bg-white rounded-xl border border-slate-200 p-5 space-y-4">
      <div className="flex items-center gap-2">
        <Database className="w-5 h-5 text-brand-600" />
        <h2 className="font-medium">Aktiekurs-diagnostik</h2>
      </div>
      <p className="text-sm text-slate-700">
        Visa pollerstatus + tvinga manuell hämtning av kurser. Användbart
        om eleven ser tomma kurser eller "marknaden stängd"-banner när
        börsen borde vara öppen.
      </p>
      <div className="flex items-center gap-2 flex-wrap">
        <button
          onClick={loadStatus}
          disabled={busy}
          className="border border-slate-300 hover:bg-slate-50 rounded-md px-3 py-2 text-sm disabled:opacity-50"
        >
          {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : "Hämta status"}
        </button>
        <button
          onClick={pollNow}
          disabled={busy}
          className="bg-brand-600 hover:bg-brand-700 text-white rounded-md px-3 py-2 text-sm disabled:opacity-50"
        >
          {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : "Polla kurser nu"}
        </button>
      </div>
      {err && (
        <div className="text-sm text-rose-600 border-l-2 border-rose-300 pl-3 py-1">
          {err}
        </div>
      )}
      {pollResult && (
        <pre className="bg-slate-50 border border-slate-200 rounded p-3 text-xs text-slate-700 overflow-x-auto">
          Poll-resultat: {JSON.stringify(pollResult, null, 2)}
        </pre>
      )}
      {status && (
        <pre className="bg-slate-50 border border-slate-200 rounded p-3 text-xs text-slate-700 overflow-x-auto">
          {JSON.stringify(status, null, 2)}
        </pre>
      )}
    </section>
  );
}


function DbMigrationsCard() {
  const [busy, setBusy] = useState<"master" | "scope" | null>(null);
  const [log, setLog] = useState<string[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [columns, setColumns] = useState<Record<string, string[]> | null>(null);

  async function runMaster() {
    if (!confirm(
      "Tvinga master-DB-migrationerna att köra direkt mot databasen?\n\n" +
      "Idempotent — säker att köra om en migration tidigare failat. " +
      "Loggen visar exakt vad som hände.",
    )) return;
    setBusy("master");
    setErr(null);
    setLog(null);
    try {
      const res = await api<{ ok: boolean; log: string[] }>(
        "/admin/ai/db/run-migrations",
        { method: "POST" },
      );
      setLog(res.log);
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(null);
    }
  }

  async function runScope() {
    if (!confirm(
      "Tvinga SCOPE-DB-migrationerna att köra (loans.loan_kind etc.)?\n\n" +
      "Behövs efter en deploy om Postgres-loggar visar t.ex. " +
      "'column loans.loan_kind does not exist'. Idempotent.",
    )) return;
    setBusy("scope");
    setErr(null);
    setLog(null);
    try {
      const res = await api<{ ok: boolean; log: string[] }>(
        "/admin/ai/db/run-scope-migrations",
        { method: "POST" },
      );
      setLog(res.log);
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(null);
    }
  }

  async function loadColumns() {
    try {
      const res = await api<{ tables: Record<string, string[]> }>(
        "/admin/ai/db/scope-columns",
      );
      setColumns(res.tables);
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <section className="bg-white rounded-xl border border-slate-200 p-5 space-y-4">
      <div className="flex items-center gap-2">
        <Database className="w-5 h-5 text-brand-600" />
        <h2 className="font-medium">DB-migrationer</h2>
      </div>
      <p className="text-sm text-slate-700">
        Tvinga DB-migrationerna att köra. Master-migrationerna gäller
        teachers/students/profiles, scope-migrationerna gäller alla
        elevdata-tabeller (loans, transactions, accounts osv).
        Idempotent.
      </p>
      <div className="flex items-center gap-2 flex-wrap">
        <button
          onClick={runMaster}
          disabled={busy !== null}
          className="bg-brand-600 hover:bg-brand-700 text-white rounded-md px-4 py-2 text-sm flex items-center gap-2 disabled:opacity-50"
        >
          {busy === "master" ? (
            <Loader2 className="w-4 h-4 animate-spin" />
          ) : (
            <Wrench className="w-4 h-4" />
          )}
          Master-migrationer
        </button>
        <button
          onClick={runScope}
          disabled={busy !== null}
          className="bg-amber-600 hover:bg-amber-700 text-white rounded-md px-4 py-2 text-sm flex items-center gap-2 disabled:opacity-50"
        >
          {busy === "scope" ? (
            <Loader2 className="w-4 h-4 animate-spin" />
          ) : (
            <Wrench className="w-4 h-4" />
          )}
          Scope-migrationer (loans, transactions…)
        </button>
        <button
          onClick={loadColumns}
          disabled={busy !== null}
          className="border border-slate-300 hover:bg-slate-50 rounded-md px-3 py-2 text-sm"
        >
          Visa scope-kolumner
        </button>
        {log && (
          <span className="text-xs text-emerald-700">
            Klart — {log.length} log-rader
          </span>
        )}
      </div>
      {err && (
        <div className="text-sm text-rose-600 border-l-2 border-rose-300 pl-3 py-1">
          {err}
        </div>
      )}
      {log && log.length > 0 && (
        <pre className="bg-slate-50 border border-slate-200 rounded p-3 text-xs text-slate-700 overflow-x-auto whitespace-pre-wrap max-h-80">
          {log.join("\n")}
        </pre>
      )}
      {columns && (
        <div className="text-xs space-y-2">
          <div className="font-semibold">Scope-DB-kolumner per tabell:</div>
          {Object.entries(columns).map(([tbl, cols]) => (
            <div key={tbl} className="border-l-2 border-slate-200 pl-2">
              <div className="font-medium text-slate-800">{tbl}</div>
              <div className="text-slate-500 break-all">
                {cols.length === 0 ? "(tabell finns inte)" : cols.join(", ")}
              </div>
            </div>
          ))}
        </div>
      )}
    </section>
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

// ---------- SMTP-konfiguration (super-admin) ----------

type SmtpConfig = {
  configured: boolean;
  source: string;        // "db" | "env" | ""
  host: string;
  port: number;
  user: string;
  password_set: boolean;
  password_preview: string;
  starttls: boolean;
  mail_from: string;
  mail_from_name: string;
  public_base_url: string;
};

function SmtpSection() {
  const [cfg, setCfg] = useState<SmtpConfig | null>(null);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [testTo, setTestTo] = useState("");

  // Form-state
  const [host, setHost] = useState("");
  const [port, setPort] = useState(587);
  const [user, setUser] = useState("");
  const [password, setPassword] = useState("");
  const [starttls, setStarttls] = useState(true);
  const [mailFrom, setMailFrom] = useState("");
  const [fromName, setFromName] = useState("Ekonomilabbet");
  const [baseUrl, setBaseUrl] = useState("");

  function syncForm(c: SmtpConfig) {
    setHost(c.host);
    setPort(c.port);
    setUser(c.user);
    // Behåll lösenordsfältet tomt — visning är 'password_preview'
    setPassword("");
    setStarttls(c.starttls);
    setMailFrom(c.mail_from);
    setFromName(c.mail_from_name);
    setBaseUrl(c.public_base_url);
  }

  async function load() {
    try {
      const c = await api<SmtpConfig>("/admin/smtp/config");
      setCfg(c);
      syncForm(c);
    } catch (e) {
      if (e instanceof ApiError && e.status === 403) {
        // Inte super-admin — visa inget
        setCfg(null);
      } else {
        setErr(e instanceof Error ? e.message : String(e));
      }
    }
  }
  useEffect(() => { load(); }, []);

  async function save() {
    setBusy(true); setMsg(null); setErr(null);
    try {
      const body: Record<string, unknown> = {
        host, port, user, starttls,
        mail_from: mailFrom,
        mail_from_name: fromName,
        public_base_url: baseUrl,
      };
      // Skicka bara password om användaren skrivit något — annars
      // behåller backend befintligt.
      if (password.trim()) body.password = password.trim();
      const c = await api<SmtpConfig>("/admin/smtp/config", {
        method: "POST",
        body: JSON.stringify(body),
      });
      setCfg(c);
      syncForm(c);
      setMsg("Sparat. Testa via 'Skicka testmail' nedan.");
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function clear() {
    if (!confirm("Rensa SMTP-config? Faller tillbaka till env-vars om sådana finns.")) return;
    setBusy(true); setMsg(null); setErr(null);
    try {
      const c = await api<SmtpConfig>("/admin/smtp/config", { method: "DELETE" });
      setCfg(c);
      syncForm(c);
      setMsg("Rensat.");
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function sendTest() {
    if (!testTo.trim()) return;
    setBusy(true); setMsg(null); setErr(null);
    try {
      await api("/admin/smtp/test", {
        method: "POST",
        body: JSON.stringify({ to: testTo.trim() }),
      });
      setMsg(`Testmail skickat till ${testTo.trim()}. Kolla inkorgen.`);
    } catch (e) {
      if (e instanceof ApiError && e.status === 503) {
        setErr("SMTP är inte konfigurerat — fyll i config först.");
      } else if (e instanceof ApiError && e.status === 502) {
        // Backend skickar { detail: { message, hint } } så super-admin
        // ser exakt vad SMTP-servern svarade och hur det kan fixas.
        const body = e.body as { detail?: { message?: string; hint?: string } } | undefined;
        const detail = body?.detail;
        const message = detail?.message ?? "Kunde inte skicka mail (okänt fel)";
        const hint = detail?.hint;
        setErr(hint ? `${message}\n\n→ ${hint}` : message);
      } else {
        setErr(e instanceof Error ? e.message : String(e));
      }
    } finally {
      setBusy(false);
    }
  }

  if (cfg === null) {
    return null; // Inte super-admin eller fel — tysta
  }

  return (
    <section className="bg-white border-[1.5px] border-rule p-5 space-y-4">
      <div className="flex items-center gap-2">
        <Mail className="w-5 h-5" />
        <h2 className="serif text-xl">SMTP-konfiguration</h2>
      </div>
      <div className="text-sm text-[#444] space-y-1">
        <div>
          Status:{" "}
          {cfg.configured ? (
            <span className="font-medium text-emerald-700">
              Konfigurerad
              {cfg.password_set && ` (lösenord ${cfg.password_preview})`}
            </span>
          ) : (
            <span className="font-medium text-amber-700">Saknas</span>
          )}
        </div>
        {cfg.source && (
          <div className="text-xs text-[#888]">
            Källa: {cfg.source === "db"
              ? "sparad via detta formulär"
              : "miljövariabler (HEMBUDGET_SMTP_*)"}
          </div>
        )}
      </div>

      <div className="grid md:grid-cols-2 gap-3">
        <FormField label="SMTP-host">
          <input
            type="text"
            value={host}
            onChange={(e) => setHost(e.target.value)}
            placeholder="smtp.gmail.com"
            className="w-full border-[1.5px] border-rule px-3 py-2 text-sm focus:border-ink outline-none font-mono"
          />
        </FormField>
        <FormField label="Port">
          <input
            type="number"
            value={port}
            onChange={(e) => setPort(parseInt(e.target.value, 10) || 587)}
            className="w-full border-[1.5px] border-rule px-3 py-2 text-sm focus:border-ink outline-none font-mono"
          />
        </FormField>
        <FormField label="Användare">
          <input
            type="text"
            value={user}
            onChange={(e) => setUser(e.target.value)}
            placeholder="info@ekonomilabbet.org"
            className="w-full border-[1.5px] border-rule px-3 py-2 text-sm focus:border-ink outline-none font-mono"
          />
        </FormField>
        <FormField
          label={cfg.password_set ? "Nytt lösenord (lämna tomt för oförändrat)" : "Lösenord (Gmail app-password)"}
        >
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder={cfg.password_set ? "•••• •••• (skriv för att ändra)" : "abcdefghijklmnop"}
            autoComplete="off"
            spellCheck={false}
            className="w-full border-[1.5px] border-rule px-3 py-2 text-sm focus:border-ink outline-none font-mono"
          />
        </FormField>
        <FormField label="Mail-from-adress">
          <input
            type="email"
            value={mailFrom}
            onChange={(e) => setMailFrom(e.target.value)}
            placeholder="info@ekonomilabbet.org"
            className="w-full border-[1.5px] border-rule px-3 py-2 text-sm focus:border-ink outline-none font-mono"
          />
        </FormField>
        <FormField label="Avsändarnamn">
          <input
            type="text"
            value={fromName}
            onChange={(e) => setFromName(e.target.value)}
            className="w-full border-[1.5px] border-rule px-3 py-2 text-sm focus:border-ink outline-none"
          />
        </FormField>
        <FormField label="Publik bas-URL (för mail-länkar)">
          <input
            type="url"
            value={baseUrl}
            onChange={(e) => setBaseUrl(e.target.value)}
            placeholder="https://ekonomilabbet.org"
            className="w-full border-[1.5px] border-rule px-3 py-2 text-sm focus:border-ink outline-none font-mono"
          />
        </FormField>
        <FormField label="STARTTLS">
          <label className="flex items-center gap-2 text-sm py-2">
            <input
              type="checkbox"
              checked={starttls}
              onChange={(e) => setStarttls(e.target.checked)}
            />
            Använd STARTTLS (rekommenderat för port 587)
          </label>
        </FormField>
      </div>

      <details className="border-l-[3px] border-ink pl-4 py-1">
        <summary className="cursor-pointer eyebrow">
          Konfigurera Gmail (vanligaste fallet)
        </summary>
        <div className="mt-3 body-prose text-sm space-y-2">
          <p>
            Gmail kräver ett <strong>app-password</strong> (16 tecken,
            inga mellanslag). Vanligt Gmail-lösen funkar INTE via SMTP.
          </p>
          <ol className="list-decimal pl-5 space-y-1">
            <li>Slå på 2-stegs-verifiering på Google-kontot om du inte redan har det.</li>
            <li>
              Gå till{" "}
              <a
                href="https://myaccount.google.com/apppasswords"
                target="_blank"
                rel="noreferrer"
                className="nav-link"
              >
                myaccount.google.com/apppasswords
              </a>
            </li>
            <li>Skapa ett nytt app-password (välj "Mail" + "Övrigt: Ekonomilabbet").</li>
            <li>
              Fyll i nedan: host <span className="kbd">smtp.gmail.com</span>,
              port <span className="kbd">587</span>, STARTTLS PÅ, användare =
              full mail-adress (info@…), lösenord = de 16 tecknen utan
              mellanslag.
            </li>
            <li>Klicka <strong>Spara config</strong> och sen <strong>Skicka testmail</strong>.</li>
          </ol>
          <p className="text-xs text-[#888] serif-italic mt-2">
            Får du fel? Felmeddelandet under testmail-knappen visar exakt
            vad SMTP-servern svarade med en hint om hur det fixas.
          </p>
        </div>
      </details>

      <div className="flex gap-2 flex-wrap">
        <button
          onClick={save}
          disabled={busy || !host.trim() || !user.trim() || !mailFrom.trim()}
          className="btn-dark rounded-md px-4 py-2 text-sm font-medium disabled:opacity-50 flex items-center gap-2"
        >
          {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <Check className="w-4 h-4" />}
          Spara config
        </button>
        {cfg.source === "db" && (
          <button
            onClick={clear}
            disabled={busy}
            className="btn-outline rounded-md px-4 py-2 text-sm flex items-center gap-2 disabled:opacity-50"
          >
            <Trash2 className="w-4 h-4" /> Rensa DB-config
          </button>
        )}
      </div>

      <div className="pt-3 border-t border-rule">
        <div className="eyebrow mb-2">Testa SMTP</div>
        <div className="flex gap-2 flex-wrap">
          <input
            type="email"
            value={testTo}
            onChange={(e) => setTestTo(e.target.value)}
            placeholder="din-mail@example.com"
            className="flex-1 min-w-[240px] border-[1.5px] border-rule px-3 py-2 text-sm focus:border-ink outline-none font-mono"
          />
          <button
            onClick={sendTest}
            disabled={busy || !testTo.trim() || !cfg.configured}
            className="btn-outline rounded-md px-4 py-2 text-sm flex items-center gap-2 disabled:opacity-50"
          >
            {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
            Skicka testmail
          </button>
        </div>
        <p className="text-xs text-[#888] mt-2">
          Skickar ett kort testmail med aktiv config. Verifierar att Gmail
          app-password fungerar utan att triggra ett riktigt signup-flöde.
        </p>
      </div>

      {msg && (
        <div className="text-xs bg-paper border border-rule p-2 text-[#444]">
          {msg}
        </div>
      )}
      {err && (
        <div className="text-sm text-[#b91c1c] border-l-2 border-[#b91c1c] pl-3 py-2 whitespace-pre-line">
          {err}
        </div>
      )}
    </section>
  );
}

function FormField({
  label, children,
}: { label: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <div className="eyebrow mb-1">{label}</div>
      {children}
    </label>
  );
}


// ---------- Landningssidans gallery ----------

type LandingAsset = {
  id: number;
  slot: string;
  title: string;
  body: string;
  chip: string;
  chip_color: string;
  sort_order: number;
  has_image: boolean;
  image_url: string | null;
};

function LandingGallerySection() {
  const [assets, setAssets] = useState<LandingAsset[] | null>(null);
  const [err, setErr] = useState<string | null>(null);

  async function reload() {
    try {
      const rows = await api<LandingAsset[]>("/admin/landing/gallery");
      setAssets(rows);
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    }
  }

  useEffect(() => {
    reload();
  }, []);

  if (err) {
    return (
      <section className="bg-white rounded-xl border border-slate-200 p-4">
        <h2 className="font-medium mb-2 flex items-center gap-2">
          <Image className="w-4 h-4" /> Landningssidans skärmdumpar
        </h2>
        <div className="text-xs text-rose-700">{err}</div>
      </section>
    );
  }

  if (assets === null) {
    return (
      <section className="bg-white rounded-xl border border-slate-200 p-4">
        <h2 className="font-medium mb-2 flex items-center gap-2">
          <Image className="w-4 h-4" /> Landningssidans skärmdumpar
        </h2>
        <div className="text-xs text-slate-500 flex items-center gap-2">
          <Loader2 className="w-3 h-3 animate-spin" /> Laddar…
        </div>
      </section>
    );
  }

  return (
    <section className="bg-white rounded-xl border border-slate-200 p-4 space-y-3">
      <div>
        <h2 className="font-medium flex items-center gap-2">
          <Image className="w-4 h-4" /> Landningssidans skärmdumpar
        </h2>
        <p className="text-xs text-slate-500 mt-1">
          Sex slots i "Vyerna"-galleriet på landningssidan. Ladda upp en
          PNG/JPEG (max 5 MB) per slot. Tomma slots visas som
          placeholder-kort.
        </p>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        {assets.map((a) => (
          <LandingAssetEditor
            key={a.id}
            asset={a}
            onSaved={reload}
          />
        ))}
      </div>
    </section>
  );
}

function LandingAssetEditor({
  asset, onSaved,
}: { asset: LandingAsset; onSaved: () => void }) {
  const [title, setTitle] = useState(asset.title);
  const [body, setBody] = useState(asset.body);
  const [chip, setChip] = useState(asset.chip);
  const [chipColor, setChipColor] = useState(asset.chip_color);
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  const previewUrl = file
    ? URL.createObjectURL(file)
    : asset.has_image && asset.image_url
    ? `${getApiBase()}${asset.image_url}?v=${asset.id}-${asset.title}`
    : null;

  async function save() {
    setBusy(true); setMsg(null);
    try {
      const form = new FormData();
      form.set("title", title);
      form.set("body", body);
      form.set("chip", chip);
      form.set("chip_color", chipColor);
      form.set("sort_order", String(asset.sort_order));
      if (file) form.set("image", file);
      const tok = getToken();
      const r = await fetch(
        `${getApiBase()}/admin/landing/gallery/${asset.id}`,
        {
          method: "PUT",
          body: form,
          headers: tok ? { Authorization: `Bearer ${tok}` } : {},
        },
      );
      if (!r.ok) {
        let detail = `${r.status}`;
        try {
          const j = await r.json();
          detail = j.detail || detail;
        } catch {/* */}
        throw new Error(detail);
      }
      setFile(null);
      setMsg("Sparat ✓");
      onSaved();
    } catch (e) {
      setMsg(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function clearImage() {
    if (!confirm(`Ta bort bild från "${asset.title}"?`)) return;
    setBusy(true); setMsg(null);
    try {
      await api(`/admin/landing/gallery/${asset.id}/image`, {
        method: "DELETE",
      });
      setFile(null);
      onSaved();
    } catch (e) {
      setMsg(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="border border-slate-200 rounded-lg p-3 space-y-2">
      <div className="flex items-center justify-between gap-2">
        <div className="text-xs eyebrow">{asset.slot}</div>
        {asset.has_image && (
          <button
            onClick={clearImage}
            disabled={busy}
            className="text-xs text-rose-700 hover:underline disabled:opacity-50"
          >
            Ta bort bild
          </button>
        )}
      </div>
      <div className="aspect-[4/3] bg-slate-50 border border-slate-200 rounded overflow-hidden flex items-center justify-center">
        {previewUrl ? (
          <img
            src={previewUrl}
            alt={title}
            className="w-full h-full object-contain"
          />
        ) : (
          <div className="text-xs text-slate-400 text-center px-3">
            Ingen bild uppladdad — visas som placeholder på landningssidan.
          </div>
        )}
      </div>
      <label className="block text-xs">
        <input
          type="file"
          accept="image/png,image/jpeg,image/webp,image/gif"
          onChange={(e) => setFile(e.target.files?.[0] || null)}
          className="block w-full text-xs"
        />
      </label>
      <div className="grid grid-cols-3 gap-2">
        <input
          value={chip}
          onChange={(e) => setChip(e.target.value.slice(0, 4))}
          placeholder="Chip"
          className="border border-slate-300 rounded px-2 py-1 text-sm"
        />
        <select
          value={chipColor}
          onChange={(e) => setChipColor(e.target.value)}
          className="border border-slate-300 rounded px-2 py-1 text-sm col-span-2"
        >
          <option value="grund">grund</option>
          <option value="fordj">fordj</option>
          <option value="expert">expert</option>
          <option value="konto">konto</option>
          <option value="risk">risk</option>
          <option value="special">special</option>
        </select>
      </div>
      <input
        value={title}
        onChange={(e) => setTitle(e.target.value)}
        placeholder="Titel"
        className="w-full border border-slate-300 rounded px-2 py-1 text-sm"
      />
      <textarea
        value={body}
        onChange={(e) => setBody(e.target.value)}
        placeholder="Beskrivande text"
        rows={2}
        className="w-full border border-slate-300 rounded px-2 py-1 text-sm"
      />
      <div className="flex items-center gap-2">
        <button
          onClick={save}
          disabled={busy}
          className="flex items-center gap-1 bg-ink text-white text-sm rounded px-3 py-1.5 hover:opacity-90 disabled:opacity-50"
        >
          {busy ? <Loader2 className="w-3 h-3 animate-spin" /> : <Upload className="w-3 h-3" />}
          {file ? "Ladda upp + spara" : "Spara"}
        </button>
        {msg && (
          <span className="text-xs text-slate-600">{msg}</span>
        )}
      </div>
    </div>
  );
}


// ---------- Landings-variant (A/B-test) ----------

function LandingVariantSection() {
  const [variant, setVariant] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  useEffect(() => {
    api<{ variant: string }>("/landing/variant")
      .then((r) => setVariant(r.variant))
      .catch(() => setVariant("default"));
  }, []);

  async function setTo(v: "default" | "c") {
    setBusy(true);
    setMsg(null);
    try {
      const r = await api<{ variant: string }>("/admin/landing/variant", {
        method: "PUT",
        body: JSON.stringify({ variant: v }),
      });
      setVariant(r.variant);
      setMsg(
        `Aktiv variant: ${r.variant === "c" ? "Variant C (SaaS-stil)" : "Standard (paper-stil)"}.`,
      );
    } catch (e) {
      setMsg(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="bg-white rounded-xl border border-slate-200 p-4 space-y-3">
      <div>
        <h2 className="font-medium flex items-center gap-2">
          <ShieldCheck className="w-4 h-4" /> Landningssidans variant (A/B)
        </h2>
        <p className="text-xs text-slate-500 mt-1">
          Två landings-designer finns. Standard är paper-stilen vi byggt
          tillsammans; Variant C är SaaS/dashboard-stilen som testas mot
          en annan tonalitet. Toggle-bytet slår igenom direkt — inga
          revision-byten behövs.
        </p>
      </div>
      <div className="flex items-center gap-3 flex-wrap">
        <div className="text-sm">
          <span className="text-slate-500">Aktiv:</span>{" "}
          {variant === null ? (
            <span className="text-slate-400">laddar…</span>
          ) : (
            <span className="font-medium">
              {variant === "c" ? "Variant C (SaaS)" : "Standard (paper)"}
            </span>
          )}
        </div>
        <button
          type="button"
          onClick={() => setTo("default")}
          disabled={busy || variant === "default"}
          className="btn-outline rounded-md px-3 py-1.5 text-sm disabled:opacity-50"
        >
          Sätt Standard
        </button>
        <button
          type="button"
          onClick={() => setTo("c")}
          disabled={busy || variant === "c"}
          className="btn-dark rounded-md px-3 py-1.5 text-sm disabled:opacity-50"
        >
          Sätt Variant C
        </button>
        {busy && (
          <span className="text-xs text-slate-500 flex items-center gap-1">
            <Loader2 className="w-3 h-3 animate-spin" /> Sparar…
          </span>
        )}
        {msg && <span className="text-xs text-slate-600">{msg}</span>}
      </div>
      <p className="text-xs text-slate-500">
        Tips: öppna ekonomilabbet.org i en privat flik efter byte för
        att slippa cachning.
      </p>
    </section>
  );
}

// ---------- Finnhub (aktiekurser) ----------

type FinnhubKeyStatus = {
  configured: boolean;
  source: string;     // "db" | "env" | ""
  preview: string;
};

type FinnhubTestResult = {
  ok: boolean;
  ticker?: string;
  last?: number;
  change_pct?: number | null;
  ts?: string;
  error?: string;
};

function FinnhubSection() {
  const [status, setStatus] = useState<FinnhubKeyStatus | null>(null);
  const [newKey, setNewKey] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [testResult, setTestResult] = useState<FinnhubTestResult | null>(null);

  async function reload() {
    try {
      const r = await api<FinnhubKeyStatus>("/admin/ai/finnhub-key");
      setStatus(r);
    } catch (e) {
      setMsg(e instanceof Error ? e.message : String(e));
    }
  }

  useEffect(() => { reload(); }, []);

  async function save() {
    if (!newKey.trim() || newKey.trim().length < 10) {
      setMsg("Nyckeln ser för kort ut. Hämta från finnhub.io/dashboard.");
      return;
    }
    setBusy(true); setMsg(null); setTestResult(null);
    try {
      const r = await api<FinnhubKeyStatus>("/admin/ai/finnhub-key", {
        method: "POST",
        body: JSON.stringify({ key: newKey.trim() }),
      });
      setStatus(r);
      setNewKey("");
      setMsg("Nyckel sparad. Klicka 'Testa nyckel' för att verifiera.");
    } catch (e) {
      setMsg(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function remove() {
    if (!confirm(
      "Radera Finnhub-nyckeln? Aktiekurserna faller tillbaka till mock-" +
      "providern (slumpgenererade testpriser) tills en ny nyckel " +
      "läggs in eller FINNHUB_API_KEY-env är satt.",
    )) return;
    setBusy(true); setMsg(null);
    try {
      const r = await api<FinnhubKeyStatus>("/admin/ai/finnhub-key", {
        method: "DELETE",
      });
      setStatus(r);
      setMsg("Nyckeln raderad.");
    } catch (e) {
      setMsg(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function testKey() {
    setBusy(true); setMsg(null); setTestResult(null);
    try {
      const r = await api<FinnhubTestResult>("/admin/ai/finnhub-test", {
        method: "POST",
      });
      setTestResult(r);
    } catch (e) {
      setMsg(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="bg-white rounded-xl border border-slate-200 p-5 space-y-4">
      <div className="flex items-center gap-2">
        <Key className="w-5 h-5 text-brand-600" />
        <h2 className="font-medium">Finnhub API-nyckel (aktiekurser)</h2>
      </div>
      <div className="text-sm text-slate-700 space-y-1">
        <div>
          Status:{" "}
          {status?.configured ? (
            <span className="font-medium text-emerald-700">
              Konfigurerad {status.preview && `(${status.preview})`}
            </span>
          ) : (
            <span className="font-medium text-amber-700">
              Saknas — kurser visas från mock-data tills nyckel läggs in
            </span>
          )}
        </div>
        {status?.source && (
          <div className="text-xs text-slate-500">
            Källa:{" "}
            {status.source === "db"
              ? "sparad via detta formulär"
              : "FINNHUB_API_KEY (miljövariabel)"}
          </div>
        )}
      </div>
      <div className="space-y-2">
        <label className="block text-xs font-medium text-slate-600">
          {status?.configured ? "Byt nyckel" : "Lägg in nyckel"}
        </label>
        <div className="flex gap-2">
          <input
            type="password"
            value={newKey}
            onChange={(e) => setNewKey(e.target.value)}
            placeholder="t.ex. cnp9j8pr01qkvl4t1l3gcnp9j8pr01qkvl4t1l40"
            className="flex-1 border border-slate-300 rounded px-3 py-2 text-sm font-mono"
            disabled={busy}
            autoComplete="off"
            spellCheck={false}
          />
          <button
            onClick={save}
            disabled={busy || !newKey.trim()}
            className="btn-dark rounded-md px-4 py-2 text-sm font-medium disabled:opacity-50 flex items-center gap-2"
          >
            {busy ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <Check className="w-4 h-4" />
            )}
            Spara
          </button>
        </div>
        <p className="text-xs text-slate-500">
          Skapa gratis konto på{" "}
          <a
            href="https://finnhub.io/register"
            target="_blank" rel="noreferrer"
            className="underline text-brand-700"
          >
            finnhub.io
          </a>
          {" "}— gratis nivå räcker (60 anrop/min, vi använder ~30/poll).
          Nyckeln lagras i master-DB och används av aktiepollern.
        </p>
        <div className="flex gap-2 items-center flex-wrap">
          {status?.configured && (
            <button
              onClick={testKey}
              disabled={busy}
              className="text-xs bg-emerald-50 border border-emerald-300 text-emerald-800 hover:bg-emerald-100 px-3 py-1.5 rounded-md disabled:opacity-50"
            >
              Testa nyckel (hämta VOLV-B.ST)
            </button>
          )}
          {status?.source === "db" && (
            <button
              onClick={remove}
              disabled={busy}
              className="text-xs text-rose-600 hover:text-rose-800 flex items-center gap-1 disabled:opacity-50"
            >
              <Trash2 className="w-3 h-3" />
              Radera sparad nyckel
            </button>
          )}
        </div>
        {testResult && (
          <div className={`text-xs rounded p-2 ${
            testResult.ok
              ? "bg-emerald-50 border border-emerald-200 text-emerald-900"
              : "bg-rose-50 border border-rose-200 text-rose-900"
          }`}>
            {testResult.ok ? (
              <>
                ✓ Fungerar! {testResult.ticker} = {testResult.last} SEK
                {testResult.change_pct !== null && testResult.change_pct !== undefined && (
                  <> ({testResult.change_pct >= 0 ? "+" : ""}{testResult.change_pct.toFixed(2)} %)</>
                )}
                {testResult.ts && <> · {new Date(testResult.ts).toLocaleString("sv-SE")}</>}
              </>
            ) : (
              <>✗ {testResult.error}</>
            )}
          </div>
        )}
        {msg && (
          <div className="text-xs bg-slate-50 border border-slate-200 rounded p-2 text-slate-700">
            {msg}
          </div>
        )}
      </div>
    </section>
  );
}

// ---------- Klassdisplay-inställningar (Wellbeing-events) ----------

type ClassDisplaySettings = {
  teacher_id: number;
  teacher_email: string;
  teacher_name: string;
  class_list_enabled: boolean;
  show_full_names: boolean;
  invite_classmates_enabled: boolean;
  cost_split_model: string;
  class_event_creation_enabled: boolean;
  max_invites_per_week: number;
};

function ClassDisplaySection() {
  const [rows, setRows] = useState<ClassDisplaySettings[]>([]);
  const [loading, setLoading] = useState(true);
  const [busyId, setBusyId] = useState<number | null>(null);
  const [msg, setMsg] = useState<string | null>(null);

  async function reload() {
    setLoading(true);
    try {
      const r = await api<ClassDisplaySettings[]>("/admin/ai/class-display");
      setRows(r);
    } catch (e) {
      setMsg(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { reload(); }, []);

  async function update(teacherId: number, patch: Partial<ClassDisplaySettings>) {
    setBusyId(teacherId);
    setMsg(null);
    try {
      await api<ClassDisplaySettings>("/admin/ai/class-display", {
        method: "POST",
        body: JSON.stringify({ teacher_id: teacherId, ...patch }),
      });
      await reload();
    } catch (e) {
      setMsg(e instanceof Error ? e.message : String(e));
    } finally {
      setBusyId(null);
    }
  }

  return (
    <section className="bg-white rounded-xl border border-slate-200 p-5 space-y-4">
      <div className="flex items-center gap-2">
        <ShieldCheck className="w-5 h-5 text-brand-600" />
        <h2 className="font-medium">Klass-funktioner (Wellbeing &amp; events)</h2>
      </div>
      <div className="text-xs text-slate-600">
        Per-lärar-toggles för Wellbeing-events. Default: minimal exponering
        — bara klasskompis-bjudningar är på, klasslista och fullständiga
        namn är av. Eleverna kan inte se varandras Wellbeing förrän
        läraren explicit slår på det.
      </div>

      {loading && <div className="text-sm text-slate-500">Laddar…</div>}
      {msg && (
        <div className="text-xs bg-rose-50 border border-rose-200 rounded p-2 text-rose-900">
          {msg}
        </div>
      )}

      {!loading && rows.length === 0 && (
        <div className="text-sm text-slate-500">Inga lärare hittade.</div>
      )}

      {rows.map((r) => (
        <div key={r.teacher_id} className="border rounded-lg p-3 space-y-2">
          <div className="flex items-center justify-between gap-2">
            <div>
              <div className="font-medium text-sm">{r.teacher_name}</div>
              <div className="text-xs text-slate-500">{r.teacher_email}</div>
            </div>
            {busyId === r.teacher_id && (
              <Loader2 className="w-3 h-3 animate-spin text-slate-400" />
            )}
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-2 text-sm">
            <label className="flex items-center gap-2">
              <input
                type="checkbox"
                checked={r.invite_classmates_enabled}
                onChange={(e) =>
                  update(r.teacher_id, { invite_classmates_enabled: e.target.checked })
                }
                disabled={busyId === r.teacher_id}
              />
              Klasskompis-bjudningar tillåtna
            </label>
            <label className="flex items-center gap-2">
              <input
                type="checkbox"
                checked={r.class_list_enabled}
                onChange={(e) =>
                  update(r.teacher_id, { class_list_enabled: e.target.checked })
                }
                disabled={busyId === r.teacher_id}
              />
              Anonymiserad klasslista (Wellbeing-rangordning)
            </label>
            <label className="flex items-center gap-2">
              <input
                type="checkbox"
                checked={r.show_full_names}
                onChange={(e) =>
                  update(r.teacher_id, { show_full_names: e.target.checked })
                }
                disabled={busyId === r.teacher_id || !r.class_list_enabled}
              />
              <span className={!r.class_list_enabled ? "text-slate-400" : ""}>
                Visa namn (kräver elev-opt-in)
              </span>
            </label>
            <label className="flex items-center gap-2">
              <input
                type="checkbox"
                checked={r.class_event_creation_enabled}
                onChange={(e) =>
                  update(r.teacher_id, {
                    class_event_creation_enabled: e.target.checked,
                  })
                }
                disabled={busyId === r.teacher_id}
              />
              Klassgemensamma events (V2)
            </label>
            <label className="flex items-center gap-2">
              Kostnadsmodell:
              <select
                value={r.cost_split_model}
                onChange={(e) =>
                  update(r.teacher_id, { cost_split_model: e.target.value })
                }
                disabled={busyId === r.teacher_id}
                className="border rounded px-2 py-1 text-xs"
              >
                <option value="split">Dela jämnt</option>
                <option value="inviter_pays">Bjudaren betalar</option>
                <option value="each_pays_own">Var och en betalar sig själv</option>
              </select>
            </label>
            <label className="flex items-center gap-2">
              Max bjudningar/vecka:
              <input
                type="number"
                min={0} max={50}
                value={r.max_invites_per_week}
                onChange={(e) =>
                  update(r.teacher_id, {
                    max_invites_per_week: parseInt(e.target.value || "0"),
                  })
                }
                disabled={busyId === r.teacher_id}
                className="border rounded px-2 py-1 text-xs w-16"
              />
            </label>
          </div>
        </div>
      ))}
    </section>
  );
}
