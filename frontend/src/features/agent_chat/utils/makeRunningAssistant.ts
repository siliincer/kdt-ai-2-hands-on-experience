import { newId } from './makeNewId';

import type { ChatUiMessage } from '../types/interface';

export function makeRunningAssistant(): ChatUiMessage {
  return { id: newId(), role: 'assistant', parts: [], status: 'running' };
}
