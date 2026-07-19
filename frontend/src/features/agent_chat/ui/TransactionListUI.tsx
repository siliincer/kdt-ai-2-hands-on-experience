import type { TransactionItem, TransactionListArgs } from '../types/hitl';
import type { ToolCallMessagePartComponent } from '@assistant-ui/react';

const fmtDate = (iso?: string) => (iso ? iso.slice(0, 10) : '');

/**
 * transaction_list 결과 렌더러 (계약 4.3).
 * ADR C3: 첫 페이지는 SSE inline payload(args)로 온다. 표시명은 transaction_title.
 * 이후 페이지는 transaction_query_id 로 FE·BE 가 처리한다(Agent 재개 없음) — TODO.
 */
export const TransactionListUI: ToolCallMessagePartComponent = ({ args }) => {
  const a = (args ?? {}) as TransactionListArgs;
  const transactions = a.transactions ?? [];
  const period = a.period;

  return (
    <div className="mt-2 rounded-2xl border border-border bg-card p-4">
      <div className="mb-1 flex items-center gap-2">
        <span className="text-lg">🧾</span>
        <p className="text-sm font-semibold text-foreground">거래내역</p>
      </div>
      {period?.start_date && period?.end_date ? (
        <p className="mb-3 text-xs text-muted-foreground">
          {period.start_date} ~ {period.end_date}
        </p>
      ) : null}

      {transactions.length === 0 ? (
        <p className="text-sm text-muted-foreground">거래내역이 없어요.</p>
      ) : (
        <div className="space-y-2">
          {transactions.map((tx: TransactionItem) => {
            const inflow = tx.amount >= 0;
            return (
              <div
                key={tx.transaction_id}
                className="flex items-center justify-between gap-3 border-b py-2 last:border-b-0"
                style={{ borderColor: 'var(--border)' }}
              >
                <div className="min-w-0">
                  <p className="text-sm text-foreground">
                    {tx.transaction_title}
                  </p>
                  <p className="text-[10px] text-muted-foreground">
                    {fmtDate(tx.occurred_at)}
                  </p>
                </div>
                <span
                  className={`text-sm font-medium ${inflow ? 'text-chart-2' : 'text-foreground'}`}
                >
                  {inflow ? '+' : ''}
                  {tx.amount.toLocaleString()}원
                </span>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};
