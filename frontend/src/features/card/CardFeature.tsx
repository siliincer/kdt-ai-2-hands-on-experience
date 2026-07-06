import { useState } from 'react';
import { useNavigate } from 'react-router';

import { NAVY, MINT } from '@/shared/constants/color';
import { F } from '@/shared/constants/font';
import { cards } from '@/features/mockData/mockData';

function CardInfoCard({ onNavigate }: { onNavigate: (path: string) => void }) {
  const [activeCard, setActiveCard] = useState(0);

  const actions = [
    {
      emoji: '🚨',
      label: '분실신고',
      fn: undefined as (() => void) | undefined,
    },
    {
      emoji: '💳',
      label: '한도설정',
      fn: undefined as (() => void) | undefined,
    },
    { emoji: '📄', label: '청구서', fn: () => onNavigate('/bill') },
    {
      emoji: '🔒',
      label: '카드 정지',
      fn: undefined as (() => void) | undefined,
    },
  ];

  return (
    <div>
      <div className="mb-4 flex items-center gap-2">
        <span className="text-lg">💳</span>
        <p
          className="text-sm font-semibold"
          style={{ color: NAVY, fontFamily: F }}
        >
          내 카드
        </p>
      </div>
      <div className="relative mb-4 h-32.5">
        {cards.map((card, index) => (
          <button
            key={card.name}
            type="button"
            onClick={() => setActiveCard(index)}
            className="absolute left-0 top-0 w-full rounded-3xl p-4 text-left text-white shadow-xl transition-all"
            style={{
              background: card.bg,
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
              <p>REALFINANCE</p>
            </div>
          </button>
        ))}
      </div>
      <div className="mb-4 flex justify-center gap-2">
        {cards.map((_, index) => (
          <button
            key={index}
            type="button"
            onClick={() => setActiveCard(index)}
            className="rounded-full transition-all"
            style={{
              width: activeCard === index ? 16 : 6,
              height: 6,
              background: activeCard === index ? MINT : '#CBD5E1',
            }}
          />
        ))}
      </div>
      <div className="grid grid-cols-4 gap-2">
        {actions.map((action) => (
          <button
            key={action.label}
            type="button"
            onClick={action.fn}
            className="rounded-3xl bg-slate-100 py-3 text-[10px] font-medium hover:opacity-90"
            style={{ fontFamily: F }}
          >
            <div className="text-xl">{action.emoji}</div>
            <div className="mt-2">{action.label}</div>
          </button>
        ))}
      </div>
    </div>
  );
}

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
