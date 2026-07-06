// hooks/useCustomTanstack.ts
import { useQuery } from '@tanstack/react-query';
import type { UseQueryOptions, UseQueryResult } from '@tanstack/react-query';
import { customFetch } from '../api/customFetch';
import { APIError } from '../error/APIError';

// ----------------------------------------------------
// 1. 조회용 훅 (useCustomTanstackQuery) 타입 및 구현
// ----------------------------------------------------
interface CustomQueryConfig<T> extends Omit<
  UseQueryOptions<T, APIError, T>,
  'queryFn'
> {
  url: string;
  fetchOptions?: RequestInit;
}

export function useCustomTanstackQuery<T>({
  queryKey,
  url,
  fetchOptions,
  ...options
}: CustomQueryConfig<T>): UseQueryResult<T, APIError> {
  return useQuery<T, APIError>({
    queryKey,
    // 💡 v5의 abort signal과 사용자가 넘긴 fetchOptions를 안전하게 병합합니다.
    queryFn: ({ signal }) => customFetch<T>(url, { signal, ...fetchOptions }),
    ...options,
  });
}
/*
사용 예시
const { data, isLoading, error, isError } = useCustomTanstackQuery<Post>({
  queryKey: ['post', postId],
  url: `/api/posts/${postId}`,
  // 💡 특정 API에 커스텀 헤더나 인증 토큰 등을 개별 적용하고 싶을 때 사용
  fetchOptions: {
    headers: { 'X-Custom-Header': 'MyValue' }
  },
  retry: false
});
*/
