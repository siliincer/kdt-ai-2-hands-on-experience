// 인증 만료(401) 전역 시그널. shared 가 entities(user store)에 의존하지 않도록
// 이벤트로 느슨하게 연결한다. App 이 구독해서 logout + 로그인 화면 리다이렉트.

export const UNAUTHORIZED_EVENT = 'rf:unauthorized';

export function emitUnauthorized(): void {
  window.dispatchEvent(new Event(UNAUTHORIZED_EVENT));
}

export function onUnauthorized(handler: () => void): () => void {
  window.addEventListener(UNAUTHORIZED_EVENT, handler);
  return () => window.removeEventListener(UNAUTHORIZED_EVENT, handler);
}
