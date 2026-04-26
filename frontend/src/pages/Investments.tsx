import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowDown, ArrowUp, Star, TrendingUp, X } from "lucide-react";
import { useMemo, useState } from "react";
import { api, formatSEK } from "@/api/client";
import { Card } from "@/components/Card";
import type { Account } from "@/types/models";

interface Stock {
  ticker: string;
  name: string;
  name_sv: string | null;
  sector: string;
  currency: string;
  exchange: string;
  active: boolean;
  last?: number;
  bid?: number | null;
  ask?: number | null;
  change_pct?: number | null;
  ts?: string | null;
}

interface Holding {
  ticker: string;
  quantity: number;
  avg_cost: number;
  last_price: number;
  market_value: number;
  cost_basis: number;
  unrealized_pnl: number;
  sector: string;
  account_id: number;
}

interface Portfolio {
  holdings: Holding[];
  total_market_value: number;
  total_cost_basis: number;
  unrealized_pnl: number;
  cash_balance: number;
  total_value: number;
  sector_weights: Record<string, number>;
}

interface LedgerRow {
  id: number;
  ticker: string;
  side: "buy" | "sell";
  quantity: number;
  price: number;
  courtage: number;
  total_amount: number;
  realized_pnl: number | null;
  student_rationale: string | null;
  executed_at: string;
}

interface MarketStatus {
  open: boolean;
  now: string;
  next_open: string | null;
}

type Tab = "overview" | "market" | "portfolio" | "ledger";

export default function Investments() {
  const [tab, setTab] = useState<Tab>("overview");
  const [tradeModal, setTradeModal] = useState<{ ticker: string; side: "buy" | "sell" } | null>(null);

  const universeQ = useQuery({
    queryKey: ["stocks-universe"],
    queryFn: () => api<{ stocks: Stock[]; count: number }>("/stocks/universe"),
    refetchInterval: 30_000, // var 30 sek under sidvisning
  });
  const portfolioQ = useQuery({
    queryKey: ["stocks-portfolio"],
    queryFn: () => api<Portfolio>("/stocks/portfolio"),
    refetchInterval: 30_000,
  });
  const ledgerQ = useQuery({
    queryKey: ["stocks-ledger"],
    queryFn: () => api<{ ledger: LedgerRow[]; count: number }>("/stocks/ledger"),
  });
  const marketQ = useQuery({
    queryKey: ["stocks-market"],
    queryFn: () => api<MarketStatus>("/stocks/market/status"),
    refetchInterval: 60_000,
  });
  const watchlistQ = useQuery({
    queryKey: ["stocks-watchlist"],
    queryFn: () => api<{ tickers: string[]; count: number }>("/stocks/watchlist"),
  });

  const stocks = universeQ.data?.stocks ?? [];
  const portfolio = portfolioQ.data;
  const ledger = ledgerQ.data?.ledger ?? [];
  const market = marketQ.data;
  const watchlist = new Set(watchlistQ.data?.tickers ?? []);

  return (
    <div className="p-3 md:p-6 space-y-4 max-w-6xl">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="serif text-3xl flex items-center gap-2">
            <TrendingUp className="w-7 h-7" />
            Aktier
          </h1>
          <div className="text-sm text-slate-700 mt-1">
            Handla 30 svenska large-caps från OMXS30. Avanza Mini-courtage
            (1 kr min, 0,25 % över ~400 kr).
            {market && (
              <span className="ml-2">
                {market.open ? (
                  <span className="inline-block px-2 py-0.5 rounded bg-emerald-100 text-emerald-800">
                    Börsen öppen
                  </span>
                ) : (
                  <span className="inline-block px-2 py-0.5 rounded bg-slate-200 text-slate-700">
                    Börsen stängd
                    {market.next_open ? ` — öppnar ${new Date(market.next_open).toLocaleString("sv-SE")}` : ""}
                  </span>
                )}
              </span>
            )}
          </div>
          <div className="text-xs text-amber-700 mt-1">
            Kurser kan vara försenade ~15 min. Detta är en pedagogisk
            simulator — inte finansiell rådgivning.
          </div>
        </div>
      </div>

      <div className="flex gap-2 border-b">
        {(["overview", "market", "portfolio", "ledger"] as Tab[]).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`px-3 py-2 text-sm border-b-2 ${
              tab === t
                ? "border-brand-600 text-brand-700"
                : "border-transparent text-slate-600"
            }`}
          >
            {t === "overview" && "Översikt"}
            {t === "market" && `Marknad (${stocks.length})`}
            {t === "portfolio" && `Portfölj (${portfolio?.holdings.length ?? 0})`}
            {t === "ledger" && `Order-historik (${ledger.length})`}
          </button>
        ))}
      </div>

      {tab === "overview" && portfolio && (
        <OverviewTab portfolio={portfolio} />
      )}
      {tab === "market" && (
        <MarketTab
          stocks={stocks}
          watchlist={watchlist}
          onTrade={(t) => setTradeModal({ ticker: t, side: "buy" })}
          marketOpen={market?.open ?? false}
        />
      )}
      {tab === "portfolio" && portfolio && (
        <PortfolioTab
          portfolio={portfolio}
          onTrade={(t, s) => setTradeModal({ ticker: t, side: s })}
          marketOpen={market?.open ?? false}
        />
      )}
      {tab === "ledger" && <LedgerTab rows={ledger} />}

      {tradeModal && (
        <TradeModal
          ticker={tradeModal.ticker}
          side={tradeModal.side}
          stock={stocks.find((s) => s.ticker === tradeModal.ticker)}
          holding={portfolio?.holdings.find((h) => h.ticker === tradeModal.ticker)}
          cashBalance={portfolio?.cash_balance ?? 0}
          onClose={() => setTradeModal(null)}
          marketOpen={market?.open ?? false}
        />
      )}
    </div>
  );
}

