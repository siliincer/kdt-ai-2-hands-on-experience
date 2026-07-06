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

// waiting_input일 때 내려오는 구조화 UI 힌트 (시트 UI Spec 계약).
// ui가 없으면(reply만 있으면) 텍스트 말풍선으로 렌더링한다 — 폴백 보장.
export type AgentChatUiType =
  | 'account_card_list' // 계좌 카드 목록 선택 (options: 계좌 배열)
  | 'search_select' // 수취인 검색/선택 (options: 수취인 배열)
  | 'number_input' // 금액 입력
  | 'confirm_modal' // 승인 카드 (display: 요약 필드, actions: 버튼 라벨)
  | 'auth_request'; // 본인 인증 요청

export interface AgentChatUi {
  type: AgentChatUiType | (string & {});
  // 카드에 표시할 요약 값들 (예: recipient_name, amount, from_account_name)
  display?: Record<string, unknown>;
  // 선택지 목록 (계좌/수취인 등)
  options?: Array<Record<string, unknown>>;
  // 버튼 라벨 — 선택한 라벨 문자열을 다음 메시지로 그대로 보내면 된다
  actions?: string[];
  [key: string]: unknown;
}

export interface AgentChatResponse {
  reply: string;
  status: AgentChatStatus;
  thread_id: string;
  prompt_for: string | null;
  ui: AgentChatUi | null;
}
