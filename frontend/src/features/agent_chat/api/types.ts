// 에이전트 채팅 API 타입 (backend AgentChatRequest/AgentChatData와 동일 계약)

export type AgentChatStatus =
  | 'completed' // 워크플로우 정상 완료
  | 'waiting_input' // 추가 입력 대기 — reply가 질문, thread_id 회송 필요
  | 'blocked' // 가드레일 차단
  | 'no_match' // 매칭되는 워크플로우 없음
  | 'failed'; // 워크플로우 실행 실패

export interface AgentChatRequest {
  message: string;
  // 직전 응답의 status가 waiting_input일 때만 그대로 회송한다.
  thread_id?: string | null;
  user_id?: string;
}

export interface AgentChatResponse {
  reply: string;
  status: AgentChatStatus;
  thread_id: string;
  prompt_for: string | null;
}
