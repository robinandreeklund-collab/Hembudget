import { useState } from "react";
import { Link } from "react-router-dom";
import { ArrowLeft, Mail, Users } from "lucide-react";
import { api, ApiError } from "@/api/client";
import { useAuth } from "@/hooks/useAuth";
import { Turnstile } from "@/components/Turnstile";

export default function TeacherSignup() {
  const { schoolStatus } = useAuth();
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [turnstileToken, setTurnstileToken] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);
  const siteKey = schoolStatus?.turnstile_site_key ?? "";

  async function handle(e: React.FormEvent) {
    e.preventDefault();
    setErr(null);
    if (password.length < 8) return setErr("Lösenord måste vara minst 8 tecken.");
    if (password !== confirm) return setErr("Lösenorden matchar inte.");
    if (siteKey && !turnstileToken)
      return setErr("Säkerhetskontroll pågår — vänta en sekund.");
    setBusy(true);
    try {
      await api("/teacher/signup", {
        method: "POST",
        body: JSON.stringify({ email, password, name: name || "Lärare" }),
        turnstileToken: turnstileToken ?? undefined,
      });
      setDone(true);
    } catch (e: unknown) {
      if (e instanceof ApiError && e.status === 503) {
        setErr(
          "E-postutskick är inte påslaget på servern. Kontakta administratören.",
        );
      } else if (e instanceof ApiError && e.status === 429) {
        setErr("För många försök. Vänta en stund och försök igen.");
      } else {
        setErr(e instanceof Error ? e.message : "Registrering misslyckades");
      }
    } finally {
      setBusy(false);
    }
  }

  if (done) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-slate-50 to-brand-50 grid place-items-center p-6">
        <div className="w-full max-w-md bg-white rounded-2xl shadow-xl p-8 border border-slate-200">
          <div className="flex items-center gap-2 text-brand-600 mb-3">
            <Mail className="w-6 h-6" />
            <h1 className="text-xl font-semibold">Kolla din inkorg</h1>
          </div>
          <p className="text-sm text-slate-700 leading-relaxed">
            Vi har skickat ett bekräftelsemail till{" "}
            <span className="font-semibold">{email}</span>. Klicka på länken
            i mailet för att aktivera ditt konto. Länken är giltig i 24 timmar.
          </p>
          <p className="text-sm text-slate-500 mt-4">
            Hittar du inte mailet? Kolla skräpposten.
          </p>
          <Link
            to="/login/teacher"
            className="mt-6 block text-center w-full bg-brand-600 hover:bg-brand-700 text-white rounded-lg py-2.5 font-medium"
          >
            Till inloggning
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 to-brand-50 grid place-items-center p-6">
      <div className="w-full max-w-md">
        <Link
          to="/login/teacher"
          className="text-sm text-slate-600 hover:text-brand-700 flex items-center gap-1 mb-4"
        >
          <ArrowLeft className="w-4 h-4" /> Tillbaka till inloggning
        </Link>
        <form
          onSubmit={handle}
          className="bg-white rounded-2xl shadow-xl p-8 space-y-4 border border-slate-200"
        >
          <div className="flex items-center gap-2 text-brand-600">
            <Users className="w-6 h-6" />
            <h1 className="text-xl font-semibold">Skapa lärarkonto</h1>
          </div>
          <p className="text-sm text-slate-600">
            Skapa ett konto och bekräfta din e-post så är du igång.
          </p>
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="E-post"
            autoFocus
            className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-brand-500 outline-none"
          />
          <input
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Namn"
            className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-brand-500 outline-none"
          />
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="Lösenord (minst 8 tecken)"
            className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-brand-500 outline-none"
          />
          <input
            type="password"
            value={confirm}
            onChange={(e) => setConfirm(e.target.value)}
            placeholder="Bekräfta lösenord"
            className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-brand-500 outline-none"
          />
          <Turnstile
            siteKey={siteKey}
            onToken={setTurnstileToken}
            onExpire={() => setTurnstileToken(null)}
          />
          {err && <div className="text-sm text-rose-600">{err}</div>}
          <button
            disabled={busy || (Boolean(siteKey) && !turnstileToken)}
            className="w-full bg-brand-600 hover:bg-brand-700 text-white rounded-lg py-2.5 font-medium disabled:opacity-50"
          >
            {busy ? "Skapar konto…" : "Skapa konto"}
          </button>
        </form>
      </div>
    </div>
  );
}
