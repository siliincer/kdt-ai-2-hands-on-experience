import { Wrench } from 'lucide-react';

import { ThinkingIndicator } from './ThinkingIndicator';

import type {
  ReasoningMessagePartComponent,
  TextMessagePartComponent,
  ToolCallMessagePartComponent,
} from '@assistant-ui/react';

/**
 * 텍스트 파트. 빈 텍스트(= assistant-ui 의 empty-running 플레이스홀더)일 때는
 * "생각 중" 인디케이터를 보여준다(응답 대기 UX). 실제 토큰이 오면 텍스트로 대체.
 */
export const MessageText: TextMessagePartComponent = ({ text }) =>
  text ? (
    <p className="whitespace-pre-wrap text-sm leading-relaxed">{text}</p>
  ) : (
    <ThinkingIndicator />
  );

/** status 이벤트 → 접이식 느낌의 "진행 상황" 블록 (기본은 hidden 이라 override) */
export const ReasoningBlock: ReasoningMessagePartComponent = ({ text }) => {
  if (!text) return null;
  return (
    <div className="my-1 rounded-lg border border-border/60 bg-muted/40 px-3 py-2 text-xs text-muted-foreground">
      <p className="mb-1 font-medium">진행 상황</p>
      <p className="whitespace-pre-wrap leading-relaxed">{text}</p>
    </div>
  );
};

/** tool_call(진행) → 작은 칩. confirm_* 는 by_name 에서 처리되므로 여기 안 옴 */
export const ToolProgressChip: ToolCallMessagePartComponent = ({
  argsText,
  status,
}) => {
  const running = status?.type === 'running';
  return (
    <div className="my-1 inline-flex items-center gap-2 rounded-full border border-border/60 bg-muted/40 px-3 py-1.5 text-xs text-muted-foreground">
      <Wrench className={`h-3.5 w-3.5 ${running ? 'animate-pulse' : ''}`} />
      <span>{argsText || '도구 실행 중...'}</span>
    </div>
  );
};
