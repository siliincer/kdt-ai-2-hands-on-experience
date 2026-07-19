import { HITL_CARD } from './uiStyles';

import type { AccountListArgs, AccountListItem } from '../types/hitl';
import type { ToolCallMessagePartComponent } from '@assistant-ui/react';

/**
 * account_list 결과 렌더러 (계약 4.1).
 * ADR C3: 데이터는 SSE inline payload(args)로 온다. 잔액·전체 계좌번호는 없다.
 */
export const AccountListUI: ToolCallMessagePartComponent = ({ args }) => {
  const a = (args ?? {}) as AccountListArgs;
  const accounts = a.accounts ?? [];

  return (
    <div className={HITL_CARD}>
      <div className="mb-3 flex items-center gap-2">
        <span className="text-lg">🏦</span>
        <p className="text-sm font-semibold text-foreground">내 계좌 목록</p>
      </div>

      {accounts.length === 0 ? (
        <p className="text-sm text-muted-foreground">계좌가 없어요.</p>
      ) : (
        <div className="space-y-2">
          {accounts.map((account: AccountListItem) => (
            <div
              key={account.account_id}
              className="rounded-2xl border border-border p-3"
            >
              <div className="flex items-center gap-2">
                <span className="text-sm font-medium text-foreground">
                  {account.account_alias || account.bank_name}
                </span>
                {account.is_default ? (
                  <span className="rounded-full border border-border bg-secondary px-2 py-0.5 text-[10px] text-secondary-foreground">
                    기본
                  </span>
                ) : null}
              </div>
              <p className="mt-0.5 text-xs text-muted-foreground">
                {account.bank_name} · {account.masked_account_number}
              </p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};
