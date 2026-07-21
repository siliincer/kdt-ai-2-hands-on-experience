import { customFetch } from '@/shared/api/customFetch';

import { RECIPIENT_CANDIDATE_VERIFY_URL } from '../constants/constants';

/**
 * 신규 수취 계좌 검증 (FE 전용, 계약 부록 29.2)
 * POST /api/v1/recipient-candidates:verify → { recipient_candidate_id, ... }
 *
 * 계좌번호 원문은 이 API 까지만 전달되고, 이후 흐름(Agent 재개·Prepare)은
 * recipient_candidate_id 참조만 사용한다. 예금주명은 마스킹되어 반환된다.
 */
export interface RecipientCandidateVerifyResult {
  recipient_candidate_id: string;
  name: string;
  bank_name: string | null;
  masked_account_number: string;
  status: string;
  expires_at: string;
}

export async function verifyRecipientCandidate(
  chatSessionId: string,
  accountNumber: string,
  bankName?: string | null,
): Promise<RecipientCandidateVerifyResult> {
  const token = sessionStorage.getItem('rf_access_token') ?? '';
  return customFetch<RecipientCandidateVerifyResult>(
    RECIPIENT_CANDIDATE_VERIFY_URL,
    {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify({
        chat_session_id: chatSessionId,
        bank_name: bankName ?? null,
        account_number: accountNumber,
      }),
    },
  );
}
