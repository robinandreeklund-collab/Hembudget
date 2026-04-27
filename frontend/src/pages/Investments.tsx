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
  market_value: number;            // SEK
  market_value_native?: number;    // i affärsvalutan (SEK eller USD)
  cost_basis: number;              // SEK
  cost_basis_native?: number;      // i affärsvalutan
  unrealized_pnl: number;          // SEK
  unrealized_pnl_native?: number;  // i affärsvalutan
  currency?: string;
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
  fx_usd_sek: number | null;
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

type Tab = "overview" | "market" | "portfolio" | "orders" | "ledger";

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
        {(["overview", "market", "portfolio", "orders", "ledger"] as Tab[]).map((t) => (
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
            {t === "orders" && "Ordrar"}
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
      {tab === "orders" && <OrdersTab />}
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

const LEARN_TIPS = [
  {
    title: "Diversifiering är gratis lunch",
    body: "Sprid över 5+ aktier i olika sektorer. När en faller har en annan oftast tur. Riskpremien minskar utan att förväntad avkastning gör det.",
  },
  {
    title: "Tid på marknaden > timing",
    body: "Att sitta still i 10 år slår oftast den som försöker köpa lågt och sälja högt. Marknaden är oförutsägbar på kort sikt men trendar uppåt över decennier.",
  },
  {
    title: "Courtaget äter avkastningen",
    body: "Mini-courtage ≈ 0,25 % per affär. Köp + sälj = 0,5 %. Handla ofta och du betalar mer än utdelningen ger.",
  },
  {
    title: "ISK schablonbeskattas",
    body: "Inom ISK betalar du ca 0,9 % per år på portföljens snittvärde — inte vinstskatt. Bra för långsiktigt sparande, mindre bra om du sitter på obeskattade förluster.",
  },
  {
    title: "Utlandshandel kostar extra",
    body: "USA-aktier handlas i USD: utöver mäklarcourtaget tillkommer 0,25 % valutaväxlingsavgift på köp OCH sälj. Det blir alltså 0,5 % bara i FX om du säljer samma år som du köpte. Ofta värt det för dollar-bolag du inte hittar i Sverige (Apple, Nvidia) — men gör inte småbeställningar.",
  },
];


interface FxData {
  rate: number | null;
  ts: string | null;
  history: { date: string; rate: number }[];
  change_pct_30d: number | null;
}


function FxCard() {
  const { data } = useQuery({
    queryKey: ["fx-usd-sek"],
    queryFn: () => api<FxData>("/stocks/fx/usd-sek"),
    refetchInterval: 5 * 60_000,  // var 5:e min
  });
  if (!data || data.rate === null) return null;

  const change = data.change_pct_30d;
  const minRate = data.history.length
    ? Math.min(...data.history.map((p) => p.rate))
    : data.rate;
  const maxRate = data.history.length
    ? Math.max(...data.history.map((p) => p.rate))
    : data.rate;

  return (
    <Card title="USD / SEK — valutakurs">
      <div className="flex items-baseline gap-3">
        <div className="text-3xl serif">
          {data.rate.toFixed(2)} kr / $
        </div>
        {change !== null && change !== undefined && (
          <div
            className={`text-sm font-medium ${
              change > 0 ? "text-rose-700" : change < 0 ? "text-emerald-700" : "text-slate-600"
            }`}
            title="Kronkursens rörelse senaste 30 dagar"
          >
            {change > 0 ? "+" : ""}{change.toFixed(2)} % på 30 d
          </div>
        )}
      </div>
      {data.history.length > 1 && (
        <div className="mt-3">
          <div className="flex items-center justify-between text-xs text-slate-600 mb-1">
            <span>Min: {minRate.toFixed(2)}</span>
            <span>Max: {maxRate.toFixed(2)}</span>
          </div>
          <div className="h-12 relative border-t border-b border-slate-100">
            <svg
              viewBox="0 0 300 50"
              preserveAspectRatio="none"
              className="w-full h-full"
            >
              <polyline
                fill="none"
                stroke="#4f46e5"
                strokeWidth="1.5"
                points={data.history.map((p, i) => {
                  const x = (i / Math.max(1, data.history.length - 1)) * 300;
                  const range = maxRate - minRate || 1;
                  const y = 50 - ((p.rate - minRate) / range) * 45 - 2.5;
                  return `${x},${y}`;
                }).join(" ")}
              />
            </svg>
          </div>
        </div>
      )}
      <div className="mt-3 text-xs text-slate-700 leading-snug border-l-2 border-amber-300 pl-2">
        <strong>Valutarisk:</strong> en starkare krona betyder att USD-aktier
        blir billigare i SEK när du säljer — alltså valutaförlust även om
        aktien gick upp i USD. Och tvärtom: en svagare krona ger valutavinst.
        Senaste {data.history.length} dagar:{" "}
        {change !== null && change > 0
          ? `kronan har försvagats ${change.toFixed(1)} % → bra om du äger USD-aktier`
          : change !== null && change < 0
            ? `kronan har stärkts ${Math.abs(change).toFixed(1)} % → dåligt för USD-aktier (valutaförlust)`
            : "stabil"}
        .
      </div>
    </Card>
  );
}


function OverviewTab({ portfolio }: { portfolio: Portfolio }) {
  const pnl = portfolio.unrealized_pnl;
  const pnlPct = portfolio.total_cost_basis > 0
    ? (pnl / portfolio.total_cost_basis) * 100
    : 0;
  const cashSharePct = portfolio.total_value > 0
    ? (portfolio.cash_balance / portfolio.total_value) * 100
    : 100;
  const holdingCount = portfolio.holdings?.length ?? 0;
  const sectorCount = Object.keys(portfolio.sector_weights).length;

  // Bästa/sämsta innehav (största absoluta P&L %)
  const pnlPctOf = (h: Holding): number =>
    h.cost_basis > 0 ? (h.unrealized_pnl / h.cost_basis) * 100 : 0;
  const sortedByPnl = [...(portfolio.holdings ?? [])].sort(
    (a, b) => pnlPctOf(b) - pnlPctOf(a),
  );
  const top = sortedByPnl[0];
  const worst = sortedByPnl.length > 1 ? sortedByPnl[sortedByPnl.length - 1] : null;

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
        <Card title="Totalt värde">
          <div className="text-2xl serif">{formatSEK(portfolio.total_value)}</div>
          <div className="text-xs text-slate-600 mt-1">
            varav likvid: {formatSEK(portfolio.cash_balance)} ({cashSharePct.toFixed(0)} %)
          </div>
        </Card>
        <Card title="Orealiserad P&L">
          <div className={`text-2xl serif ${pnl >= 0 ? "text-emerald-700" : "text-red-700"}`}>
            {pnl >= 0 ? "+" : ""}{formatSEK(pnl)}
          </div>
          <div className="text-xs text-slate-600 mt-1">
            {pnlPct >= 0 ? "+" : ""}{pnlPct.toFixed(2)} % på {formatSEK(portfolio.total_cost_basis)}
          </div>
        </Card>
        <Card title="Spridning">
          <div className="text-2xl serif">{holdingCount}</div>
          <div className="text-xs text-slate-600 mt-1">
            innehav i {sectorCount} sektor{sectorCount === 1 ? "" : "er"}
          </div>
          {holdingCount > 0 && holdingCount < 5 && (
            <div className="text-[10px] text-amber-700 mt-1">
              ⚠ Sprid på minst 5 för bättre diversifiering
            </div>
          )}
        </Card>
        <Card title="Bästa innehav">
          {top ? (
            <>
              <div className="text-base font-semibold">{top.ticker}</div>
              <div className={`text-sm ${pnlPctOf(top) >= 0 ? "text-emerald-700" : "text-red-700"}`}>
                {pnlPctOf(top) >= 0 ? "+" : ""}{pnlPctOf(top).toFixed(2)} %
              </div>
              {worst && worst.ticker !== top.ticker && (
                <div className="text-[10px] text-slate-500 mt-1">
                  Sämst: {worst.ticker} ({pnlPctOf(worst).toFixed(1)} %)
                </div>
              )}
            </>
          ) : (
            <div className="text-slate-500 text-sm">Inga innehav än</div>
          )}
        </Card>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-[1fr_320px] gap-4">
        <Card title="Sektorvikter">
          {sectorCount === 0 ? (
            <div className="text-slate-500 text-sm">Inga innehav än — gå till Marknad och köp din första aktie.</div>
          ) : (
            <div className="space-y-2">
              {Object.entries(portfolio.sector_weights)
                .sort((a, b) => b[1] - a[1])
                .map(([sector, weight]) => (
                  <div key={sector}>
                    <div className="flex items-center justify-between text-sm">
                      <span>{sector}</span>
                      <span className="font-medium">{weight.toFixed(1)} %</span>
                    </div>
                    <div className="h-1.5 bg-slate-100 rounded mt-0.5">
                      <div
                        className="h-full bg-brand-500 rounded"
                        style={{ width: `${Math.min(weight, 100)}%` }}
                      />
                    </div>
                  </div>
                ))}
            </div>
          )}
        </Card>

        <Card title="Lär dig">
          <div className="space-y-3">
            {LEARN_TIPS.map((t) => (
              <div key={t.title} className="border-l-2 border-amber-300 pl-2">
                <div className="text-xs font-semibold text-slate-800">{t.title}</div>
                <div className="text-[11px] text-slate-600 leading-snug mt-0.5">
                  {t.body}
                </div>
              </div>
            ))}
          </div>
        </Card>
      </div>

      <FxCard />
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

  const [search, setSearch] = useState("");
  const [sectorFilter, setSectorFilter] = useState<string | null>(null);
  const [sortBy, setSortBy] = useState<"name" | "change" | "watchlist">("name");

  // Stats högst upp
  const winnersToday = stocks.filter(
    (s) => (s.change_pct ?? 0) > 0,
  ).length;
  const losersToday = stocks.filter(
    (s) => (s.change_pct ?? 0) < 0,
  ).length;

  const sectors = useMemo(() => {
    const set = new Set<string>();
    for (const s of stocks) set.add(s.sector);
    return Array.from(set).sort();
  }, [stocks]);

  const filtered = useMemo(() => {
    let list = stocks;
    if (sectorFilter) list = list.filter((s) => s.sector === sectorFilter);
    if (search.trim()) {
      const q = search.trim().toLowerCase();
      list = list.filter(
        (s) =>
          s.name.toLowerCase().includes(q) ||
          s.ticker.toLowerCase().includes(q),
      );
    }
    if (sortBy === "change") {
      list = [...list].sort(
        (a, b) => (b.change_pct ?? -9999) - (a.change_pct ?? -9999),
      );
    } else if (sortBy === "watchlist") {
      list = [...list].sort((a, b) => {
        const aw = watchlist.has(a.ticker) ? 0 : 1;
        const bw = watchlist.has(b.ticker) ? 0 : 1;
        if (aw !== bw) return aw - bw;
        return a.name.localeCompare(b.name);
      });
    } else {
      list = [...list].sort((a, b) => a.name.localeCompare(b.name));
    }
    return list;
  }, [stocks, search, sectorFilter, sortBy, watchlist]);

  const grouped = useMemo(() => {
    const out = new Map<string, Stock[]>();
    for (const s of filtered) {
      if (!out.has(s.sector)) out.set(s.sector, []);
      out.get(s.sector)!.push(s);
    }
    return out;
  }, [filtered]);

  return (
    <div className="space-y-4">
      {/* Stats + sök + filter + sortering */}
      <Card>
        <div className="flex items-center gap-4 flex-wrap text-sm">
          <div className="flex items-center gap-3 mr-auto">
            <span className="text-emerald-700">▲ {winnersToday} upp</span>
            <span className="text-red-700">▼ {losersToday} ner</span>
            <span className="text-slate-500 text-xs">
              ({stocks.length} aktier totalt {marketOpen ? "· börsen öppen" : "· börsen stängd"})
            </span>
          </div>
          <input
            type="search"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Sök aktie eller ticker…"
            className="border rounded px-2 py-1 text-sm w-48"
          />
          <select
            value={sortBy}
            onChange={(e) => setSortBy(e.target.value as typeof sortBy)}
            className="border rounded px-2 py-1 text-sm"
          >
            <option value="name">Sortera: A-Ö</option>
            <option value="change">Sortera: störst rörelse</option>
            <option value="watchlist">Sortera: watchlist först</option>
          </select>
        </div>
        <div className="flex gap-1 flex-wrap mt-3">
          <button
            onClick={() => setSectorFilter(null)}
            className={`text-xs px-2 py-1 rounded border ${
              sectorFilter === null
                ? "bg-brand-600 text-white border-brand-600"
                : "bg-white border-slate-200 hover:border-brand-300"
            }`}
          >
            Alla sektorer
          </button>
          {sectors.map((sec) => (
            <button
              key={sec}
              onClick={() =>
                setSectorFilter(sectorFilter === sec ? null : sec)
              }
              className={`text-xs px-2 py-1 rounded border ${
                sectorFilter === sec
                  ? "bg-brand-600 text-white border-brand-600"
                  : "bg-white border-slate-200 hover:border-brand-300"
              }`}
            >
              {sec}
            </button>
          ))}
        </div>
      </Card>

      {filtered.length === 0 && (
        <Card>
          <div className="text-sm text-slate-500 text-center py-6">
            Inga aktier matchar dina filter.
          </div>
        </Card>
      )}

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
                    <div className="font-medium flex items-center gap-2">
                      {s.name}
                      {s.currency && s.currency !== "SEK" && (
                        <span
                          className="text-[10px] px-1.5 py-0.5 rounded bg-amber-100 text-amber-800 border border-amber-200"
                          title="Utländsk aktie — extra valutaväxlingsavgift 0,25 % vid handel"
                        >
                          {s.currency}
                        </span>
                      )}
                    </div>
                    <div className="text-xs text-slate-500">{s.ticker}</div>
                  </div>
                  <div className="text-right pr-3">
                    {s.last !== undefined ? (
                      <>
                        <div className={`font-medium ${marketOpen ? "" : "text-slate-700"}`}>
                          {s.currency === "USD"
                            ? `$${s.last.toFixed(2)}`
                            : formatSEK(s.last)}
                        </div>
                        {s.change_pct !== null && s.change_pct !== undefined && (
                          <div
                            className={`text-xs ${
                              s.change_pct >= 0 ? "text-emerald-700" : "text-red-700"
                            } ${marketOpen ? "" : "opacity-70"}`}
                          >
                            {s.change_pct >= 0 ? "+" : ""}{s.change_pct.toFixed(2)} %
                          </div>
                        )}
                        {!marketOpen && s.ts && (
                          <div className="text-[10px] text-slate-500" title={`Senast handlad ${new Date(s.ts).toLocaleString("sv-SE")}`}>
                            stängd · {new Date(s.ts).toLocaleDateString("sv-SE", { weekday: "short" })} {new Date(s.ts).toLocaleTimeString("sv-SE", { hour: "2-digit", minute: "2-digit" })}
                          </div>
                        )}
                      </>
                    ) : (
                      <div className="text-slate-400 text-sm">— väntar på kurs —</div>
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
                    disabled={s.last === undefined}
                    title={!marketOpen ? "Börsen är stängd — ordern läggs i kö och utförs vid öppning" : undefined}
                    className="bg-brand-600 text-white px-3 py-1.5 rounded text-sm disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    {marketOpen ? "Köp" : "Stängd"}
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
          {portfolio.holdings.map((h) => {
            const isUsd = h.currency === "USD";
            const fmtNative = (v: number): string =>
              isUsd ? `$${v.toFixed(2)}` : formatSEK(v);
            return (
            <tr key={h.ticker} className="border-b last:border-0">
              <td className="py-2">
                <div className="font-medium flex items-center gap-2">
                  {h.ticker}
                  {isUsd && (
                    <span
                      className="text-[10px] px-1.5 py-0.5 rounded bg-amber-100 text-amber-800 border border-amber-200"
                      title="USD-aktie — kurs i SEK påverkas av USD/SEK-växelkursen"
                    >
                      USD
                    </span>
                  )}
                </div>
                <div className="text-xs text-slate-500">{h.sector}</div>
              </td>
              <td>{h.quantity}</td>
              <td>{fmtNative(h.avg_cost)}</td>
              <td>{fmtNative(h.last_price)}</td>
              <td>
                {formatSEK(h.market_value)}
                {isUsd && h.market_value_native !== undefined && (
                  <div className="text-[10px] text-slate-500">
                    {fmtNative(h.market_value_native)}
                  </div>
                )}
              </td>
              <td className={h.unrealized_pnl >= 0 ? "text-emerald-700" : "text-red-700"}>
                {h.unrealized_pnl >= 0 ? "+" : ""}
                {formatSEK(h.unrealized_pnl)}
                {isUsd && h.unrealized_pnl_native !== undefined && (
                  <div className="text-[10px] text-slate-500">
                    i USD: {h.unrealized_pnl_native >= 0 ? "+" : ""}
                    {fmtNative(h.unrealized_pnl_native)}
                  </div>
                )}
              </td>
              <td className="text-right space-x-1">
                <button
                  onClick={() => onTrade(h.ticker, "buy")}
                  className="px-2 py-1 text-xs rounded bg-emerald-600 text-white"
                  title={!marketOpen ? "Marknaden stängd — läggs i kö" : undefined}
                >
                  Köp
                </button>
                <button
                  onClick={() => onTrade(h.ticker, "sell")}
                  className="px-2 py-1 text-xs rounded bg-amber-600 text-white"
                  title={!marketOpen ? "Marknaden stängd — läggs i kö" : undefined}
                >
                  Sälj
                </button>
              </td>
            </tr>
          );
        })}
        </tbody>
      </table>
    </Card>
  );
}

// --- Orders (kö) ---

interface PendingOrder {
  id: number;
  account_id: number;
  ticker: string;
  side: "buy" | "sell";
  quantity: number;
  reference_price: number;
  status: "pending" | "executed" | "cancelled";
  requested_at: string;
  executed_at: string | null;
  executed_price: number | null;
  locked_amount: number;
  cancel_reason: string | null;
  student_rationale: string | null;
}


function OrdersTab() {
  const qc = useQueryClient();
  // Refetch:ar var 30:e sek så executade ordrar dyker upp utan reload.
  // GET-anropet trigger:ar också lazy-execution på backend.
  const ordersQ = useQuery({
    queryKey: ["stocks-orders"],
    queryFn: () => api<{ orders: PendingOrder[]; count: number }>("/stocks/orders"),
    refetchInterval: 30_000,
  });
  const cancelMut = useMutation({
    mutationFn: (o: PendingOrder) =>
      api(
        `/stocks/orders/${o.id}?account_id=${o.account_id}`,
        { method: "DELETE" },
      ),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["stocks-orders"] });
      qc.invalidateQueries({ queryKey: ["stocks-portfolio"] });
    },
  });

  const orders = ordersQ.data?.orders ?? [];
  const pending = orders.filter((o) => o.status === "pending");
  const completed = orders.filter((o) => o.status !== "pending");

  if (orders.length === 0) {
    return (
      <Card>
        <div className="text-sm text-slate-500">
          Du har inga köordrar. När du försöker handla utanför börstid
          kan du lägga ordern i kö här.
        </div>
      </Card>
    );
  }

  const fmt = (o: PendingOrder, value: number) =>
    o.ticker.endsWith(".ST")
      ? formatSEK(value)
      : `$${value.toFixed(2)}`;

  return (
    <div className="space-y-4">
      {pending.length > 0 && (
        <Card title={`Pending ordrar (${pending.length})`}>
          <table className="w-full text-sm">
            <thead className="text-left text-slate-600 border-b">
              <tr>
                <th className="py-2">Ticker</th>
                <th>Sida</th>
                <th>Antal</th>
                <th>Refpris</th>
                <th>Lagd</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {pending.map((o) => (
                <tr key={o.id} className="border-b last:border-0">
                  <td className="py-2 font-medium">{o.ticker}</td>
                  <td>
                    <span
                      className={
                        o.side === "buy"
                          ? "text-emerald-700 font-medium"
                          : "text-amber-700 font-medium"
                      }
                    >
                      {o.side === "buy" ? "Köp" : "Sälj"}
                    </span>
                  </td>
                  <td>{o.quantity}</td>
                  <td>{fmt(o, o.reference_price)}</td>
                  <td className="text-xs text-slate-500">
                    {new Date(o.requested_at).toLocaleString("sv-SE")}
                  </td>
                  <td className="text-right">
                    <button
                      onClick={() => cancelMut.mutate(o)}
                      disabled={cancelMut.isPending}
                      className="px-2 py-1 text-xs rounded border text-slate-700 hover:bg-slate-50"
                    >
                      Avbryt
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="mt-3 text-xs text-slate-600 italic border-l-2 border-amber-300 pl-2">
            Ordern utförs automatiskt så fort marknaden öppnar — priset
            blir det första pollade kursvärdet (kan skilja från refpriset
            ovan). USA-aktier handlas via NYSE/NASDAQ men exekveras under
            Stockholm-börsens öppettider i denna pedagogiska simulator.
          </div>
        </Card>
      )}

      {completed.length > 0 && (
        <Card title={`Tidigare ordrar (${completed.length})`}>
          <table className="w-full text-sm">
            <thead className="text-left text-slate-600 border-b">
              <tr>
                <th className="py-2">Ticker</th>
                <th>Sida</th>
                <th>Antal</th>
                <th>Status</th>
                <th>Pris</th>
                <th>Tid</th>
              </tr>
            </thead>
            <tbody>
              {completed.map((o) => (
                <tr key={o.id} className="border-b last:border-0">
                  <td className="py-2 font-medium">{o.ticker}</td>
                  <td>{o.side === "buy" ? "Köp" : "Sälj"}</td>
                  <td>{o.quantity}</td>
                  <td>
                    {o.status === "executed" ? (
                      <span className="text-emerald-700">Utförd</span>
                    ) : (
                      <span className="text-rose-700">
                        Avbruten
                        {o.cancel_reason && (
                          <span className="text-xs text-slate-500 ml-1">
                            ({o.cancel_reason})
                          </span>
                        )}
                      </span>
                    )}
                  </td>
                  <td>
                    {o.executed_price !== null
                      ? fmt(o, o.executed_price)
                      : "—"}
                  </td>
                  <td className="text-xs text-slate-500">
                    {(o.executed_at ?? o.requested_at) &&
                      new Date(
                        o.executed_at ?? o.requested_at,
                      ).toLocaleString("sv-SE")}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}
    </div>
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
    mutationFn: (body: {
      account_id: number; quantity: number; student_rationale: string;
      side?: string;
    }) => {
      // Marknaden öppen → direkt-handel. Stängd → lägg i kö.
      if (marketOpen) {
        return api(`/stocks/${ticker}/${side}`, {
          method: "POST",
          body: JSON.stringify(body),
        });
      } else {
        return api(`/stocks/${ticker}/queue`, {
          method: "POST",
          body: JSON.stringify({ ...body, side }),
        });
      }
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["stocks-portfolio"] });
      qc.invalidateQueries({ queryKey: ["stocks-ledger"] });
      qc.invalidateQueries({ queryKey: ["stocks-orders"] });
      qc.invalidateQueries({ queryKey: ["balances"] });
      onClose();
    },
    onError: (e: unknown) => {
      setError(e instanceof Error ? e.message : "Kunde inte genomföra ordern");
    },
  });

  const canTrade =
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
          <div className="text-sm text-amber-800 bg-amber-50 border border-amber-200 rounded p-2 space-y-1">
            <div>
              <strong>Marknaden är stängd just nu.</strong> Du kan lägga
              ordern i kö så utförs den automatiskt vid nästa öppning.
            </div>
            <div className="text-xs italic">
              Priset blir det första som finns när marknaden öppnar — kan
              skilja sig från {formatSEK(price)} som visas nu.
            </div>
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
              ? "Skickar…"
              : !marketOpen
              ? (side === "buy" ? "Lägg köp i kö" : "Lägg sälj i kö")
              : side === "buy"
              ? "Bekräfta köp"
              : "Bekräfta sälj"}
          </button>
        </div>
      </div>
    </div>
  );
}
