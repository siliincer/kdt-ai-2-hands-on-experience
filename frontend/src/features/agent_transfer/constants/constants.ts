import type { AgentStreamEventType } from '@/shared/types/sse';

const CONNECT_URL = '/backendApi/api/v1/sse/connect';

// 백엔드가 event: 필드로 보내는 이름들(raw "[DONE]" sentinel 도 event:done 으로 옴)
const NAMED_EVENTS: AgentStreamEventType[] = [
  'status',
  'token',
  'tool_call',
  'need_approval',
  'done',
  'error',
];

export { CONNECT_URL, NAMED_EVENTS };
