import { useCallback, useEffect, useRef } from 'react';

import {
  useExternalStoreRuntime,
  type AppendMessage,
} from '@assistant-ui/react';
import { useMutation } from '@tanstack/react-query';

import { useAgentStream } from '@/features/agent_transfer/model/useAgentStream';

import { approveAgentAction } from '../api/approve';
import { authenticateAgentAction } from '../api/authenticate';
import { sendChat } from '../api/sendChat';
import { submitAgentInput } from '../api/submitInput';
import { verifyRecipientCandidate } from '../api/verifyRecipientCandidate';
import { convertMessage } from './chatMessage';
import { useChatStore } from './chatStore';
import { extractText } from '../utils/extractText';

import type { ApprovalDecision, ChatRuntime } from '../types/interface';

/**
 * assistant-ui external store 런타임 + SSE 파이프라인 연결.
 *
 * 상태 분담:
 * - zustand(useChatStore): 실시간 SSE chunk 축적(메시지 상태)
 * - tanstack query(useMutation): 선언적 HTTP(sendChat/approve, pending·error 관리)
 * - useAgentStream: SSE 연결/재연결 소유
 */
export function useChatRuntime(): ChatRuntime {
  const agent = useAgentStream({ maxRetries: 5 });

  const messages = useChatStore((state) => state.messages);
  const runningId = useChatStore((state) => state.runningId);
  const setMessages = useChatStore((state) => state.setMessages);
  const startTurn = useChatStore((state) => state.startTurn);
  const foldIntoRunning = useChatStore((state) => state.foldIntoRunning);
  const failRunning = useChatStore((state) => state.failRunning);
  const reset = useChatStore((state) => state.reset);

  const chatSessionIdRef = useRef<string | null>(null);
  const processedRef = useRef(0);

  // HITL 상호작용 에러는 채팅 UI 안에서 인라인 처리한다. TanStack 전역 기본값
  // (mutations.throwOnError)이 켜져 있어 mutateAsync 를 로컬에서 잡아도 렌더 중
  // 재throw 되어 ErrorBoundary 로 튀므로, 이 mutation 들에서는 명시적으로 끈다.
  const sendMutation = useMutation({
    throwOnError: false,
    mutationFn: (vars: { message: string; chatSessionId: string | null }) =>
      sendChat(vars.message, vars.chatSessionId),
  });
  const approveMutation = useMutation({
    throwOnError: false,
    mutationFn: (vars: {
      chatSessionId: string;
      approvalId: string;
      decision: ApprovalDecision;
      args?: Record<string, unknown>;
      component?: string;
    }) =>
      approveAgentAction(
        vars.chatSessionId,
        vars.approvalId,
        vars.decision,
        vars.args,
        vars.component,
      ),
  });
  const submitInputMutation = useMutation({
    throwOnError: false,
    mutationFn: (vars: {
      chatSessionId: string;
      inputRequestId: string;
      value: Record<string, unknown>;
    }) => submitAgentInput(vars.chatSessionId, vars.inputRequestId, vars.value),
  });
  const authenticateMutation = useMutation({
    throwOnError: false,
    mutationFn: (vars: {
      chatSessionId: string;
      authContextId: string;
      password: string | null;
      cancel?: boolean;
    }) =>
      authenticateAgentAction(
        vars.chatSessionId,
        vars.authContextId,
        vars.password,
        vars.cancel ?? false,
      ),
  });
  const verifyRecipientMutation = useMutation({
    throwOnError: false,
    mutationFn: (vars: {
      chatSessionId: string;
      accountNumber: string;
      bankName?: string | null;
    }) =>
      verifyRecipientCandidate(
        vars.chatSessionId,
        vars.accountNumber,
        vars.bankName,
      ),
  });

  // 로그인 세션마다 깨끗이 시작한다. AssistantProvider 는 로그인 상태에서만 마운트되지만
  // useChatStore 는 모듈 전역 싱글턴이라 로그아웃/언마운트를 넘어 이전 대화가 남는다.
  // 마운트(=새 로그인)마다 스토어·스트림·커서를 리셋해 이전 기록 렌더를 막는다.
  useEffect(() => {
    reset();
    agent.reset();
    chatSessionIdRef.current = null;
    processedRef.current = 0;
    // 마운트 1회만. reset/agent.reset 은 안정적 참조.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // agent 가 바인딩한 세션 id 추적(재연결 시 사용)
  useEffect(() => {
    if (agent.chatSessionId) chatSessionIdRef.current = agent.chatSessionId;
  }, [agent.chatSessionId]);

  // 새 SSE 이벤트를 running assistant 메시지에 fold (zustand 로 축적).
  // running 대상이 없으면 커서를 전진시키지 않는다(소비-후-폐기로 인한 유실 방지).
  useEffect(() => {
    if (!runningId) return;
    if (processedRef.current >= agent.events.length) return;
    const fresh = agent.events.slice(processedRef.current);
    processedRef.current = agent.events.length;
    foldIntoRunning(fresh);
  }, [agent.events, runningId, foldIntoRunning]);

  const onNew = useCallback(
    async (message: AppendMessage) => {
      const text = extractText(message);
      if (!text) return;

      startTurn(text);
      try {
        const { chat_session_id } = await sendMutation.mutateAsync({
          message: text,
          chatSessionId: chatSessionIdRef.current,
        });
        chatSessionIdRef.current = chat_session_id;
        // 이 턴을 위해 스트림 (재)연결(replay-from-last-event-id)
        agent.start(chat_session_id);
      } catch (error) {
        // 전송 실패 시 빈 running 버블을 남기지 않고 에러로 마감한다(롤백).
        // 401 은 customFetch 가 emitUnauthorized → App 이 로그인 화면으로 전환한다.
        const reason =
          error instanceof Error && error.message
            ? error.message
            : '메시지를 보내지 못했어요. 잠시 후 다시 시도해 주세요.';
        failRunning(reason);
      }
    },
    [agent, startTurn, sendMutation, failRunning],
  );

  const approve = useCallback(
    async (
      approvalId: string,
      decision: ApprovalDecision,
      args?: Record<string, unknown>,
      component?: string,
    ) => {
      const chatSessionId = chatSessionIdRef.current;
      if (!chatSessionId) return;
      await approveMutation.mutateAsync({
        chatSessionId,
        approvalId,
        decision,
        args,
        component,
      });
      // 후속 이벤트는 열려 있는 스트림으로 흘러와 현재 메시지에 이어 fold 된다.
    },
    [approveMutation],
  );

  const submitInput = useCallback(
    async (inputRequestId: string, value: Record<string, unknown>) => {
      const chatSessionId = chatSessionIdRef.current;
      if (!chatSessionId) return;
      await submitInputMutation.mutateAsync({
        chatSessionId,
        inputRequestId,
        value,
      });
      // 후속 이벤트는 열려 있는 스트림으로 흘러와 현재 메시지에 이어 fold 된다.
    },
    [submitInputMutation],
  );

  const authenticate = useCallback(
    async (
      authContextId: string,
      password: string,
      options?: { cancel?: boolean },
    ) => {
      const chatSessionId = chatSessionIdRef.current;
      if (!chatSessionId) return 'failed';
      const { auth_status } = await authenticateMutation.mutateAsync({
        chatSessionId,
        authContextId,
        // 취소 시 비밀번호는 무시된다(백엔드가 cancel 로 분기).
        password: options?.cancel ? null : password,
        cancel: options?.cancel ?? false,
      });
      // 후속 이벤트(결과·재인증) 또는 취소 terminal done 이 열린 스트림으로 흘러온다.
      return auth_status;
    },
    [authenticateMutation],
  );

  const verifyRecipient = useCallback(
    async (accountNumber: string, bankName?: string | null) => {
      const chatSessionId = chatSessionIdRef.current;
      if (!chatSessionId) {
        throw new Error('세션이 없어 수취 계좌를 검증할 수 없습니다.');
      }
      const { recipient_candidate_id } =
        await verifyRecipientMutation.mutateAsync({
          chatSessionId,
          accountNumber,
          bankName,
        });
      return recipient_candidate_id;
    },
    [verifyRecipientMutation],
  );

  const isRunning =
    agent.status === 'connecting' ||
    agent.status === 'streaming' ||
    sendMutation.isPending;

  const runtime = useExternalStoreRuntime({
    messages,
    setMessages,
    isRunning,
    onNew,
    convertMessage,
  });

  return { runtime, approve, submitInput, authenticate, verifyRecipient };
}
