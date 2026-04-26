import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { CheckCircle2, XCircle, Loader } from "lucide-react";
import { api, ApiError } from "@/api/client";
import { AuthShell } from "@/components/paper";

type State = "pending" | "ok" | "expired" | "invalid" | "error";

export default function VerifyEmail() {
  const [params] = useSearchParams();
  const token = params.get("token") ?? "";
  const [state, setState] = useState<State>("pending");
  const [msg, setMsg] = useState("");

  useEffect(() => {
    if (!token) {
      setState("invalid");
      setMsg("Länken saknar token.");
      return;
    }
    (async () => {
      try {
        await api(`/teacher/verify-email?token=${encodeURIComponent(token)}`);
        setState("ok");
      } catch (e: unknown) {
        if (e instanceof ApiError) {
          if (e.status === 410) {
            setState("expired");
            setMsg(
              typeof e.body === "object" &&
                e.body &&
                "detail" in (e.body as Record<string, unknown>)
                ? String((e.body as { detail: unknown }).detail)
                : "Länken är redan använd eller har gått ut.",
            );
          } else if (e.status === 404) {
            setState("invalid");
            setMsg("Länken är ogiltig.");
          } else {
            setState("error");
            setMsg(e.message);
          }
        } else {
          setState("error");
          setMsg(e instanceof Error ? e.message : "Oväntat fel.");
        }
      }
    })();
  }, [token]);

  if (state === "pending") {
    return (
      <AuthShell title="Bekräftar…" eyebrow="Verifiering">
        <div className="text-center py-4">
          <Loader className="w-10 h-10 text-ink mx-auto animate-spin" strokeWidth={1.5} />
        </div>
      </AuthShell>
    );
  }

  if (state === "ok") {
    return (
      <AuthShell title="E-post bekräftad" eyebrow="Klart" back="/login/teacher" backLabel="Tillbaka">
        <div className="text-center">
          <CheckCircle2 className="w-12 h-12 text-ink mx-auto" strokeWidth={1.5} />
          <p className="body-prose text-sm mt-3">
            Kontot är aktivt. Du kan nu logga in.
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
      title={state === "expired" ? "Länken kan inte användas" : "Ogiltig länk"}
      eyebrow="Verifiering"
      back="/login/teacher"
      backLabel="Tillbaka"
    >
      <div className="text-center">
        <XCircle className="w-12 h-12 text-ink mx-auto" strokeWidth={1.5} />
        <p className="body-prose text-sm mt-3">{msg}</p>
        <Link
          to="/login/teacher"
          className="btn-outline mt-6 inline-block w-full text-center px-5 py-3 rounded-md"
        >
          Till inloggning
        </Link>
      </div>
    </AuthShell>
  );
}
