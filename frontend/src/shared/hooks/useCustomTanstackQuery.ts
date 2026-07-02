// hooks/useCustomQuery.ts
import { useQuery } from '@tanstack/react-query';
import type { UseQueryOptions, UseQueryResult } from '@tanstack/react-query';
import { customFetch } from '../api/customFetch';
import { APIError } from '../error/APIError';

// useQuery의 옵션 중 queryKey와 queryFn을 제외한 나머지 옵션 타입 정의
type UseCustomQueryOptions<T> = Omit<
  UseQueryOptions<T, APIError, T>,
  'queryKey' | 'queryFn'
>;

/**
 * APIError가 기본 내장된 통일된useQuery 래퍼 훅
 * @param queryKey 쿼리 키 배열
 * @param url 요청할 API 상대 경로
 * @param options retry 등 추가 쿼리 옵션 (선택)
 */
export function useCustomTanstackQuery<T>(
  queryKey: unknown[],
  url: string,
  fetchOptions?: RequestInit,
  tanstackOptions?: UseCustomQueryOptions<T>,
): UseQueryResult<T, APIError> {
  return useQuery<T, APIError>({
    queryKey,
    // 💡 이제 내부에서 알아서 customFetch를 호출하므로 바깥 코드가 간결해집니다.
    queryFn: () => customFetch<T>(url, fetchOptions),
    ...tanstackOptions,
  });
}

/*
// 💡 복잡한 화살표 함수와 에러 타입 지정 없이 한 줄로 처리 가능!
const { data, isLoading, isError, error } = useCustomQuery<User>(
  ['user', userId],
  `/api/users/${userId}`,
  { retry: false } // 필요한 옵션만 깔끔하게 전달
);
*/
