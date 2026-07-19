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

/** text_input need_input args(계약 3.1) */
export interface TextInputArgs {
  title?: string;
  description?: string;
  validation?: { required?: boolean; max_length?: number };
  actions?: string[];
  inputRequestId?: string;
  ui_contract_id?: string;
}

/** confirm_modal need_approval args(계약 3.7). 목적별 표시 필드 + 승인 대기 id */
export interface ConfirmModalArgs {
  purpose?: string;
  title?: string;
  // 설정(별칭) 목적의 표시 필드.
  account?: {
    account_id?: string;
    bank_name?: string | null;
    masked_account_number?: string;
  };
  alias?: string;
  allowed_change_targets?: string[];
  actions?: string[];
  /** convertMessage 가 실어 주는 need_approval 대기 id(= confirmation_id) */
  approvalId?: string;
}

/** setting_result 결과 args(inline payload, 계약 4.6) */
export interface SettingResultArgs {
  purpose?: string;
  outcome?: string;
  account?: { account_id?: string; masked_account_number?: string };
  alias?: string;
  completed_at?: string;
}
