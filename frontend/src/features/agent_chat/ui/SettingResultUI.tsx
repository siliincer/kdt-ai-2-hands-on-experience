import { Check } from 'lucide-react';

import { joinParts } from '../utils/format';

import { HITL_CARD } from './uiStyles';

import type { SettingResultArgs } from '../types/hitl';
import type { ToolCallMessagePartComponent } from '@assistant-ui/react';

const PURPOSE_LABEL: Record<string, string> = {
  account_alias: '계좌 별칭 변경',
  default_account: '기본 계좌 변경',
};

/**
 * setting_result 결과 렌더러 (계약 4.6).
 * ADR C3: 데이터는 SSE inline payload(args)로 온다(별도 fetch 없음).
 * 기본계좌·계좌 별칭 변경 완료(또는 변경 없음)를 표시한다.
 */
export const SettingResultUI: ToolCallMessagePartComponent = ({ args }) => {
  const a = (args ?? {}) as SettingResultArgs;
  const title = PURPOSE_LABEL[a.purpose ?? ''] ?? '설정 변경';
  const unchanged = a.outcome === 'unchanged';

  return (
    <div className={HITL_CARD}>
      <div className="mb-3 flex items-center gap-2">
        <span className="flex h-6 w-6 items-center justify-center rounded-full bg-chart-2/15 text-chart-2">
          <Check className="h-4 w-4" />
        </span>
        <p className="text-sm font-semibold text-foreground">
          {title} {unchanged ? '변경 없음' : '완료'}
        </p>
      </div>

      <div className="space-y-2 rounded-2xl border border-border p-3">
        {a.account?.masked_account_number ? (
          <div className="flex items-center justify-between gap-3">
            <span className="text-xs text-muted-foreground">계좌</span>
            <span className="text-sm text-foreground">
              {joinParts(
                a.account.account_alias ?? a.account.bank_name,
                a.account.masked_account_number,
              )}
            </span>
          </div>
        ) : null}
        {a.alias ? (
          <div className="flex items-center justify-between gap-3">
            <span className="text-xs text-muted-foreground">새 별칭</span>
            <span className="text-sm font-medium text-foreground">
              {a.alias}
            </span>
          </div>
        ) : null}
      </div>
    </div>
  );
};
