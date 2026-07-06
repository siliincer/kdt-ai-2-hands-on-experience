import { useQuery } from '@tanstack/react-query';

function App() {
  // 1. useQuery를 사용하여 로컬 서버의 데이터를 조회합니다.
  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: ['localData'], // 캐싱에 사용할 유니크한 키값
    queryFn: async () => {
      const response = await fetch(`/backendApi/api/v1/users`);

      if (!response.ok) {
        throw new Error('서버에서 데이터를 가져오지 못했습니다.');
      }

      return response.json();
    },
  });

  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-8 bg-slate-900 text-white">
      <h1 className="text-4xl font-bold text-emerald-400 animate-pulse">
        Tailwind v4 세팅 완료!
      </h1>

      {/* 2. 상태별 UI 처리 */}
      <div className="flex flex-col items-center gap-4">
        {isLoading && (
          <p className="text-slate-400 animate-pulse">데이터 로딩 중...</p>
        )}

        {isError && <p className="text-rose-400">에러 발생: {error.message}</p>}

        {data && (
          <div className="rounded-lg bg-slate-800 p-4 border border-slate-700">
            <p className="text-sm text-slate-400 mb-2">서버 응답 데이터:</p>
            <pre className="text-emerald-300 font-mono">
              {JSON.stringify(data, null, 2)}
            </pre>
          </div>
        )}

        {/* 3. 수동으로 다시 불러오고 싶을 때 누르는 버튼 */}
        <button
          onClick={() => refetch()}
          disabled={isLoading}
          className="mt-2 rounded-lg bg-emerald-500 px-6 py-3 font-semibold text-slate-900 transition-colors hover:bg-emerald-400 disabled:bg-slate-700 disabled:text-slate-500"
        >
          {isLoading ? '새로고침 중...' : '데이터 다시 불러오기'}
        </button>
      </div>
    </div>
  );
}

export default App;
