import { useState } from "react";
import { useAuth } from "@/hooks/useAuth";
import { Lock } from "lucide-react";

export default function Login() {
  const { initialized, login, initialize } = useAuth();
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const needsInit = initialized === false;

  async function handle(e: React.FormEvent) {
    e.preventDefault();
    setErr(null);
    if (needsInit) {
      if (password.length < 8) return setErr("Lösenord måste vara minst 8 tecken.");
      if (password !== confirm) return setErr("Lösenorden matchar inte.");
    }
    setBusy(true);
    try {
      needsInit ? await initialize(password) : await login(password);
      window.location.reload();
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "Inloggning misslyckades");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="h-full grid place-items-center bg-gradient-to-br from-slate-50 to-brand-50">
      <form onSubmit={handle} className="bg-white rounded-2xl shadow-lg p-8 w-96 space-y-4 border border-slate-200">
        <div className="flex items-center gap-2 text-brand-600">
          <Lock className="w-5 h-5" />
          <h1 className="text-xl font-semibold">Hembudget</h1>
        </div>
        <p className="text-sm text-slate-500">
          {needsInit
            ? "Välj ett master-lösenord. Det används för att kryptera din databas — det kan inte återställas."
            : "Logga in med ditt master-lösenord."}
        </p>
        <input
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          placeholder="Lösenord"
          autoFocus
          className="w-full px-3 py-2 border rounded-lg border-slate-300 focus:ring-2 focus:ring-brand-500 outline-none"
        />
        {needsInit && (
          <input
            type="password"
            value={confirm}
            onChange={(e) => setConfirm(e.target.value)}
            placeholder="Bekräfta lösenord"
            className="w-full px-3 py-2 border rounded-lg border-slate-300 focus:ring-2 focus:ring-brand-500 outline-none"
          />
        )}
        {err && <div className="text-sm text-rose-600">{err}</div>}
        <button
          disabled={busy}
          className="w-full bg-brand-600 text-white rounded-lg py-2 font-medium hover:bg-brand-700 disabled:opacity-50"
        >
          {busy ? "Arbetar…" : needsInit ? "Skapa och logga in" : "Logga in"}
        </button>
      </form>
    </div>
  );
}
