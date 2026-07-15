// 지출이나 수입 내역에
// 카테고리(Category) 태그를 달고 변경할 수 있는 UI 컴포넌트
import { useState, useEffect, useRef } from 'react';
import { Tag } from 'lucide-react';

import { NAVY, MINT, GRAY_BG } from '@/shared/constants/color';
import { F } from '@/shared/constants/font';
import { CATS } from '@/shared/constants/categories';

interface CatBadgeProps {
  cat: string;
  onEdit: (category: string) => void;
}

export function CatBadge({ cat, onEdit }: CatBadgeProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [customValue, setCustomValue] = useState('');
  const containerRef = useRef<HTMLSpanElement>(null);

  // 팝업 바깥 클릭 시 닫히는 로직
  useEffect(() => {
    const handleOutsideClick = (event: MouseEvent) => {
      if (
        containerRef.current &&
        !containerRef.current.contains(event.target as Node)
      ) {
        setIsOpen(false);
      }
    };

    if (isOpen) {
      document.addEventListener('mousedown', handleOutsideClick);
    }

    return () => {
      document.removeEventListener('mousedown', handleOutsideClick);
    };
  }, [isOpen]);

  // 카테고리 선택 및 변경 공통 핸들러
  const handleSelect = (value: string) => {
    if (!value.trim()) return;
    onEdit(value);
    setCustomValue('');
    setIsOpen(false);
  };

  return (
    <span ref={containerRef} className="relative inline-flex">
      {/* 카테고리 뱃지 버튼 */}
      <button
        type="button"
        onClick={() => setIsOpen((prev) => !prev)}
        className="inline-flex items-center gap-1 rounded px-2 py-1 text-[10px] font-medium bg-[#EFEFEF] text-[#6B7A99]"
        style={{ fontFamily: F }}
      >
        <Tag size={9} />
        {cat}
      </button>

      {/* 카테고리 선택 팝업 */}
      {isOpen && (
        <div className="absolute left-0 top-full z-10 mt-2 w-60 rounded-2xl border border-slate-200 bg-white p-3 shadow-lg">
          {/* 기본 카테고리 그리드 */}
          <div className="grid grid-cols-4 gap-1 mb-2">
            {CATS.map((category) => {
              const isSelected = cat === category;
              return (
                <button
                  key={category}
                  type="button"
                  onClick={() => handleSelect(category)}
                  className="rounded py-1 text-[10px] font-medium transition-colors"
                  style={{
                    background: isSelected ? MINT : GRAY_BG,
                    color: isSelected ? NAVY : '#6B7A99',
                    fontFamily: F,
                  }}
                >
                  {category}
                </button>
              );
            })}
          </div>

          {/* 직접 입력 input 영역 */}
          <div className="flex gap-1">
            <input
              value={customValue}
              onChange={(e) => setCustomValue(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleSelect(customValue)}
              className="flex-1 rounded px-2 py-1 text-[10px] outline-none"
              style={{ background: GRAY_BG, color: NAVY, fontFamily: F }}
              placeholder="직접 입력..."
            />
            {customValue.trim() && (
              <button
                type="button"
                onClick={() => handleSelect(customValue)}
                className="rounded px-2 text-[10px] font-medium"
                style={{ background: MINT, color: NAVY, fontFamily: F }}
              >
                ✓
              </button>
            )}
          </div>
        </div>
      )}
    </span>
  );
}
