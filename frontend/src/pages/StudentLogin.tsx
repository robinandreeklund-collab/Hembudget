import { useState } from "react";
import { Link } from "react-router-dom";
import { useAuth } from "@/hooks/useAuth";
import { Turnstile } from "@/components/Turnstile";
import { AuthShell, PaperButton } from "@/components/paper";

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
    <AuthShell
      eyebrow="Ekonomilabbet"
      title="Elevinloggning"
      intro="Ange din 6-teckens kod som din lärare har gett dig."
    >
      <form onSubmit={handle} className="space-y-4">
        <input
          type="text"
          value={code}
          onChange={(e) => setCode(e.target.value.toUpperCase())}
          placeholder="ABC123"
          autoFocus
          maxLength={6}
          className="w-full px-3 py-4 border-[1.5px] border-rule bg-white text-ink focus:border-ink outline-none font-mono tracking-[0.4em] text-center text-2xl placeholder:text-[#bbb]"
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
          disabled={busy || code.length < 4}
          size="lg"
          className="w-full justify-center disabled:opacity-50"
        >
          {busy ? "Loggar in…" : "Logga in"}
        </PaperButton>
        <div className="text-center text-sm text-[#666] pt-3 border-t border-rule">
          Är du lärare eller skolledare?{" "}
          <Link to="/login/teacher" className="nav-link">
            Lärarinloggning
          </Link>
        </div>
      </form>
    </AuthShell>
  );
}
