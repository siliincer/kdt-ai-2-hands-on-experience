import { useNavigate } from 'react-router';

import { cards } from '@/features/mockData/mockData';

import type { CardsData } from '@/shared/types/ui';

import { CardInfoCard } from './CardInfoCard';

// 라우트(디버그) 잔존용 어댑터: 목데이터를 CardsData 형태로. E단계에서 라우트째 제거.
const MOCK_CARDS: CardsData = { cards };

export default function CardFeature() {
  const navigate = useNavigate();

  return (
    // 고정 어두운 스킨을 공통 카드 테마 스펙(bg-card, border-border)으로 변경
    <div className="rounded-3xl border border-border bg-card p-6 shadow-sm">
      <div className="mb-6 flex items-center justify-between gap-4">
        <div>
          <h2 className="text-xl font-semibold text-foreground">카드 관리</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            카드를 한눈에 보고 청구서를 확인할 수 있습니다.
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
      <CardInfoCard data={MOCK_CARDS} onPrompt={() => navigate('/bill')} />
    </div>
  );
}
