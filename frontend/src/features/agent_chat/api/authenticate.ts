import { customFetch } from '@/shared/api/customFetch';

import { AGENT_AUTHENTICATE_URL } from '../constants/constants';

/**
 * 추가 인증(비밀번호 재확인) 제출·취소 (UI-HITL 계약 3.8)
 * POST /api/v1/agent/authenticate → { auth_status }
 *
 * 비밀번호 원문은 Backend 까지만 전달되고 Agent 로 넘어가지 않는다(계약 7.2).
 * Backend 가 검증한 결과 상태(verified/failed/cancelled)만 반환하며, 후속은 SSE 로 흘러온다.
 * cancel=true 면 비밀번호 없이 인증을 취소하고 송금 워크플로우를 중단한다.
 */
export async function authenticateAgentAction(
  chatSessionId: string,
  authContextId: string,
  password: string | null,
  cancel = false,
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
      // 취소 시 비밀번호 필드는 보내지 않는다(백엔드가 cancel 로 분기).
      ...(cancel ? { cancel: true } : { password }),
    }),
  });
}
