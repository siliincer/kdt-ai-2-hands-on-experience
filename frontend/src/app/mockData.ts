export type Account = {
  id: number;
  name: string;
  bank: string;
  balance: number;
  badge: string;
};

export type QuickAction = {
  label: string;
  description: string;
  accent: string;
};

export type Insight = {
  title: string;
  value: string;
  tone: string;
};

export type Transaction = {
  id: number;
  title: string;
  date: string;
  amount: number;
  type: 'income' | 'expense';
  note: string;
};

export const accounts: Account[] = [
  {
    id: 1,
    name: '입출금통장',
    bank: '신한은행',
    balance: 8240000,
    badge: '자유입출금',
  },
  {
    id: 2,
    name: '저축예금',
    bank: '카카오뱅크',
    balance: 1540000,
    badge: '자동이체',
  },
  {
    id: 3,
    name: '카드청구',
    bank: '하나카드',
    balance: 380000,
    badge: '이번 달 결제',
  },
];

export const quickActions: QuickAction[] = [
  {
    label: '송금하기',
    description: '지금 바로 받는 사람에게 송금해보세요.',
    accent: 'from-emerald-400 to-emerald-500',
  },
  {
    label: '지출분석',
    description: '카테고리별 소비 패턴을 확인해보세요.',
    accent: 'from-sky-400 to-sky-500',
  },
  {
    label: '자동이체',
    description: '반복 지출을 한 번에 관리할 수 있어요.',
    accent: 'from-violet-400 to-violet-500',
  },
];

export const insights: Insight[] = [
  {
    title: '이번 주 지출',
    value: '약 128만원',
    tone: '소비가 늘어났어요.',
  },
  {
    title: '저축률',
    value: '42%',
    tone: '목표치에 가까워지고 있어요.',
  },
  {
    title: '자동이체',
    value: '7건',
    tone: '정리된 상태입니다.',
  },
];

export const recentTransactions: Transaction[] = [
  {
    id: 101,
    title: '급여 입금',
    date: '오늘 09:20',
    amount: 3200000,
    type: 'income',
    note: '6월 급여',
  },
  {
    id: 102,
    title: '스타벅스',
    date: '오늘 08:10',
    amount: -7800,
    type: 'expense',
    note: '아메리카노 구매',
  },
  {
    id: 103,
    title: '월세 이체',
    date: '어제 00:00',
    amount: -550000,
    type: 'expense',
    note: '6월 월세',
  },
  {
    id: 104,
    title: '카카오페이 환불',
    date: '어제 19:40',
    amount: 15000,
    type: 'income',
    note: '환불 완료',
  },
];
