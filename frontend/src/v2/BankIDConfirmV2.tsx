/**
 * BankID-confirm — mobil-vy.
 *
 * Eleven scannar QR-koden på desktop med mobilen → hamnar här via
 * /v2/bankid/confirm/:token. Visar sammanfattning + PIN-form.
 *
 * Anonym (ingen inloggning krävs) — token + Student.bank_pin_hash
 * räcker som security. Samma modell som v1
 * /bank/sign?token=X.
 */
import { useEffect, useState } from "react";
import { useParams, useSearchParams } from "react-router-dom";
import { v2Api } from "./api";

const SEK = (n: number) =>
  new Intl.NumberFormat("sv-SE", { maximumFractionDigits: 0 }).format(n);

const SHORT_DATE = (iso: string): string => {
  const d = new Date(iso);
  return d.toLocaleDateString("sv-SE", {
    day: "numeric",
    month: "short",
  });
};

type Info = Awaited<ReturnType<typeof v2Api.bankidConfirmInfo>>;

export function BankIDConfirmV2() {
  const { token } = useParams<{ token: string }>();
  const [searchParams] = useSearchParams();
  const sidParam = searchParams.get("sid");
  const sid = sidParam ? parseInt(sidParam, 10) : undefined;
  const [info, setInfo] = useState<Info | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pin, setPin] = useState("");
  const [signing, setSigning] = useState(false);
  const [signed, setSigned] = useState(false);

  useEffect(() => {
    if (!token) return;
    v2Api
      .bankidConfirmInfo(token, sid)
      .then(setInfo)
      .catch((e) => setError(String((e as Error)?.message || e)));
  }, [token, sid]);

  async function submit() {
    if (!token) return;
    if (!/^\d{4}$/.test(pin)) {
      setError("PIN måste vara 4 siffror");
      return;
    }
    setSigning(true);
    setError(null);
    try {
      const r = await v2Api.bankidConfirmSign(token, pin, sid);
      if (r.status === "signed") {
        setSigned(true);
      }
    } catch (e) {
      setError(String((e as Error)?.message || e));
    } finally {
      setSigning(false);
    }
  }

  const wrapStyle: React.CSSProperties = {
    minHeight: "100vh",
    background: "linear-gradient(180deg, #0a0e1a 0%, #0f1525 60%, #0a0e1a 100%)",
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

  if (error && !info) {
    return (
      <div style={wrapStyle}>
        <div style={cardStyle}>
          <div style={eyeStyle}>● Ekonomilabbet-ID</div>
          <h1 style={headerStyle}>Sessionen finns inte</h1>
          <p style={{ color: "rgba(255,255,255,0.65)" }}>
            QR-koden kan ha gått ut. Scanna en ny från banken.
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

  if (!info) {
    return (
      <div style={wrapStyle}>
        <div style={cardStyle}>
          <div style={eyeStyle}>● Ekonomilabbet-ID</div>
          <p style={{ color: "rgba(255,255,255,0.65)" }}>Laddar session…</p>
        </div>
      </div>
    );
  }

  if (signed || info.status === "signed") {
    return (
      <div style={wrapStyle}>
        <div style={cardStyle}>
          <div
            style={{
              ...eyeStyle,
              color: "#6ee7b7",
            }}
          >
            ● Signerat
          </div>
          <h1 style={headerStyle}>
            ✓ {SEK(info.total_amount)} kr signerat
          </h1>
          <p
            style={{
              color: "rgba(255,255,255,0.65)",
              fontSize: 14,
              lineHeight: 1.5,
              marginBottom: 18,
            }}
          >
            {info.invoice_count} fakturor är nu schemalagda som autogiro.
            Banken drar dem automatiskt på respektive förfallodag.
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
            Du kan stänga den här fliken. Desktop-vyn uppdateras
            automatiskt.
          </div>
        </div>
      </div>
    );
  }

  if (info.status === "cancelled") {
    return (
      <div style={wrapStyle}>
        <div style={cardStyle}>
          <div style={eyeStyle}>● Avbruten</div>
          <h1 style={headerStyle}>Sessionen är avbruten</h1>
          <p style={{ color: "rgba(255,255,255,0.65)" }}>
            Skapa en ny från banken.
          </p>
        </div>
      </div>
    );
  }

  if (!info.has_pin) {
    return (
      <div style={wrapStyle}>
        <div style={cardStyle}>
          <div style={eyeStyle}>● PIN saknas</div>
          <h1 style={headerStyle}>Du måste sätta en BankID-PIN först</h1>
          <p
            style={{
              color: "rgba(255,255,255,0.65)",
              fontSize: 14,
              lineHeight: 1.5,
              marginBottom: 14,
            }}
          >
            Logga in på desktop, gå till banken och välj en 4-siffrig
            PIN. Kom sedan tillbaka och scanna QR-koden igen.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div style={wrapStyle}>
      <div style={cardStyle}>
        <div style={eyeStyle}>● Ekonomilabbet-ID · sandbox</div>
        <h1 style={headerStyle}>
          Signera {SEK(info.total_amount)} kr
        </h1>
        <p
          style={{
            color: "rgba(255,255,255,0.65)",
            fontSize: 14,
            lineHeight: 1.5,
            marginTop: 0,
            marginBottom: 18,
          }}
        >
          {info.invoice_count} fakturor · totalt {SEK(info.total_amount)} kr.
          Ange din 4-siffriga PIN för att godkänna autogiro.
        </p>

        {/* Faktura-sammanfattning */}
        <div
          style={{
            border: "1px solid rgba(255,255,255,0.1)",
            borderRadius: 8,
            padding: "12px 14px",
            marginBottom: 18,
            background: "rgba(255,255,255,0.02)",
            maxHeight: 180,
            overflowY: "auto",
          }}
        >
          {info.invoices.slice(0, 6).map((inv) => (
            <div
              key={inv.upcoming_id}
              style={{
                display: "flex",
                justifyContent: "space-between",
                gap: 8,
                padding: "6px 0",
                fontFamily: "JetBrains Mono, monospace",
                fontSize: 11,
                color: "rgba(255,255,255,0.85)",
                borderBottom: "1px solid rgba(255,255,255,0.04)",
              }}
            >
              <span style={{ flex: 1, overflow: "hidden", textOverflow: "ellipsis" }}>
                {inv.name}
              </span>
              <span style={{ color: "rgba(255,255,255,0.5)", fontSize: 9 }}>
                {SHORT_DATE(inv.due_date)}
              </span>
              <span style={{ color: "var(--warm, #fbbf24)", fontWeight: 700 }}>
                {SEK(inv.amount)} kr
              </span>
            </div>
          ))}
          {info.invoices.length > 6 && (
            <div
              style={{
                padding: "6px 0",
                fontFamily: "JetBrains Mono, monospace",
                fontSize: 10,
                color: "rgba(255,255,255,0.5)",
                textAlign: "center",
              }}
            >
              + {info.invoices.length - 6} fler fakturor
            </div>
          )}
        </div>

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
