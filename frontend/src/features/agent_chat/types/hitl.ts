// UI-HITL 계약(agent-ui-hitl-contract.md)의 입력·결과 UI Payload 타입.
// foldEvent 가 need_input/component 이벤트를 tool-call part 로 접을 때 args 로 실린다.

/** account_card_list 항목(계약 3.3) */
export interface AccountCardItem {
  account_id: string;
  bank_name: string;
  account_alias?: string;
  account_type?: string;
  masked_account_number: string;
  currency?: string;
  is_default?: boolean;
}

/** account_card_list need_input args(payload + 대기 식별자) */
export interface AccountCardListArgs {
  title?: string;
  accounts?: AccountCardItem[];
  actions?: string[];
  /** convertMessage 가 실어 주는 need_input 대기 id */
  inputRequestId?: string;
  ui_contract_id?: string;
}

/** balance_result 항목(계약 4.2) */
export interface BalanceResultItem {
  account_id: string;
  account_alias?: string;
  masked_account_number: string;
  balance: number;
  available_amount: number;
  currency?: string;
}

/** balance_result 결과 args(inline payload, ADR C3) */
export interface BalanceResultArgs {
  accounts?: BalanceResultItem[];
}
