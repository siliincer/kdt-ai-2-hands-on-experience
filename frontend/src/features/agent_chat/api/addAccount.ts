import { customFetch } from '@/shared/api/customFetch';

import { ADD_ACCOUNT_URL } from '../constants/constants';

export interface AddAccountResult {
  account_id: string;
  bank_name: string;
  masked_account_number: string;
  balance: number;
  currency: string;
}

/**
 * 계좌 추가 (FE 슬래시 명령 `/add_account <은행명>` 전용, 임시 UX)
 * POST /api/v1/accounts → { account_id, bank_name, masked_account_number, ... }
 *
 * Agent 워크플로우가 아직 없어 Backend 를 직접 호출한다. 은행명 검증은 Backend 가 한다.
 */
export async function addAccount(bankName: string): Promise<AddAccountResult> {
  const token = sessionStorage.getItem('rf_access_token') ?? '';
  return customFetch<AddAccountResult>(ADD_ACCOUNT_URL, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({ bank_name: bankName }),
  });
}
