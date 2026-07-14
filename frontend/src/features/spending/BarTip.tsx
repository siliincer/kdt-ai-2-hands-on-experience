import { M, F } from '@/shared/constants/font';
import { NAVY } from '@/shared/constants/color';

import type { TooltipProps } from 'recharts';
import type { BarCatDatum } from '@/shared/types/ui';

export function BarTip({
  active,
  payload,
  label,
}: TooltipProps<number, string>) {
  if (!active || !payload?.length) return null;

  // 차트에 바인딩된 현재 막대의 원본 datum(BarCatDatum)을 그대로 사용.
  const data = payload[0]?.payload as BarCatDatum | undefined;
  if (!data) return null;

  return (
    <div
      className="rounded-2xl bg-white p-3 shadow-lg"
      style={{ border: '1px solid rgba(15,30,61,0.1)', minWidth: 200 }}
    >
      <div className="mb-2 flex items-center justify-between">
        <p
          className="text-[10px] font-bold"
          style={{ color: NAVY, fontFamily: F }}
        >
          {label}
        </p>
        <p
          className="text-[10px] font-bold"
          style={{
            color: data.change >= 0 ? '#FF4D4F' : '#3B82F6',
            fontFamily: M,
          }}
        >
          {data.change >= 0 ? '+' : ''}
          {data.change}%
        </p>
      </div>
      <p
        className="mb-2 text-[10px]"
        style={{ color: '#6B7A99', fontFamily: M }}
      >
        {data.prev.toLocaleString()} → {data.curr.toLocaleString()}원
      </p>
      {data.added.length > 0 ? (
        <>
          <p
            className="mb-1 text-[10px] font-bold"
            style={{ color: '#3B82F6', fontFamily: F }}
          >
            + 추가
          </p>
          {data.added.map((item) => (
            <div
              key={item.name}
              className="mb-1 flex justify-between text-[10px]"
            >
              <span style={{ color: NAVY, fontFamily: F }}>{item.name}</span>
              <span style={{ color: '#3B82F6', fontFamily: M }}>
                +{item.amount.toLocaleString()}원
              </span>
            </div>
          ))}
        </>
      ) : null}
      {data.removed.length > 0 ? (
        <>
          <p
            className="mt-1 mb-1 text-[10px] font-bold"
            style={{ color: '#FF4D4F', fontFamily: F }}
          >
            − 감소
          </p>
          {data.removed.map((item) => (
            <div
              key={item.name}
              className="mb-1 flex justify-between text-[10px]"
            >
              <span style={{ color: NAVY, fontFamily: F }}>{item.name}</span>
              <span style={{ color: '#FF4D4F', fontFamily: M }}>
                -{item.amount.toLocaleString()}원
              </span>
            </div>
          ))}
        </>
      ) : null}
    </div>
  );
}
