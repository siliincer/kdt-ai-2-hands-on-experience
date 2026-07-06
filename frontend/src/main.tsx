import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ErrorBoundary } from 'react-error-boundary';
import ErrorFallback from './pages/ErrorFallback.tsx';
import './styles/index.css';
import { ThemeProvider } from './app/providers/ThemeProvider.tsx';
import App from './app/App.tsx';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      // 디버깅: API 에러 발생 시 최상위 Error Boundry로 에러를 던집니다.
      throwOnError: true,
      // 에러 발생 시 기본 3회 재시도를 꺼두거나 조절
      retry: false,
    },
    mutations: {
      throwOnError: true,
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
