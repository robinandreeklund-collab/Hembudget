/**
 * LandingVariantC.tsx — alternativ landing-design (SaaS/dashboard-stil).
 *
 * Aktiveras av super-admin via /admin/landing/variant ('c'). Frontend
 * fetchar /landing/variant vid mount och App.tsx routar dit.
 *
 * Designskillnader mot Landing.tsx (paper-stil):
 *  - Inter + JetBrains Mono i stället för Spectral serif
 *  - Mjuk pastel-palett (#f8fafc bakgrund)
 *  - Tab-navigation, command-palette-sök, status-strip
 *  - Mascoten "Ugglan" som AI-coach-personlighet
 *  - Tre-vyer-kort som inkluderar kommande riktig-ekonomi-pitch
 *
 * Sektioner (bygger ut stegvis):
 *  - Header (sticky)
 *  - Hero med periodisk-karta
 *  - Features (9-grid med tab-filter)
 *  - Moments (5 nyckelmoment)
 *  - Logic (3-grid)
 *  - Problem
 *  - Two-Ways (skola/hemma/kommer)
 *  - Screens
 *  - Pricing
 *  - FAQ
 *  - Contact (återanvänd från Landing.tsx)
 *  - Footer (återanvänd från Landing.tsx)
 */
import { useState } from "react";

export default function LandingVariantC() {
  return (
    <div
      style={{
        width: "100%",
        minHeight: "100vh",
        background: "#f8fafc",
        fontFamily: '"Inter", "Helvetica Neue", system-ui, sans-serif',
        color: "#0f172a",
      }}
    >
      <DevPlaceholder />
    </div>
  );
}

function DevPlaceholder() {
  const [, force] = useState(0);
  return (
    <div
      style={{
        maxWidth: 720,
        margin: "0 auto",
        padding: "80px 24px",
        textAlign: "center",
      }}
    >
      <div
        style={{
          display: "inline-block",
          padding: "4px 12px",
          background: "#fef3c7",
          color: "#78350f",
          fontFamily: 'ui-monospace, "SF Mono", monospace',
          fontSize: 11,
          letterSpacing: 1.2,
          textTransform: "uppercase",
          borderRadius: 100,
          marginBottom: 24,
        }}
      >
        Variant C · under uppbyggnad
      </div>
      <h1 style={{ fontSize: 40, fontWeight: 700, letterSpacing: -1.2 }}>
        Den nya designen rullar ut sektion för sektion.
      </h1>
      <p style={{ marginTop: 16, color: "#475569", fontSize: 16 }}>
        Super-admin har slagit på den alternativa landings-designen för
        A/B-test. Resterande sektioner (Hero, features, pricing m.m.)
        läggs till i kommande uppdateringar.
      </p>
      <button
        type="button"
        onClick={() => force((v) => v + 1)}
        style={{ display: "none" }}
      />
    </div>
  );
}