// --- Översikt ---

function OverviewTab({ portfolio }: { portfolio: Portfolio }) {
  const pnl = portfolio.unrealized_pnl;
  const pnlPct = portfolio.total_cost_basis > 0
    ? (pnl / portfolio.total_cost_basis) * 100
    : 0;
  return (
    <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
      <Card title="Totalt portföljvärde">
        <div className="text-3xl serif">{formatSEK(portfolio.total_value)}</div>
        <div className="text-sm text-slate-600 mt-1">
          inkl. likvid: {formatSEK(portfolio.cash_balance)}
        </div>
      </Card>
      <Card title="Orealiserad vinst/förlust">
        <div className={`text-3xl serif ${pnl >= 0 ? "text-emerald-700" : "text-red-700"}`}>
          {pnl >= 0 ? "+" : ""}{formatSEK(pnl)}
        </div>
        <div className="text-sm text-slate-600 mt-1">
          {pnlPct >= 0 ? "+" : ""}{pnlPct.toFixed(2)} % på anskaffningsvärde
        </div>
      </Card>
      <Card title="Sektorvikter">
        <div className="space-y-1 text-sm">
          {Object.entries(portfolio.sector_weights)
            .sort((a, b) => b[1] - a[1])
            .map(([sector, weight]) => (
              <div key={sector} className="flex items-center justify-between">
                <span>{sector}</span>
                <span className="font-medium">{weight.toFixed(1)} %</span>
              </div>
            ))}
          {Object.keys(portfolio.sector_weights).length === 0 && (
            <div className="text-slate-500">Inga innehav än</div>
          )}
        </div>
      </Card>
    </div>
  );
}

// --- Marknad ---

