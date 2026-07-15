import { useState } from 'react';

import { F } from '@/shared/constants/font';

import type { CardsData } from '@/shared/types/ui';

export function CardInfoCard({
  data,
  onPrompt,
}: {
  data: CardsData;
  onPrompt?: (text: string) => void;
}) {
  const { cards } = data;
  const [activeCard, setActiveCard] = useState(0);

  const actions = [
    {
      emoji: '💳',
      label: '한도설정',
      fn: () => onPrompt?.('한도 설정 해줘'),
    },
    {
      emoji: '📄',
      label: '청구서',
      fn: () => onPrompt?.('카드 청구서 보여줘'),
    },
    {
      emoji: '🔒',
      label: '카드 정지',
      fn: () => onPrompt?.('카드 정지시켜줘'),
    },
  ];

  return (
    <div>
      <div className="mb-4 flex items-center gap-2">
        <span className="text-lg">💳</span>
        <p
          className="text-sm font-semibold text-foreground"
          style={{ fontFamily: F }}
        >
          내 카드
        </p>
      </div>

      {/* 카드 덱 레이아웃 높이 및 적층 구조 유지 */}
      <div className="relative mb-4 h-32.5">
        {cards.map((card, index) => (
          <button
            key={card.name}
            type="button"
            onClick={() => setActiveCard(index)}
            className="absolute left-0 top-0 w-full rounded-3xl p-4 text-left text-white shadow-xl transition-all"
            style={{
              background: card.bg || 'var(--primary)',
              top: index * 12,
              zIndex: activeCard === index ? 10 : 9 - index,
              transform: activeCard === index ? 'scale(1)' : 'scale(0.96)',
            }}
          >
            <p
              className="mb-4 text-xs font-semibold opacity-90"
              style={{ fontFamily: F }}
            >
              {card.name}
            </p>
            <p className="mb-4 font-mono text-sm tracking-[0.35em]">
              {card.num}
            </p>
            <div className="flex items-end justify-between text-[10px] opacity-90">
              <div>
                <p>VALID THRU</p>
                <p className="font-mono">{card.exp}</p>
              </div>
              <p className="font-medium tracking-wider">REALFINANCE</p>
            </div>
          </button>
        ))}
      </div>

      {/* 페이지네이션 도트의 하드코딩 색상을 accent 및 muted 시스템 변수로 맵핑 */}
      <div className="mb-4 flex justify-center gap-2">
        {cards.map((_, index) => (
          <button
            key={index}
            type="button"
            onClick={() => setActiveCard(index)}
            className="rounded-full transition-all duration-200"
            style={{
              width: activeCard === index ? 16 : 6,
              height: 6,
              background:
                activeCard === index
                  ? 'var(--accent)'
                  : 'var(--muted-foreground)',
            }}
          />
        ))}
      </div>

      {/* 하단 액션 버튼들의 고정 회색 스킨을 테마 세컨더리 시스템 스펙으로 전환 */}
      <div className="grid grid-cols-4 gap-2">
        {actions.map((action) => (
          <button
            key={action.label}
            type="button"
            onClick={action.fn}
            className="rounded-3xl bg-secondary py-3 text-[10px] font-medium text-secondary-foreground transition-all hover:bg-muted active:scale-95"
            style={{ fontFamily: F }}
          >
            <div className="text-xl">{action.emoji}</div>
            <div className="mt-2 text-foreground/90">{action.label}</div>
          </button>
        ))}
      </div>
    </div>
  );
}
