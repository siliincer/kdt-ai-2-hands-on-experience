import { customFetch } from '@/shared/api/customFetch';

import { AGENT_AUTHENTICATE_URL } from '../constants/constants';

/**
 * 추가 인증(비밀번호 재확인) 제출 (UI-HITL 계약 3.8)
 * POST /api/v1/agent/authenticate → { auth_status }
 *
 * 비밀번호 원문은 Backend 까지만 전달되고 Agent 로 넘어가지 않는다(계약 7.2).
 * Backend 가 검증한 결과 상태(verified/failed)만 반환하며, 후속은 SSE 로 흘러온다.
 */
export async function authenticateAgentAction(
  chatSessionId: string,
  authContextId: string,
  password: string,
): Promise<{ auth_status: string }> {
  const token = sessionStorage.getItem('rf_access_token') ?? '';
  return customFetch<{ auth_status: string }>(AGENT_AUTHENTICATE_URL, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({
      chat_session_id: chatSessionId,
      auth_context_id: authContextId,
      password,
    }),
  });
}
