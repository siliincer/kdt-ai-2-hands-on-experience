// HITL UI 컴포넌트 공통 Tailwind 클래스 상수(중복 제거).
// 카드/버튼 껍데기는 계약 UI 전반에서 반복되므로 한 곳에 모은다.

/** 결과·입력 카드 컨테이너 */
export const HITL_CARD = 'mt-2 rounded-2xl border border-border bg-card p-4';

/** 하단 1차 액션(승인/확인/선택 완료). disabled 는 opacity-40. */
export const HITL_BTN_PRIMARY =
  'rounded-full bg-primary px-4 py-1.5 text-xs font-medium text-primary-foreground transition disabled:opacity-40';

/** 하단 2차 액션(취소/뒤로). */
export const HITL_BTN_SECONDARY =
  'rounded-full border border-border px-4 py-1.5 text-xs font-medium text-muted-foreground transition hover:bg-muted/40';

/** 목록 항목/작은 pill 버튼(옵션 선택·프리셋·수취인 등). */
export const HITL_BTN_PILL =
  'rounded-full border border-border px-4 py-1.5 text-xs font-medium text-foreground transition hover:bg-muted/40';

/** 하단 액션 행(우측 정렬). */
export const HITL_ACTIONS_ROW = 'mt-3 flex items-center justify-end gap-2';

/** 텍스트/숫자/날짜 입력 필드 기본 클래스. */
export const HITL_INPUT =
  'w-full rounded-xl border border-border bg-input-background px-3 py-2 text-sm text-foreground outline-none placeholder:text-muted-foreground focus:border-primary';
