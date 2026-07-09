import type { BalanceData } from '@/shared/types/ui';

interface BalanceCardProps {
  data: BalanceData;
  /** 카드 내 액션 → 자연어 프롬프트 전송(라우팅 대신 chat 흐름). */
  onPrompt?: (text: string) => void;
}

export type { BalanceCardProps };
