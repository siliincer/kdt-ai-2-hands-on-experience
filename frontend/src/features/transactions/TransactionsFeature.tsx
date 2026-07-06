import { useNavigate } from 'react-router';
import { TransactionsCard } from './TransactionCard';

export default function TransactionsFeature() {
  const navigate = useNavigate();

  return (
    <div className="rounded-3xl border border-white/10 bg-slate-800/70 p-6">
      <div className="mb-6 flex items-center justify-between gap-4">
        <div>
          <h2 className="text-xl font-semibold text-white">거래 내역</h2>
          <p className="mt-1 text-sm text-slate-400">
            최근 거래 기록과 지출 흐름을 자세히 확인해보세요.
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
      <TransactionsCard />
    </div>
  );
}
