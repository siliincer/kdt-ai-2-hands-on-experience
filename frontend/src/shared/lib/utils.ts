import { BANKS, BANK_KOR } from '@/features/mockData/mockData';
import type { TxItem } from '@/shared/types/interface';

function kor(n: number): string {
  if (!n) return '';
  const digits = ['', '일', '이', '삼', '사', '오', '육', '칠', '팔', '구'];
  const units = ['', '십', '백', '천'];
  const scales = ['', '만', '억', '조'];

  const chunk = (value: number) => {
    let str = '';
    for (let i = 3; i >= 0; i -= 1) {
      const digit = Math.floor(value / 10 ** i) % 10;
      if (!digit) continue;
      str += `${digit === 1 && i > 0 ? '' : digits[digit]}${units[i]}`;
    }
    return str;
  };

  let result = '';
  let remainder = n;
  let scale = 0;

  while (remainder > 0) {
    const part = remainder % 10000;
    if (part) result = `${chunk(part)}${scales[scale]}${result}`;
    remainder = Math.floor(remainder / 10000);
    scale += 1;
  }

  return `${result}원`;
}

const fmtAmt = (raw: string) => (raw ? Number(raw).toLocaleString() : '');
const parseAmtInput = (value: string) =>
  value
    .replace(/,/g, '')
    .replace(/[^0-9]/g, '')
    .replace(/^0+(?!$)/, '');

function formatScheduled(dt: string) {
  const date = new Date(dt);
  const now = new Date();
  const tomorrow = new Date(now);
  tomorrow.setDate(tomorrow.getDate() + 1);

  const dayLabel =
    date.toDateString() === now.toDateString()
      ? '오늘'
      : date.toDateString() === tomorrow.toDateString()
        ? '내일'
        : `${date.getMonth() + 1}월 ${date.getDate()}일`;

  const hours = date.getHours();
  const ampm = hours < 12 ? '오전' : '오후';
  const hour = hours === 0 ? 12 : hours > 12 ? hours - 12 : hours;
  const minute = date.getMinutes();

  return `${dayLabel} ${ampm} ${hour}시${minute > 0 ? ` ${minute}분` : ''}`;
}

function parseContactText(text: string) {
  const result: { name?: string; bank?: string; account?: string } = {};
  const sortedBanks = [...BANKS].sort((a, b) => b.length - a.length);

  for (const bank of sortedBanks) {
    if (text.includes(bank)) {
      result.bank = BANK_KOR[bank] || bank;
      break;
    }
  }

  const accountMatch = text.match(/\d[\d\s-]{9,}\d/);
  if (accountMatch) {
    result.account = accountMatch[0]
      .trim()
      .replace(/\s+/g, '-')
      .replace(/-{2,}/g, '-');
  }

  const bankNames = BANKS.flatMap((bank) => bank.match(/[가-힣]+/g) || []);
  const nameMatch = (text.match(/[가-힣]{2,4}/g) || []).find(
    (word) =>
      !bankNames.some(
        (bankName) => bankName === word || bankName.includes(word),
      ),
  );
  if (nameMatch) result.name = nameMatch;

  return result;
}

function formatCurrency(value: number) {
  return new Intl.NumberFormat('ko-KR', {
    style: 'currency',
    currency: 'KRW',
    maximumFractionDigits: 0,
  }).format(value);
}

function detectRecurring(transactions: TxItem[]) {
  const groups: Record<string, Set<string>> = {};
  transactions
    .filter((tx) => tx.type === 'out')
    .forEach((tx) => {
      const key = `${tx.name}__${Math.abs(tx.amount)}__${tx.day}`;
      if (!groups[key]) groups[key] = new Set();
      groups[key].add(tx.month);
    });

  return Object.entries(groups)
    .filter(([, months]) => months.size >= 2)
    .map(([key]) => {
      const [name, amount, day] = key.split('__');
      return { name, amount: Number(amount), day: Number(day) };
    });
}

export {
  kor,
  fmtAmt,
  parseAmtInput,
  formatScheduled,
  parseContactText,
  formatCurrency,
  detectRecurring,
};
