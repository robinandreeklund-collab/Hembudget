/**
 * useScrollAnimation — central GSAP + ScrollTrigger-setup för Variant C.
 *
 * Registrerar plugin:et en gång (idempotent) och exponerar:
 *  - useReducedMotion: läser prefers-reduced-motion live (uppdateras
 *    om användaren ändrar OS-inställning under sessionen).
 *  - registerScrollTrigger: säker registrering av ScrollTrigger på
 *    klientsidan; no-op vid SSR.
 *
 * Sektioner som vill köra animationer importerar gsap + ScrollTrigger
 * direkt och använder useGSAP() från @gsap/react för cleanup. Den här
 * filen håller bara den delade init-logiken så vi inte registrerar
 * plugins flera gånger eller missar reduce-motion.
 */
import { useEffect, useState } from "react";
import gsap from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";

let registered = false;

export function registerScrollTrigger(): void {
  if (registered) return;
  if (typeof window === "undefined") return;
  gsap.registerPlugin(ScrollTrigger);
  registered = true;
}

/**
 * Läser prefers-reduced-motion som boolean och prenumererar på
 * change-event så hooken triggar om-render om användaren togglar
 * inställningen mitt i sessionen.
 */
export function useReducedMotion(): boolean {
  const [reduced, setReduced] = useState<boolean>(() => {
    if (typeof window === "undefined" || !window.matchMedia) return false;
    return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  });
  useEffect(() => {
    if (typeof window === "undefined" || !window.matchMedia) return;
    const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
    const onChange = (e: MediaQueryListEvent) => setReduced(e.matches);
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, []);
  return reduced;
}
