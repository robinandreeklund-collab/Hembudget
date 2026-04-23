/**
 * Bildunderlag — alla PDF/bild-bilagor i systemet, grupperat per månad.
 *
 * Två typer:
 * 1. Fakturor (kind=bill) — PDF/bild som vision-parseats eller bifogats
 *    till en transaktion via /transactions attach-invoice.
 * 2. Lönespecs (kind=income) — PDF:er importerade via /salaries PDF-
 *    uppladdning (source=salary_pdf).
 *
 * Per bilaga visar vi: månad, kind, namn, belopp, datum, källa och en
 * "📎 Öppna"-knapp. Actions: öppna i ny flik, ta bort. Visar även om
 * bilagan är kopplad till en matchad Transaction.
 *
 * Datakälla: /upcoming/?only_future=false filtrerat på source_image_path.
 */
import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ChevronDown, ChevronRight, FileText, Image as ImageIcon,
  Paperclip, Trash2,
} from "lucide-react";
import { api, formatSEK, getApiBase, getToken } from "@/api/client";
import { Card } from "@/components/Card";

interface UpcomingRef {
  id: number;
  kind: "bill" | "income";
  name: string;
  amount: number;
  expected_date: string;
  owner: string | null;
  source: string;
  source_image_path: string | null;
  matched_transaction_id: number | null;
  payment_status?: "unpaid" | "partial" | "paid" | "overpaid";
}

const SV_MONTHS = [
  "januari", "februari", "mars", "april", "maj", "juni",
  "juli", "augusti", "september", "oktober", "november", "december",
];

function fmtMonth(ym: string): string {
  const [y, m] = ym.split("-").map(Number);
  if (!y || !m) return ym;
  return `${SV_MONTHS[m - 1]} ${y}`;
}

function fileExt(path: string | null): string {
  if (!path) return "";
  const m = path.toLowerCase().match(/\.([a-z0-9]+)$/);
  return m ? m[1] : "";
}

export default function Attachments() {
  const qc = useQueryClient();
  const [filterKind, setFilterKind] = useState<"all" | "bill" | "income">("all");

  const listQ = useQuery({
    queryKey: ["attachments"],
    queryFn: () => api<UpcomingRef[]>("/upcoming/?only_future=false"),
  });

  const deleteMut = useMutation({
    mutationFn: (id: number) => api(`/upcoming/${id}`, { method: "DELETE" }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["attachments"] });
      qc.invalidateQueries({ queryKey: ["upcoming"] });
      qc.invalidateQueries({ queryKey: ["ytd-income"] });
    },
  });

  // Bara rader med bifogad fil
  const withFiles = (listQ.data ?? []).filter(
    (u) => u.source_image_path != null,
  );
  const filtered = withFiles.filter((u) =>
    filterKind === "all" ? true : u.kind === filterKind,
  );

  const byMonth = useMemo(() => {
    const map = new Map<string, UpcomingRef[]>();
    for (const u of filtered) {
      const ym = u.expected_date.slice(0, 7);
      if (!map.has(ym)) map.set(ym, []);
      map.get(ym)!.push(u);
    }
    return [...map.entries()]
      .sort(([a], [b]) => (a < b ? 1 : -1))
      .map(([ym, items]) => ({
        ym,
        items: items.sort((a, b) =>
          a.expected_date < b.expected_date ? 1 : -1,
        ),
      }));
  }, [filtered]);

  const totalCount = withFiles.length;
  const billsCount = withFiles.filter((u) => u.kind === "bill").length;
  const incomesCount = withFiles.filter((u) => u.kind === "income").length;

  function openAttachment(u: UpcomingRef) {
    const token = getToken();
    fetch(`${getApiBase()}/upcoming/${u.id}/source`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    })
      .then((r) => {
        if (!r.ok) throw new Error("Filen saknas eller kan ej öppnas");
        return r.blob();
      })
      .then((b) => window.open(URL.createObjectURL(b), "_blank"))
      .catch((e) => alert(String(e.message ?? e)));
  }

  return (
    <div className="p-3 md:p-6 space-y-4 md:space-y-5 max-w-6xl">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold flex items-center gap-2">
          <Paperclip className="w-6 h-6" />
          Bildunderlag
        </h1>
      </div>

      <div className="grid grid-cols-3 gap-3">
        <Stat label="Totalt" value={String(totalCount)} />
        <Stat
          label="Fakturor"
          value={String(billsCount)}
          tone="amber"
          active={filterKind === "bill"}
          onClick={() =>
            setFilterKind(filterKind === "bill" ? "all" : "bill")
          }
        />
        <Stat
          label="Lönespecs"
          value={String(incomesCount)}
          tone="emerald"
          active={filterKind === "income"}
          onClick={() =>
            setFilterKind(filterKind === "income" ? "all" : "income")
          }
        />
      </div>

      {listQ.isLoading ? (
        <div className="text-sm text-slate-700">Laddar…</div>
      ) : byMonth.length === 0 ? (
        <Card>
          <div className="text-sm text-slate-700">
            Inga bildunderlag ännu. Ladda upp fakturor via{" "}
            <a href="/upcoming" className="text-brand-600 underline">
              /upcoming
            </a>{" "}
            eller lönespecs via{" "}
            <a href="/salaries" className="text-brand-600 underline">
              /salaries
            </a>
            .
          </div>
        </Card>
      ) : (
        <div className="space-y-2">
          {byMonth.map((m, idx) => (
            <MonthSection
              key={m.ym}
              ym={m.ym}
              items={m.items}
              startExpanded={idx === 0}
              onOpen={openAttachment}
              onDelete={(id, name) => {
                if (
                  confirm(
                    `Ta bort "${name}" permanent?\n\nDetta raderar upcoming-raden OCH den bifogade filen från disken. Matchade transaktioner påverkas inte.`,
                  )
                ) {
                  deleteMut.mutate(id);
                }
              }}
            />
          ))}
        </div>
      )}
    </div>
  );
}

