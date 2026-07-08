import type { ToolCallMessagePartComponent } from '@assistant-ui/react';

import { BalanceToolUI } from './BalanceToolUI';
import { ConfirmTransferToolUI } from './ConfirmTransferToolUI';

/**
 * assistant-ui tools.by_name 레지스트리.
 * - render_*  : component 시그널(읽기전용 카드). 툴 UI 가 데이터를 fetch.
 * - confirm_* : need_approval(HITL 편집·확인 폼).
 * 새 카드 추가 시 여기 한 줄만 등록한다.
 */
export const TOOL_UI_REGISTRY: Record<string, ToolCallMessagePartComponent> = {
  render_balance: BalanceToolUI,
  confirm_transfer: ConfirmTransferToolUI,
};
