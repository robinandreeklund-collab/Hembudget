import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { CheckCircle2, XCircle, Loader } from "lucide-react";
import { api, ApiError } from "@/api/client";

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

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 to-brand-50 grid place-items-center p-6">
      <div className="w-full max-w-md bg-white rounded-2xl shadow-xl p-8 border border-slate-200 text-center">
        {state === "pending" && (
          <>
            <Loader className="w-10 h-10 text-brand-600 mx-auto animate-spin" />
            <h1 className="text-xl font-semibold mt-4">Bekräftar…</h1>
          </>
        )}
        {state === "ok" && (
          <>
            <CheckCircle2 className="w-12 h-12 text-emerald-500 mx-auto" />
            <h1 className="text-xl font-semibold mt-3">E-post bekräftad</h1>
            <p className="text-sm text-slate-600 mt-2">
              Kontot är aktivt. Du kan nu logga in.
            </p>
            <Link
              to="/login/teacher"
              className="mt-6 inline-block w-full bg-brand-600 hover:bg-brand-700 text-white rounded-lg py-2.5 font-medium"
            >
              Till inloggning
            </Link>
          </>
        )}
        {(state === "expired" || state === "invalid" || state === "error") && (
          <>
            <XCircle className="w-12 h-12 text-rose-500 mx-auto" />
            <h1 className="text-xl font-semibold mt-3">
              {state === "expired" ? "Länken kan inte användas" : "Ogiltig länk"}
            </h1>
            <p className="text-sm text-slate-600 mt-2">{msg}</p>
            <Link
              to="/login/teacher"
              className="mt-6 inline-block w-full border border-slate-300 hover:bg-slate-50 rounded-lg py-2.5 font-medium"
            >
              Till inloggning
            </Link>
          </>
        )}
      </div>
    </div>
  );
}
