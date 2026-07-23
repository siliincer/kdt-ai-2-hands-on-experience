import { createContext, useContext } from 'react';

import type { ChatRuntime } from '../types/interface';

/** 신규 수취 계좌 검증 함수를 recipient_select 툴 UI 로 내려주는 컨텍스트. */
export const RecipientVerifyContext = createContext<
  ChatRuntime['verifyRecipient'] | null
>(null);

export function useVerifyRecipient(): ChatRuntime['verifyRecipient'] {
  const verifyRecipient = useContext(RecipientVerifyContext);
  if (!verifyRecipient) {
    throw new Error(
      'useVerifyRecipient must be used within <AssistantProvider>',
    );
  }
  return verifyRecipient;
}
