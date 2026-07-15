import { customFetch } from '@/shared/api/customFetch';

import { APPROVE_URL } from '../constants/constants';

import type { ApprovalDecision } from '../types/interface';

/**
 * confirm 카드(HITL) 승인/거절
 * POST /api/v1/agent/approve  → 에이전트 후속 턴 재개(진행은 SSE)
 */
export async function approveAgentAction(
  chatSessionId: string,
  approvalId: string,
  decision: ApprovalDecision,
  args?: Record<string, unknown>,
  component?: string,
): Promise<{ decision: string }> {
  const token = sessionStorage.getItem('rf_access_token') ?? '';
  return customFetch<{ decision: string }>(APPROVE_URL, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({
      chat_session_id: chatSessionId,
      approval_id: approvalId,
      decision,
      args: args ?? null,
      component: component ?? null,
    }),
  });
}
