/**
 * Modul-detalj v2 · /v2/moduler/:moduleId
 *
 * Wrappar v1 ModuleView (full step-renderare med heartbeat, AI,
 * celebration) inom v2-shell (V2Banner topbar, dark surface).
 *
 * v1-komponenten är stylad med Tailwind ljus-utility-klasser. Istället
 * för att skriva om hela renderaren skopar vi om de klasserna till
 * V2-mörka motsvarigheter via .v2-module-skin (se module.css). Det ger
 * V2-look (dark gradient, serif-rubriker, indigo highlights) utan att
 * röra v1-logiken (heartbeat, AI, celebrate-overlay).
 */
import { Link } from "react-router-dom";
import { V2Banner } from "./V2Banner";
import { ModuleViewInner } from "../pages/ModuleView";
import "./module.css";


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

      <div className="v2-module-skin" style={{ margin: "12px 0 28px" }}>
        <ModuleViewInner />
      </div>
    </div>
  );
}
