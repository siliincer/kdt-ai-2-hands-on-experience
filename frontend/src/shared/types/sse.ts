// 백엔드 backend/schemas/sse.py 와 1:1 대응하는 SSE/Agent 스트림 타입

export type AgentStreamEventType =
  | 'status'
  | 'token'
  | 'tool_call'
  | 'component'
  | 'need_approval'
  | 'done'
  | 'error';

export interface AgentStreamEvent {
  event_type: AgentStreamEventType;
  content: string;
  approval_id?: string | null;
  metadata?: Record<string, unknown> | null;
}

// GET /api/v1/sse/ticket 응답
export interface SseTicketResponse {
  sse_session_id: string;
  chat_session_id: string;
  expires_in: number;
}

// useAgentStream 훅의 연결 상태
export type AgentStreamStatus =
  | 'idle' // 아직 시작 안 함
  | 'connecting' // 티켓 발급 + EventSource 여는 중
  | 'streaming' // 이벤트 수신 중
  | 'done' // [DONE] 수신, 정상 종료
  | 'error'; // 재시도 소진 등 실패
