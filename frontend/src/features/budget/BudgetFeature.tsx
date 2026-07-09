import { useNavigate } from 'react-router';

import { BudgetCard } from './BudgetCard';

export default function BudgetFeature() {
  const navigate = useNavigate();

  return (
    // 고정 다크 배경을 시스템 공통 카드 스펙(bg-card, border-border)으로 변경
    <div className="rounded-3xl border border-border bg-card p-6 shadow-sm">
      <div className="mb-6 flex items-center justify-between gap-4">
        <div>
          <h2 className="text-xl font-semibold text-foreground">예산 관리</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            예산을 설정하고 구독을 관리하여 소비 습관을 지속적으로 개선하세요.
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
      <BudgetCard />
    </div>
  );
}
