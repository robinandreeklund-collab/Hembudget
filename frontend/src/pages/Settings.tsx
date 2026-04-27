import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api, formatSEK } from "@/api/client";
import { Card } from "@/components/Card";
import TibberSettings from "@/components/TibberSettings";
import { useAuth } from "@/hooks/useAuth";
import type { Account, HouseholdUser } from "@/types/models";

interface SubHealth {
  id: number;
  merchant: string;
  amount: number;
  interval_days: number;
  last_seen: string | null;
  days_since: number | null;
  is_stale: boolean;
  annual_cost: number;
}

interface SubHealthResp {
  stale_days: number;
  subscriptions: SubHealth[];
  stale_annual_cost: number;
  total_annual_cost: number;
}

export default function Settings() {
  const { logout, schoolMode } = useAuth();
  const qc = useQueryClient();
  const statusQ = useQuery({
    queryKey: ["status"],
    queryFn: () =>
      api<{ initialized: boolean; db_path: string; lm_studio: string }>("/status"),
  });
  const usersQ = useQuery({
    queryKey: ["users"],
    queryFn: () => api<HouseholdUser[]>("/users"),
  });
  const accountsQ = useQuery({
    queryKey: ["accounts"],
    queryFn: () => api<Account[]>("/accounts"),
  });
  const settingsQ = useQuery({
    queryKey: ["app-settings"],
    queryFn: () => api<Record<string, unknown>>("/settings/"),
  });
  const backupsQ = useQuery({
    queryKey: ["backups"],
    queryFn: () =>
      api<{
        directory: string;
        backups: Array<{
          filename: string;
          label: string;
          size_bytes: number;
          created_at: string;
        }>;
      }>("/backup/list"),
  });

  const [newUserName, setNewUserName] = useState("");
  const createUserMut = useMutation({
    mutationFn: (name: string) =>
      api<HouseholdUser>("/users", {
        method: "POST",
        body: JSON.stringify({ name }),
      }),
    onSuccess: () => {
      setNewUserName("");
      qc.invalidateQueries({ queryKey: ["users"] });
      qc.invalidateQueries({ queryKey: ["accounts"] });
    },
  });
  const deleteUserMut = useMutation({
    mutationFn: (id: number) =>
      api(`/users/${id}`, { method: "DELETE" }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["users"] });
      qc.invalidateQueries({ queryKey: ["accounts"] });
    },
  });

  const setDefaultDebitMut = useMutation({
    mutationFn: (accountId: number | null) =>
      accountId == null
        ? api("/settings/default_debit_account_id", { method: "DELETE" })
        : api("/settings/default_debit_account_id", {
            method: "PUT",
            body: JSON.stringify({ value: accountId }),
          }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["app-settings"] }),
  });

  const [backupLabel, setBackupLabel] = useState("");
  const createBackupMut = useMutation({
    mutationFn: (label: string) =>
      api<{ filename: string }>("/backup/create", {
        method: "POST",
        body: JSON.stringify({ label: label || null }),
      }),
    onSuccess: () => {
      setBackupLabel("");
      qc.invalidateQueries({ queryKey: ["backups"] });
    },
  });
  const restoreBackupMut = useMutation({
    mutationFn: (filename: string) =>
      api<{ restored_from: string; pre_restore_backup: string }>(
        "/backup/restore",
        {
          method: "POST",
          body: JSON.stringify({ filename }),
        },
      ),
    onSuccess: () => {
      // Efter restore är hela databasen annorlunda — tvinga reload
      alert(
        "Databasen återställd. Sidan laddas om så alla vyer läses från " +
          "den återställda datan.",
      );
      window.location.reload();
    },
  });
  const deleteBackupMut = useMutation({
    mutationFn: (filename: string) =>
      api(`/backup/${encodeURIComponent(filename)}`, { method: "DELETE" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["backups"] }),
  });

  const currentDefaultDebit =
    (settingsQ.data?.default_debit_account_id as number | undefined) ?? null;
  const lmQ = useQuery({
    queryKey: ["lm-status"],
    queryFn: () => api<{ alive: boolean; base_url: string; model: string }>("/chat/lm-studio-status"),
  });

  const detectSubsMut = useMutation({
    mutationFn: () =>
      api<{ count: number; subscriptions: unknown[] }>("/budget/subscriptions/detect", {
        method: "POST",
      }),
  });
  const deleteSubMut = useMutation({
    mutationFn: (id: number) =>
      api(`/budget/subscriptions/${id}`, { method: "DELETE" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["subs-health"] }),
  });

  const subHealthQ = useQuery({
    queryKey: ["subs-health"],
    queryFn: () =>
      api<SubHealthResp>("/budget/subscriptions/health?stale_days=60"),
  });
  // Hälsokollstabellen kan vara lång — börja minimerad. Summan visas
  // alltid på kort-headern så man ser totalen utan att fälla ut.
  const [subsOpen, setSubsOpen] = useState(false);

  const scanTransfersMut = useMutation({
    mutationFn: () =>
      api<{ pairs: number; ambiguous: number; details: [number, number][] }>(
        "/admin/scan-transfers",
        { method: "POST" },
      ),
  });

  const recategorizeMut = useMutation({
    mutationFn: () =>
      api<{
        seed_rules_removed: number;
        txs_processed: number;
        categorized: number;
        still_uncategorized: number;
      }>("/admin/recategorize", { method: "POST" }),
  });

  return (
    <div className="p-3 md:p-6 space-y-4 md:space-y-4 max-w-2xl">
      <h1 className="serif text-3xl leading-tight">Inställningar</h1>

      {/* System-kortet är driftsinformation om DB-sökväg och LM Studio —
          inte relevant i school-läget där elever inte ska se infrastrukturen. */}
      {!schoolMode && (
        <Card title="System">
          <div className="text-sm space-y-1">
            <div>DB: <code className="bg-slate-100 px-1 rounded">{statusQ.data?.db_path}</code></div>
            <div>LM Studio: <code className="bg-slate-100 px-1 rounded">{statusQ.data?.lm_studio}</code></div>
            <div>
              Status:{" "}
              <span className={lmQ.data?.alive ? "text-emerald-600" : "text-rose-600"}>
                {lmQ.data?.alive ? "ansluten" : "ej ansluten"}
              </span>
            </div>
            <div>Modell: {lmQ.data?.model}</div>
          </div>
        </Card>
      )}

      <Card title="Hushållsmedlemmar">
        <div className="text-sm text-slate-700 mb-2">
          Lägg till familjemedlemmar så kan du tagga varje konto med ägare.
          Dashboard och familje-rapporten använder detta för att fördela
          inkomst/utgift per person.
        </div>
        <div className="space-y-1 mb-3">
          {(usersQ.data ?? []).length === 0 ? (
            <div className="text-xs text-slate-700">Inga medlemmar registrerade än.</div>
          ) : (
            (usersQ.data ?? []).map((u) => (
              <div key={u.id} className="flex items-center justify-between text-sm border-b py-1.5">
                <span>{u.name}</span>
                <button
                  onClick={() => {
                    if (confirm(`Ta bort '${u.name}'? Kontona behåller sin data men visas som Gemensamt.`)) {
                      deleteUserMut.mutate(u.id);
                    }
                  }}
                  className="text-xs text-rose-600 hover:text-rose-800"
                >
                  Ta bort
                </button>
              </div>
            ))
          )}
        </div>
        <div className="flex gap-2">
          <input
            value={newUserName}
            onChange={(e) => setNewUserName(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && newUserName.trim()) {
                createUserMut.mutate(newUserName.trim());
              }
            }}
            placeholder="Förnamn"
            className="border rounded px-2 py-1.5 text-sm flex-1"
          />
          <button
            onClick={() => newUserName.trim() && createUserMut.mutate(newUserName.trim())}
            disabled={!newUserName.trim() || createUserMut.isPending}
            className="bg-brand-600 text-white px-3 py-1.5 rounded text-sm disabled:opacity-50"
          >
            Lägg till
          </button>
        </div>
      </Card>

      <Card title="Fakturor — default-konto">
        <div className="text-sm text-slate-700 mb-2">
          Nya kommande fakturor utan explicit debit-konto får automatiskt
          det konto du väljer här. Perfekt om alla hushållsfakturor dras
          från samma gemensamma konto.
        </div>
        <select
          value={currentDefaultDebit ?? ""}
          onChange={(e) =>
            setDefaultDebitMut.mutate(
              e.target.value ? Number(e.target.value) : null,
            )
          }
          className="border rounded px-2 py-1.5 w-full text-sm bg-white"
        >
          <option value="">Inget default — välj manuellt per faktura</option>
          {(accountsQ.data ?? []).map((a) => (
            <option key={a.id} value={a.id}>
              {a.name} ({a.bank})
            </option>
          ))}
        </select>
        {setDefaultDebitMut.isPending && (
          <div className="text-xs text-slate-600 mt-1">Sparar…</div>
        )}
      </Card>

      <Card title="Backup & återställning">
        <div className="text-sm text-slate-700 mb-3">
          Ta en snapshot av databasen så du kan rulla tillbaka om något
          blir fel. Typiskt flöde: spara "januari" när januari är klar —
          om februari-importen blir fel kan du återställa och göra om.
        </div>
        <div className="flex gap-2 mb-3">
          <input
            value={backupLabel}
            onChange={(e) => setBackupLabel(e.target.value)}
            placeholder="Namn (t.ex. 'januari-2026')"
            className="border rounded px-2 py-1.5 text-sm flex-1"
          />
          <button
            onClick={() => createBackupMut.mutate(backupLabel)}
            disabled={createBackupMut.isPending}
            className="bg-brand-600 text-white px-3 py-1.5 rounded text-sm disabled:opacity-50"
          >
            {createBackupMut.isPending ? "Sparar…" : "Skapa backup"}
          </button>
        </div>
        {(backupsQ.data?.backups ?? []).length === 0 ? (
          <div className="text-xs text-slate-700">
            Inga backuper ännu. Filerna sparas under{" "}
            <code className="bg-slate-100 px-1 rounded">
              {backupsQ.data?.directory ?? "data_dir/backups"}
            </code>
            .
          </div>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs uppercase text-slate-700 border-b">
                <th className="py-1.5 pr-3">Namn</th>
                <th className="py-1.5 pr-3">Skapad</th>
                <th className="py-1.5 pr-3 text-right">Storlek</th>
                <th className="py-1.5 pr-3 text-right">Åtgärd</th>
              </tr>
            </thead>
            <tbody>
              {(backupsQ.data?.backups ?? []).map((b) => (
                <tr key={b.filename} className="border-b last:border-0">
                  <td className="py-1.5 pr-3 font-medium">{b.label}</td>
                  <td className="py-1.5 pr-3 text-xs text-slate-700">
                    {b.created_at.replace("T", " ").slice(0, 19)}
                  </td>
                  <td className="py-1.5 pr-3 text-right text-xs text-slate-700">
                    {(b.size_bytes / 1024).toFixed(0)} kB
                  </td>
                  <td className="py-1.5 pr-3 text-right">
                    <button
                      onClick={() => {
                        if (
                          confirm(
                            `Återställ databasen från '${b.label}'?\n\nAll data ` +
                              "som tillkommit efter denna backup GÅR FÖRLORADE. " +
                              "En pre-restore-kopia sparas automatiskt så du kan " +
                              "ångra.",
                          )
                        ) {
                          restoreBackupMut.mutate(b.filename);
                        }
                      }}
                      disabled={restoreBackupMut.isPending}
                      className="text-xs nav-link mr-3 disabled:opacity-50"
                    >
                      Återställ
                    </button>
                    <button
                      onClick={() => {
                        if (confirm(`Radera backup '${b.label}'?`)) {
                          deleteBackupMut.mutate(b.filename);
                        }
                      }}
                      className="text-xs text-rose-600 hover:underline"
                    >
                      Radera
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>

      <Card
        title="Prenumerationer — hälsokoll"
        action={
          <div className="flex items-center gap-3">
            {subHealthQ.data && (
              <span className="text-xs text-slate-700">
                Totalt {formatSEK(subHealthQ.data.total_annual_cost)}/år
                {subHealthQ.data.stale_annual_cost > 0 && (
                  <span className="ml-2 text-amber-700">
                    · {formatSEK(subHealthQ.data.stale_annual_cost)}/år att granska
                  </span>
                )}
              </span>
            )}
            <button
              onClick={() => setSubsOpen((v) => !v)}
              className="text-xs text-slate-700 hover:text-slate-900 border rounded px-2 py-0.5"
            >
              {subsOpen ? "Dölj" : "Visa"}
            </button>
          </div>
        }
      >
        {!subsOpen ? (
          <div className="text-sm text-slate-700">
            {subHealthQ.data?.subscriptions?.length
              ? `${subHealthQ.data.subscriptions.length} aktiva prenumerationer. Klicka "Visa" för detaljer.`
              : "Inga aktiva prenumerationer registrerade."}
          </div>
        ) : subHealthQ.isLoading ? (
          <div className="text-sm text-slate-700">Analyserar…</div>
        ) : !subHealthQ.data || subHealthQ.data.subscriptions.length === 0 ? (
          <div className="text-sm text-slate-700">
            Inga aktiva prenumerationer registrerade. Klicka "Hitta prenumerationer nu" nedan.
          </div>
        ) : (
          <>
            {subHealthQ.data.stale_annual_cost > 0 && (
              <div className="bg-amber-50 border border-amber-200 text-amber-800 rounded px-3 py-2 text-sm mb-3">
                Du har {formatSEK(subHealthQ.data.stale_annual_cost)}/år i
                prenumerationer som inte dragits senaste{" "}
                {subHealthQ.data.stale_days} dagarna — överväg att säga upp.
              </div>
            )}
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs uppercase text-slate-700 border-b">
                  <th className="py-1.5 pr-3">Tjänst</th>
                  <th className="py-1.5 pr-3 text-right">Pris</th>
                  <th className="py-1.5 pr-3 text-right">Senast dragen</th>
                  <th className="py-1.5 pr-3 text-right">Per år</th>
                  <th className="py-1.5 pr-3 text-right w-32">Åtgärd</th>
                </tr>
              </thead>
              <tbody>
                {subHealthQ.data.subscriptions.map((s) => (
                  <tr
                    key={s.id}
                    className={`border-b last:border-0 ${
                      s.is_stale ? "bg-amber-50" : ""
                    }`}
                  >
                    <td className="py-1.5 pr-3">
                      <div className="font-medium">{s.merchant}</div>
                      <div className="text-xs text-slate-700">
                        var {s.interval_days}:e dag
                      </div>
                    </td>
                    <td className="py-1.5 pr-3 text-right">
                      {formatSEK(s.amount)}
                    </td>
                    <td
                      className={`py-1.5 pr-3 text-right text-xs ${
                        s.is_stale ? "text-amber-700 font-semibold" : "text-slate-700"
                      }`}
                    >
                      {s.last_seen
                        ? `${s.last_seen} (${s.days_since}d sedan)`
                        : "— aldrig sedd"}
                    </td>
                    <td className="py-1.5 pr-3 text-right font-semibold">
                      {formatSEK(s.annual_cost)}
                    </td>
                    <td className="py-1.5 pr-3 text-right">
                      <button
                        onClick={() => {
                          if (confirm(
                            `Ta bort "${s.merchant}" som prenumeration?\n\n` +
                            "Detta raderar prenumerations-registreringen och " +
                            "eventuella auto-genererade kommande-rader. " +
                            "Bakomliggande bankrader rörs inte.",
                          )) {
                            deleteSubMut.mutate(s.id);
                          }
                        }}
                        disabled={deleteSubMut.isPending}
                        className="text-xs text-rose-600 hover:text-rose-800 disabled:opacity-50"
                        title="Ta bort som prenumeration"
                      >
                        Ta bort
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </>
        )}
      </Card>

      <Card title="Automatik">
        <div className="space-y-3">
          <div>
            <button
              className="bg-brand-600 text-white px-4 py-2 rounded"
              onClick={() => detectSubsMut.mutate()}
              disabled={detectSubsMut.isPending}
            >
              {detectSubsMut.isPending ? "Analyserar…" : "Hitta prenumerationer nu"}
            </button>
            {detectSubsMut.data && (
              <pre className="mt-2 bg-slate-900 text-slate-100 text-xs p-3 rounded overflow-x-auto">
                {JSON.stringify(detectSubsMut.data, null, 2)}
              </pre>
            )}
          </div>

          <div>
            <button
              className="bg-brand-600 text-white px-4 py-2 rounded"
              onClick={() => scanTransfersMut.mutate()}
              disabled={scanTransfersMut.isPending}
            >
              {scanTransfersMut.isPending ? "Skannar…" : "Hitta överföringar mellan konton"}
            </button>
            <div className="text-xs text-slate-700 mt-1">
              Matchar transaktioner med motsatt belopp mellan dina konton (±0,5 %, ±3 dagar).
              Körs automatiskt efter varje import, men kan köras om manuellt.
            </div>
            {scanTransfersMut.data && (
              <div className="mt-2 text-sm">
                <strong>{scanTransfersMut.data.pairs}</strong> nya par hittade.
                {scanTransfersMut.data.ambiguous > 0 && (
                  <span className="text-amber-700 ml-2">
                    {scanTransfersMut.data.ambiguous} tvetydiga (behöver manuell granskning).
                  </span>
                )}
              </div>
            )}
          </div>

          <div>
            <button
              className="bg-slate-800 text-white px-4 py-2 rounded"
              onClick={() => recategorizeMut.mutate()}
              disabled={recategorizeMut.isPending}
            >
              {recategorizeMut.isPending ? "Kör om…" : "Omseeda regler + omkategorisera"}
            </button>
            <div className="text-xs text-slate-700 mt-1">
              Tar bort inbyggda seed-regler, lägger till de senaste från koden och
              kör om kategoriseringen på alla transaktioner som du inte själv har
              rättat. Dina egna rättningar behålls.
            </div>
            {recategorizeMut.data && (
              <div className="mt-2 text-sm">
                <strong>{recategorizeMut.data.categorized}</strong> av{" "}
                {recategorizeMut.data.txs_processed} transaktioner kategoriserade.
                {" "}
                ({recategorizeMut.data.seed_rules_removed} gamla seed-regler ersatta,
                {" "}{recategorizeMut.data.still_uncategorized} kvar okategoriserade — de
                hamnar hos LLM:en vid nästa import.)
              </div>
            )}
          </div>
        </div>
      </Card>

      {/* Tibber-OAuth är desktop-funktion (kopplar elev-konto i hemmet
          mot Tibber-API). Ej relevant i school-läget. */}
      {!schoolMode && <TibberSettings />}

      <Card title="Session">
        <button className="bg-rose-600 text-white px-4 py-2 rounded" onClick={logout}>
          Logga ut
        </button>
      </Card>
    </div>
  );
}
