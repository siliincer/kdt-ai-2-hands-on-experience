import type { ThreadMessageLike } from '@assistant-ui/react';

import type { AgentStreamEvent } from '@/shared/types/sse';

import type {
  ChatReasoningPart,
  ChatTextPart,
  ChatUiMessage,
} from '../types/interface';

import { newId } from '../utils/makeNewId';

/**
 * SSE 이벤트 하나를 현재 assistant 메시지에 접어 넣는다(불변 갱신).
 * onNew 가 만든 running assistant 메시지에만 적용된다.
 */
export function foldEvent(
  message: ChatUiMessage,
  event: AgentStreamEvent,
): ChatUiMessage {
  const parts = [...message.parts];
  const metadata = event.metadata ?? undefined;

  switch (event.event_type) {
    case 'token': {
      const last = parts[parts.length - 1];
      if (last && last.type === 'text') {
        parts[parts.length - 1] = { ...last, text: last.text + event.content };
      } else {
        parts.push({ type: 'text', text: event.content });
      }
      return { ...message, parts };
    }
    case 'status': {
      const idx = parts.findIndex((p) => p.type === 'reasoning');
      if (idx >= 0) {
        const prev = parts[idx] as ChatReasoningPart;
        parts[idx] = { ...prev, text: `${prev.text}\n${event.content}` };
      } else {
        parts.push({ type: 'reasoning', text: event.content });
      }
      return { ...message, parts };
    }
    case 'tool_call': {
      parts.push({
        type: 'tool-call',
        toolCallId: newId(),
        toolName: (metadata?.tool as string) ?? 'tool',
        argsText: event.content,
        args: metadata,
      });
      return { ...message, parts };
    }
    case 'need_approval': {
      parts.push({
        type: 'tool-call',
        toolCallId: newId(),
        toolName: (metadata?.tool as string) ?? 'confirm',
        argsText: event.content,
        args: (metadata?.args as Record<string, unknown>) ?? undefined,
        approvalId: event.approval_id ?? undefined,
      });
      return { ...message, parts };
    }
    case 'error': {
      parts.push({ type: 'text', text: event.content });
      return { ...message, parts, status: 'error' };
    }
    case 'done': {
      if (event.content) parts.push({ type: 'text', text: event.content });
      return { ...message, parts, status: 'complete' };
    }
    default:
      return message;
  }
}

/** ChatUiMessage → assistant-ui ThreadMessageLike */
export function convertMessage(message: ChatUiMessage): ThreadMessageLike {
  if (message.role === 'user') {
    const text = message.parts
      .filter((p): p is ChatTextPart => p.type === 'text')
      .map((p) => p.text)
      .join('');
    return { role: 'user', id: message.id, content: [{ type: 'text', text }] };
  }

  const content = message.parts.map((part) => {
    if (part.type === 'text') {
      return { type: 'text' as const, text: part.text };
    }
    if (part.type === 'reasoning') {
      return { type: 'reasoning' as const, text: part.text };
    }
    return {
      type: 'tool-call' as const,
      toolCallId: part.toolCallId,
      toolName: part.toolName,
      args: part.args ?? {},
      argsText: part.argsText,
    };
  });

  return {
    role: 'assistant',
    id: message.id,
    content,
  } as ThreadMessageLike;
}
