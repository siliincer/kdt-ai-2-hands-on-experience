import { type ReactNode } from 'react';

import { AssistantRuntimeProvider } from '@assistant-ui/react';

import { ApproveContext } from '@/features/agent_chat/model/approveContext';
import { useChatRuntime } from '@/features/agent_chat/model/useChatRuntime';

export function AssistantProvider({ children }: { children: ReactNode }) {
  const { runtime, approve } = useChatRuntime();
  return (
    <AssistantRuntimeProvider runtime={runtime}>
      <ApproveContext.Provider value={approve}>
        {children}
      </ApproveContext.Provider>
    </AssistantRuntimeProvider>
  );
}
