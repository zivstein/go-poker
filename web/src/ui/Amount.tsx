import { formatMoney } from "../format/money";

export interface AmountProps {
  value: number;
}

/** Whole dollars with grouping, tabular numerals (W16, W20). */
export function Amount({ value }: AmountProps) {
  return <span>{formatMoney(value)}</span>;
}
