/**
 * V2Banner är nu en re-export av V2Topbar (Fas 2AA).
 *
 * Den gamla feta dev-bannern är borttagen — minimal status-info
 * ligger istället i V2DevFooter (renderad globalt i App.tsx).
 * Befintliga imports av V2Banner fungerar fortfarande och får
 * den nya, prototyptrogna topbar-stilen.
 */
export { V2Topbar as V2Banner } from "./V2Topbar";
