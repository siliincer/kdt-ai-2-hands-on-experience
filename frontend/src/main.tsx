import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ErrorBoundary } from 'react-error-boundary';
import ErrorFallback from './pages/ErrorFallback.tsx';
import './styles/index.css';
import { ThemeProvider } from './app/providers/ThemeProvider.tsx';
import App from './app/App.tsx';
import { APIError } from './shared/error/APIError';

// 401(인증 만료)은 ErrorBoundary 로 던지지 않는다 → App 이 로그인 화면으로 리다이렉트.
const isUnauthorized = (error: unknown) =>
  error instanceof APIError && error.status === 401;

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      // 디버깅: API 에러 발생 시 최상위 Error Boundry로 에러를 던집니다. (401 제외)
      throwOnError: (error) => !isUnauthorized(error),
      // 에러 발생 시 기본 3회 재시도를 꺼두거나 조절
      retry: false,
    },
    mutations: {
      throwOnError: (error) => !isUnauthorized(error),
    },
  },
});

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <ErrorBoundary
        FallbackComponent={ErrorFallback}
        onReset={() => {
          // 다시 시도할 때 tanstack query의 모든 에러 상태를 초기화
          queryClient.resetQueries();
        }}
      >
        <ThemeProvider>
          <App />
        </ThemeProvider>
      </ErrorBoundary>
    </QueryClientProvider>
  </StrictMode>,
);
