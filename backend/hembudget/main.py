from __future__ import annotations

import argparse
import logging
import sys

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api import (
    admin, auth, balances, budget, chat, elpris, loans, reports, scenarios,
    tax, transactions, transfers, upcoming, upload,
)
from .config import settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)


def build_app() -> FastAPI:
    app = FastAPI(
        title="Hembudget API",
        version="0.1.0",
        description="Lokal AI-driven familjeekonomi (Nemotron Nano 3 via LM Studio)",
    )
    # I demo-mode tillåt alla origins (publik Render-deploy)
    import os
    demo = os.environ.get("HEMBUDGET_DEMO_MODE", "").lower() in ("1", "true", "yes")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"] if demo else [
            "tauri://localhost",
            "http://tauri.localhost",
            "http://localhost:1420",
            "http://127.0.0.1:1420",
        ],
        allow_credentials=not demo,   # wildcard + credentials är inte tillåtet
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(auth.router)
    app.include_router(transactions.router)
    app.include_router(upload.router)
    app.include_router(budget.router)
    app.include_router(chat.router)
    app.include_router(scenarios.router)
    app.include_router(tax.router)
    app.include_router(reports.router)
    app.include_router(loans.router)
    app.include_router(transfers.router)
    app.include_router(upcoming.router)
    app.include_router(balances.router)
    app.include_router(elpris.router)
    app.include_router(admin.router)

    @app.get("/healthz")
    def healthz() -> dict:
        return {"ok": True, "version": "0.1.0"}

    return app


app = build_app()


@app.on_event("startup")
def _demo_bootstrap() -> None:
    """Vid demo-mode: fyll databasen med användarens CSV/XLSX-data vid start."""
    try:
        from .demo import bootstrap_if_empty
        result = bootstrap_if_empty()
        if result and not result.get("skipped"):
            logging.getLogger(__name__).info("demo bootstrap: %s", result)
    except Exception:
        logging.getLogger(__name__).exception("demo bootstrap failed")


def main() -> None:
    parser = argparse.ArgumentParser(description="Hembudget sidecar server")
    parser.add_argument("--host", default=settings.host)
    parser.add_argument("--port", type=int, default=settings.port)
    parser.add_argument("--print-port", action="store_true",
                        help="Print chosen port on first line of stdout (for Tauri).")
    args = parser.parse_args()

    if args.print_port:
        # Bind to 0 first to discover port, then pass to uvicorn
        import socket
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.bind((args.host, 0))
        port = sock.getsockname()[1]
        sock.close()
        print(port, flush=True)
    else:
        port = args.port or 8765

    uvicorn.run(app, host=args.host, port=port, log_level="info")


if __name__ == "__main__":
    main()
