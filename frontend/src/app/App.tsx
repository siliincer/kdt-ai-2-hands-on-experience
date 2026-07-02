function App() {
  return (
    // 전체 화면을 부모 flex로 잡고, 세로 정렬(flex-col)과 간격(gap-8)을 줍니다.
    <div className="flex min-h-screen flex-col items-center justify-center gap-8 bg-slate-900">
      <h1 className="text-4xl font-bold text-emerald-400 animate-pulse">
        Tailwind v4 세팅 완료!
      </h1>
    </div>
  );
}

export default App;
