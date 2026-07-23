// Chat 기능 엔드포인트 및 UI 상수

export const CHAT_URL = '/backendApi/api/v1/chat';
export const APPROVE_URL = '/backendApi/api/v1/agent/approve';
export const AGENT_INPUT_URL = '/backendApi/api/v1/agent/input';
export const AGENT_AUTHENTICATE_URL = '/backendApi/api/v1/agent/authenticate';
// 신규 수취 계좌 검증(FE 전용) — 원문 계좌번호는 이 API 까지만 도달하고
// 응답으로 recipient_candidate_id 참조를 받는다(계약 부록 29.2).
export const RECIPIENT_CANDIDATE_VERIFY_URL =
  '/backendApi/api/v1/recipient-candidates:verify';

// UI Data API (BFF) — component 시그널 이후 카드 데이터 조회(ADR-002)
export const UI_BALANCE_URL = '/backendApi/api/v1/ui/balance';
export const UI_SPENDING_URL = '/backendApi/api/v1/ui/spending';
export const UI_TRANSACTIONS_URL = '/backendApi/api/v1/ui/transactions';
export const UI_BUDGET_URL = '/backendApi/api/v1/ui/budget';
export const UI_CARDS_URL = '/backendApi/api/v1/ui/cards';

// 빠른 프롬프트 pill(기존 네비게이션 링크 대체) — 클릭 시 자연어 메시지 전송
// TODO(FE): agent workflow 기능 추가에 따라 추가
export const QUICK_PROMPTS: { label: string; prompt: string }[] = [
  // "송금하고 싶어" 는 타인송금/본인이체 양쪽으로 해석돼 모호하므로, 타인송금으로
  // 확정 라우팅되도록 "다른 사람에게"(에게+송금 키워드)로 명시한다.
  { label: '송금하기', prompt: '다른 사람에게 송금하고 싶어' },
  { label: '잔액 확인', prompt: '내 잔액 알려줘' },
  { label: '소비 분석', prompt: '이번 달 소비 분석해줘' },
  { label: '카드 청구서', prompt: '카드 청구서 보여줘' },
];
