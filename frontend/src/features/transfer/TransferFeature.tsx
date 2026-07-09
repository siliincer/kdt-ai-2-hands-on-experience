import { useNavigate } from 'react-router';

import { TransferCard } from './TransferCard';

export default function TransferFeature() {
  const navigate = useNavigate();

  return (
    // 1. 하드코딩된 bg-slate-800 대신 테마 변수 bg-card, border-border 적용
    <div className="rounded-3xl border border-border bg-card p-6 transition-colors duration-200">
      <div className="mb-6 flex items-center justify-between gap-4">
        <div>
          {/* text-foreground로 라이트(진한네이비)/다크(화이트) 자동 대응 */}
          <h2 className="text-xl font-semibold text-foreground">송금</h2>
          {/* text-muted-foreground로 부연 설명 글자색 자동 대응 */}
          <p className="mt-1 text-sm text-foreground">
            받는 사람, 금액, 일정을 확인하고 안전하게 송금하세요.
          </p>
        </div>
        <button
          type="button"
          onClick={() => navigate('/')}
          // 2. 홈으로 버튼을 테마 변수화하여 하얀 배경과 어두운 배경 모두에 어울리도록 수정
          className="rounded-2xl border border-border px-4 py-2 text-sm text-foreground transition-colors hover:bg-muted"
        >
          홈으로
        </button>
      </div>
      <TransferCard />
    </div>
  );
}
