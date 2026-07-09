import { customFetch } from '@/shared/api/customFetch';

import { CHAT_URL } from '../constants/constants';

import type { ChatResponse } from '../types/interface';

/**
 * 사용자 메시지 전송
 * POST /api/v1/chat  → { chat_session_id }
 * 진행 상황은 응답이 아니라 SSE(agent:stream:{chat_session_id})로 스트리밍된다.
 */
export async function sendChat(
  message: string,
  chatSessionId?: string | null,
): Promise<ChatResponse> {
  const token = sessionStorage.getItem('rf_access_token') ?? '';
  return customFetch<ChatResponse>(CHAT_URL, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({
      chat_session_id: chatSessionId ?? null,
      message,
    }),
  });
}
