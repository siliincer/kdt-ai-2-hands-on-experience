import { useMutation } from '@tanstack/react-query';
import type {
  UseMutationOptions,
  UseMutationResult,
} from '@tanstack/react-query';
import { customFetch } from '../api/customFetch';
import { APIError } from '../error/APIError';

// ----------------------------------------------------
// 변경용 훅 (useCustomTanstackMutation) 타입 및 구현
// ----------------------------------------------------
// 변동적인 데이터(Variables)를 받아 mutation을 실행하기 위한 설정 인터페이스
interface CustomMutationConfig<TData, TVariables> extends Omit<
  UseMutationOptions<TData, APIError, TVariables>,
  'mutationFn'
> {
  url: string;
  // 고정적인 fetch 옵션이 필요하다면 지정 (예: { method: 'POST' })
  fetchOptions?: Omit<RequestInit, 'body'>;
}

export function useCustomTanstackMutation<TData, TVariables = void>({
  url,
  fetchOptions,
  ...options
}: CustomMutationConfig<TData, TVariables>): UseMutationResult<
  TData,
  APIError,
  TVariables
> {
  return useMutation<TData, APIError, TVariables>({
    // 💡 mutate() 호출 시 인자로 넘어오는 variables를 body에 JSON 스트링으로 주입합니다.
    mutationFn: (variables) => {
      const isJson = typeof variables === 'object' && variables !== null;

      return customFetch<TData>(url, {
        method: 'POST', // 기본값 설정을 하되, 사용자가 fetchOptions로 PUT 등을 주면 덮어씌워짐
        headers: isJson ? { 'Content-Type': 'application/json' } : undefined,
        ...fetchOptions,
        body: isJson ? JSON.stringify(variables) : (variables as BodyInit),
      });
    },
    ...options,
  });
}

/*
const { mutate, isPending, error, isError } = useCustomTanstackMutation<CreateUserResponse, CreateUserPayload>({
    url: '/api/users',
    fetchOptions: { method: 'POST' }, // 필요 시 PUT, DELETE 등으로 변경 가능
    onSuccess: (data) => {
        alert(`생성 성공! ID: ${data.id}`);
    }
});

const handleSubmit = () => {
// 💡 실행 시점에 데이터 객체만 깔끔하게 전달합니다.
    mutate({ name: '홍길동', email: 'gildong@example.com' });
};

return (
    <button onClick={handleSubmit} disabled={isPending}>
        {isPending ? '등록 중...' : '유저 생성'}
    </button>
);
*/
