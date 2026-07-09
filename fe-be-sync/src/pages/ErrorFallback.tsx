import type { FallbackProps } from 'react-error-boundary';

function ErrorFallback({ error, resetErrorBoundary }: FallbackProps) {
  // error 객체가 실제 Error의 인스턴스인지 체크합니다.
  const errorMessage = error instanceof Error ? error.message : String(error);

  return (
    <div style={{ padding: '20px', textAlign: 'center' }}>
      <h2>문제가 발생했습니다.</h2>
      <pre style={{ color: 'red' }}>{errorMessage}</pre>
      {/* 버튼을 누르면 Tanstack Query의 캐시가 비워지고 화면이 재렌더링 됩니다.*/}
      <button onClick={resetErrorBoundary}>다시 시도하기</button>
    </div>
  );
}

export default ErrorFallback;
