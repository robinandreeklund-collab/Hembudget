export const ACCOUNT_TYPES = [
  { value: "checking", label: "Lönekonto / Privatkonto" },
  { value: "shared", label: "Gemensamt konto (räkningar)" },
  { value: "savings", label: "Sparkonto" },
  { value: "credit", label: "Kreditkort" },
  { value: "isk", label: "ISK / Investeringssparkonto" },
  { value: "pension", label: "Pensionskonto" },
  { value: "other", label: "Övrigt" },
] as const;

export type AccountType = (typeof ACCOUNT_TYPES)[number]["value"];

/** Account types that can be used as a payer of a credit card. */
export const PAYER_TYPES: AccountType[] = ["checking", "shared"];

export function accountTypeLabel(value: string): string {
  return ACCOUNT_TYPES.find((t) => t.value === value)?.label ?? value;
}

export function isPayer(type: string): boolean {
  return PAYER_TYPES.includes(type as AccountType);
}
