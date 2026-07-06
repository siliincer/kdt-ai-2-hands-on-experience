import { useNavigate } from 'react-router';

import { BudgetCard } from './BudgetCard';

export default function BudgetFeature() {
  const navigate = useNavigate();

  return (
    <div className="rounded-3xl border border-white/10 bg-slate-800/70 p-6">
      <div className="mb-6 flex items-center justify-between gap-4">
        <div>
          <h2 className="text-xl font-semibold text-white">예산 관리</h2>
          <p className="mt-1 text-sm text-slate-400">
            예산을 설정하고 구독을 관리하여 소비 습관을 지속적으로 개선하세요.
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
      <BudgetCard />
    </div>
  );
}