function Stat({
  label,
  value,
  tone,
  active,
  onClick,
}: {
  label: string;
  value: string;
  tone?: "amber" | "emerald";
  active?: boolean;
  onClick?: () => void;
}) {
  const toneCls =
    tone === "amber"
      ? "text-amber-700 border-amber-200"
      : tone === "emerald"
      ? "text-emerald-700 border-emerald-200"
      : "text-slate-700 border-slate-200";
  return (
    <button
      onClick={onClick}
      disabled={!onClick}
      className={
        "border rounded-lg p-3 bg-white text-left transition " +
        toneCls +
        (onClick ? " hover:shadow-sm cursor-pointer" : "") +
        (active ? " ring-2 ring-offset-1 ring-brand-400" : "")
      }
    >
      <div className="text-xs uppercase tracking-wide">{label}</div>
      <div className="text-2xl font-semibold mt-0.5">{value}</div>
      {onClick && (
        <div className="text-xs mt-1 opacity-70">
          {active ? "filter aktivt" : "klicka för att filtrera"}
        </div>
      )}
    </button>
  );
}

function MonthSection({
  ym,
  items,
  startExpanded,
  onOpen,
  onDelete,
}: {
  ym: string;
  items: UpcomingRef[];
  startExpanded: boolean;
  onOpen: (u: UpcomingRef) => void;
  onDelete: (id: number, name: string) => void;
}) {
  const [open, setOpen] = useState(startExpanded);
  const totalAmount = items.reduce((s, i) => s + Math.abs(i.amount), 0);

  return (
    <div className="border rounded-lg overflow-hidden bg-white">
      <button
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center gap-3 px-3 py-2 hover:bg-slate-50 text-left"
      >
        {open ? (
          <ChevronDown className="w-4 h-4 text-slate-600 shrink-0" />
        ) : (
          <ChevronRight className="w-4 h-4 text-slate-600 shrink-0" />
        )}
        <div className="flex-1">
          <div className="font-medium capitalize">{fmtMonth(ym)}</div>
          <div className="text-xs text-slate-700">
            {items.length} underlag · {formatSEK(totalAmount)}
          </div>
        </div>
      </button>
      {open && (
        <div className="border-t divide-y">
          {items.map((u) => (
            <AttachmentRow
              key={u.id}
              item={u}
              onOpen={() => onOpen(u)}
              onDelete={() => onDelete(u.id, u.name)}
            />
          ))}
        </div>
      )}
    </div>
  );
}

function AttachmentRow({
  item,
  onOpen,
  onDelete,
}: {
  item: UpcomingRef;
  onOpen: () => void;
  onDelete: () => void;
}) {
  const ext = fileExt(item.source_image_path);
  const Icon = ext === "pdf" ? FileText : ImageIcon;
  const isPaid = item.payment_status === "paid";
  const isMatched = item.matched_transaction_id != null;

  return (
    <div className="flex items-center gap-3 px-3 py-2 text-sm hover:bg-slate-50">
      <Icon className="w-4 h-4 text-slate-600 shrink-0" />
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="font-medium truncate">{item.name}</span>
          {item.kind === "bill" ? (
            <span className="text-xs bg-amber-100 text-amber-800 px-1.5 py-0.5 rounded">
              Faktura
            </span>
          ) : (
            <span className="text-xs bg-emerald-100 text-emerald-800 px-1.5 py-0.5 rounded">
              Lön
            </span>
          )}
          {isPaid && (
            <span className="text-xs text-emerald-600">✓ matchad</span>
          )}
          {!isPaid && isMatched && (
            <span className="text-xs text-slate-600">
              #{item.matched_transaction_id}
            </span>
          )}
        </div>
        <div className="text-xs text-slate-700">
          {item.expected_date}
          {item.owner && ` · ${item.owner}`}
          {" · "}
          {item.source}
          {ext && ` · .${ext}`}
        </div>
      </div>
      <div
        className={
          "font-medium shrink-0 " +
          (item.kind === "income"
            ? "text-emerald-700"
            : item.amount < 0
            ? "text-rose-600"
            : "text-slate-800")
        }
      >
        {item.kind === "income" ? "+" : ""}
        {formatSEK(item.amount)}
      </div>
      <button
        onClick={onOpen}
        className="text-brand-600 hover:text-brand-800 text-xs underline shrink-0"
        title="Öppna i ny flik"
      >
        Öppna
      </button>
      <button
        onClick={onDelete}
        className="text-slate-600 hover:text-rose-600 shrink-0"
        title="Ta bort upcoming-rad + fil"
      >
        <Trash2 className="w-4 h-4" />
      </button>
    </div>
  );
}
