import { useMutation } from "@tanstack/react-query";
import { useState } from "react";
import { api, formatSEK } from "@/api/client";
import { Card } from "@/components/Card";

type Kind = "mortgage" | "savings_goal" | "move";

export default function Scenarios() {
  const [kind, setKind] = useState<Kind>("mortgage");
  const [params, setParams] = useState<Record<string, unknown>>({
    price: 5000000,
    cash_down: 1000000,
    interest_rate: 0.042,
    household_income_yearly: 900000,
    monthly_fee: 4500,
  });
  const [result, setResult] = useState<unknown>(null);

  const calcMut = useMutation({
    mutationFn: () =>
      api("/scenarios/calculate", {
        method: "POST",
        body: JSON.stringify({ name: "Ad hoc", kind, params }),
      }),
    onSuccess: (r) => setResult(r),
  });

  function setParam(key: string, val: unknown) {
    setParams((p) => ({ ...p, [key]: val }));
  }

  function numInput(key: string, label: string, step = "1") {
    return (
      <label className="block text-sm">
        <div className="text-slate-500">{label}</div>
        <input
          type="number"
          step={step}
          value={String(params[key] ?? "")}
          onChange={(e) => setParam(key, Number(e.target.value))}
          className="border rounded px-2 py-1 w-full"
        />
      </label>
    );
  }

  function switchKind(k: Kind) {
    setKind(k);
    setResult(null);
    if (k === "mortgage") {
      setParams({
        price: 5000000, cash_down: 1000000, interest_rate: 0.042,
        household_income_yearly: 900000, monthly_fee: 4500,
      });
    } else if (k === "savings_goal") {
      setParams({
        target_amount: 500000, horizon_months: 120,
        monthly_contribution: 3000, expected_annual_return: 0.07, start_balance: 0,
      });
    } else {
      setParams({ current_monthly_cost: 20000, new_monthly_cost: 15000, moving_cost: 30000, horizon_months: 60 });
    }
  }

  return (
    <div className="p-6 space-y-4 max-w-4xl">
      <h1 className="text-2xl font-semibold">Scenarioanalys</h1>

      <div className="flex gap-2">
        {(["mortgage", "savings_goal", "move"] as Kind[]).map((k) => (
          <button
            key={k}
            onClick={() => switchKind(k)}
            className={`px-3 py-1.5 rounded border ${
              kind === k ? "bg-brand-600 text-white border-brand-600" : "bg-white border-slate-300"
            }`}
          >
            {k === "mortgage" ? "Bolån" : k === "savings_goal" ? "Sparmål" : "Flytt"}
          </button>
        ))}
      </div>

      <Card title="Parametrar">
        <div className="grid grid-cols-3 gap-3">
          {kind === "mortgage" && (
            <>
              {numInput("price", "Pris (kr)")}
              {numInput("cash_down", "Kontantinsats (kr)")}
              {numInput("interest_rate", "Ränta (decimal, t.ex. 0.042)", "0.001")}
              {numInput("household_income_yearly", "Hushållsinkomst/år")}
              {numInput("monthly_fee", "Månadsavgift BRF")}
            </>
          )}
          {kind === "savings_goal" && (
            <>
              {numInput("target_amount", "Målbelopp")}
              {numInput("horizon_months", "Månader")}
              {numInput("monthly_contribution", "Månadssparande")}
              {numInput("expected_annual_return", "Avkastning/år (0.07)", "0.001")}
              {numInput("start_balance", "Startkapital")}
            </>
          )}
          {kind === "move" && (
            <>
              {numInput("current_monthly_cost", "Nuvarande/mån")}
              {numInput("new_monthly_cost", "Nya/mån")}
              {numInput("moving_cost", "Flyttkostnad")}
              {numInput("horizon_months", "Horisont (mån)")}
            </>
          )}
        </div>
        <button
          className="mt-3 bg-brand-600 text-white px-4 py-2 rounded"
          disabled={calcMut.isPending}
          onClick={() => calcMut.mutate()}
        >
          {calcMut.isPending ? "Beräknar…" : "Räkna"}
        </button>
      </Card>

      {result !== null && <ScenarioResult kind={kind} result={result as Record<string, unknown>} />}
    </div>
  );
}

function Row({ k, v }: { k: string; v: string }) {
  return (
    <div className="flex justify-between border-b py-1.5 last:border-0">
      <span className="text-slate-500">{k}</span>
      <span className="font-medium">{v}</span>
    </div>
  );
}

function ScenarioResult({ kind, result }: { kind: Kind; result: Record<string, unknown> }) {
  if (kind === "mortgage") {
    return (
      <Card title="Resultat — Bolån">
        <Row k="Lånebelopp" v={formatSEK(result.loan_amount as number)} />
        <Row k="Belåningsgrad (LTV)" v={`${((result.ltv as number) * 100).toFixed(1)} %`} />
        <Row k="Amortering (år)" v={`${((result.amortization_rate_annual as number) * 100).toFixed(1)} %`} />
        <Row k="Ränta brutto/mån" v={formatSEK(result.monthly_interest_gross as number)} />
        <Row k="Ränta netto/mån (efter avdrag)" v={formatSEK(result.monthly_interest_net as number)} />
        <Row k="Amortering/mån" v={formatSEK(result.monthly_amortization as number)} />
        <Row k="Fastighetsavgift/mån" v={formatSEK(result.monthly_property_tax as number)} />
        <Row k="BRF-avgift/mån" v={formatSEK(result.monthly_fee as number)} />
        <Row k="Summa netto/mån" v={formatSEK(result.monthly_total_net as number)} />
        <div className="mt-3 text-xs text-slate-500">
          Antaganden: {(result.assumptions as string[]).join("; ")}
        </div>
      </Card>
    );
  }
  if (kind === "savings_goal") {
    return (
      <Card title="Resultat — Sparmål">
        <Row k="Projicerat saldo" v={formatSEK(result.projected_balance as number)} />
        <Row k="Målbelopp" v={formatSEK(result.target_amount as number)} />
        <Row k="Saknas" v={formatSEK(result.shortfall as number)} />
        <Row k="Krävs/mån för att nå" v={formatSEK(result.required_monthly_to_hit as number)} />
      </Card>
    );
  }
  return (
    <Card title="Resultat — Flytt">
      <Row k="Månadsskillnad" v={formatSEK(result.monthly_delta as number)} />
      <Row k="Break-even" v={result.breakeven_months != null ? `${result.breakeven_months} mån` : "—"} />
      <Row k="Total över horisont" v={formatSEK(result.total_over_horizon as number)} />
    </Card>
  );
}
