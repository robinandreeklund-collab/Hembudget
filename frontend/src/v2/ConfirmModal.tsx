/**
 * ConfirmModal · stylad bekräftelse-dialog som ersätter native
 * window.confirm(). Matchar v2-temat (mörk bakgrund, serif-titel,
 * mono-knappar).
 *
 * Användning:
 *
 *   const [confirmOpen, setConfirmOpen] = useState(false);
 *   ...
 *   <ConfirmModal
 *     open={confirmOpen}
 *     title="Tacka nej?"
 *     body="Vill du tacka nej till lån-erbjudandet?"
 *     confirmLabel="Ja, tacka nej"
 *     cancelLabel="Avbryt"
 *     destructive
 *     onConfirm={() => { ...; setConfirmOpen(false); }}
 *     onCancel={() => setConfirmOpen(false)}
 *   />
 */

type ConfirmModalProps = {
  open: boolean;
  title: string;
  body: React.ReactNode;
  confirmLabel?: string;
  cancelLabel?: string;
  destructive?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
};


export function ConfirmModal({
  open,
  title,
  body,
  confirmLabel = "Bekräfta",
  cancelLabel = "Avbryt",
  destructive = false,
  onConfirm,
  onCancel,
}: ConfirmModalProps) {
  if (!open) return null;
  return (
    <div
      onClick={onCancel}
      style={{
        position: "fixed", inset: 0,
        background: "rgba(0,0,0,0.75)", zIndex: 250,
        display: "flex", alignItems: "center",
        justifyContent: "center", padding: 20,
      }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          background: "#0f1525",
          border: "1px solid rgba(255,255,255,0.10)",
          borderRadius: 12,
          padding: 26,
          maxWidth: 480,
          width: "100%",
          boxShadow: "0 20px 60px rgba(0,0,0,0.45)",
        }}
      >
        <div style={{
          fontFamily: "var(--mono)",
          fontSize: 10,
          letterSpacing: 1.4,
          color: destructive ? "#fda594" : "#a5b4fc",
          textTransform: "uppercase",
        }}>
          ● Bekräfta åtgärd
        </div>
        <h2 style={{
          fontFamily: "var(--serif)",
          color: "#fff",
          fontSize: 22,
          fontWeight: 700,
          margin: "10px 0 14px",
          letterSpacing: "-0.3px",
        }}>
          {title}
        </h2>
        <div style={{
          fontFamily: "var(--serif)",
          fontSize: 14,
          color: "rgba(255,255,255,0.78)",
          lineHeight: 1.6,
          whiteSpace: "pre-wrap",
          marginBottom: 22,
        }}>
          {body}
        </div>
        <div style={{ display: "flex", gap: 10, justifyContent: "flex-end" }}>
          <button
            type="button"
            onClick={onCancel}
            style={{
              padding: "10px 18px",
              background: "transparent",
              border: "1px solid rgba(255,255,255,0.18)",
              borderRadius: 100,
              color: "rgba(255,255,255,0.7)",
              fontFamily: "var(--mono)",
              fontSize: 10.5,
              fontWeight: 700,
              letterSpacing: "1.2px",
              textTransform: "uppercase",
              cursor: "pointer",
            }}
          >
            {cancelLabel}
          </button>
          <button
            type="button"
            onClick={onConfirm}
            style={{
              padding: "10px 18px",
              background: destructive ? "#dc4c2b" : "var(--accent)",
              border: 0,
              borderRadius: 100,
              color: "#fff",
              fontFamily: "var(--mono)",
              fontSize: 10.5,
              fontWeight: 700,
              letterSpacing: "1.2px",
              textTransform: "uppercase",
              cursor: "pointer",
            }}
          >
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
