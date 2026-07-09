interface TransferPrefill {
  name?: string;
  bank?: string;
  account?: string;
  amtRaw?: string;
  scheduled?: string;
}

interface TransferConfirmValues {
  name: string;
  bank: string;
  account: string;
  amount: string;
  time: string;
}

interface TransferCardProps {
  prefill?: TransferPrefill;
  /** 주어지면 confirm 모드: 내부 완료 화면 대신 이 콜백을 호출한다(HITL). */
  onConfirm?: (values: TransferConfirmValues) => void;
  onCancel?: () => void;
  submitLabel?: string;
  disabled?: boolean;
}

export type { TransferCardProps, TransferConfirmValues, TransferPrefill };
