import { useNavigate } from 'react-router';
import { SpendingCard } from './SpendingCard';

export default function SpendingFeature() {
  const navigate = useNavigate();

  return (
    // bg-slate-800/70 카드를 시스템 테마인 bg-card 및 테두리선 var(--border)로 매핑
    <div className="rounded-3xl border border-border bg-card p-6 shadow-sm">
      <div className="mb-6 flex items-center justify-between gap-4">
        <div>
          {/* text-white를 시스템 기본 전경색인 text-foreground로 변경 */}
          <h2 className="text-xl font-semibold text-foreground">소비 분석</h2>
          {/* 부가 설명 텍스트를 시스템 보조 색상인 text-muted-foreground로 변경 */}
          <p className="mt-1 text-sm text-muted-foreground">
            지출 패턴을 확인하고 카테고리별 분석을 통해 현명한 소비 결정을
            돕습니다.
          </p>
        </div>
        <button
          type="button"
          onClick={() => navigate('/')}
          // 버튼 스타일을 시스템 테두리(border-border) 및 전경색(text-foreground), 호버 시 보조 배경(hover:bg-muted/50)으로 대응
          className="rounded-2xl border border-border px-4 py-2 text-sm text-foreground transition hover:bg-muted/50"
        >
          홈으로
        </button>
      </div>
      <SpendingCard onNavigate={navigate} />
    </div>
  );
}
