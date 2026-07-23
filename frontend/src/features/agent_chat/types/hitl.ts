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
  /** false면 단일 선택(라디오 동작) — 송금 출금계좌 등 값 하나만 쓰는 워크플로우.
   * 미지정 시 단일 선택으로 취급한다(안전한 기본값). */
  multiple?: boolean;
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

/** 마스킹 계좌/수취인 표시 참조 */
export interface DisplayAccountRef {
  account_id?: string;
  bank_name?: string | null;
  account_alias?: string;
  masked_account_number?: string;
}

export interface DisplayRecipientRef {
  name?: string | null;
  bank_name?: string | null;
  masked_account_number?: string;
}

/** confirm_modal need_approval args(계약 3.7). 목적별 표시 필드 + 승인 대기 id */
export interface ConfirmModalArgs {
  purpose?: string;
  title?: string;
  // 설정(별칭) 목적의 표시 필드.
  account?: DisplayAccountRef;
  alias?: string;
  // 송금 목적의 표시 필드.
  from_account?: DisplayAccountRef;
  recipient?: DisplayRecipientRef;
  to_account?: DisplayAccountRef;
  amount?: number;
  currency?: string;
  allowed_change_targets?: string[];
  actions?: string[];
  /** convertMessage 가 실어 주는 need_approval 대기 id(= confirmation_id) */
  approvalId?: string;
  /** 같은 턴에서 새 확인 카드가 떠서 이 카드가 더 이상 유효하지 않을 때. */
  superseded?: boolean;
}

/** number_input need_input args(계약 3.4) */
export interface NumberInputArgs {
  title?: string;
  currency?: string;
  min?: number;
  actions?: string[];
  inputRequestId?: string;
  ui_contract_id?: string;
}

/** recipient_select 최근 수취인 항목(계약 3.2) */
export interface RecentRecipient {
  to_recipient_id: string;
  name: string;
  bank_name?: string | null;
  masked_account_number: string;
  last_transfer_at?: string;
}

/** recipient_select need_input args(계약 3.2) */
export interface RecipientSelectArgs {
  state?: string;
  title?: string;
  recipient_selection_reason?: string;
  recent_recipients?: RecentRecipient[];
  manual_input?: { enabled?: boolean; fields?: string[] };
  actions?: string[];
  inputRequestId?: string;
  ui_contract_id?: string;
}

/** option_select 항목·args(계약 3.6) */
export interface OptionItem {
  value: string;
  label: string;
}

export interface OptionSelectArgs {
  title?: string;
  options?: OptionItem[];
  actions?: string[];
  inputRequestId?: string;
  ui_contract_id?: string;
}

/** auth_request need 인증 args(계약 3.8). FE 는 비밀번호 재확인으로 처리 */
export interface AuthRequestArgs {
  title?: string;
  available_methods?: string[];
  actions?: string[];
  /** convertMessage 가 실어 주는 인증 대기 id */
  authContextId?: string;
}

/** transfer_result 결과 args(inline payload, 계약 4.5) */
export interface TransferResultArgs {
  transaction_id?: string;
  completed_at?: string;
  from_account?: DisplayAccountRef;
  recipient?: DisplayRecipientRef;
  amount?: number;
  currency?: string;
}

/** period_input need_input args(계약 3.5) */
export interface PeriodInputArgs {
  title?: string;
  presets?: string[];
  manual_range?: boolean;
  actions?: string[];
  inputRequestId?: string;
  ui_contract_id?: string;
}

/** account_list 결과 항목(계약 4.1) */
export interface AccountListItem {
  account_id: string;
  bank_name: string;
  account_alias?: string;
  account_type?: string;
  masked_account_number: string;
  currency?: string;
  is_default?: boolean;
  status?: string;
}

export interface AccountListArgs {
  accounts?: AccountListItem[];
}

/** transaction_list 결과 항목·args(계약 4.3) */
export interface TransactionItem {
  transaction_id: string;
  transaction_title: string;
  amount: number;
  currency?: string;
  occurred_at?: string;
}

export interface TransactionListArgs {
  account_ids?: string[];
  period?: { start_date?: string | null; end_date?: string | null };
  transactions?: TransactionItem[];
  transaction_query_id?: string;
  pagination?: { next_cursor?: string | null };
}

/** amount_summary 결과 args(계약 4.4) */
export interface AmountSummaryArgs {
  account_ids?: string[];
  start_date?: string | null;
  end_date?: string | null;
  summary_type?: string;
  total_amount?: number;
  currency?: string;
}

/** 안내·오류·차단 메시지 args(계약 2.2) */
export interface MessageArgs {
  title?: string;
  message?: string;
  content?: string;
  /** blocked_message 전용 부가 설명(BlockedView.description) — 차단 사유. */
  description?: string;
}

/** setting_result 결과 args(inline payload, 계약 4.6) */
export interface SettingResultArgs {
  purpose?: string;
  outcome?: string;
  account?: { account_id?: string; masked_account_number?: string };
  alias?: string;
  completed_at?: string;
}
