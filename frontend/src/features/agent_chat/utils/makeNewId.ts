import { v4 as uuidv4 } from 'uuid';

export function newId(): string {
  return uuidv4();
}

// uuid 라이브러리는 내부적으로 crypto.randomUUID 호환성을 알아서 처리하므로
// HTTP 환경에서도 안전하게 작동합니다.
