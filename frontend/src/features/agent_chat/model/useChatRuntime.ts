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
  const setMessages = useChatStore((state) => state.setMessages);
  const startTurn = useChatStore((state) => state.startTurn);
  const foldIntoRunning = useChatStore((state) => state.foldIntoRunning);

  const chatSessionIdRef = useRef<string | null>(null);
  const processedRef = useRef(0);

  const sendMutation = useMutation({
    mutationFn: (vars: { message: string; chatSessionId: string | null }) =>
      sendChat(vars.message, vars.chatSessionId),
  });
  const approveMutation = useMutation({
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
    mutationFn: (vars: {
      chatSessionId: string;
      inputRequestId: string;
      value: Record<string, unknown>;
    }) => submitAgentInput(vars.chatSessionId, vars.inputRequestId, vars.value),
  });
  const authenticateMutation = useMutation({
    mutationFn: (vars: {
      chatSessionId: string;
      authContextId: string;
      password: string;
    }) =>
      authenticateAgentAction(
        vars.chatSessionId,
        vars.authContextId,
        vars.password,
      ),
  });
  const verifyRecipientMutation = useMutation({
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

  // agent 가 바인딩한 세션 id 추적(재연결 시 사용)
  useEffect(() => {
    if (agent.chatSessionId) chatSessionIdRef.current = agent.chatSessionId;
  }, [agent.chatSessionId]);

  // 새 SSE 이벤트를 running assistant 메시지에 fold (zustand 로 축적)
  useEffect(() => {
    if (processedRef.current >= agent.events.length) return;
    const fresh = agent.events.slice(processedRef.current);
    processedRef.current = agent.events.length;
    foldIntoRunning(fresh);
  }, [agent.events, foldIntoRunning]);

  const onNew = useCallback(
    async (message: AppendMessage) => {
      const text = extractText(message);
      if (!text) return;

      startTurn(text);
      const { chat_session_id } = await sendMutation.mutateAsync({
        message: text,
        chatSessionId: chatSessionIdRef.current,
      });
      chatSessionIdRef.current = chat_session_id;
      // 이 턴을 위해 스트림 (재)연결(replay-from-last-event-id)
      agent.start(chat_session_id);
    },
    [agent, startTurn, sendMutation],
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
    async (authContextId: string, password: string) => {
      const chatSessionId = chatSessionIdRef.current;
      if (!chatSessionId) return 'failed';
      const { auth_status } = await authenticateMutation.mutateAsync({
        chatSessionId,
        authContextId,
        password,
      });
      // 후속 이벤트(결과 또는 재인증)는 열려 있는 스트림으로 흘러온다.
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
