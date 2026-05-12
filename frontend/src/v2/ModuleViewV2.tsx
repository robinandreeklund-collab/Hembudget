/**
 * Modul-detalj v2 · /v2/moduler/:moduleId
 *
 * Wrappar v1 ModuleView (full step-renderare med heartbeat, AI,
 * celebration) inom v2-shell · samma `v2-lan-root` + `shell` +
 * `actor-back` som övriga aktör-vyer (Aktier, Avanza, Huvudboken).
 *
 * v1-komponenten är stylad med Tailwind ljus-utility-klasser. Istället
 * för att skriva om hela renderaren skopar vi om de klasserna till
 * V2-mörka motsvarigheter via .v2-module-skin (se module.css). Det ger
 * V2-look (orange accent, serif-rubriker, mörka kort) utan att röra
 * v1-logiken (heartbeat, AI, celebrate-overlay).
 */
import { Link } from "react-router-dom";
import { V2Banner } from "./V2Banner";
import { ModuleViewInner } from "../pages/ModuleView";
import "./module.css";


export function ModuleViewV2() {
  return (
    <div className="v2-lan-root">
      <V2Banner status={{ role: "student", is_super_admin: false }} />

      <div className="shell">
        <Link className="actor-back" to="/v2/moduler">
          ← Tillbaka till mina moduler
        </Link>

        <div className="v2-module-skin" style={{ marginTop: 12 }}>
          <ModuleViewInner />
        </div>
      </div>
    </div>
  );
}
