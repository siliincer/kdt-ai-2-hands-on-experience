import { createContext, useContext } from 'react';

import type { ChatRuntime } from '../types/interface';

/** 추가 인증(비밀번호 재확인) 제출 함수를 툴 UI 로 내려주는 컨텍스트. */
export const AuthenticateContext = createContext<
  ChatRuntime['authenticate'] | null
>(null);

export function useAuthenticate(): ChatRuntime['authenticate'] {
  const authenticate = useContext(AuthenticateContext);
  if (!authenticate) {
    throw new Error('useAuthenticate must be used within <AssistantProvider>');
  }
  return authenticate;
}
