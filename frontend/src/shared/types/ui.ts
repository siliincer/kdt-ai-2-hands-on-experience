// 백엔드 backend/schemas/ui.py (UI Data API, BFF) 와 1:1 대응.
// component SSE 시그널(ADR-002) 이후 FE 가 이 형태를 fetch 한다.

export interface AccountSummary {
  id: number;
  bank: string;
  alias: string;
  tail: string;
  balance: number;
  color: string;
}

export interface BalanceData {
  total: number;
  accounts: AccountSummary[];
}

// --- spending (소비 분석, GET /ui/spending) ---

export interface PieDatum {
  name: string;
  value: number;
  color: string;
  amount: number;
}

export interface ChangeItem {
  name: string;
  amount: number;
}

export interface BarCatDatum {
  name: string;
  change: number;
  prev: number;
  curr: number;
  added: ChangeItem[];
  removed: ChangeItem[];
}

export interface MonthlySpendDatum {
  month: string;
  amount: number;
}

export interface CatTxDatum {
  name: string;
  date: string;
  amount: number;
}

export interface SpendingData {
  pie: PieDatum[];
  bar: BarCatDatum[];
  monthly: MonthlySpendDatum[];
  catTx: Record<string, CatTxDatum[]>;
}

// --- transactions (거래 내역, GET /ui/transactions) ---

export interface TransactionItem {
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

export interface TransactionsData {
  months: string[];
  items: TransactionItem[];
}

// --- budget (예산 현황, GET /ui/budget) ---

export interface BudgetItem {
  cat: string;
  used: number;
  total: number;
}

export interface SubscriptionItem {
  name: string;
  amount: number;
  active: boolean;
}

export interface BudgetData {
  budgetItems: BudgetItem[];
  subItems: SubscriptionItem[];
}

// --- cards (카드 관리, GET /ui/cards) ---

export interface CreditCard {
  name: string;
  num: string;
  exp: string;
  bg: string;
}

export interface CardsData {
  cards: CreditCard[];
}
