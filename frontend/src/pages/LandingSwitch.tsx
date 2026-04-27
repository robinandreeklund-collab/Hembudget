/**
 * LandingSwitch.tsx — fetchar aktiv landings-variant från
 * /landing/variant och router till respektive komponent.
 *
 * Default: variant 'c' (Ekonomilabbet v5-rebuild). Super-admin kan
 * toggla tillbaka till 'default' (paper-stilen i Landing.tsx) i
 * admin-panelen för A/B-test.
 *
 * Vid laddning visas LandingVariantC direkt (optimistisk default) —
 * om backend skulle returnera 'default' växlar vi då över utan att
 * blocka first paint. För majoriteten av besökare betyder det noll
 * flicker.
 */
import { useEffect, useState } from "react";
import { api } from "@/api/client";
import Landing from "./Landing";
import LandingVariantC from "./LandingVariantC";

type VariantOut = { variant: string };

export default function LandingSwitch() {
  const [variant, setVariant] = useState<string>("c");

  useEffect(() => {
    api<VariantOut>("/landing/variant")
      .then((r) => {
        if (r.variant === "default") setVariant("default");
      })
      .catch(() => undefined);
  }, []);

  return variant === "default" ? <Landing /> : <LandingVariantC />;
}
