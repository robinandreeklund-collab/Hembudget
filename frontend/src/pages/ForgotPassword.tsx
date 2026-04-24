import { useState } from "react";
import { Link } from "react-router-dom";
import { ArrowLeft, Mail } from "lucide-react";
import { api, ApiError } from "@/api/client";
import { useAuth } from "@/hooks/useAuth";
import { Turnstile } from "@/components/Turnstile";

export default function ForgotPassword() {
  const { schoolStatus } = useAuth();
  const [email, setEmail] = useState("");
  const [turnstileToken, setTurnstileToken] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);
  const siteKey = schoolStatus?.turnstile_site_key ?? "";

  async function handle(e: React.FormEvent) {
    e.preventDefault();
    setErr(null);
    if (siteKey && !turnstileToken)
      return setErr("Säkerhetskontroll pågår — vänta en sekund.");
    setBusy(true);
    try {
      await api("/teacher/request-password-reset", {
        method: "POST",
        body: JSON.stringify({ email }),
        turnstileToken: turnstileToken ?? undefined,
      });
      setDone(true);
    } catch (e: unknown) {
      if (e instanceof ApiError && e.status === 503) {
        setErr("E-postutskick är inte påslaget. Kontakta administratören.");
      } else if (e instanceof ApiError && e.status === 429) {
        setErr("För många försök. Vänta en stund.");
      } else {
        setErr(e instanceof Error ? e.message : "Något gick fel.");
      }
    } finally {
      setBusy(false);
    }
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
        {done ? (
          <div className="bg-white rounded-2xl shadow-xl p-8 border border-slate-200">
            <div className="flex items-center gap-2 text-brand-600 mb-3">
              <Mail className="w-6 h-6" />
              <h1 className="text-xl font-semibold">Kolla din inkorg</h1>
            </div>
            <p className="text-sm text-slate-700 leading-relaxed">
              Om ett konto finns för{" "}
              <span className="font-semibold">{email}</span> har vi skickat
              en länk för att välja nytt lösenord. Länken gäller i 60 minuter.
            </p>
            <p className="text-sm text-slate-500 mt-4">
              Hittar du inte mailet? Kolla skräpposten.
            </p>
          </div>
        ) : (
          <form
            onSubmit={handle}
            className="bg-white rounded-2xl shadow-xl p-8 space-y-4 border border-slate-200"
          >
            <h1 className="text-xl font-semibold">Glömt lösenord?</h1>
            <p className="text-sm text-slate-600">
              Ange din e-post så skickar vi en länk för att välja ett nytt.
            </p>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="E-post"
              autoFocus
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
              {busy ? "Skickar…" : "Skicka länk"}
            </button>
          </form>
        )}
      </div>
    </div>
  );
}
