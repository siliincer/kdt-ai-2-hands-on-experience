import { useNavigate } from 'react-router';
import { SpendingCard } from './SpendingCard';

export default function SpendingFeature() {
  const navigate = useNavigate();

  return (
    <div className="rounded-3xl border border-white/10 bg-slate-800/70 p-6">
      <div className="mb-6 flex items-center justify-between gap-4">
        <div>
          <h2 className="text-xl font-semibold text-white">소비 분석</h2>
          <p className="mt-1 text-sm text-slate-400">
            지출 패턴을 확인하고 카테고리별 분석을 통해 현명한 소비 결정을
            돕습니다.
          </p>
        </div>
        <button
          type="button"
          onClick={() => navigate('/')}
          className="rounded-2xl border border-slate-600 px-4 py-2 text-sm text-slate-200 transition hover:bg-slate-900"
        >
          홈으로
        </button>
      </div>
      <SpendingCard onNavigate={navigate} />
    </div>
  );
}
