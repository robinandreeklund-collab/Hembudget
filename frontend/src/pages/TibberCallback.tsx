import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "@/api/client";
import { Card } from "@/components/Card";

/**
 * OAuth 2.0 callback-sida för Tibber. Tibber redirectar hit med
 * ?code=...&state=... efter att användaren godkänt access. Vi byter
 * code mot tokens via backend och skickar sedan tillbaka till /settings.
 *
 * Obs: redirect_uri måste vara registrerad i Tibbers dev-konsol och
 * matcha EXAKT URL:en (http://localhost:1420/Callback).
 */
export default function TibberCallback() {
  const navigate = useNavigate();
  const [status, setStatus] = useState<"loading" | "ok" | "error">("loading");
  const [message, setMessage] = useState<string>("");

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const code = params.get("code");
    const state = params.get("state");
    const err = params.get("error");
    const errDesc = params.get("error_description");

    if (err) {
      setStatus("error");
      setMessage(
        `Tibber avvisade auktoriseringen: ${err}${
          errDesc ? ` — ${errDesc}` : ""
        }`,
      );
      return;
    }
    if (!code || !state) {
      setStatus("error");
      setMessage(
        "Saknar code eller state i callback-URL:en. Starta om OAuth-flödet från /settings.",
      );
      return;
    }

    api<{ ok: boolean; profile: { name?: string } }>(
      "/utility/tibber/oauth/callback",
      {
        method: "POST",
        body: JSON.stringify({ code, state }),
      },
    )
      .then((res) => {
        setStatus("ok");
        setMessage(
          res.profile?.name
            ? `Inloggad som ${res.profile.name}. Omdirigerar…`
            : "Inloggning lyckades. Omdirigerar…",
        );
        setTimeout(() => navigate("/settings"), 1500);
      })
      .catch((e: Error) => {
        setStatus("error");
        setMessage(e.message);
      });
  }, [navigate]);

  return (
    <div className="p-6 max-w-xl">
      <Card title="Tibber — auktorisering">
        {status === "loading" && (
          <div className="text-sm text-slate-700">
            Byter engångskod mot access-token…
          </div>
        )}
        {status === "ok" && (
          <div className="text-sm text-emerald-700">✓ {message}</div>
        )}
        {status === "error" && (
          <>
            <div className="text-sm text-rose-700">⚠ {message}</div>
            <button
              onClick={() => navigate("/settings")}
              className="mt-3 bg-slate-700 text-white px-3 py-1.5 rounded text-sm"
            >
              Tillbaka till Inställningar
            </button>
          </>
        )}
      </Card>
    </div>
  );
}
