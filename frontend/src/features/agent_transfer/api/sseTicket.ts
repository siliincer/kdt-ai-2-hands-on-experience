import { customFetch } from '@/shared/api/customFetch';

import type { SseTicketResponse } from '@/shared/types/sse';

/**
 * SSE 연결용 일회성 티켓 발급
 * GET /api/v1/sse/ticket?chat_session_id={optional}
 *
 * EventSource는 Authorization 헤더를 못 보내므로, Bearer JWT로 먼저 티켓을 받고
 * 그 sse_session_id 로 connect 한다(ADR-001).
 * chatSessionId 를 넘기면 같은 대화 스트림에 재부착, 생략하면 새 대화 세션 생성.
 */
export async function getSseTicket(
  chatSessionId?: string,
): Promise<SseTicketResponse> {
  const token = sessionStorage.getItem('rf_access_token') ?? '';
  const query = chatSessionId
    ? `?chat_session_id=${encodeURIComponent(chatSessionId)}`
    : '';

  return customFetch<SseTicketResponse>(
    `/backendApi/api/v1/sse/ticket${query}`,
    {
      method: 'GET',
      headers: {
        Authorization: `Bearer ${token}`,
      },
    },
  );
}
