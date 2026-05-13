/**
 * BankSignV2 · mobil-vyn för generisk BankID-session-signering.
 *
 * Eleven scannar QR-koden från en BankIdSignModal (lån-signering,
 * mm.) på desktop → hamnar här via /v2/bank-sign/:token. Visar
 * session-info + PIN-form. Vid lyckad PIN → POST /bank/session/
 * {token}/confirm → desktop's polling detekterar confirmed_at och
 * fortsätter med åtgärden (t.ex. acceptera lån).
 *
 * Skiljer sig från BankIDConfirmV2 som är specifik för
 * fakturasignering — den här är generisk för alla BankID-session-
 * purposes (private_loan_sign_*, mm.). Använder samma v2-design.
 *
 * Anonym (ingen inloggning krävs) — token + Student.bank_pin_hash
 * räcker som security. Samma modell som v1 /bank/sign?token=X men
 * med v2-design och utan dependency på fakturalisting.
 */
import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { api } from "@/api/client";


type SessionStatus = {
  token: string;
  purpose: string;
  status: "pending" | "signed" | "expired";
  confirmed_at: string | null;
  expires_at: string;
};


export function BankSignV2() {
  const { token } = useParams<{ token: string }>();
  const [status, setStatus] = useState<SessionStatus | null>(null);
  const [pin, setPin] = useState("");
  const [signing, setSigning] = useState(false);
  const [signed, setSigned] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!token) return;
    api<SessionStatus>(`/bank/session/${encodeURIComponent(token)}`)
      .then(setStatus)
      .catch((e) => setError(String((e as Error)?.message || e)));
  }, [token]);

  async function submit() {
    if (!token) return;
    if (!/^\d{4}$/.test(pin)) {
      setError("PIN måste vara 4 siffror");
      return;
    }
    setSigning(true);
    setError(null);
    try {
      await api<{ ok: boolean }>(
        `/bank/session/${encodeURIComponent(token)}/confirm`,
        { method: "POST", body: JSON.stringify({ pin }) },
      );
      setSigned(true);
    } catch (e) {
      setError(String((e as Error)?.message || e));
    } finally {
      setSigning(false);
    }
  }

  // Pedagogisk text baserat på purpose-prefix
  const purposeLabel = (() => {
    const p = status?.purpose || "";
    if (p.startsWith("private_loan_sign_")) return "Signera lån";
    if (p.startsWith("login")) return "Logga in";
    return "BankID-signering";
  })();

  const wrapStyle: React.CSSProperties = {
    minHeight: "100vh",
    background:
      "linear-gradient(180deg, #0a0e1a 0%, #0f1525 60%, #0a0e1a 100%)",
    color: "#fff",
    fontFamily: "Source Serif 4, Georgia, serif",
    display: "grid",
    placeItems: "center",
    padding: "24px 16px",
  };
  const cardStyle: React.CSSProperties = {
    width: "100%",
    maxWidth: 420,
    background: "#0f1525",
    border: "1px solid var(--accent, #dc4c2b)",
    borderRadius: 14,
    padding: "28px 24px 24px",
    boxShadow: "0 20px 60px -10px rgba(0,0,0,0.6)",
  };
  const eyeStyle: React.CSSProperties = {
    fontFamily: "JetBrains Mono, monospace",
    fontSize: 9.5,
    letterSpacing: "1.6px",
    textTransform: "uppercase",
    color: "var(--accent, #dc4c2b)",
    marginBottom: 8,
  };
  const headerStyle: React.CSSProperties = {
    fontFamily: "Source Serif 4, Georgia, serif",
    fontSize: 22,
    fontWeight: 700,
    color: "#fff",
    letterSpacing: "-0.4px",
    margin: "0 0 6px 0",
  };

  if (!token) {
    return (
      <div style={wrapStyle}>
        <div style={cardStyle}>
          <div style={eyeStyle}>● Ekonomilabbet-ID</div>
          <h1 style={headerStyle}>Ogiltig länk</h1>
          <p style={{ color: "rgba(255,255,255,0.65)" }}>
            Sessionstoken saknas. Scanna QR-koden igen från desktop.
          </p>
        </div>
      </div>
    );
  }

  if (error && !status) {
    return (
      <div style={wrapStyle}>
        <div style={cardStyle}>
          <div style={eyeStyle}>● Ekonomilabbet-ID</div>
          <h1 style={headerStyle}>Sessionen finns inte</h1>
          <p style={{ color: "rgba(255,255,255,0.65)" }}>
            QR-koden kan ha gått ut. Scanna en ny från desktop.
          </p>
          <pre
            style={{
              fontFamily: "JetBrains Mono, monospace",
              fontSize: 10,
              color: "#fca5a5",
              marginTop: 14,
              whiteSpace: "pre-wrap",
            }}
          >
            {error}
          </pre>
        </div>
      </div>
    );
  }

  if (!status) {
    return (
      <div style={wrapStyle}>
        <div style={cardStyle}>
          <div style={eyeStyle}>● Ekonomilabbet-ID</div>
          <p style={{ color: "rgba(255,255,255,0.65)" }}>Laddar session…</p>
        </div>
      </div>
    );
  }

  if (signed || status.confirmed_at) {
    return (
      <div style={wrapStyle}>
        <div style={cardStyle}>
          <div style={{ ...eyeStyle, color: "#6ee7b7" }}>● Signerat</div>
          <h1 style={headerStyle}>✓ {purposeLabel} klar</h1>
          <p
            style={{
              color: "rgba(255,255,255,0.65)",
              fontSize: 14,
              lineHeight: 1.5,
              marginBottom: 18,
            }}
          >
            Du kan stänga den här fliken. Desktop-vyn uppdateras
            automatiskt och slutför åtgärden.
          </p>
          <div
            style={{
              padding: "12px 16px",
              background: "rgba(110,231,183,0.06)",
              border: "1px solid rgba(110,231,183,0.4)",
              borderRadius: 8,
              fontFamily: "JetBrains Mono, monospace",
              fontSize: 11,
              color: "#6ee7b7",
              letterSpacing: "0.4px",
            }}
          >
            Signaturen är bekräftad
          </div>
        </div>
      </div>
    );
  }

  if (status.status === "expired") {
    return (
      <div style={wrapStyle}>
        <div style={cardStyle}>
          <div style={eyeStyle}>● Avbruten</div>
          <h1 style={headerStyle}>Sessionen har löpt ut</h1>
          <p style={{ color: "rgba(255,255,255,0.65)" }}>
            Skapa en ny session från desktop.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div style={wrapStyle}>
      <div style={cardStyle}>
        <div style={eyeStyle}>● Ekonomilabbet-ID · sandbox</div>
        <h1 style={headerStyle}>{purposeLabel}</h1>
        <p
          style={{
            color: "rgba(255,255,255,0.65)",
            fontSize: 14,
            lineHeight: 1.5,
            marginTop: 0,
            marginBottom: 18,
          }}
        >
          Ange din 4-siffriga BankID-PIN för att godkänna åtgärden.
          Desktop-vyn slutför sedan automatiskt.
        </p>

        {/* PIN-input */}
        <input
          type="password"
          inputMode="numeric"
          pattern="[0-9]*"
          maxLength={4}
          autoFocus
          placeholder="••••"
          value={pin}
          onChange={(e) => {
            const v = e.target.value.replace(/[^0-9]/g, "");
            setPin(v);
            if (v.length === 4) {
              setTimeout(() => submit(), 100);
            }
          }}
          style={{
            width: "100%",
            padding: "16px 20px",
            fontSize: 32,
            textAlign: "center",
            letterSpacing: "0.5em",
            background: "rgba(255,255,255,0.04)",
            border: "1px solid rgba(255,255,255,0.18)",
            borderRadius: 10,
            color: "#fff",
            fontFamily: "JetBrains Mono, monospace",
            fontWeight: 700,
            marginBottom: 14,
          }}
          disabled={signing}
        />

        {error && (
          <div
            style={{
              padding: "10px 14px",
              background: "rgba(252,165,165,0.06)",
              border: "1px solid rgba(252,165,165,0.4)",
              borderRadius: 8,
              color: "#fca5a5",
              fontFamily: "JetBrains Mono, monospace",
              fontSize: 11,
              marginBottom: 14,
            }}
          >
            {error}
          </div>
        )}

        <button
          type="button"
          disabled={signing || pin.length !== 4}
          onClick={submit}
          style={{
            width: "100%",
            padding: "14px 20px",
            background: "var(--accent, #dc4c2b)",
            color: "#fff",
            border: 0,
            borderRadius: 100,
            fontFamily: "JetBrains Mono, monospace",
            fontSize: 11,
            fontWeight: 700,
            letterSpacing: "1.2px",
            textTransform: "uppercase",
            cursor: signing || pin.length !== 4 ? "not-allowed" : "pointer",
            opacity: signing || pin.length !== 4 ? 0.6 : 1,
          }}
        >
          {signing ? "Signerar…" : "Signera →"}
        </button>

        <div
          style={{
            marginTop: 18,
            fontFamily: "JetBrains Mono, monospace",
            fontSize: 9,
            letterSpacing: "1.2px",
            textTransform: "uppercase",
            color: "rgba(255,255,255,0.4)",
            textAlign: "center",
          }}
        >
          Sandbox · ingen riktig BankID-anrop görs
        </div>
      </div>
    </div>
  );
}
