import type { AgentStreamEvent, AgentStreamStatus } from '@/shared/types/sse';

export interface UseAgentStreamOptions {
  /** 기존 대화에 재부착. 생략 시 티켓 발급이 새 chat_session 을 만든다. */
  chatSessionId?: string;
  /** 마운트 시 자동 연결. 기본 false(사용자가 start() 호출). */
  autoStart?: boolean;
  /** 재연결 최대 시도 횟수. 기본 5. */
  maxRetries?: number;
}

export interface UseAgentStreamResult {
  events: AgentStreamEvent[];
  status: AgentStreamStatus;
  /** 티켓이 바인딩한 대화 세션 ID(재연결·다음 턴에 재사용). */
  chatSessionId: string | null;
  error: string | null;
  start: () => void;
  stop: () => void;
  /** 이벤트 로그를 비우고 idle 로 되돌린다(스트림은 끊지 않음). */
  reset: () => void;
}
