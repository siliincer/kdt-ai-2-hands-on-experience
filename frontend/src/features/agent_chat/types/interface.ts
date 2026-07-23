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

// 레거시 송금/자동이체 confirm 은 approve/reject.
// confirm_modal(UI-HITL 계약 3.7)은 approve/change_requested/cancelled.
export type ApprovalDecision =
  'approve' | 'reject' | 'change_requested' | 'cancelled';

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
  /** 전송/재개 실패 시 running assistant 를 에러 메시지로 마감하고 runningId 를 푼다 */
  failRunning: (text: string) => void;
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
  /**
   * 추가 인증(auth_request) UI 에서 비밀번호 재확인 제출 시 호출(계약 3.8).
   * 비밀번호는 Backend 까지만 전달되고 후속은 SSE 로 흘러온다. 반환값은 검증 상태.
   */
  authenticate: (authContextId: string, password: string) => Promise<string>;
  /**
   * recipient_select UI 의 신규 계좌 입력 시 호출(계약 부록 29.2).
   * 은행·계좌번호 원문을 Backend 로 검증해 recipient_candidate_id 를 받는다.
   * 이후 submitInput 은 이 참조만 제출한다(원문은 Agent State 를 통과하지 않는다).
   */
  verifyRecipient: (
    accountNumber: string,
    bankName?: string | null,
  ) => Promise<string>;
}
