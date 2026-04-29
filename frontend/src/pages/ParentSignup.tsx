import { useState } from "react";
import { Link } from "react-router-dom";
import { api, ApiError } from "@/api/client";
import { useAuth } from "@/hooks/useAuth";
import { Turnstile } from "@/components/Turnstile";
import { EditorialAuthShell } from "@/components/editorial/EditorialAuthShell";
import { LiveTime, LiveCountdown } from "@/components/editorial/LiveClock";

// Tekniskt samma signup-flöde som TeacherSignup, men:
// - postar till /parent/signup (sätter is_family_account=true i DB)
// - copy:n riktas till en förälder, inte till en lärare
// - back-länkar till /login (samma login-form används av båda)
export default function ParentSignup() {
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
      await api("/parent/signup", {
        method: "POST",
        body: JSON.stringify({
          email, password, name: name || "Förälder",
        }),
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
          Klicka på länken så är ditt familjekonto aktivt. Länken är giltig i 24 timmar.
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
      topNavRight={
        <Link to="/login" className="ed-top-link">Logga in</Link>
      }
    >
      <div className="ed-eyebrow">Skapa familjekonto · Vol. 03</div>

      <div className="ed-clock">
        <div className="ed-clock-time">
          Klockan är <LiveTime />.
        </div>
        <LiveCountdown minutes={1} />
      </div>

      <p className="ed-subhead">
        Ett konto för dig — sen lägger du till barnen och de får var sin
        sex-teckens-kod att logga in med. <em>En minut</em> till hela
        familjen är inne.
      </p>

      <div className="ed-card">
        <form onSubmit={handle} className="ed-form" noValidate>
          <input
            className="ed-input"
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="Din e-post"
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
            {busy ? "Skapar konto…" : "Skapa familjekonto"}
            <span className="ed-btn-arrow">→</span>
          </button>
          <div className="ed-foot-note">
            Är du istället lärare?{" "}
            <Link to="/signup/teacher" className="ed-foot-link">
              Skapa lärarkonto
            </Link>
          </div>
        </form>
      </div>
    </EditorialAuthShell>
  );
}
