// Chat 기능 엔드포인트 및 UI 상수

export const CHAT_URL = '/backendApi/api/v1/chat';
export const APPROVE_URL = '/backendApi/api/v1/agent/approve';

// 빠른 프롬프트 pill(기존 네비게이션 링크 대체) — 클릭 시 자연어 메시지 전송
export const QUICK_PROMPTS: { label: string; prompt: string }[] = [
  { label: '송금하기', prompt: '송금하고 싶어' },
  { label: '잔액 확인', prompt: '내 잔액 알려줘' },
  { label: '소비 분석', prompt: '이번 달 소비 분석해줘' },
  { label: '카드 청구서', prompt: '카드 청구서 보여줘' },
];
