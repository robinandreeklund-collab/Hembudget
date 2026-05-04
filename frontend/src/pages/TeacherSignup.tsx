import { useState } from "react";
import { Link } from "react-router-dom";
import { api, ApiError } from "@/api/client";
import { useAuth } from "@/hooks/useAuth";
import { Turnstile } from "@/components/Turnstile";
import { EditorialAuthShell } from "@/components/editorial/EditorialAuthShell";
import { AuthAwareTopLinks } from "@/components/editorial/AuthAwareTopLinks";
import { LiveTime, LiveCountdown } from "@/components/editorial/LiveClock";

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
      <EditorialAuthShell
        topNavRight={
          <Link to="/login" className="ed-top-link">Logga in</Link>
        }
      >
        <div className="ed-eyebrow">Snart klart · Kolla inkorgen</div>
        <h1 className="ed-headline">
          Mailet är på <em>väg</em>.
        </h1>
        <p className="ed-subhead">
          Vi har skickat ett bekräftelsemail till <strong>{email}</strong>.
          Klicka på länken så är ditt lärarkonto aktivt. Länken är giltig i 24 timmar.
          Hittar du inte mailet? Kolla skräpposten.
        </p>
        <Link to="/login" className="ed-btn" style={{ textDecoration: "none" }}>
          Till inloggning <span className="ed-btn-arrow">→</span>
        </Link>
      </EditorialAuthShell>
    );
  }

  return (
    <EditorialAuthShell
      topNavRight={<AuthAwareTopLinks />}
    >
      <div className="ed-eyebrow">Skapa lärarkonto · Vol. 01</div>

      <div className="ed-clock">
        <div className="ed-clock-time">
          Klockan är <LiveTime />.
        </div>
        <LiveCountdown minutes={1} />
      </div>

      <p className="ed-subhead">
        Ett konto, ett bekräftelsemail. <em>Sextio sekunder</em> till klassen
        är på plats — sen ser du varje elevs vecka som en pentagon.
      </p>

      <div className="ed-card">
        <form onSubmit={handle} className="ed-form" noValidate>
          <input
            className="ed-input"
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="E-post · skola eller jobb"
            autoFocus
            required
          />
          <input
            className="ed-input"
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Ditt namn"
          />
          <input
            className="ed-input"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="Lösenord (minst 8 tecken)"
            required
          />
          <input
            className="ed-input"
            type="password"
            value={confirm}
            onChange={(e) => setConfirm(e.target.value)}
            placeholder="Bekräfta lösenord"
            required
          />
          <Turnstile
            siteKey={siteKey}
            onToken={setTurnstileToken}
            onExpire={() => setTurnstileToken(null)}
          />
          {err && <div className="ed-error">{err}</div>}
          <button
            type="submit"
            className="ed-btn"
            disabled={busy || (Boolean(siteKey) && !turnstileToken)}
          >
            {busy ? "Skapar konto…" : "Skapa lärarkonto"}
            <span className="ed-btn-arrow">→</span>
          </button>
          <div className="ed-foot-note">
            Är du istället förälder?{" "}
            <Link to="/signup/parent" className="ed-foot-link">
              Skapa familjekonto
            </Link>
          </div>
        </form>
      </div>
    </EditorialAuthShell>
  );
}
