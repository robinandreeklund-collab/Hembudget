/**
 * Global state för interaktiva guider.
 *
 * Lagrar nuvarande guide + steg + completed-set i localStorage så
 * eleven inte måste börja om varje session. Auto-start av Intro
 * sköts via useAutoStartIntroGuide()-hooken nedan.
 */
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { GUIDES, type GuideDef } from "./guidesData";

const COMPLETED_KEY = "v2_completed_guides";
const INTRO_DONE_KEY = "v2_intro_guide_done";
const INTRO_DISMISSED_KEY = "v2_intro_guide_dismissed";

type GuideState = {
  activeKey: string | null;
  stepIndex: number;
  isOpen: boolean;
  completedKeys: Set<string>;
};

type GuideActions = {
  startGuide: (key: string) => void;
  nextStep: () => void;
  prevStep: () => void;
  endGuide: (markCompleted?: boolean) => void;
  dismissIntro: () => void;
  hasCompleted: (key: string) => boolean;
};

type GuideContextValue = GuideState & GuideActions & {
  activeGuide: GuideDef | null;
};

const GuideContext = createContext<GuideContextValue | null>(null);

function readCompleted(): Set<string> {
  try {
    const raw = localStorage.getItem(COMPLETED_KEY);
    if (!raw) return new Set();
    const parsed = JSON.parse(raw);
    if (Array.isArray(parsed)) return new Set(parsed.map(String));
    return new Set();
  } catch {
    return new Set();
  }
}

function writeCompleted(s: Set<string>) {
  try {
    localStorage.setItem(COMPLETED_KEY, JSON.stringify(Array.from(s)));
  } catch {
    // localStorage full eller blockerat — fail-soft
  }
}

export function GuideProvider({ children }: { children: ReactNode }) {
  const [activeKey, setActiveKey] = useState<string | null>(null);
  const [stepIndex, setStepIndex] = useState(0);
  const [completedKeys, setCompletedKeys] = useState<Set<string>>(
    () => readCompleted(),
  );

  const isOpen = activeKey != null;
  const activeGuide = activeKey ? GUIDES[activeKey] || null : null;

  const startGuide = useCallback((key: string) => {
    if (!GUIDES[key]) return;
    setActiveKey(key);
    setStepIndex(0);
  }, []);

  const endGuide = useCallback((markCompleted = false) => {
    if (markCompleted && activeKey) {
      const next = new Set(completedKeys);
      next.add(activeKey);
      setCompletedKeys(next);
      writeCompleted(next);
      if (activeKey === "intro") {
        try {
          localStorage.setItem(INTRO_DONE_KEY, "1");
        } catch {
          // fail-soft
        }
      }
    }
    setActiveKey(null);
    setStepIndex(0);
  }, [activeKey, completedKeys]);

  const nextStep = useCallback(() => {
    if (!activeGuide) return;
    if (stepIndex >= activeGuide.steps.length - 1) {
      endGuide(true);
      return;
    }
    setStepIndex((i) => i + 1);
  }, [activeGuide, stepIndex, endGuide]);

  const prevStep = useCallback(() => {
    if (stepIndex > 0) setStepIndex((i) => i - 1);
  }, [stepIndex]);

  const dismissIntro = useCallback(() => {
    try {
      localStorage.setItem(INTRO_DISMISSED_KEY, "1");
    } catch {
      // fail-soft
    }
    if (activeKey === "intro") endGuide(false);
  }, [activeKey, endGuide]);

  const hasCompleted = useCallback(
    (key: string) => completedKeys.has(key),
    [completedKeys],
  );

  // Esc stänger guiden
  useEffect(() => {
    if (!isOpen) return;
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") endGuide(false);
      else if (e.key === "ArrowRight") nextStep();
      else if (e.key === "ArrowLeft") prevStep();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [isOpen, endGuide, nextStep, prevStep]);

  const value = useMemo<GuideContextValue>(
    () => ({
      activeKey,
      stepIndex,
      isOpen,
      completedKeys,
      activeGuide,
      startGuide,
      nextStep,
      prevStep,
      endGuide,
      dismissIntro,
      hasCompleted,
    }),
    [
      activeKey, stepIndex, isOpen, completedKeys, activeGuide,
      startGuide, nextStep, prevStep, endGuide, dismissIntro,
      hasCompleted,
    ],
  );

  return (
    <GuideContext.Provider value={value}>{children}</GuideContext.Provider>
  );
}

export function useGuide(): GuideContextValue {
  const ctx = useContext(GuideContext);
  if (!ctx) {
    throw new Error("useGuide must be used inside <GuideProvider>");
  }
  return ctx;
}

/**
 * Hooka in i HubV2: om eleven slutat onboarding men inte sett
 * intro-guiden — starta den auto efter 800 ms (så Hub:s data hinner
 * laddas och pentagonen är synlig).
 */
export function useAutoStartIntroGuide() {
  const { startGuide, isOpen } = useGuide();
  useEffect(() => {
    if (isOpen) return;
    let dismissed = false;
    let done = false;
    try {
      dismissed = localStorage.getItem(INTRO_DISMISSED_KEY) === "1";
      done = localStorage.getItem(INTRO_DONE_KEY) === "1";
    } catch {
      // fail-soft
    }
    if (dismissed || done) return;
    const t = setTimeout(() => {
      startGuide("intro");
    }, 800);
    return () => clearTimeout(t);
  }, [startGuide, isOpen]);
}
