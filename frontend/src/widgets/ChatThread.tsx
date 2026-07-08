import { useState } from 'react';

import {
  ComposerPrimitive,
  MessagePrimitive,
  ThreadPrimitive,
} from '@assistant-ui/react';
import { LogOut, Moon, Send, SunMedium } from 'lucide-react';

import { QUICK_PROMPTS } from '@/features/agent_chat/constants/constants';
import { ConfirmTransferToolUI } from '@/features/agent_chat/ui/ConfirmTransferToolUI';
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
    by_name: { confirm_transfer: ConfirmTransferToolUI },
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
      <div className="max-w-[85%] rounded-2xl border border-border bg-card px-4 py-2 text-sm text-foreground">
        <MessagePrimitive.Parts components={ASSISTANT_PART_COMPONENTS} />
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

function Composer() {
  return (
    <ComposerPrimitive.Root className="flex items-center gap-2 border-t border-border px-4 py-3">
      <ComposerPrimitive.Input
        rows={1}
        autoFocus
        placeholder="무엇이든 물어보세요 (예: 이성한 신한 110 222 221 111)"
        className="flex-1 resize-none rounded-full border border-border bg-input-background px-4 py-2 text-sm text-foreground outline-none placeholder:text-muted-foreground"
      />
      <ComposerPrimitive.Send className="inline-flex h-10 w-10 items-center justify-center rounded-full bg-muted text-foreground">
        <Send className="h-4 w-4" />
      </ComposerPrimitive.Send>
    </ComposerPrimitive.Root>
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
