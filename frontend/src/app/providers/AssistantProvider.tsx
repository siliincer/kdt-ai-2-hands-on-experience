import { type ReactNode } from 'react';

import { AssistantRuntimeProvider } from '@assistant-ui/react';

import { ApproveContext } from '@/features/agent_chat/model/approveContext';
import { AuthenticateContext } from '@/features/agent_chat/model/authenticateContext';
import { RecipientVerifyContext } from '@/features/agent_chat/model/recipientVerifyContext';
import { SubmitInputContext } from '@/features/agent_chat/model/submitInputContext';
import { useChatRuntime } from '@/features/agent_chat/model/useChatRuntime';

export function AssistantProvider({ children }: { children: ReactNode }) {
  const { runtime, approve, submitInput, authenticate, verifyRecipient } =
    useChatRuntime();
  return (
    <AssistantRuntimeProvider runtime={runtime}>
      <ApproveContext.Provider value={approve}>
        <SubmitInputContext.Provider value={submitInput}>
          <AuthenticateContext.Provider value={authenticate}>
            <RecipientVerifyContext.Provider value={verifyRecipient}>
              {children}
            </RecipientVerifyContext.Provider>
          </AuthenticateContext.Provider>
        </SubmitInputContext.Provider>
      </ApproveContext.Provider>
    </AssistantRuntimeProvider>
  );
}
