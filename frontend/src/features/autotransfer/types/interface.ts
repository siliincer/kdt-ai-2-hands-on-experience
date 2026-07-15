interface AutoTransferPrefill {
  account?: string;
  /** 금액(숫자 문자열, 원 단위) */
  amount?: string;
  /** 이체일 라벨(예: '매월 25일') */
  day?: string;
}

interface AutoTransferConfirmValues {
  account: string;
  amount: string;
  day: string;
}

interface AutoTransferFormCardProps {
  prefill?: AutoTransferPrefill;
  /** 주어지면 confirm 모드: 내부 완료 화면 대신 이 콜백을 호출한다(HITL). */
  onConfirm?: (values: AutoTransferConfirmValues) => void;
  onCancel?: () => void;
  submitLabel?: string;
  disabled?: boolean;
  /** 레거시(라우트) 호환: confirm 모드가 아닐 때 취소 버튼 동작. */
  onDone?: () => void;
}

export type {
  AutoTransferConfirmValues,
  AutoTransferFormCardProps,
  AutoTransferPrefill,
};
