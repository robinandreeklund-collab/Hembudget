/**
 * BizActionModal · ersätter alert() vid HTTP 402 / liknande pedagogiska
 * felfall i företagsläget.
 *
 * Stödjer två lägen:
 *   1. Felmeddelande (default · onConfirm saknas)
 *   2. Bekräftelse-fråga (onConfirm satt → primary-knapp triggar action
 *      i stället för att navigera)
 *
 * Användning · fel:
 *   const [errorModal, setErrorModal] = useState<BizActionModalProps | null>(null);
 *   try { await api(...) } catch (e) {
 *     setErrorModal(parseBizError(e));
 *   }
 *
 * Användning · bekräftelse:
 *   setConfirmModal({
 *     kind: "confirm",
 *     title: "Hyra Hyrd 1-rumslokal?",
 *     message: "4 000 kr/mån. Första månadens buffert dras direkt.",
 *     primaryCtaLabel: "Hyr →",
 *     onConfirm: () => doRent(),
 *   });
 */
import { Link } from "react-router-dom";


export type BizActionModalKind =
  | "kassa_low"      // Otillräcklig kassa → ta tillväxtlån
  | "uc_rejected"    // UC-avslag → kontakta lärare
  | "buffer_low"     // Hyra/månadskostnad utan buffert
  | "confirm"        // Bekräfta ett köp/aktion (positiv)
  | "generic";       // fallback


export type BizActionModalProps = {
  kind: BizActionModalKind;
  title: string;
  message: string;
  primaryCtaLabel?: string;
  primaryCtaHref?: string;
  onConfirm?: () => void;  // sätt för bekräfta-läget
  onClose: () => void;
};


export function BizActionModal({
  kind,
  title,
  message,
  primaryCtaLabel,
  primaryCtaHref,
  onConfirm,
  onClose,
}: BizActionModalProps) {
  const palette = kind === "uc_rejected"
    ? { eye: "⚠ KREDITUPPLYSNING · AVSLAG", color: "#fda594", border: "rgba(220,76,43,0.40)", bg: "rgba(220,76,43,0.08)" }
    : kind === "buffer_low"
      ? { eye: "⚠ FÖR LITEN BUFFERT", color: "#fbbf24", border: "rgba(251,191,36,0.40)", bg: "rgba(251,191,36,0.08)" }
      : kind === "kassa_low"
        ? { eye: "⚠ OTILLRÄCKLIG KASSA", color: "#fbbf24", border: "rgba(251,191,36,0.40)", bg: "rgba(251,191,36,0.08)" }
        : kind === "confirm"
          ? { eye: "● BEKRÄFTA", color: "#c7d2fe", border: "rgba(99,102,241,0.40)", bg: "rgba(99,102,241,0.06)" }
          : { eye: "⚠ KAN INTE UTFÖRA", color: "#fda594", border: "rgba(220,76,43,0.40)", bg: "rgba(220,76,43,0.08)" };

  return (
    <div
      onClick={onClose}
      style={{
        position: "fixed", inset: 0, zIndex: 200,
        background: "rgba(0,0,0,0.7)",
        display: "flex", alignItems: "center", justifyContent: "center",
        padding: 20,
      }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          maxWidth: 560,
          width: "100%",
          padding: "32px 28px",
          background: `linear-gradient(135deg, ${palette.bg}, rgba(15,21,37,0.65))`,
          border: `1px solid ${palette.border}`,
          borderTop: `3px solid ${palette.color}`,
          borderRadius: 12,
        }}
      >
        <div style={{
          fontFamily: "JetBrains Mono, monospace",
          fontSize: 11, fontWeight: 700, letterSpacing: 1.6,
          color: palette.color,
        }}>
          {palette.eye}
        </div>
        <h1 style={{
          fontFamily: "Source Serif 4, Georgia, serif",
          fontSize: 24, color: "#fff", fontWeight: 700,
          margin: "10px 0 16px", letterSpacing: -0.4,
        }}>
          {title}
        </h1>
        <p style={{
          color: "rgba(255,255,255,0.82)",
          fontFamily: "Source Serif 4, Georgia, serif",
          fontSize: 14.5, lineHeight: 1.6, margin: 0,
          whiteSpace: "pre-wrap",
        }}>
          {message}
        </p>

        <div style={{
          display: "flex", gap: 10, marginTop: 22,
          flexWrap: "wrap", justifyContent: "flex-end",
        }}>
          {onConfirm && primaryCtaLabel && (
            <button
              onClick={() => { onConfirm(); onClose(); }}
              style={{
                background: "#fbbf24",
                color: "#422006",
                padding: "10px 18px",
                borderRadius: 6,
                fontFamily: "JetBrains Mono, monospace",
                fontSize: 11, fontWeight: 700, letterSpacing: 1.2,
                textTransform: "uppercase",
                border: "none",
                cursor: "pointer",
              }}
            >
              {primaryCtaLabel}
            </button>
          )}
          {!onConfirm && primaryCtaLabel && primaryCtaHref && (
            <Link
              to={primaryCtaHref}
              onClick={onClose}
              style={{
                background: "#fbbf24",
                color: "#422006",
                padding: "10px 18px",
                borderRadius: 6,
                fontFamily: "JetBrains Mono, monospace",
                fontSize: 11, fontWeight: 700, letterSpacing: 1.2,
                textTransform: "uppercase",
                textDecoration: "none",
              }}
            >
              {primaryCtaLabel}
            </Link>
          )}
          <button
            onClick={onClose}
            style={{
              background: "transparent",
              border: "1px solid rgba(255,255,255,0.18)",
              color: "rgba(255,255,255,0.7)",
              padding: "10px 18px",
              borderRadius: 6,
              fontFamily: "JetBrains Mono, monospace",
              fontSize: 11, fontWeight: 700, letterSpacing: 1.2,
              textTransform: "uppercase",
              cursor: "pointer",
            }}
          >
            {onConfirm ? "Avbryt" : "Stäng"}
          </button>
        </div>
      </div>
    </div>
  );
}


// Plocka isär 'HTTP 402: ... — <detail>' och bygg props baserat på
// keywords i meddelandet. Fallback till generic.
export function parseBizError(err: unknown): BizActionModalProps {
  const msg = String((err as Error)?.message || err);
  // Backend-detalj efter ' — '
  const m = msg.match(/—\s*(.+)$/);
  const detail = (m ? m[1] : msg).trim();

  if (msg.includes("HTTP 402")) {
    if (detail.includes("UC-score") || detail.toLowerCase().includes("avslag")) {
      return {
        kind: "uc_rejected",
        title: "Banken avslog din ansökan.",
        message: detail,
        primaryCtaLabel: "Öppna postlådan",
        primaryCtaHref: "/v2/postladan",
        onClose: () => undefined,
      };
    }
    if (detail.includes("buffert") || detail.includes("trygghets")) {
      return {
        kind: "buffer_low",
        title: "Du har för liten buffert kvar.",
        message: detail,
        primaryCtaLabel: "Ansök om tillväxtlån",
        primaryCtaHref: "/v2/foretag/tillvaxt",
        onClose: () => undefined,
      };
    }
    return {
      kind: "kassa_low",
      title: "Du saknar pengar i kassan.",
      message: detail,
      primaryCtaLabel: "Ansök om tillväxtlån",
      primaryCtaHref: "/v2/foretag/tillvaxt",
      onClose: () => undefined,
    };
  }

  return {
    kind: "generic",
    title: "Något gick fel.",
    message: detail || msg,
    onClose: () => undefined,
  };
}
