import { create } from 'zustand';
import { foldEvent } from './chatMessage';
import { makeRunningAssistant } from '@/features/agent_chat/utils/makeRunningAssistant';
import { makeUserMessage } from '@/features/agent_chat/utils/makeUserMessage';

import type { ChatState } from '../types/interface';

/**
 * 실시간 SSE chunk 축적용 zustand 스토어.
 *
 * 역할 분리: zustand 는 ms 단위로 쏟아지는 스트림 chunk 를 렌더 트리 밖에서
 * 축적하는 데 유리하고(구독 컴포넌트만 리렌더), tanstack query 는 선언적 HTTP
 * (sendChat/approve mutation)를 담당한다. external store 런타임이 이 messages 를 읽는다.
 */
export const useChatStore = create<ChatState>((set) => ({
  messages: [],
  runningId: null,

  setMessages: (messages) => set({ messages: [...messages] }),

  startTurn: (userText) => {
    const user = makeUserMessage(userText);
    const assistant = makeRunningAssistant();
    set((state) => ({
      messages: [...state.messages, user, assistant],
      runningId: assistant.id,
    }));
  },

  foldIntoRunning: (events) =>
    set((state) => {
      const targetId = state.runningId;
      if (!targetId) return state;
      return {
        messages: state.messages.map((message) => {
          if (message.id !== targetId) return message;
          let next = message;
          for (const event of events) next = foldEvent(next, event);
          return next;
        }),
      };
    }),

  reset: () => set({ messages: [], runningId: null }),
}));
