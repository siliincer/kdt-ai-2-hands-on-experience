import { useRef, useState } from 'react';

import {
  MessagePrimitive,
  ThreadPrimitive,
  useThread,
  useThreadRuntime,
} from '@assistant-ui/react';
import { LogOut, Moon, Send, SunMedium } from 'lucide-react';
import TextareaAutosize from 'react-textarea-autosize';

import { QUICK_PROMPTS } from '@/features/agent_chat/constants/constants';
import { TOOL_UI_REGISTRY } from '@/features/agent_chat/ui/componentRegistry';
import {
  MessageText,
  ReasoningBlock,
  ToolProgressChip,
} from '@/features/agent_chat/ui/messageParts';
import { logoutApi, useUserStore } from '@/entities/user';
import { useTheme } from '@/shared/hooks/useTheme';

const ASSISTANT_PART_COMPONENTS = {
  Text: MessageText,
  Reasoning: ReasoningBlock,
  tools: {
    by_name: TOOL_UI_REGISTRY,
    Fallback: ToolProgressChip,
  },
};

function UserMessage() {
  return (
    <MessagePrimitive.Root className="mb-4 flex justify-end">
      <div className="max-w-[80%] rounded-2xl bg-primary px-4 py-2 text-sm text-primary-foreground">
        <MessagePrimitive.Parts />
      </div>
    </MessagePrimitive.Root>
  );
}

function AssistantMessage() {
  return (
    <MessagePrimitive.Root className="mb-4 flex justify-start">
      {/* 카드(툴 UI)가 넓게 보이도록 사용자 말풍선 직전까지 폭 확장 */}
      <div className="w-full max-w-[92%] rounded-2xl border border-border bg-card px-4 py-2 text-sm text-foreground">
        {/* tool-call 로 끝나는 메시지(confirm 카드 등) 뒤에 붙던 "생각 중" 슬롯 비활성화 */}
        <MessagePrimitive.Parts
          components={ASSISTANT_PART_COMPONENTS}
          unstable_showEmptyOnNonTextEnd={false}
        />
      </div>
    </MessagePrimitive.Root>
  );
}

function ChatHeader() {
  const { theme, toggleTheme } = useTheme();
  const logout = useUserStore((state) => state.logout);
  const userName = useUserStore((state) => state.user?.name);
  const [isLoggingOut, setIsLoggingOut] = useState(false);

  const handleLogout = async () => {
    if (isLoggingOut) return;
    setIsLoggingOut(true);
    try {
      await logoutApi();
    } catch {
      // 세션 정리는 실패해도 진행
    } finally {
      logout();
      setIsLoggingOut(false);
    }
  };

  return (
    <header className="flex items-center justify-between border-b border-border px-4 py-3">
      <div className="flex items-center gap-2">
        <span className="text-lg">🤖</span>
        <span className="font-semibold text-foreground">RealFinance</span>
      </div>
      <div className="flex items-center gap-2">
        {userName ? (
          <span className="hidden text-sm text-muted-foreground sm:inline">
            {userName}님
          </span>
        ) : null}
        <button
          type="button"
          onClick={toggleTheme}
          className="inline-flex h-9 items-center justify-center rounded-full border border-border px-3 text-foreground"
        >
          {theme === 'dark' ? (
            <SunMedium className="h-4 w-4" />
          ) : (
            <Moon className="h-4 w-4" />
          )}
        </button>
        <button
          type="button"
          onClick={handleLogout}
          disabled={isLoggingOut}
          className="inline-flex items-center gap-1.5 rounded-full border border-border px-3 py-1.5 text-sm text-foreground"
        >
          <LogOut className="h-4 w-4" />
          {isLoggingOut ? '로그아웃 중...' : '로그아웃'}
        </button>
      </div>
    </header>
  );
}

function EmptyState() {
  return (
    <ThreadPrimitive.Empty>
      <div className="flex flex-col items-start gap-3 rounded-2xl border border-border bg-card px-4 py-5">
        <p className="text-sm font-medium text-foreground">
          안녕하세요! 무엇을 도와드릴까요?
        </p>
        <div className="flex flex-wrap gap-2">
          {QUICK_PROMPTS.map((item) => (
            <ThreadPrimitive.Suggestion
              key={item.label}
              prompt={item.prompt}
              method="replace"
              autoSend
              className="rounded-full border border-accent px-3 py-1.5 text-sm text-accent-foreground hover:bg-accent/10"
            >
              {item.label}
            </ThreadPrimitive.Suggestion>
          ))}
        </div>
      </div>
    </ThreadPrimitive.Empty>
  );
}

/**
 * 커스텀 컴포저(TextareaAutosize 기반).
 * - Enter=전송, Shift+Enter=줄바꿈.
 * - IME(한글/일본어 등) 조합 중 Enter 는 무시 → 조합 확정용 중복 Enter 로 인한 오전송/포커스 깨짐 방지.
 * - 입력창은 minRows=1 에서 내용에 맞춰 늘다가 max-h(≈maxRows)에서 내부 스크롤.
 * - 전송/Enter 는 **AI 렌더링 중(isRunning)에만 비활성화**(글자 수와 무관) → 답변을 하나씩 처리하도록 유도.
 */
function Composer() {
  const thread = useThreadRuntime();
  const isRunning = useThread((state) => state.isRunning);
  const [text, setText] = useState('');
  const isComposingRef = useRef(false);

  const send = () => {
    const trimmed = text.trim();
    if (!trimmed || isRunning) return;
    thread.append(trimmed);
    setText('');
  };

  const handleKeyDown = (event: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key !== 'Enter' || event.shiftKey) return;
    // IME 조합 중이면 전송하지 않는다(조합 확정 Enter 와 전송 Enter 분리).
    if (
      event.nativeEvent.isComposing ||
      event.nativeEvent.keyCode === 229 ||
      isComposingRef.current
    ) {
      return;
    }
    event.preventDefault();
    send();
  };

  return (
    <div className="flex items-end gap-2 border-t border-border px-4 py-3">
      <TextareaAutosize
        value={text}
        onChange={(event) => setText(event.target.value)}
        onKeyDown={handleKeyDown}
        onCompositionStart={() => {
          isComposingRef.current = true;
        }}
        onCompositionEnd={() => {
          isComposingRef.current = false;
        }}
        autoFocus
        minRows={1}
        maxRows={6}
        placeholder="무엇이든 물어보세요 (예: 이성한 신한 110 222 221 111)"
        className="max-h-40 flex-1 resize-none overflow-y-auto rounded-2xl border border-border bg-input-background px-4 py-2 text-sm text-foreground outline-none placeholder:text-muted-foreground"
      />
      <button
        type="button"
        onClick={send}
        disabled={isRunning}
        aria-label="전송"
        className="inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-muted text-foreground transition-opacity disabled:opacity-50"
      >
        <Send className="h-4 w-4" />
      </button>
    </div>
  );
}

export default function ChatThread() {
  return (
    <ThreadPrimitive.Root className="mx-auto flex h-dvh w-full max-w-2xl flex-col overflow-hidden border border-border bg-background">
      <ChatHeader />
      <ThreadPrimitive.Viewport className="flex-1 overflow-y-auto px-4 py-4">
        <EmptyState />
        <ThreadPrimitive.Messages
          components={{
            UserMessage,
            AssistantMessage,
          }}
        />
      </ThreadPrimitive.Viewport>
      <Composer />
    </ThreadPrimitive.Root>
  );
}
