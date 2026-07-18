import { type ReactNode } from 'react';

import { AssistantRuntimeProvider } from '@assistant-ui/react';

import { ApproveContext } from '@/features/agent_chat/model/approveContext';
import { SubmitInputContext } from '@/features/agent_chat/model/submitInputContext';
import { useChatRuntime } from '@/features/agent_chat/model/useChatRuntime';

export function AssistantProvider({ children }: { children: ReactNode }) {
  const { runtime, approve, submitInput } = useChatRuntime();
  return (
    <AssistantRuntimeProvider runtime={runtime}>
      <ApproveContext.Provider value={approve}>
        <SubmitInputContext.Provider value={submitInput}>
          {children}
        </SubmitInputContext.Provider>
      </ApproveContext.Provider>
    </AssistantRuntimeProvider>
  );
}
