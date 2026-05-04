/**
 * GuideOverlay — global spotlight + tip-card för aktiv guide.
 *
 * Renderar:
 * - .guide-scrim (mörkt overlay som scrollar med viewporten)
 * - .guide-spotlight (rektangel runt nuvarande target-element)
 * - .guide-tip (kort med eye/h/prose + Föregående/Nästa-knappar)
 *
 * Navigerar mellan rätt routes via useNavigate. Reglar position via
 * getBoundingClientRect på 350 ms efter scrollIntoView.
 */
import { useEffect, useRef, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { useGuide } from "./GuideContext";
import "./guide.css";

export function GuideOverlay() {
  const {
    isOpen, activeGuide, stepIndex,
    nextStep, prevStep, endGuide,
  } = useGuide();
  const navigate = useNavigate();
  const location = useLocation();
  const [spotRect, setSpotRect] = useState<{
    left: number; top: number; width: number; height: number;
  } | null>(null);
  const [tipPos, setTipPos] = useState<{
    left: number; top: number;
  } | null>(null);
  const tipRef = useRef<HTMLDivElement>(null);

  const step = activeGuide?.steps[stepIndex];
  const totalSteps = activeGuide?.steps.length || 0;

  // Navigera till rätt route om vi inte är där
  useEffect(() => {
    if (!isOpen || !step) return;
    if (location.pathname !== step.route) {
      navigate(step.route);
    }
  }, [isOpen, step, location.pathname, navigate]);

  // Mätning av spotlight-position
  useEffect(() => {
    if (!isOpen || !step) {
      setSpotRect(null);
      setTipPos(null);
      return;
    }
    let cancelled = false;
    function measure() {
      if (cancelled || !step) return;
      const el = document.querySelector(
        step.selector,
      ) as HTMLElement | null;
      if (!el) {
        // Element finns inte än — försök igen om 200 ms (max 5 ggr)
        return null;
      }
      el.scrollIntoView({ block: "center", behavior: "smooth" });
      // Vänta på scroll innan vi mäter
      setTimeout(() => {
        if (cancelled) return;
        const r = el.getBoundingClientRect();
        const pad = 8;
        setSpotRect({
          left: r.left - pad,
          top: r.top - pad,
          width: r.width + pad * 2,
          height: r.height + pad * 2,
        });

        const vw = window.innerWidth;
        const vh = window.innerHeight;
        const isMobile = vw < 700;

        // På mobil placeras tip-kortet alltid ankrad till botten av
        // skärmen och spänner hela bredden — inga out-of-bounds-fel.
        if (isMobile) {
          setTipPos({ left: -1, top: -1 });  // mobile-läge styrs av CSS
          return;
        }

        // Desktop: smart placering med tipW/tipH-beräkning
        const tipW = Math.min(380, vw - 40);
        const tipH = 240;
        const margin = 16;
        const safeTop = 70;  // topbar
        const safeBottom = vh - 50;  // dev-footer
        let left = r.left + r.width / 2 - tipW / 2;
        let top = r.bottom + margin;
        const placement = step.placement;
        if (placement === "bottom") {
          left = Math.max(20, Math.min(vw - tipW - 20, left));
          top = r.bottom + margin;
          if (top + tipH > safeBottom) top = r.top - tipH - margin;
        } else if (placement === "top") {
          left = Math.max(20, Math.min(vw - tipW - 20, left));
          top = r.top - tipH - margin;
          if (top < safeTop) top = r.bottom + margin;
        } else if (placement === "right") {
          left = r.right + margin;
          top = r.top + r.height / 2 - tipH / 2;
          if (left + tipW > vw - 20) left = r.left - tipW - margin;
          if (left < 20) left = 20;
          if (top < safeTop) top = safeTop;
          if (top + tipH > safeBottom) top = safeBottom - tipH;
        } else if (placement === "left") {
          left = r.left - tipW - margin;
          top = r.top + r.height / 2 - tipH / 2;
          if (left < 20) left = r.right + margin;
          if (left + tipW > vw - 20) left = vw - tipW - 20;
          if (top < safeTop) top = safeTop;
          if (top + tipH > safeBottom) top = safeBottom - tipH;
        } else if (placement === "bottom-left") {
          left = Math.max(20, r.right - tipW);
          top = r.bottom + margin;
        }
        // Final clamp · ingen overflow åt något håll
        left = Math.max(20, Math.min(vw - tipW - 20, left));
        top = Math.max(safeTop, Math.min(safeBottom - tipH, top));
        setTipPos({ left, top });
      }, 350);
      return el;
    }
    // Försök mäta direkt; om elementet inte finns, retry x5.
    // Efter 5 försök: visa tip-kortet centrerat på skärmen utan
    // spotlight, så användaren aldrig fastnar med en tom scrim.
    let tries = 0;
    let interval: ReturnType<typeof setInterval> | null = null;
    const elNow = measure();
    if (elNow == null) {
      interval = setInterval(() => {
        if (cancelled) {
          if (interval) clearInterval(interval);
          return;
        }
        tries += 1;
        const el = measure();
        if (el != null || tries > 5) {
          if (interval) clearInterval(interval);
          if (el == null) {
            // Fallback · centrera tip på viewporten utan spotlight
            const vw = window.innerWidth;
            const vh = window.innerHeight;
            const tipW = Math.min(380, vw - 40);
            const tipH = 240;
            setSpotRect(null);
            setTipPos({
              left: Math.max(20, (vw - tipW) / 2),
              top: Math.max(80, (vh - tipH) / 2),
            });
          }
        }
      }, 250);
    }
    function onResize() {
      measure();
    }
    window.addEventListener("resize", onResize);
    return () => {
      cancelled = true;
      if (interval) clearInterval(interval);
      window.removeEventListener("resize", onResize);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isOpen, step?.selector, step?.placement, location.pathname]);

  if (!isOpen || !step || !activeGuide) return null;

  const isLast = stepIndex === totalSteps - 1;

  return (
    <>
      <div className="guide-scrim on" onClick={() => endGuide(false)} />
      {spotRect && (
        <div
          className="guide-spotlight"
          style={{
            left: spotRect.left,
            top: spotRect.top,
            width: spotRect.width,
            height: spotRect.height,
          }}
        />
      )}
      {tipPos && (
        <div
          ref={tipRef}
          className={`guide-tip${
            tipPos.left < 0 ? " guide-tip-mobile" : ""
          }`}
          style={
            tipPos.left < 0
              ? undefined
              : { left: tipPos.left, top: tipPos.top }
          }
        >
          <div className="guide-tip-eye">{step.eye}</div>
          <div
            className="guide-tip-h"
            dangerouslySetInnerHTML={{ __html: step.h }}
          />
          <p
            className="guide-tip-prose"
            dangerouslySetInnerHTML={{ __html: step.prose }}
          />
          <div className="guide-tip-foot">
            <div className="guide-tip-prog">
              Steg <strong>{stepIndex + 1}</strong> av{" "}
              <strong>{totalSteps}</strong>
            </div>
            <div className="guide-tip-actions">
              <button
                type="button"
                className="guide-tip-btn ghost"
                onClick={() => endGuide(false)}
              >
                Hoppa över
              </button>
              <button
                type="button"
                className="guide-tip-btn ghost"
                onClick={prevStep}
                disabled={stepIndex === 0}
              >
                ← Tillbaka
              </button>
              <button
                type="button"
                className="guide-tip-btn solid"
                onClick={nextStep}
              >
                {isLast ? "Klar — börja!" : "Nästa →"}
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
