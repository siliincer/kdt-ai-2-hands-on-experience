import type { AssistantRuntime } from '@assistant-ui/react';

import type { AgentStreamEvent } from '@/shared/types/sse';

// --- 메시지 모델 (우리가 소유하는 external store 타입) ---

export interface ChatTextPart {
  type: 'text';
  text: string;
}
export interface ChatReasoningPart {
  type: 'reasoning';
  text: string;
}
export interface ChatToolPart {
  type: 'tool-call';
  toolCallId: string;
  toolName: string;
  argsText: string;
  args?: Record<string, unknown>;
  /** need_approval 이벤트에서 온 승인 대기 id (confirm 카드 HITL) */
  approvalId?: string;
  /** need_input 이벤트에서 온 일반 입력 대기 id (UI-HITL 계약 1.3) */
  inputRequestId?: string;
  /** authentication_required 이벤트에서 온 추가 인증 대기 id */
  authContextId?: string;
}
export type ChatPart = ChatTextPart | ChatReasoningPart | ChatToolPart;

export type ChatMessageStatus = 'running' | 'complete' | 'error';

export interface ChatUiMessage {
  id: string;
  role: 'user' | 'assistant';
  parts: ChatPart[];
  status: ChatMessageStatus;
}

// --- API ---

export type ApprovalDecision = 'approve' | 'reject';

export interface ChatResponse {
  chat_session_id: string;
}

// --- zustand 스토어 (실시간 SSE chunk 축적) ---

export interface ChatState {
  messages: ChatUiMessage[];
  /** 현재 스트리밍 중인 assistant 메시지 id */
  runningId: string | null;
  setMessages: (messages: readonly ChatUiMessage[]) => void;
  /** 사용자 메시지 + 빈 running assistant 를 추가하고 runningId 를 잡는다 */
  startTurn: (userText: string) => void;
  /** SSE 이벤트들을 running assistant 메시지에 접어 넣는다 */
  foldIntoRunning: (events: AgentStreamEvent[]) => void;
  reset: () => void;
}

// --- 런타임 훅 반환 ---

export interface ChatRuntime {
  runtime: AssistantRuntime;
  /**
   * confirm 카드(HITL)에서 승인/거절 시 호출.
   * `component` 로 어떤 confirm(transfer/autotransfer)인지 BE 에 알려 후속 턴을 분기한다.
   */
  approve: (
    approvalId: string,
    decision: ApprovalDecision,
    args?: Record<string, unknown>,
    component?: string,
  ) => Promise<void>;
  /**
   * 일반 입력·선택 대기(need_input) UI 에서 제출 시 호출(UI-HITL 계약 1.5).
   * `value` 는 UI 계약별 `*_outcome` 필드를 포함한다(예: account_selection_outcome).
   */
  submitInput: (
    inputRequestId: string,
    value: Record<string, unknown>,
  ) => Promise<void>;
}
