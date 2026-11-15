/** Whole dollars with grouping, never cents or an abbreviation (W20). */
export function formatMoney(amount: number): string {
  return `$${amount.toLocaleString("en-US")}`;
}
