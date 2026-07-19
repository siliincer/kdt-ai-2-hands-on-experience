// HITL 카드 표시용 포맷 헬퍼(비즈니스 로직과 무관한 순수 함수).

/** 금액을 "50,000원" 형태로 포맷한다(null/undefined 는 0). */
export function won(amount?: number | null): string {
  return `${(amount ?? 0).toLocaleString()}원`;
}

/** 은행명·마스킹번호 등 표시 조각을 공백으로 잇는다(빈 값 제외). */
export function joinParts(...parts: (string | null | undefined)[]): string {
  return parts.filter(Boolean).join(' ');
}
