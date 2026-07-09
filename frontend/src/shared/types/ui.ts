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
