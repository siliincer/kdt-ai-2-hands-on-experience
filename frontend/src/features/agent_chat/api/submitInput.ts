import { customFetch } from '@/shared/api/customFetch';

import { AGENT_INPUT_URL } from '../constants/constants';

/**
 * 일반 입력·선택 대기(need_input) 회신 (UI-HITL 계약 1.5)
 * POST /api/v1/agent/input  → 에이전트 후속 턴 재개(진행은 SSE)
 *
 * `value` 는 UI 계약별 `*_outcome` 필드를 포함한다(예: account_selection_outcome).
 * 승인(approve)과 달리 입력 요청은 `input_request_id` 로 대기 행을 매칭한다.
 */
export async function submitAgentInput(
  chatSessionId: string,
  inputRequestId: string,
  value: Record<string, unknown>,
): Promise<{ input_request_id: string }> {
  const token = sessionStorage.getItem('rf_access_token') ?? '';
  return customFetch<{ input_request_id: string }>(AGENT_INPUT_URL, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({
      chat_session_id: chatSessionId,
      input_request_id: inputRequestId,
      value,
    }),
  });
}
