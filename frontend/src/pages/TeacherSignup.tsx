import { useState } from "react";
import { Link } from "react-router-dom";
import { api, ApiError } from "@/api/client";
import { useAuth } from "@/hooks/useAuth";
import { Turnstile } from "@/components/Turnstile";
import { AuthShell, PaperButton, PaperInput } from "@/components/paper";

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
      <AuthShell
        eyebrow="Snart klart"
        title="Kolla din inkorg"
        back="/login/teacher"
        backLabel="Tillbaka till inloggning"
      >
        <p className="body-prose text-sm">
          Vi har skickat ett bekräftelsemail till{" "}
          <span className="kbd">{email}</span>. Klicka på länken i mailet
          för att aktivera ditt konto. Länken är giltig i 24 timmar.
        </p>
        <p className="text-xs text-[#888] serif-italic mt-3">
          Hittar du inte mailet? Kolla skräpposten.
        </p>
        <Link
          to="/login/teacher"
          className="btn-dark mt-6 inline-block w-full text-center px-5 py-3 rounded-md"
        >
          Till inloggning
        </Link>
      </AuthShell>
    );
  }

  return (
    <AuthShell
      eyebrow="Ekonomilabbet"
      title="Skapa lärarkonto"
      intro="Skapa ett konto och bekräfta din e-post så är du igång."
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
        <PaperInput
          type="text"
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="Namn"
        />
        <PaperInput
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          placeholder="Lösenord (minst 8 tecken)"
        />
        <PaperInput
          type="password"
          value={confirm}
          onChange={(e) => setConfirm(e.target.value)}
          placeholder="Bekräfta lösenord"
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
          {busy ? "Skapar konto…" : "Skapa konto"}
        </PaperButton>
      </form>
    </AuthShell>
  );
}
