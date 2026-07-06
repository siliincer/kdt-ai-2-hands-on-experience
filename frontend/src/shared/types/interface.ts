interface BarCatData {
  name: string;
  change: number;
  prev: number;
  curr: number;
  added: { name: string; amount: number }[];
  removed: { name: string; amount: number }[];
}

interface TxItem {
  id: number;
  name: string;
  emoji: string;
  date: string;
  month: string;
  day: number;
  amount: number;
  type: 'in' | 'out';
  category: string;
}

interface ChartTooltipPayload {
  name: string;
  value: number;
  payload: {
    name: string;
    change: number;
    prev: number;
    curr: number;
    added: Array<{ name: string; amount: number }>;
    removed: Array<{ name: string; amount: number }>;
  };
}

interface PieClickEntry {
  name: string;
  value: number;
  amount: number;
  color: string;
}

export type { BarCatData, TxItem, PieClickEntry, ChartTooltipPayload };
