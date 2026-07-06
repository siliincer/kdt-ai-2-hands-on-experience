import { useNavigate } from 'react-router';
import { CardInfoCard } from './CardInfoCard';

export default function CardFeature() {
  const navigate = useNavigate();

  return (
    <div className="rounded-3xl border border-white/10 bg-slate-800/70 p-6">
      <div className="mb-6 flex items-center justify-between gap-4">
        <div>
          <h2 className="text-xl font-semibold text-white">카드 관리</h2>
          <p className="mt-1 text-sm text-slate-400">
            카드를 한눈에 보고 청구서를 확인할 수 있습니다.
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
      <CardInfoCard onNavigate={navigate} />
    </div>
  );
}
