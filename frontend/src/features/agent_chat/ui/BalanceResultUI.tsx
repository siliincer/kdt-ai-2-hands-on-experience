import { won } from '../utils/format';

import { HITL_CARD } from './uiStyles';

import type { BalanceResultArgs, BalanceResultItem } from '../types/hitl';
import type { ToolCallMessagePartComponent } from '@assistant-ui/react';

/**
 * balance_result 결과 렌더러 (계약 4.2).
 * ADR C3: 데이터는 SSE inline payload(args)로 오므로 별도 fetch 하지 않는다.
 * 계좌별 잔액과 출금 가능 금액을 표시한다(Agent 는 계산하지 않음).
 */
export const BalanceResultUI: ToolCallMessagePartComponent = ({ args }) => {
  const a = (args ?? {}) as BalanceResultArgs;
  const accounts = a.accounts ?? [];

  return (
    <div className={HITL_CARD}>
      <div className="mb-3 flex items-center gap-2">
        <span className="text-lg">💳</span>
        <p className="text-sm font-semibold text-foreground">잔액 조회 결과</p>
      </div>

      {accounts.length === 0 ? (
        <p className="text-sm text-muted-foreground">표시할 잔액이 없어요.</p>
      ) : (
        <div className="space-y-3">
          {accounts.map((account: BalanceResultItem) => (
            <div
              key={account.account_id}
              className="rounded-2xl border border-border p-3"
            >
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <p className="text-xs font-medium text-foreground">
                    {account.account_alias || account.masked_account_number}
                  </p>
                  <p className="mt-0.5 text-[10px] text-muted-foreground">
                    {account.masked_account_number}
                  </p>
                </div>
                <div className="text-right">
                  <p className="text-sm font-bold text-foreground">
                    {won(account.balance)}
                  </p>
                  <p className="mt-0.5 text-[10px] text-muted-foreground">
                    출금 가능 {won(account.available_amount)}
                  </p>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};
