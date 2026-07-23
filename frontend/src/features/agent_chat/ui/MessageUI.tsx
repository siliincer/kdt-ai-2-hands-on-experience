import { AlertTriangle, Ban, Info } from 'lucide-react';

import type { MessageArgs } from '../types/hitl';
import type { ToolCallMessagePartComponent } from '@assistant-ui/react';

/**
 * 안내(message)·오류(error_message)·차단(blocked_message) 결과 렌더러 (계약 2.2).
 * 사용자 회신을 기다리지 않는 결과·안내 UI. 텍스트는 args(params) 또는 argsText 로 온다.
 * 대부분의 mock 흐름은 status/token/error 텍스트로 처리하고, 이 컴포넌트는 실 Agent 가
 * render_message/render_error_message/render_blocked_message 를 낼 때 렌더된다.
 */

function messageText(args: unknown, argsText?: string): string {
  const a = (args ?? {}) as MessageArgs;
  return a.message ?? a.content ?? a.title ?? argsText ?? '';
}

export const MessageUI: ToolCallMessagePartComponent = ({ args, argsText }) => (
  <div className="mt-2 flex items-start gap-2 rounded-2xl border border-border bg-card p-4">
    <Info className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" />
    <p className="text-sm text-foreground">{messageText(args, argsText)}</p>
  </div>
);

export const ErrorMessageUI: ToolCallMessagePartComponent = ({
  args,
  argsText,
}) => (
  <div className="mt-2 flex items-start gap-2 rounded-2xl border border-destructive/40 bg-destructive/5 p-4">
    <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-destructive" />
    <p className="text-sm text-foreground">{messageText(args, argsText)}</p>
  </div>
);

export const BlockedMessageUI: ToolCallMessagePartComponent = ({
  args,
  argsText,
}) => {
  const a = (args ?? {}) as MessageArgs;
  return (
    <div className="mt-2 flex items-start gap-2 rounded-2xl border border-border bg-muted/40 p-4">
      <Ban className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" />
      <div className="flex flex-col gap-1">
        <p className="text-sm text-foreground">{messageText(args, argsText)}</p>
        {a.description ? (
          <p className="text-xs text-muted-foreground">{a.description}</p>
        ) : null}
      </div>
    </div>
  );
};
