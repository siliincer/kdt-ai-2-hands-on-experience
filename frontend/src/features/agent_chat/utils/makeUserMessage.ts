import { newId } from './makeNewId';

import type { ChatUiMessage } from '../types/interface';

export function makeUserMessage(text: string): ChatUiMessage {
  return {
    id: newId(),
    role: 'user',
    parts: [{ type: 'text', text }],
    status: 'complete',
  };
}
