import {
  handleRequestErrorForTanstackQuery,
  isBackendErrorResponse,
  handleBackendError,
} from './api_exception_handler';
import { APIError } from '../error/APIError';
import { emitUnauthorized } from '../lib/authEvents';
import type { CommonResponse } from './api_exception_handler';

export async function customFetch<T>(
  url: string,
  options?: RequestInit,
): Promise<T> {
  try {
    const response = await fetch(url, options);

    // 500 등 HTTP 에러 상태코드이거나 response.ok가 false인 경우
    if (!response.ok) {
      // 401: 토큰 만료/인증 실패 → 전역 로그아웃 시그널(리프레시 토큰 미도입).
      // ErrorBoundary 대신 로그인 화면으로 리다이렉트되도록 App 이 구독한다.
      // 단, 로그인 요청 자체의 401(비밀번호 오류 등)은 제외
      if (response.status === 401 && !url.includes('/login')) {
        emitUnauthorized();
        throw new APIError(
          '세션이 만료되었습니다. 다시 로그인해 주세요.',
          { code: 'UNAUTHORIZED' },
          401,
        );
      }

      let errorBody: unknown;
      try {
        // 백엔드가 보낸 에러 JSON 읽기 시도
        errorBody = await response.json();
      } catch {
        // JSON 파싱 실패 시 일반 에러로 처리
        throw new Error(
          `서버 에러가 발생했습니다. (상태코드: ${response.status})`,
        );
      }

      // BackendErrorResponse 가드 함수 활용
      if (isBackendErrorResponse(errorBody)) {
        // BackendErrorResponse 구조를 CommonResponse로 정규화 변환
        const formattedBackendError = handleBackendError(errorBody);
        // TanStack Query가 인지할 수 있도록 APIError에 메시지와 상세 코드 주입하여 throw
        throw new APIError(
          formattedBackendError.message || '서버 오류가 발생했습니다.',
          formattedBackendError.data, // { code, details } 구조
        );
      }

      throw new Error(
        `서버 응답 오류가 발생했습니다. (상태코드: ${response.status})`,
      );
    }

    // 200번대 정상 응답 처리
    const result = (await response.json()) as CommonResponse<T>;

    // HTTP는 200이지만 내부 success가 false인 비즈니스 에러 케이스
    if (!result.success) {
      throw new APIError(result.message || '요청 처리에 실패했습니다.');
    }

    // 최종 성공 시 데이터 단언 후 반환 (null 방어)
    return result.data as T;
  } catch (error) {
    // 이미 customFetch 내부에서 발생시켜 던진 APIError는 그대로 상위로 pass
    if (error instanceof APIError) {
      throw error;
    }

    // 'Failed to fetch' 같은 네트워크/브라우저 레벨 에러를 처리하여 APIError로 throw
    handleRequestErrorForTanstackQuery(error);

    // TypeScript 컴파일러 에러 방지용 (실제론 위 핸들러에서 무조건 throw하므로 실행 안 됨)
    throw error;
  }
}