function MarketTab({
  stocks,
  watchlist,
  onTrade,
  marketOpen,
}: {
  stocks: Stock[];
  watchlist: Set<string>;
  onTrade: (ticker: string) => void;
  marketOpen: boolean;
}) {
  const qc = useQueryClient();
  const watchMut = useMutation({
    mutationFn: (params: { ticker: string; add: boolean }) =>
      api(`/stocks/watchlist/${params.add ? "add" : "remove"}`, {
        method: "POST",
        body: JSON.stringify({ ticker: params.ticker }),
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["stocks-watchlist"] }),
  });

  const grouped = useMemo(() => {
    const out = new Map<string, Stock[]>();
    for (const s of stocks) {
      if (!out.has(s.sector)) out.set(s.sector, []);
      out.get(s.sector)!.push(s);
    }
    return out;
  }, [stocks]);

  return (
    <div className="space-y-4">
      {Array.from(grouped.entries()).map(([sector, list]) => (
        <Card key={sector} title={`${sector} (${list.length})`}>
          <div className="space-y-1">
            {list.map((s) => {
              const onWatch = watchlist.has(s.ticker);
              return (
                <div
                  key={s.ticker}
                  className="flex items-center justify-between border-b last:border-0 py-2"
                >
                  <div className="flex-1">
                    <div className="font-medium">{s.name}</div>
                    <div className="text-xs text-slate-500">{s.ticker}</div>
                  </div>
                  <div className="text-right pr-3">
                    {s.last !== undefined ? (
                      <>
                        <div className="font-medium">{formatSEK(s.last)}</div>
                        {s.change_pct !== null && s.change_pct !== undefined && (
                          <div
                            className={`text-xs ${
                              s.change_pct >= 0 ? "text-emerald-700" : "text-red-700"
                            }`}
                          >
                            {s.change_pct >= 0 ? "+" : ""}{s.change_pct.toFixed(2)} %
                          </div>
                        )}
                      </>
                    ) : (
                      <div className="text-slate-400 text-sm">— ingen kurs —</div>
                    )}
                  </div>
                  <button
                    onClick={() =>
                      watchMut.mutate({ ticker: s.ticker, add: !onWatch })
                    }
                    className="p-1 hover:bg-slate-100 rounded mr-2"
                    title={onWatch ? "Ta bort från watchlist" : "Lägg till i watchlist"}
                  >
                    <Star
                      className={`w-4 h-4 ${
                        onWatch ? "fill-amber-400 text-amber-500" : "text-slate-400"
                      }`}
                    />
                  </button>
                  <button
                    onClick={() => onTrade(s.ticker)}
                    disabled={!marketOpen || s.last === undefined}
                    className="bg-brand-600 text-white px-3 py-1.5 rounded text-sm disabled:opacity-50"
                  >
                    Köp
                  </button>
                </div>
              );
            })}
          </div>
        </Card>
      ))}
    </div>
  );
}

// --- Portfölj ---

