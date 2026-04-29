import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, ApiError } from "@/api/client";
import { useAuth } from "@/hooks/useAuth";
import { Turnstile } from "@/components/Turnstile";
import { EditorialAuthShell } from "@/components/editorial/EditorialAuthShell";
import { AuthAwareTopLinks } from "@/components/editorial/AuthAwareTopLinks";
import { LiveTime, LiveCountdown } from "@/components/editorial/LiveClock";

type Mode = "login" | "bootstrap";

export default function TeacherLogin() {
  const { schoolMode, schoolStatus, teacherLogin, teacherBootstrap } = useAuth();
  const [mode, setMode] = useState<Mode>("login");
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [secret, setSecret] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [turnstileToken, setTurnstileToken] = useState<string | null>(null);
  const [unverified, setUnverified] = useState(false);
  const [resendMsg, setResendMsg] = useState<string | null>(null);
  const siteKey = schoolStatus?.turnstile_site_key ?? "";

  // Om ingen lärare finns än, välj bootstrap automatiskt
  useEffect(() => {
    if (schoolMode && schoolStatus?.bootstrap_ready) {
      setMode("bootstrap");
    }
  }, [schoolMode, schoolStatus?.bootstrap_ready]);

  async function handle(e: React.FormEvent) {
    e.preventDefault();
    setErr(null);
    setUnverified(false);
    setResendMsg(null);
    setBusy(true);
    try {
      if (siteKey && !turnstileToken) {
        throw new Error("Säkerhetskontroll pågår — vänta en sekund och försök igen.");
      }
      if (mode === "bootstrap") {
        if (password.length < 8)
          throw new Error("Lösenord måste vara minst 8 tecken.");
        if (password !== confirm)
          throw new Error("Lösenorden matchar inte.");
        await teacherBootstrap(
          secret, email, password, name || "Lärare",
          turnstileToken ?? undefined,
        );
      } else {
        await teacherLogin(email, password, turnstileToken ?? undefined);
      }
      window.location.reload();
    } catch (e: unknown) {
      if (
        e instanceof ApiError &&
        e.status === 403 &&
        typeof e.body === "object" &&
        e.body &&
        (e.body as { detail?: string }).detail === "email_unverified"
      ) {
        setUnverified(true);
        setErr(
          "E-postadressen är inte bekräftad. Klicka på länken vi skickat eller begär ett nytt mail.",
        );
      } else {
        setErr(e instanceof Error ? e.message : "Inloggning misslyckades");
      }
    } finally {
      setBusy(false);
    }
  }

  async function resendVerify() {
    setResendMsg(null);
    try {
      await api("/teacher/request-verify-resend", {
        method: "POST",
        body: JSON.stringify({ email }),
        turnstileToken: turnstileToken ?? undefined,
      });
      setResendMsg("Nytt mail skickat om kontot finns. Kolla inkorgen.");
    } catch (e: unknown) {
      setResendMsg(
        e instanceof ApiError && e.status === 429
          ? "För många försök. Vänta en stund."
          : e instanceof Error
            ? e.message
            : "Kunde inte skicka nytt mail.",
      );
    }
  }

  const isBootstrap = mode === "bootstrap";

  return (
    <EditorialAuthShell topNavRight={<AuthAwareTopLinks />}>
      <div className="ed-eyebrow">
        {isBootstrap ? "Skapa första lärarkontot · Bootstrap" : "Lärarinloggning · Vol. 01"}
      </div>

      <div className="ed-clock">
        <div className="ed-clock-time">
          Klockan är <LiveTime />.
        </div>
        <LiveCountdown minutes={1} />
      </div>

      <p className="ed-subhead">
        {isBootstrap
          ? schoolStatus?.bootstrap_requires_secret
            ? "Du blir super-admin för klassen. Ange bootstrap-koden från administratören och skapa kontot — under en minut till klassens första elev."
            : "Du blir super-admin för klassen. Skapa kontot — under en minut till klassens första elev kan logga in."
          : "Välkommen tillbaka. Logga in så ser du vem som behöver prat innan provet — inte efter."}
      </p>

      <div className="ed-card">
        <form onSubmit={handle} className="ed-form" noValidate>
          {isBootstrap && schoolStatus?.bootstrap_requires_secret && (
            <input
              className="ed-input"
              type="text"
              value={secret}
              onChange={(e) => setSecret(e.target.value)}
              placeholder="Bootstrap-kod"
              autoFocus
              required
            />
          )}
          <input
            className="ed-input"
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder={isBootstrap ? "E-post · skola eller jobb" : "E-post"}
            autoFocus={!isBootstrap || !schoolStatus?.bootstrap_requires_secret}
            required
          />
          {isBootstrap && (
            <input
              className="ed-input"
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Ditt namn"
            />
          )}
          <input
            className="ed-input"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder={isBootstrap ? "Lösenord (minst 8 tecken)" : "Lösenord"}
            required
          />
          {isBootstrap && (
            <input
              className="ed-input"
              type="password"
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
              placeholder="Bekräfta lösenord"
              required
            />
          )}
          <Turnstile
            siteKey={siteKey}
            onToken={setTurnstileToken}
            onExpire={() => setTurnstileToken(null)}
          />
          {err && <div className="ed-error">{err}</div>}
          {unverified && (
            <>
              <button
                type="button"
                onClick={resendVerify}
                className="ed-btn"
                style={{
                  background: "transparent",
                  border: "1px solid rgba(255,255,255,0.25)",
                  boxShadow: "none",
                }}
              >
                Skicka nytt bekräftelsemail
              </button>
              {resendMsg && (
                <div
                  style={{
                    fontSize: "13px",
                    color: "rgba(255,255,255,0.7)",
                    fontStyle: "italic",
                    textAlign: "center",
                  }}
                >
                  {resendMsg}
                </div>
              )}
            </>
          )}
          <button
            type="submit"
            className="ed-btn"
            disabled={busy || (Boolean(siteKey) && !turnstileToken)}
          >
            {busy
              ? "Arbetar…"
              : isBootstrap
                ? "Skapa lärarkonto"
                : "Logga in"}
            <span className="ed-btn-arrow">→</span>
          </button>

          {!isBootstrap && (
            <div className="ed-foot-note">
              <Link to="/forgot-password" className="ed-foot-link">
                Glömt lösenord?
              </Link>
              {!schoolStatus?.bootstrap_ready && (
                <>
                  {" · "}
                  <Link to="/signup/teacher" className="ed-foot-link">
                    Skapa lärarkonto
                  </Link>
                </>
              )}
              {" · "}
              <Link to="/login/student" className="ed-foot-link">
                Elevinloggning
              </Link>
            </div>
          )}
        </form>
      </div>
    </EditorialAuthShell>
  );
}
