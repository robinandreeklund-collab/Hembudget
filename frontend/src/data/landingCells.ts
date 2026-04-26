// Delad celldata för Variant C — tip/long/example/trains per cell.
// Konsumeras av LandingVariantC.tsx för hover-tooltip och modal.

export type CellCat = "grund" | "fordj" | "expert" | "konto" | "risk" | "prof";

export type CellInfo = {
  n: number;
  sym: string;
  name: string;
  desc: string;
  cat: CellCat;
  tip: string;
  long: string;
  example: string;
  trains: string;
};

export const CELL_INFO: CellInfo[] = [];
