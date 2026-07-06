import { useState } from 'react';
import { useNavigate } from 'react-router';
import { AutoTransferCard } from './AutoTransferCard';
import { AutoTransferFormCard } from './AutoTrnasferFormCard';

export default function AutoTransferFeature() {
  const navigate = useNavigate();
  const [showForm, setShowForm] = useState(false);

  return (
    <div className="rounded-3xl border border-white/10 bg-slate-800/70 p-6">
      <div className="mb-6 flex items-center justify-between gap-4">
        <div>
          <h2 className="text-xl font-semibold text-white">자동 이체</h2>
          <p className="mt-1 text-sm text-slate-400">
            정기 결제를 등록하고 관리할 수 있습니다.
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
      {showForm ? (
        <AutoTransferFormCard onDone={() => setShowForm(false)} />
      ) : (
        <AutoTransferCard onShowForm={() => setShowForm(true)} />
      )}
    </div>
  );
}
