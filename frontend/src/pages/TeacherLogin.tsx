import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, ApiError } from "@/api/client";
import { useAuth } from "@/hooks/useAuth";
import { Turnstile } from "@/components/Turnstile";
import { AuthShell, PaperButton, PaperInput } from "@/components/paper";

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
  // När login avvisas pga email_unverified visar vi en knapp för att
  // skicka om verifieringsmailet (utan att användaren behöver gå till
  // en separat sida).
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
      // Backend returnerar 403 med detail="email_unverified" om kontot
      // finns men inte har bekräftats. Vi erbjuder då att skicka om.
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

  return (
    <AuthShell
      eyebrow="Ekonomilabbet"
      title={mode === "bootstrap" ? "Skapa första lärarkontot" : "Lärarinloggning"}
      intro={
        mode === "bootstrap"
          ? schoolStatus?.bootstrap_requires_secret
            ? "Första gången — ange bootstrap-koden som administratören gav dig."
            : "Första gången — skapa ditt lärarkonto. Du blir super-admin för klassen."
          : "Logga in med e-post och lösenord."
      }
    >
      <form onSubmit={handle} className="space-y-3">
        {mode === "bootstrap" && schoolStatus?.bootstrap_requires_secret && (
          <PaperInput
            type="text"
            value={secret}
            onChange={(e) => setSecret(e.target.value)}
            placeholder="Bootstrap-kod"
          />
        )}
        <PaperInput
          type="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder="E-post"
          autoFocus
        />
        {mode === "bootstrap" && (
          <PaperInput
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Namn"
          />
        )}
        <PaperInput
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          placeholder="Lösenord"
        />
        {mode === "bootstrap" && (
          <PaperInput
            type="password"
            value={confirm}
            onChange={(e) => setConfirm(e.target.value)}
            placeholder="Bekräfta lösenord"
          />
        )}
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
        {unverified && (
          <div className="flex flex-col gap-2 text-sm">
            <PaperButton
              type="button"
              variant="outline"
              size="sm"
              onClick={resendVerify}
              className="w-full justify-center"
            >
              Skicka nytt bekräftelsemail
            </PaperButton>
            {resendMsg && (
              <div className="text-[#555] text-center">{resendMsg}</div>
            )}
          </div>
        )}
        <PaperButton
          type="submit"
          disabled={busy || (Boolean(siteKey) && !turnstileToken)}
          className="w-full justify-center disabled:opacity-50"
        >
          {busy ? "Arbetar…" : mode === "bootstrap" ? "Skapa lärarkonto" : "Logga in"}
        </PaperButton>

        {mode === "login" && (
          <div className="flex flex-col gap-1 text-center text-sm pt-3 border-t border-rule">
            <Link to="/forgot-password" className="nav-link inline-block">
              Glömt lösenord?
            </Link>
            {!schoolStatus?.bootstrap_ready && (
              <div className="text-[#666]">
                Inget konto än?{" "}
                <Link to="/signup/teacher" className="nav-link">
                  Skapa lärarkonto
                </Link>
              </div>
            )}
          </div>
          )}

        <div className="text-center text-sm text-[#666] pt-3 border-t border-rule">
          Är du elev?{" "}
          <Link to="/login/student" className="nav-link">
            Elevinloggning
          </Link>
        </div>
      </form>
    </AuthShell>
  );
}
