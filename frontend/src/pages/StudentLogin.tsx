import { useState } from "react";
import { Link } from "react-router-dom";
import { useAuth } from "@/hooks/useAuth";
import { Turnstile } from "@/components/Turnstile";
import { EditorialAuthShell } from "@/components/editorial/EditorialAuthShell";
import { LiveTime, LiveSecondsCountdown } from "@/components/editorial/LiveClock";

export default function StudentLogin() {
  const { studentLogin, schoolStatus } = useAuth();
  const [code, setCode] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [turnstileToken, setTurnstileToken] = useState<string | null>(null);
  const siteKey = schoolStatus?.turnstile_site_key ?? "";

  async function handle(e: React.FormEvent) {
    e.preventDefault();
    setErr(null);
    setBusy(true);
    try {
      await studentLogin(
        code.toUpperCase().trim(),
        turnstileToken ?? undefined,
      );
      window.location.reload();
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "Inloggning misslyckades");
    } finally {
      setBusy(false);
    }
  }

  return (
    <EditorialAuthShell
      topNavRight={
        <Link to="/login" className="ed-top-link">Tillbaka</Link>
      }
    >
      <div className="ed-eyebrow">Elevinloggning · Sex tecken</div>

      <div className="ed-clock">
        <div className="ed-clock-time">
          Klockan är <LiveTime />.
        </div>
        <LiveSecondsCountdown start={6} />
      </div>

      <p className="ed-subhead">
        Skriv din <em>sex-teckens-kod</em> som du fått av din lärare eller
        förälder. Inget lösenord, ingen e-post — bara koden.
      </p>

      <div className="ed-card">
        <form onSubmit={handle} className="ed-form" noValidate>
          <input
            className="ed-input ed-input-code"
            type="text"
            value={code}
            onChange={(e) => setCode(e.target.value.toUpperCase())}
            placeholder="ABC123"
            autoFocus
            maxLength={6}
            inputMode="text"
            autoComplete="off"
            spellCheck={false}
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
            disabled={busy || code.length < 4}
          >
            {busy ? "Loggar in…" : "Logga in"}
            <span className="ed-btn-arrow">→</span>
          </button>
          <div className="ed-foot-note">
            Är du lärare eller skolledare?{" "}
            <Link to="/login/teacher" className="ed-foot-link">
              Lärarinloggning
            </Link>
          </div>
        </form>
      </div>
    </EditorialAuthShell>
  );
}
