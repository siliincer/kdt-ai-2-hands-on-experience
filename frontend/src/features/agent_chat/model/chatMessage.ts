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
    case 'component': {
      // 읽기전용 카드 렌더 시그널(ADR-002): 데이터는 없고 component 키/params 만.
      // FE 툴 UI 가 UI Data API 로 데이터를 별도 fetch 한다.
      const component = (metadata?.component as string) ?? 'unknown';
      parts.push({
        type: 'tool-call',
        toolCallId: newId(),
        toolName: `render_${component}`,
        argsText: event.content,
        args: (metadata?.params as Record<string, unknown>) ?? {},
      });
      return { ...message, parts };
    }
    case 'need_input': {
      // 일반 입력·선택 대기(UI-HITL 계약 1.4). ui.type 으로 입력 UI 컴포넌트를 라우팅한다.
      // 예: ui.type='account_card_list' → 'input_account_card_list'.
      // 식별자(input_request_id)·ui_contract_id 는 args 에 실어 제출 시 사용한다.
      const ui =
        (metadata?.ui as {
          type?: string;
          payload?: Record<string, unknown>;
        }) ?? {};
      const uiType = ui.type ?? 'input';
      parts.push({
        type: 'tool-call',
        toolCallId: newId(),
        toolName: `input_${uiType}`,
        argsText: event.content,
        args: {
          ...(ui.payload ?? {}),
          ui_contract_id: metadata?.ui_contract_id,
        },
        inputRequestId: (metadata?.input_request_id as string) ?? undefined,
      });
      return { ...message, parts };
    }
    case 'need_approval': {
      // 승인 프롬프트는 진행 tool_call 과 toolName 이 겹치지 않도록 confirm_ 접두사.
      // 예: metadata.tool='transfer' → 'confirm_transfer' (전용 confirm 카드 렌더)
      const tool = (metadata?.tool as string) ?? 'action';
      parts.push({
        type: 'tool-call',
        toolCallId: newId(),
        toolName: `confirm_${tool}`,
        argsText: event.content,
        args: (metadata?.args as Record<string, unknown>) ?? undefined,
        approvalId: event.approval_id ?? undefined,
      });
      return { ...message, parts };
    }
    case 'authentication_required': {
      // 추가 인증 대기(계약 1.4·3.8). auth_request UI 로 라우팅한다.
      // 인증 원문은 FE 가 Backend 인증 API 에 직접 제출하고, auth_context_id 만 회신한다.
      const ui =
        (metadata?.ui as {
          type?: string;
          payload?: Record<string, unknown>;
        }) ?? {};
      parts.push({
        type: 'tool-call',
        toolCallId: newId(),
        toolName: 'auth_request',
        argsText: event.content,
        args: {
          ...(ui.payload ?? {}),
          ui_contract_id: metadata?.ui_contract_id,
        },
        authContextId: (metadata?.auth_context_id as string) ?? undefined,
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
    // 대기 식별자(approvalId/inputRequestId/authContextId)를 args 에 실어
    // 각 툴 UI(render props.args)로 전달한다.
    let toolArgs: Record<string, unknown> = part.args ?? {};
    if (part.approvalId)
      toolArgs = { ...toolArgs, approvalId: part.approvalId };
    if (part.inputRequestId)
      toolArgs = { ...toolArgs, inputRequestId: part.inputRequestId };
    if (part.authContextId)
      toolArgs = { ...toolArgs, authContextId: part.authContextId };
    // 툴 파트에 result 를 채워 "완료"로 표시한다. 그래야 done 으로 메시지가
    // complete 된 뒤에도 렌더된다(미완료 tool-call 은 assistant-ui 가 숨김).
    // 우리 confirm 은 자체 useApprove 로 처리하므로 result 는 표시에만 영향.
    return {
      type: 'tool-call' as const,
      toolCallId: part.toolCallId,
      toolName: part.toolName,
      args: toolArgs,
      argsText: part.argsText,
      result: {},
    };
  });

  return {
    role: 'assistant',
    id: message.id,
    content,
  } as ThreadMessageLike;
}
