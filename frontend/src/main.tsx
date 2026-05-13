import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import App from "./App";
import "./index.css";

// Sätt body[data-mode] SYNKRONT innan React renderar — så panel-display
// (privat ↔ biz) är korrekt från första frame. Om vi väntar på att
// V2Topbar:s useEffect ska sätta attributet får vi en kort flash där
// fel panel syns. Värdet ligger i localStorage från senaste mode-byte.
try {
  const m = localStorage.getItem("hb_company_mode");
  if (m === "business" || m === "private") {
    document.body.setAttribute("data-mode", m);
  }
} catch {
  // localStorage kan vara avstängd · fall back till default (private)
}

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: 1, refetchOnWindowFocus: false } },
});

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <App />
      </BrowserRouter>
    </QueryClientProvider>
  </React.StrictMode>,
);
