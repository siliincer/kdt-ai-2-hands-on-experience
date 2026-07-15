import { APIError } from '../error/APIError';

/**
 * 백엔드 API 예외 응답 타입 정의
 */
interface BackendErrorResponse {
  success: boolean;
  error: {
    code: string;
    message: string;
    details?: unknown;
  };
}

/**
 * 공통 응답 형식
 */
export interface CommonResponse<T = unknown> {
  success: boolean;
  message: string | null;
  data: T | null;
}

/**
 * 성공 응답 생성 함수
 * @param message - 응답 메시지
 * @param data - 응답 데이터
 */
export function successResponse<T>(
  message: string | null,
  data: T | null = null,
): CommonResponse<T> {
  return {
    success: true,
    message,
    data,
  };
}

/**
 * 실패 응답 생성 함수
 * @param message - 실패 메시지
 * @param data - 추가 데이터 (예: 에러 상세 정보)
 */
export function failureResponse<T = unknown>(
  message: string | null,
  data: T | null = null,
): CommonResponse<T> {
  return {
    success: false,
    message,
    data,
  };
}

/**
 * 에러 응답이 백엔드 에러 형식인지 확인
 */
export function isBackendErrorResponse(
  error: unknown,
): error is BackendErrorResponse {
  return (
    error !== null &&
    typeof error === 'object' &&
    'success' in error &&
    'error' in error &&
    typeof (error as Record<string, unknown>).error === 'object' &&
    'code' in
      ((error as Record<string, unknown>).error as Record<string, unknown>) &&
    'message' in
      ((error as Record<string, unknown>).error as Record<string, unknown>)
  );
}

/**
 * 백엔드 에러 응답을 CommonResponse로 변환
 * @param error - 백엔드에서 받은 에러 응답
 */
export function handleBackendError(
  error: unknown,
): CommonResponse<{ code: string; details?: unknown }> {
  if (isBackendErrorResponse(error)) {
    return failureResponse(error.error.message, {
      code: error.error.code,
      details: error.error.details,
    });
  }

  // 알 수 없는 에러 형식인 경우
  if (error instanceof Error) {
    return failureResponse(error.message, { code: 'UNKNOWN_ERROR' });
  }

  return failureResponse('알 수 없는 오류가 발생했습니다.', {
    code: 'UNKNOWN_ERROR',
  });
}

/**
 * API 요청 실패 시 처리 (네트워크 에러, 타임아웃 등)
 * @param error - 발생한 에러
 */
export function handleRequestError(error: unknown): CommonResponse {
  // fetch 네트워크 실패는 모든 브라우저가 TypeError를 던지지만 메시지는
  // 엔진마다 다르다(Chromium: "Failed to fetch", Firefox: "NetworkError
  // when attempting to fetch resource.", WebKit: "Load failed"). 특정 문자열만
  // 매칭하면 Chromium 밖에서 이 분기를 안 타서 사용자가 브라우저 원본 에러
  // 문구를 그대로 보게 된다 — TypeError 여부만으로 판단.
  if (error instanceof TypeError) {
    // 인터넷 연결 끊김, 서버 다운, CORS 에러, 도메인 오타
    return failureResponse('네트워크 연결을 확인해주세요.');
  }

  if (error instanceof Error) {
    return failureResponse(error.message);
  }

  return failureResponse('요청 처리 중 오류가 발생했습니다.');
}

/**
 * API 요청 실패 시 tanstack query 연계 처리 (네트워크 에러, 타임아웃 등)
 * APIError를 throw 한다.
 * TanStack Query는 기본적으로 fetch나 axios가 에러를 throw(던지기) 해야 에러 상태(isError)로 인식합니다.
 * 사용 예시: queryFn: () => customFetch<User>(`/api/users/${userId}`),
 * @param error - 발생한 에러
 */
export function handleRequestErrorForTanstackQuery(
  error: unknown,
): CommonResponse {
  // fetch 네트워크 실패는 모든 브라우저가 TypeError를 던지지만 메시지는
  // 엔진마다 다르다(Chromium: "Failed to fetch", Firefox: "NetworkError
  // when attempting to fetch resource.", WebKit: "Load failed"). 특정 문자열만
  // 매칭하면 Chromium 밖에서 이 분기를 안 타서 사용자가 브라우저 원본 에러
  // 문구를 그대로 보게 된다 — TypeError 여부만으로 판단.
  if (error instanceof TypeError) {
    throw new APIError('네트워크 연결을 확인해주세요.');
  }

  if (error instanceof Error) {
    throw new APIError(error.message);
  }

  throw new APIError('요청 처리 중 오류가 발생했습니다.');
}
