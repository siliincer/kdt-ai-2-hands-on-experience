import type { ToolCallMessagePartComponent } from '@assistant-ui/react';

import { AccountCardListUI } from './AccountCardListUI';
import { AuthRequestUI } from './AuthRequestUI';
import { BalanceResultUI } from './BalanceResultUI';
import { BalanceToolUI } from './BalanceToolUI';
import { BudgetToolUI } from './BudgetToolUI';
import { CardsToolUI } from './CardsToolUI';
import { ConfirmAutoTransferToolUI } from './ConfirmAutoTransferToolUI';
import { ConfirmModalUI } from './ConfirmModalUI';
import { ConfirmTransferToolUI } from './ConfirmTransferToolUI';
import { NumberInputUI } from './NumberInputUI';
import { OptionSelectUI } from './OptionSelectUI';
import { RecipientSelectUI } from './RecipientSelectUI';
import { SettingResultUI } from './SettingResultUI';
import { SpendingToolUI } from './SpendingToolUI';
import { TextInputUI } from './TextInputUI';
import { TransactionsToolUI } from './TransactionsToolUI';
import { TransferResultUI } from './TransferResultUI';

/**
 * assistant-ui tools.by_name 레지스트리.
 * - render_*  : component 시그널(읽기전용 카드). 대개 툴 UI 가 데이터를 fetch 하나,
 *   결과 UI(render_balance_result 등)는 SSE inline payload(args)를 바로 렌더한다(ADR C3).
 * - input_*   : need_input(HITL 입력·선택 폼). useSubmitInput 으로 제출.
 * - confirm_* : need_approval(HITL 편집·확인 폼).
 * 새 카드 추가 시 여기 한 줄만 등록한다.
 */
export const TOOL_UI_REGISTRY: Record<string, ToolCallMessagePartComponent> = {
  render_balance: BalanceToolUI,
  render_spending: SpendingToolUI,
  render_transactions: TransactionsToolUI,
  render_budget: BudgetToolUI,
  render_cards: CardsToolUI,
  render_balance_result: BalanceResultUI,
  render_setting_result: SettingResultUI,
  render_transfer_result: TransferResultUI,
  input_account_card_list: AccountCardListUI,
  input_text_input: TextInputUI,
  input_number_input: NumberInputUI,
  input_recipient_select: RecipientSelectUI,
  input_option_select: OptionSelectUI,
  auth_request: AuthRequestUI,
  confirm_transfer: ConfirmTransferToolUI,
  confirm_autotransfer: ConfirmAutoTransferToolUI,
  confirm_modal: ConfirmModalUI,
};
