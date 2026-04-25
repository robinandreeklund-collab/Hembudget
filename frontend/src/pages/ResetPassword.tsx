import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { CheckCircle2 } from "lucide-react";
import { api, ApiError } from "@/api/client";
import { AuthShell, PaperButton, PaperInput } from "@/components/paper";

export default function ResetPassword() {
  const [params] = useSearchParams();
  const token = params.get("token") ?? "";
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);

  async function handle(e: React.FormEvent) {
    e.preventDefault();
    setErr(null);
    if (!token) return setErr("Länken saknar token.");
    if (password.length < 8) return setErr("Lösenord måste vara minst 8 tecken.");
    if (password !== confirm) return setErr("Lösenorden matchar inte.");
    setBusy(true);
    try {
      await api("/teacher/reset-password", {
        method: "POST",
        body: JSON.stringify({ token, password }),
      });
      setDone(true);
    } catch (e: unknown) {
      if (e instanceof ApiError) {
        if (e.status === 410) setErr("Länken har gått ut eller redan använts. Begär en ny.");
        else if (e.status === 404) setErr("Länken är ogiltig.");
        else if (e.status === 429) setErr("För många försök. Vänta en stund.");
        else setErr(e.message);
      } else {
        setErr(e instanceof Error ? e.message : "Oväntat fel.");
      }
    } finally {
      setBusy(false);
    }
  }

  if (done) {
    return (
      <AuthShell title="Klart" eyebrow="Lösenord uppdaterat" back="/login/teacher" backLabel="Tillbaka till inloggning">
        <div className="text-center">
          <CheckCircle2 className="w-12 h-12 text-ink mx-auto" strokeWidth={1.5} />
          <p className="body-prose text-sm mt-3">
            Du kan nu logga in med ditt nya lösenord.
          </p>
          <Link
            to="/login/teacher"
            className="btn-dark mt-6 inline-block w-full text-center px-5 py-3 rounded-md"
          >
            Till inloggning
          </Link>
        </div>
      </AuthShell>
    );
  }

  return (
    <AuthShell
      title="Välj nytt lösenord"
      intro="Minst 8 tecken. Länken gäller bara en gång."
      back="/login/teacher"
      backLabel="Tillbaka till inloggning"
    >
      <form onSubmit={handle} className="space-y-3">
        <PaperInput
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          placeholder="Nytt lösenord"
          autoFocus
        />
        <PaperInput
          type="password"
          value={confirm}
          onChange={(e) => setConfirm(e.target.value)}
          placeholder="Bekräfta lösenord"
        />
        {err && (
          <div className="text-sm text-[#b91c1c] border-l-2 border-[#b91c1c] pl-3 py-1">
            {err}
          </div>
        )}
        <PaperButton
          type="submit"
          disabled={busy}
          className="w-full justify-center disabled:opacity-50"
        >
          {busy ? "Uppdaterar…" : "Spara nytt lösenord"}
        </PaperButton>
      </form>
    </AuthShell>
  );
}
