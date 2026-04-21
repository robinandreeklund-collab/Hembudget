from __future__ import annotations

import argparse
import logging
import sys

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api import (
    admin, auth, balances, budget, chat, loans, reports, scenarios, tax,
    transactions, transfers, upcoming, upload,
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
    # Only allow Tauri-originated requests (or dev server)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "tauri://localhost",
            "http://tauri.localhost",
            "http://localhost:1420",  # Vite dev
            "http://127.0.0.1:1420",
        ],
        allow_credentials=True,
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
    app.include_router(admin.router)

    @app.get("/healthz")
    def healthz() -> dict:
        return {"ok": True, "version": "0.1.0"}

    return app


app = build_app()


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
