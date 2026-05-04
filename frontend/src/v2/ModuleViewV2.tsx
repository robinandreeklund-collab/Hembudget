/**
 * Modul-detalj v2 · /v2/moduler/:moduleId
 *
 * Bug #12 · Wrappar v1 ModuleView (full step-renderare med heartbeat,
 * AI, celebration) inom v2-shell (V2Banner topbar, dark surface,
 * tillbaka-länk till v2-modullistan).
 *
 * Inner-komponenten ModuleViewInner exporteras från v1-filen och
 * återanvänder all befintlig logik utan duplicering.
 */
import { Link } from "react-router-dom";
import { V2Banner } from "./V2Banner";
import { ModuleViewInner } from "../pages/ModuleView";
import "./module-view-v2.css";


export function ModuleViewV2() {
  return (
    <div
      style={{
        minHeight: "100vh",
        background: "linear-gradient(180deg, #0a0e1a 0%, #0f1525 100%)",
      }}
    >
      <V2Banner status={{ role: "student", is_super_admin: false }} />

      <div style={{ maxWidth: 1280, margin: "0 auto", padding: "20px 28px 4px" }}>
        <Link
          to="/v2/moduler"
          style={{
            color: "rgba(255,255,255,0.6)",
            textDecoration: "none",
            fontSize: "0.9rem",
            display: "inline-flex",
            alignItems: "center",
            gap: 6,
            fontFamily: "JetBrains Mono, monospace",
            letterSpacing: 1.1,
            textTransform: "uppercase",
          }}
        >
          ← Mina moduler
        </Link>
      </div>

      {/* v2-tema · CSS-overrides i module-view-v2.css mappar v1
          Tailwind-klasser till mörkt tema (bg-slate-50 → bg-mid,
          text-slate-900 → vit, etc.). Step-renderare, AI, celebrate
          fortsätter funka identiskt — bara färgerna skiftas. */}
      <div className="v2-module-frame">
        <ModuleViewInner />
      </div>
    </div>
  );
}
