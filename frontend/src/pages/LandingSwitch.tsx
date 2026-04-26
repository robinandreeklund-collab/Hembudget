/**
 * LandingSwitch.tsx — fetchar aktiv landings-variant från
 * /landing/variant och router till respektive komponent.
 *
 * Default: paper-stilen (Landing.tsx). Variant 'c' renderar
 * LandingVariantC.tsx. Toggle:n finns i super-admin för A/B-test.
 *
 * Vid laddning visas Landing direkt (optimistisk default) — om
 * fetch:n hinner returnera 'c' växlar vi till variant C utan att
 * blocka first paint.
 */
import { useEffect, useState } from "react";
import { api } from "@/api/client";
import Landing from "./Landing";
import LandingVariantC from "./LandingVariantC";

type VariantOut = { variant: string };

export default function LandingSwitch() {
  const [variant, setVariant] = useState<string>("default");

  useEffect(() => {
    api<VariantOut>("/landing/variant")
      .then((r) => {
        if (r.variant === "c") setVariant("c");
      })
      .catch(() => undefined);
  }, []);

  return variant === "c" ? <LandingVariantC /> : <Landing />;
}
