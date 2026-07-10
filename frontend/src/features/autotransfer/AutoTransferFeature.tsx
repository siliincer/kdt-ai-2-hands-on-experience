import { useState } from 'react';
import { useNavigate } from 'react-router';
import { AutoTransferCard } from './AutoTransferCard';
import { AutoTransferFormCard } from './AutoTrnasferFormCard';

export default function AutoTransferFeature() {
  const navigate = useNavigate();
  const [showForm, setShowForm] = useState(false);

  return (
    // 고정 어두운 스킨을 시스템 카드 테마 규격(bg-card, border-border)으로 변경
    <div className="rounded-3xl border border-border bg-card p-6 shadow-sm">
      <div className="mb-6 flex items-center justify-between gap-4">
        <div>
          <h2 className="text-xl font-semibold text-foreground">자동 이체</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            정기 결제를 등록하고 관리할 수 있습니다.
          </p>
        </div>
        <button
          type="button"
          onClick={() => navigate('/')}
          className="rounded-2xl border border-border px-4 py-2 text-sm text-foreground transition hover:bg-muted/50"
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
