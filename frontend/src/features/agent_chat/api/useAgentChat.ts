import { useCustomTanstackMutation } from '../../../shared/hooks/useCustomTanstackMutation';
import type { AgentChatRequest, AgentChatResponse } from './types';

/**
 * 에이전트 채팅 mutation 훅.
 *
 * 경로: frontend → (vite dev proxy /backendApi) → backend /api/v1/agent/chat → agent /chat
 * customFetch가 CommonResponse 봉투를 풀어 data(AgentChatResponse)만 반환한다.
 *
 * 사용 예:
 *   const { mutate, isPending } = useAgentChat();
 *   mutate({ message: '잔액 얼마야?' });
 *   // 응답 status가 'waiting_input'이면 다음 요청에 thread_id를 그대로 회송한다:
 *   mutate({ message: '1번', thread_id: prev.thread_id });
 */
export function useAgentChat() {
  return useCustomTanstackMutation<AgentChatResponse, AgentChatRequest>({
    url: '/backendApi/api/v1/agent/chat',
  });
}