function PortfolioTab({
  portfolio,
  onTrade,
  marketOpen,
}: {
  portfolio: Portfolio;
  onTrade: (ticker: string, side: "buy" | "sell") => void;
  marketOpen: boolean;
}) {
  if (portfolio.holdings.length === 0) {
    return (
      <Card title="Portfölj">
        <div className="text-slate-500">
          Du har inga aktier än. Gå till "Marknad" och köp dina första.
        </div>
      </Card>
    );
  }
  return (
    <Card title={`Innehav (${portfolio.holdings.length})`}>
      <table className="w-full text-sm">
        <thead className="text-left text-slate-600 border-b">
          <tr>
            <th className="py-2">Aktie</th>
            <th>Antal</th>
            <th>Snittkurs</th>
            <th>Senaste kurs</th>
            <th>Marknadsvärde</th>
            <th>Vinst/förlust</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {portfolio.holdings.map((h) => (
            <tr key={h.ticker} className="border-b last:border-0">
              <td className="py-2">
                <div className="font-medium">{h.ticker}</div>
                <div className="text-xs text-slate-500">{h.sector}</div>
              </td>
              <td>{h.quantity}</td>
              <td>{formatSEK(h.avg_cost)}</td>
              <td>{formatSEK(h.last_price)}</td>
              <td>{formatSEK(h.market_value)}</td>
              <td className={h.unrealized_pnl >= 0 ? "text-emerald-700" : "text-red-700"}>
                {h.unrealized_pnl >= 0 ? "+" : ""}
                {formatSEK(h.unrealized_pnl)}
              </td>
              <td className="text-right space-x-1">
                <button
                  onClick={() => onTrade(h.ticker, "buy")}
                  disabled={!marketOpen}
                  className="px-2 py-1 text-xs rounded bg-emerald-600 text-white disabled:opacity-50"
                >
                  Köp
                </button>
                <button
                  onClick={() => onTrade(h.ticker, "sell")}
                  disabled={!marketOpen}
                  className="px-2 py-1 text-xs rounded bg-amber-600 text-white disabled:opacity-50"
                >
                  Sälj
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </Card>
  );
}

// --- Ledger ---

function LedgerTab({ rows }: { rows: LedgerRow[] }) {
  if (rows.length === 0) {
    return (
      <Card title="Order-historik">
        <div className="text-slate-500">Du har inte gjort några affärer än.</div>
      </Card>
    );
  }
  return (
    <Card title={`Order-historik (${rows.length})`}>
      <div className="text-xs text-slate-600 mb-2">
        Append-only ledger — varje rad är en låst affär. Läraren kan se exakt
        vilken kurs som gällde via quote_id.
      </div>
      <table className="w-full text-sm">
        <thead className="text-left text-slate-600 border-b">
          <tr>
            <th className="py-2">Tid</th>
            <th>Köp/Sälj</th>
            <th>Aktie</th>
            <th>Antal</th>
            <th>Kurs</th>
            <th>Courtage</th>
            <th>Total</th>
            <th>Vinst/förlust</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.id} className="border-b last:border-0">
              <td className="py-2 text-xs">
                {new Date(r.executed_at).toLocaleString("sv-SE")}
              </td>
              <td>
                {r.side === "buy" ? (
                  <span className="inline-flex items-center gap-1 text-emerald-700">
                    <ArrowDown className="w-3 h-3" />
                    Köp
                  </span>
                ) : (
                  <span className="inline-flex items-center gap-1 text-amber-700">
                    <ArrowUp className="w-3 h-3" />
                    Sälj
                  </span>
                )}
              </td>
              <td>{r.ticker}</td>
              <td>{r.quantity}</td>
              <td>{formatSEK(r.price)}</td>
              <td>{formatSEK(r.courtage)}</td>
              <td>{formatSEK(r.total_amount)}</td>
              <td className={
                r.realized_pnl === null
                  ? ""
                  : r.realized_pnl >= 0
                  ? "text-emerald-700"
                  : "text-red-700"
              }>
                {r.realized_pnl === null
                  ? "—"
                  : `${r.realized_pnl >= 0 ? "+" : ""}${formatSEK(r.realized_pnl)}`}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </Card>
  );
}

// --- Köp/Sälj-modal ---

function TradeModal({
  ticker,
  side,
  stock,
  holding,
  cashBalance,
  onClose,
  marketOpen,
}: {
  ticker: string;
  side: "buy" | "sell";
  stock?: Stock;
  holding?: Holding;
  cashBalance: number;
  onClose: () => void;
  marketOpen: boolean;
}) {
  const qc = useQueryClient();
  const [quantity, setQuantity] = useState<string>("1");
  const [rationale, setRationale] = useState<string>("");
  const [error, setError] = useState<string | null>(null);

  // Vi behöver veta vilket ISK-konto vi handlar i. Hämta listan här.
  const accountsQ = useQuery({
    queryKey: ["accounts"],
    queryFn: () => api<Account[]>("/accounts"),
  });
  const iskAccounts = (accountsQ.data ?? []).filter((a) => a.type === "isk");
  const [accountId, setAccountId] = useState<number | null>(
    holding?.account_id ?? null,
  );

  const qty = parseInt(quantity || "0", 10);
  const validQty = Number.isFinite(qty) && qty > 0;
  const price = stock?.last ?? 0;
  const gross = validQty ? qty * price : 0;
  const courtage = gross > 0 ? Math.max(1, +(gross * 0.0025).toFixed(2)) : 0;
  const total = side === "buy" ? gross + courtage : gross - courtage;

  const tradeMut = useMutation({
    mutationFn: (body: { account_id: number; quantity: number; student_rationale: string }) =>
      api(`/stocks/${ticker}/${side}`, {
        method: "POST",
        body: JSON.stringify(body),
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["stocks-portfolio"] });
      qc.invalidateQueries({ queryKey: ["stocks-ledger"] });
      qc.invalidateQueries({ queryKey: ["balances"] });
      onClose();
    },
    onError: (e: unknown) => {
      setError(e instanceof Error ? e.message : "Kunde inte genomföra ordern");
    },
  });

  const canTrade =
    marketOpen &&
    validQty &&
    stock?.last !== undefined &&
    accountId !== null &&
    (side === "buy" ? cashBalance >= total : (holding?.quantity ?? 0) >= qty) &&
    !tradeMut.isPending;

  return (
    <div
      className="fixed inset-0 z-50 bg-black/40 flex items-center justify-center p-4"
      onClick={onClose}
    >
      <div
        className="bg-white rounded-xl shadow-xl w-full max-w-md p-5 space-y-3"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between">
          <h2 className="serif text-2xl">
            {side === "buy" ? "Köp" : "Sälj"} {stock?.name ?? ticker}
          </h2>
          <button onClick={onClose} className="text-slate-500 hover:text-slate-800">
            <X className="w-5 h-5" />
          </button>
        </div>
        <div className="text-sm text-slate-600">
          Aktuell kurs: <strong>{formatSEK(price)}</strong>
          {stock?.ts && (
            <span className="ml-2 text-xs text-slate-500">
              (uppdaterad {new Date(stock.ts).toLocaleTimeString("sv-SE")})
            </span>
          )}
        </div>

        <div className="space-y-2">
          <label className="text-sm font-medium">ISK-konto</label>
          <select
            value={accountId ?? ""}
            onChange={(e) => setAccountId(Number(e.target.value))}
            className="w-full border rounded px-3 py-2"
          >
            <option value="" disabled>
              Välj ISK-konto…
            </option>
            {iskAccounts.map((a) => (
              <option key={a.id} value={a.id}>{a.name}</option>
            ))}
          </select>
          {iskAccounts.length === 0 && (
            <div className="text-xs text-amber-700">
              Inga ISK-konton hittades. Skapa ett under "Konton" först.
            </div>
          )}
        </div>

        <div className="space-y-2">
          <label className="text-sm font-medium">Antal aktier</label>
          <input
            type="number"
            min={1}
            value={quantity}
            onChange={(e) => setQuantity(e.target.value)}
            className="w-full border rounded px-3 py-2"
          />
          {side === "sell" && holding && (
            <div className="text-xs text-slate-600">
              Du äger {holding.quantity} st till snittkurs {formatSEK(holding.avg_cost)}
            </div>
          )}
        </div>

        <div className="space-y-2">
          <label className="text-sm font-medium">Motivering (valfritt)</label>
          <textarea
            rows={2}
            value={rationale}
            onChange={(e) => setRationale(e.target.value)}
            placeholder="Varför just denna affär?"
            className="w-full border rounded px-3 py-2 text-sm"
          />
        </div>

        {validQty && (
          <div className="bg-slate-50 border rounded p-3 text-sm space-y-1">
            <div className="flex justify-between">
              <span>Belopp ({qty} × {formatSEK(price)})</span>
              <span>{formatSEK(gross)}</span>
            </div>
            <div className="flex justify-between">
              <span>Courtage (Mini)</span>
              <span>{formatSEK(courtage)}</span>
            </div>
            <div className="flex justify-between font-semibold border-t pt-1">
              <span>{side === "buy" ? "Att betala" : "Att få"}</span>
              <span>{formatSEK(total)}</span>
            </div>
          </div>
        )}

        {!marketOpen && (
          <div className="text-sm text-amber-700 bg-amber-50 border border-amber-200 rounded p-2">
            Börsen är stängd. Du kan inte handla just nu.
          </div>
        )}
        {error && (
          <div className="text-sm text-red-700 bg-red-50 border border-red-200 rounded p-2">
            {error}
          </div>
        )}

        <div className="flex gap-2 justify-end pt-2">
          <button onClick={onClose} className="px-4 py-2 rounded border bg-white">
            Avbryt
          </button>
          <button
            disabled={!canTrade}
            onClick={() => {
              if (!canTrade || accountId === null) return;
              tradeMut.mutate({
                account_id: accountId,
                quantity: qty,
                student_rationale: rationale,
              });
            }}
            className={`px-4 py-2 rounded text-white disabled:opacity-50 ${
              side === "buy" ? "bg-emerald-600" : "bg-amber-600"
            }`}
          >
            {tradeMut.isPending
              ? "Genomför…"
              : side === "buy"
              ? "Bekräfta köp"
              : "Bekräfta sälj"}
          </button>
        </div>
      </div>
    </div>
  );
}
