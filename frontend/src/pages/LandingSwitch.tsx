/**
 * LandingSwitch.tsx — TIDIGARE: hämtade aktiv landing-variant och
 * router till Landing eller LandingVariantC. NU: tom redirect-stub
 * som tvingar full page-reload till `/`, vilket backend serverar
 * från demo-landing/index.html (den nya editorial-startsidan).
 *
 * Det här ersätter den gamla SPA-Landing.tsx för slutanvändare.
 * Komponenten används fortfarande av React Router för catch-all
 * (`*`) och `/`-routen i unauth-blocket — alla träffar på dessa
 * resulterar i att webbläsaren redirectas till backend-rooten.
 */
import { useEffect } from "react";

export default function LandingSwitch() {
  useEffect(() => {
    // window.location.replace säkerställer att SPA-laddningen ersätts
    // av en riktig GET / mot backend, som returnerar demo-landing.
    if (typeof window !== "undefined") {
      window.location.replace("/");
    }
  }, []);
  return null;
}
