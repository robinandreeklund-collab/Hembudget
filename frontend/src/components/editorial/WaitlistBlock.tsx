/**
 * WaitlistBlock — intresseanmälan till beta-väntelistan.
 *
 * Visas under beta-kod-fältet på /signup/teacher och /signup/parent.
 * Skickar mail-adress + roll till POST /waitlist/signup. Spam-skyddat
 * via Turnstile (samma site-key som signup) + backend-rate-limit.
 *
 * Designprinciper:
 * - Egen submit-knapp (separat från signup) — eleven kan bara klicka
 *   en av dem
 * - Success-state visar bekräftelse, döljer formuläret
 * - Felhantering · 429/503/network = vänligt felmeddelande
 */
import { useState } from "react";
import { api, ApiError } from "@/api/client";
import { Turnstile } from "@/components/Turnstile";

export function WaitlistBlock({
  role,
  siteKey,
}: {
  role: "teacher" | "parent";
  siteKey: string;
}) {
  const [email, setEmail] = useState("");
  const [token, setToken] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    e.stopPropagation();
    if (!email.trim()) {
      setError("Ange din e-postadress.");
      return;
    }
    if (siteKey && !token) {
      setError("Säkerhetskontroll pågår — vänta en sekund.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await api("/waitlist/signup", {
        method: "POST",
        body: JSON.stringify({
          email: email.trim(),
          role,
        }),
        turnstileToken: token ?? undefined,
      });
      setDone(true);
    } catch (e: unknown) {
      if (e instanceof ApiError && e.status === 429) {
        setError("För många försök. Vänta en stund och försök igen.");
      } else {
        setError(
          e instanceof Error ? e.message : "Anmälan misslyckades. Prova igen.",
        );
      }
    } finally {
      setBusy(false);
    }
  }

  if (done) {
    return (
      <div className="ed-waitlist-block ed-waitlist-done">
        <div className="ed-waitlist-eye">✓ Tack — du står på listan</div>
        <p className="ed-waitlist-help">
          Vi hör av oss till <strong>{email}</strong> så snart vi kan släppa
          in fler.
        </p>
      </div>
    );
  }

  return (
    <div className="ed-waitlist-block">
      <div className="ed-waitlist-eye">○ Väntelistan</div>
      <p className="ed-waitlist-help">
        Annars — sätt upp dig på väntelistan så hör vi av oss så snart vi
        kan släppa in fler.
      </p>
      <div className="ed-waitlist-row">
        <input
          className="ed-input"
          type="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder="din@epost.se"
          autoComplete="email"
          spellCheck={false}
        />
      </div>
      {/* Egen Turnstile-instans så väntelistan inte stör signup-flödet */}
      {siteKey && (
        <div style={{ marginTop: 10 }}>
          <Turnstile
            siteKey={siteKey}
            onToken={setToken}
            onExpire={() => setToken(null)}
          />
        </div>
      )}
      {error && (
        <div className="ed-waitlist-error">{error}</div>
      )}
      <button
        type="button"
        onClick={submit}
        disabled={busy || (Boolean(siteKey) && !token)}
        className="ed-waitlist-btn"
      >
        {busy ? "Skickar…" : "Sätt upp mig på väntelistan"}
      </button>
    </div>
  );
}
