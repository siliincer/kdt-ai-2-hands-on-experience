import { createContext, useContext } from 'react';

import type { ChatRuntime } from '../types/interface';

/** confirm 카드(HITL) 승인/거절 함수를 툴 UI 로 내려주는 컨텍스트. */
export const ApproveContext = createContext<ChatRuntime['approve'] | null>(
  null,
);

export function useApprove(): ChatRuntime['approve'] {
  const approve = useContext(ApproveContext);
  if (!approve) {
    throw new Error('useApprove must be used within <AssistantProvider>');
  }
  return approve;
}
