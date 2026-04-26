import { useState } from "react";
import { api, ApiError } from "@/api/client";
import { useAuth } from "@/hooks/useAuth";
import { Turnstile } from "@/components/Turnstile";
import { AuthShell, PaperButton, PaperInput } from "@/components/paper";

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

  if (done) {
    return (
      <AuthShell
        eyebrow="Snart klart"
        title="Kolla din inkorg"
        back="/login/teacher"
        backLabel="Tillbaka till inloggning"
      >
        <p className="body-prose text-sm">
          Om ett konto finns för <span className="kbd">{email}</span> har
          vi skickat en länk för att välja nytt lösenord. Länken gäller i
          60 minuter.
        </p>
        <p className="text-xs text-[#888] serif-italic mt-3">
          Hittar du inte mailet? Kolla skräpposten.
        </p>
      </AuthShell>
    );
  }

  return (
    <AuthShell
      title="Glömt lösenord?"
      intro="Ange din e-post så skickar vi en länk för att välja ett nytt."
      back="/login/teacher"
      backLabel="Tillbaka till inloggning"
    >
      <form onSubmit={handle} className="space-y-3">
        <PaperInput
          type="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder="E-post"
          autoFocus
        />
        <Turnstile
          siteKey={siteKey}
          onToken={setTurnstileToken}
          onExpire={() => setTurnstileToken(null)}
        />
        {err && (
          <div className="text-sm text-[#b91c1c] border-l-2 border-[#b91c1c] pl-3 py-1">
            {err}
          </div>
        )}
        <PaperButton
          type="submit"
          disabled={busy || (Boolean(siteKey) && !turnstileToken)}
          className="w-full justify-center disabled:opacity-50"
        >
          {busy ? "Skickar…" : "Skicka länk"}
        </PaperButton>
      </form>
    </AuthShell>
  );
}
