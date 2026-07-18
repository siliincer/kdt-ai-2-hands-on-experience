import { createContext, useContext } from 'react';

import type { ChatRuntime } from '../types/interface';

/** need_input(일반 입력·선택 대기) 제출 함수를 툴 UI 로 내려주는 컨텍스트. */
export const SubmitInputContext = createContext<
  ChatRuntime['submitInput'] | null
>(null);

export function useSubmitInput(): ChatRuntime['submitInput'] {
  const submitInput = useContext(SubmitInputContext);
  if (!submitInput) {
    throw new Error('useSubmitInput must be used within <AssistantProvider>');
  }
  return submitInput;
}
