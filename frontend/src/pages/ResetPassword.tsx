import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { CheckCircle2 } from "lucide-react";
import { api, ApiError } from "@/api/client";

export default function ResetPassword() {
  const [params] = useSearchParams();
  const token = params.get("token") ?? "";
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);

  async function handle(e: React.FormEvent) {
    e.preventDefault();
    setErr(null);
    if (!token) return setErr("Länken saknar token.");
    if (password.length < 8) return setErr("Lösenord måste vara minst 8 tecken.");
    if (password !== confirm) return setErr("Lösenorden matchar inte.");
    setBusy(true);
    try {
      await api("/teacher/reset-password", {
        method: "POST",
        body: JSON.stringify({ token, password }),
      });
      setDone(true);
    } catch (e: unknown) {
      if (e instanceof ApiError) {
        if (e.status === 410) {
          setErr("Länken har gått ut eller redan använts. Begär en ny.");
        } else if (e.status === 404) {
          setErr("Länken är ogiltig.");
        } else if (e.status === 429) {
          setErr("För många försök. Vänta en stund.");
        } else {
          setErr(e.message);
        }
      } else {
        setErr(e instanceof Error ? e.message : "Oväntat fel.");
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 to-brand-50 grid place-items-center p-6">
      <div className="w-full max-w-md bg-white rounded-2xl shadow-xl p-8 border border-slate-200">
        {done ? (
          <div className="text-center">
            <CheckCircle2 className="w-12 h-12 text-emerald-500 mx-auto" />
            <h1 className="text-xl font-semibold mt-3">Lösenord uppdaterat</h1>
            <p className="text-sm text-slate-600 mt-2">
              Du kan nu logga in med ditt nya lösenord.
            </p>
            <Link
              to="/login/teacher"
              className="mt-6 inline-block w-full bg-brand-600 hover:bg-brand-700 text-white rounded-lg py-2.5 font-medium"
            >
              Till inloggning
            </Link>
          </div>
        ) : (
          <form onSubmit={handle} className="space-y-4">
            <h1 className="text-xl font-semibold">Välj nytt lösenord</h1>
            <p className="text-sm text-slate-600">
              Minst 8 tecken. Länken gäller bara en gång.
            </p>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="Nytt lösenord"
              autoFocus
              className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-brand-500 outline-none"
            />
            <input
              type="password"
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
              placeholder="Bekräfta lösenord"
              className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-brand-500 outline-none"
            />
            {err && <div className="text-sm text-rose-600">{err}</div>}
            <button
              disabled={busy}
              className="w-full bg-brand-600 hover:bg-brand-700 text-white rounded-lg py-2.5 font-medium disabled:opacity-50"
            >
              {busy ? "Uppdaterar…" : "Spara nytt lösenord"}
            </button>
          </form>
        )}
      </div>
    </div>
  );
}
