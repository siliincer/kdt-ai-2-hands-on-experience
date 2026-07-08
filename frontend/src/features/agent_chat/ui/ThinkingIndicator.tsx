import type { EmptyMessagePartComponent } from '@assistant-ui/react';

/**
 * 대기 UX: assistant 메시지가 아직 아무 파트도 못 받은 idle 구간에 표시된다
 * (MessagePrimitive.Parts 의 Empty 슬롯). 첫 이벤트(status 등)가 오면 사라진다.
 */
export const ThinkingIndicator: EmptyMessagePartComponent = () => (
  <div className="flex items-center gap-2 text-sm text-muted-foreground">
    <span className="inline-flex gap-1">
      <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-muted-foreground [animation-delay:-0.3s]" />
      <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-muted-foreground [animation-delay:-0.15s]" />
      <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-muted-foreground" />
    </span>
    🤖 Agent가 생각 중입니다…
  </div>
);
