import { useState, useRef, useEffect } from "react";
import {
  Bot,
  Menu,
  Send,
  Mic,
  Edit2,
  Check,
  AlertTriangle,
  X,
  Bell,
  Trash2,
  Wallet,
  BarChart2,
  CreditCard,
  FileText,
  RotateCcw,
  Settings,
  Tag,
  ToggleLeft,
  ToggleRight,
  Clock,
  Banknote,
  Plus,
  ChevronDown,
  ChevronUp,
} from "lucide-react";
import SidebarDrawer from "./components/SidebarDrawer";
import LoginScreen from "./components/LoginScreen";
import {
  PieChart,
  Pie,
  Cell,
  Tooltip as RChartTip,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  LineChart,
  Line,
  ResponsiveContainer,
} from "recharts";

const NAVY = "#0F1E3D";
const MINT = "#2DD4BF";
const F = "'Noto Sans KR',sans-serif";
const M = "'DM Mono',monospace";
const GRAY_BG = "#F4F6FA";

const fmtAmt = (r: string) => (r ? Number(r).toLocaleString() : "");
const parseAmtInput = (v: string) =>
  v
    .replace(/,/g, "")
    .replace(/[^0-9]/g, "")
    .replace(/^0+(?!$)/, "");

function kor(n: number): string {
  if (!n) return "";
  const d = ["", "일", "이", "삼", "사", "오", "육", "칠", "팔", "구"];
  const p = ["", "십", "백", "천"];
  const u = ["", "만", "억", "조"];
  const chunk = (c: number) => {
    let s = "";
    for (let i = 3; i >= 0; i--) {
      const x = Math.floor(c / 10 ** i) % 10;
      if (!x) continue;
      s += (x === 1 && i > 0 ? "" : d[x]) + p[i];
    }
    return s;
  };
  let res = "",
    rem = n,
    ui = 0;
  while (rem > 0) {
    const c = rem % 10000;
    if (c) res = chunk(c) + u[ui] + res;
    rem = Math.floor(rem / 10000);
    ui++;
  }
  return res + "원";
}

function parseKoreanAmount(text: string): number | undefined {
  const manD = text.match(/(\d+)\s*만\s*원?/);
  if (manD) return parseInt(manD[1]) * 10000;
  const eokD = text.match(/(\d+)\s*억\s*원?/);
  if (eokD) return parseInt(eokD[1]) * 100000000;
  const digW = text.match(/(\d{2,9}(?:,\d{3})*)\s*원/);
  if (digW) return parseInt(digW[1].replace(/,/g, ""));
  const tbl: [string, number][] = [
    ["오백만", 5000000],
    ["삼백만", 3000000],
    ["이백만", 2000000],
    ["백만", 1000000],
    ["오십만", 500000],
    ["삼십만", 300000],
    ["이십만", 200000],
    ["십만", 100000],
    ["오만", 50000],
    ["삼만", 30000],
    ["이만", 20000],
    ["만", 10000],
    ["오천", 5000],
    ["천", 1000],
  ];
  for (const [k, v] of tbl) if (text.includes(k)) return v;
}
function parseKoreanTime(text: string): string | undefined {
  if (
    !["정오", "자정", "오전", "오후", "내일", "모레", "시"].some((t) =>
      text.includes(t),
    )
  )
    return undefined;
  const d = new Date();
  if (text.includes("모레")) d.setDate(d.getDate() + 2);
  else if (text.includes("내일")) d.setDate(d.getDate() + 1);
  if (text.includes("정오")) d.setHours(12, 0, 0, 0);
  else if (text.includes("오전")) {
    const m = text.match(/오전\s*(\d+)\s*시/);
    d.setHours(m ? parseInt(m[1]) : 9, 0, 0, 0);
  } else if (text.includes("오후")) {
    const m = text.match(/오후\s*(\d+)\s*시/);
    const h = m ? parseInt(m[1]) : 2;
    d.setHours(h < 12 ? h + 12 : h, 0, 0, 0);
  } else {
    const m = text.match(/(\d{1,2})\s*시/);
    if (m) d.setHours(parseInt(m[1]), 0, 0, 0);
  }
  const p = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}`;
}
function parseTransferIntent(text: string) {
  if (!["에게", "한테", "송금", "보내", "이체"].some((k) => text.includes(k)))
    return null;
  const rm = text.match(/([가-힣]{2,4})(?:에게|한테)/);
  const amount = parseKoreanAmount(text);
  const scheduled = parseKoreanTime(text);
  if (!rm?.[1] && !amount) return null;
  return { name: rm?.[1], amtRaw: amount?.toString(), scheduled };
}
function formatScheduled(dt: string): string {
  const d = new Date(dt);
  const now = new Date();
  const tm = new Date(now);
  tm.setDate(tm.getDate() + 1);
  const day =
    d.toDateString() === now.toDateString()
      ? "오늘"
      : d.toDateString() === tm.toDateString()
        ? "내일"
        : `${d.getMonth() + 1}월 ${d.getDate()}일`;
  const h = d.getHours();
  const ampm = h < 12 ? "오전" : "오후";
  const hour = h === 0 ? 12 : h > 12 ? h - 12 : h;
  return `${day} ${ampm} ${hour}시${d.getMinutes() > 0 ? ` ${d.getMinutes()}분` : ""}`;
}

// 긴 이름 먼저 (정렬 후 매칭) + 단축명 지원
const BANKS = [
  "카카오뱅크",
  "토스뱅크",
  "케이뱅크",
  "신한은행",
  "국민은행",
  "하나은행",
  "우리은행",
  "농협은행",
  "SC제일은행",
  "신한",
  "국민",
  "하나",
  "우리",
  "농협",
  "기업",
];
const BANK_KOR: Record<string, string> = {
  신한: "신한은행",
  국민: "국민은행",
  하나: "하나은행",
  우리: "우리은행",
  농협: "NH농협은행",
  기업: "IBK기업은행",
  카카오뱅크: "카카오뱅크",
  토스뱅크: "토스뱅크",
  케이뱅크: "케이뱅크",
  신한은행: "신한은행",
  국민은행: "국민은행",
  하나은행: "하나은행",
  우리은행: "우리은행",
};
function parseContactText(text: string) {
  const r: { name?: string; bank?: string; account?: string } = {};
  const sorted = [...BANKS].sort((a, b) => b.length - a.length);
  for (const b of sorted) {
    if (text.includes(b)) {
      r.bank = BANK_KOR[b] || b;
      break;
    }
  }
  const am = text.match(/\d[\d\s-]{9,}\d/);
  if (am) r.account = am[0].trim().replace(/\s+/g, "-").replace(/-{2,}/g, "-");
  const bankChars = BANKS.flatMap((b) => b.match(/[가-힣]+/g) || []);
  const name = (text.match(/[가-힣]{2,4}/g) || []).find(
    (w) => !bankChars.some((bc) => bc === w || bc.includes(w)),
  );
  if (name) r.name = name;
  return r;
}

// ── Types ─────────────────────────────────────────────────────────────────────
interface TransferPrefill {
  name?: string;
  bank?: string;
  account?: string;
  amtRaw?: string;
  scheduled?: string;
}
type ApprovalData = { name: string; amount: number; onConfirm: () => void };

interface FeatureItem {
  icon: string;
  label: string;
  action: string;
}
interface ConfirmSheetData {
  title: string;
  rows: { label: string; value: string }[];
  onConfirm: () => void;
}

type ChatMsg =
  | { id: number; from: "user"; text: string }
  | { id: number; from: "ai-greet" }
  | { id: number; from: "ai-text"; text: string; chips?: string[] }
  | { id: number; from: "ai-guardrail" }
  | { id: number; from: "ai-error"; text: string }
  | { id: number; from: "ai-transfer"; prefill?: TransferPrefill }
  | {
      id: number;
      from: "ai-transfer-confirm";
      recipient: string;
      bank: string;
      account: string;
      amount: number;
      scheduled?: string;
    }
  | {
      id: number;
      from: "ai-feature-list";
      topic: string;
      features: FeatureItem[];
    }
  | { id: number; from: "ai-balance" }
  | { id: number; from: "ai-account-detail"; accountId: number }
  | { id: number; from: "ai-spending" }
  | { id: number; from: "ai-transactions" }
  | { id: number; from: "ai-bill" }
  | { id: number; from: "ai-budget" }
  | { id: number; from: "ai-autotransfer" }
  | { id: number; from: "ai-autotransfer-form" }
  | { id: number; from: "ai-card" };

let _mid = 1;
const mid = () => _mid++;

const CARD_FEATURES: FeatureItem[] = [
  { icon: "💳", label: "카드 정보 조회", action: "ai-card" },
  { icon: "📄", label: "카드 청구서 확인", action: "ai-bill" },
  { icon: "🔒", label: "카드 정지", action: "ai-card" },
];
const TRANSFER_FEATURES: FeatureItem[] = [
  { icon: "🏦", label: "본인 계좌 이체", action: "ai-transfer" },
  { icon: "💸", label: "타인 송금", action: "ai-transfer" },
  { icon: "🔄", label: "자동 이체 설정", action: "ai-autotransfer" },
];
const ACCOUNT_FEATURES: FeatureItem[] = [
  { icon: "💰", label: "잔액 조회", action: "ai-balance" },
  { icon: "📋", label: "거래 내역 조회", action: "ai-transactions" },
  { icon: "🏛", label: "계좌 정보 조회", action: "ai-balance" },
];

function routeMsg(text: string): ChatMsg["from"] {
  if (["송금", "보내", "이체"].some((k) => text.includes(k)))
    return "ai-transfer";
  if (["잔액", "자산", "계좌", "통장"].some((k) => text.includes(k)))
    return "ai-balance";
  if (["소비", "지출", "분석", "카테고리"].some((k) => text.includes(k)))
    return "ai-spending";
  if (["거래", "내역", "입출금"].some((k) => text.includes(k)))
    return "ai-transactions";
  if (["카드", "청구"].some((k) => text.includes(k))) return "ai-bill";
  if (["예산", "구독", "고정비"].some((k) => text.includes(k)))
    return "ai-budget";
  if (["자동이체", "자동 이체"].some((k) => text.includes(k)))
    return "ai-autotransfer";
  const fin = [
    "돈",
    "금융",
    "은행",
    "입금",
    "출금",
    "결제",
    "이자",
    "대출",
    "저축",
    "급여",
  ].some((k) => text.includes(k));
  return fin ? "ai-text" : "ai-guardrail";
}

// ── Data ──────────────────────────────────────────────────────────────────────
interface BarCatData {
  name: string;
  change: number;
  prev: number;
  curr: number;
  added: { name: string; amount: number }[];
  removed: { name: string; amount: number }[];
}
const barData: BarCatData[] = [
  {
    name: "식비",
    change: 12,
    prev: 406714,
    curr: 455520,
    added: [
      { name: "배달의민족", amount: 28500 },
      { name: "맥도날드 (신규)", amount: 12400 },
    ],
    removed: [{ name: "CU 편의점", amount: 8000 }],
  },
  {
    name: "교통비",
    change: -8,
    prev: 278511,
    curr: 256230,
    added: [],
    removed: [
      { name: "택시 이용 감소", amount: 15000 },
      { name: "주유비 감소", amount: 8000 },
    ],
  },
  {
    name: "고정비",
    change: 3,
    prev: 483713,
    curr: 498225,
    added: [{ name: "삼성화재 보험", amount: 15000 }],
    removed: [],
  },
  {
    name: "사치비",
    change: -22,
    prev: 274007,
    curr: 213525,
    added: [],
    removed: [
      { name: "무신사 쇼핑", amount: 35000 },
      { name: "올리브영 감소", amount: 25000 },
    ],
  },
];
const pieData = [
  { name: "식비", value: 38, color: MINT, amount: 474000 },
  { name: "교통비", value: 22, color: "#3B82F6", amount: 274000 },
  { name: "고정비", value: 28, color: NAVY, amount: 349000 },
  { name: "사치비", value: 12, color: "#F97316", amount: 150000 },
];
const monthlySpend = [
  { month: "1월", amount: 1100000 },
  { month: "2월", amount: 980000 },
  { month: "3월", amount: 1350000 },
  { month: "4월", amount: 1420000 },
  { month: "5월", amount: 1120000 },
  { month: "6월", amount: 1247000 },
];
const catTx: Record<string, { name: string; date: string; amount: number }[]> =
  {
    식비: [
      { name: "스타벅스", date: "06.28", amount: 7500 },
      { name: "배달의민족", date: "06.22", amount: 28500 },
      { name: "맥도날드", date: "06.15", amount: 12400 },
      { name: "GS25", date: "06.10", amount: 4200 },
    ],
    교통비: [
      { name: "카카오T 택시", date: "06.24", amount: 13200 },
      { name: "T-money 충전", date: "06.20", amount: 30000 },
      { name: "GS칼텍스", date: "06.05", amount: 65000 },
    ],
    고정비: [
      { name: "월세", date: "06.01", amount: 550000 },
      { name: "KT 통신비", date: "06.05", amount: 55000 },
      { name: "전기·가스", date: "06.10", amount: 89000 },
    ],
    사치비: [
      { name: "올리브영", date: "06.21", amount: 85000 },
      { name: "무신사", date: "06.08", amount: 79000 },
    ],
  };
interface TxItem {
  id: number;
  name: string;
  emoji: string;
  date: string;
  month: string;
  day: number;
  amount: number;
  type: "in" | "out";
  category: string;
}
const CATS = [
  "식비",
  "교통비",
  "고정비",
  "사치비",
  "쇼핑",
  "의료",
  "교육",
  "기타",
];
const ALL_TX: TxItem[] = [
  {
    id: 601,
    name: "급여 입금",
    emoji: "💰",
    date: "06.25 09:00",
    month: "2025-06",
    day: 25,
    amount: 3200000,
    type: "in",
    category: "수입",
  },
  {
    id: 602,
    name: "월세 이서연",
    emoji: "🏠",
    date: "06.01 09:00",
    month: "2025-06",
    day: 1,
    amount: -550000,
    type: "out",
    category: "고정비",
  },
  {
    id: 603,
    name: "KT 통신비",
    emoji: "📱",
    date: "06.05 00:01",
    month: "2025-06",
    day: 5,
    amount: -55000,
    type: "out",
    category: "기타",
  },
  {
    id: 604,
    name: "스타벅스",
    emoji: "☕",
    date: "06.28 14:23",
    month: "2025-06",
    day: 28,
    amount: -7500,
    type: "out",
    category: "식비",
  },
  {
    id: 605,
    name: "카카오T 택시",
    emoji: "🚕",
    date: "06.24 22:41",
    month: "2025-06",
    day: 24,
    amount: -13200,
    type: "out",
    category: "교통비",
  },
  {
    id: 606,
    name: "쿠팡 로켓배송",
    emoji: "📦",
    date: "06.23 11:05",
    month: "2025-06",
    day: 23,
    amount: -42800,
    type: "out",
    category: "쇼핑",
  },
  {
    id: 607,
    name: "Spotify",
    emoji: "🎵",
    date: "06.15 00:01",
    month: "2025-06",
    day: 15,
    amount: -10900,
    type: "out",
    category: "고정비",
  },
  {
    id: 608,
    name: "Netflix",
    emoji: "🎬",
    date: "06.20 00:01",
    month: "2025-06",
    day: 20,
    amount: -17000,
    type: "out",
    category: "고정비",
  },
  {
    id: 609,
    name: "올리브영",
    emoji: "💄",
    date: "06.21 15:30",
    month: "2025-06",
    day: 21,
    amount: -85000,
    type: "out",
    category: "사치비",
  },
  {
    id: 501,
    name: "급여 입금",
    emoji: "💰",
    date: "05.25 09:00",
    month: "2025-05",
    day: 25,
    amount: 3200000,
    type: "in",
    category: "수입",
  },
  {
    id: 502,
    name: "월세 이서연",
    emoji: "🏠",
    date: "05.01 09:00",
    month: "2025-05",
    day: 1,
    amount: -550000,
    type: "out",
    category: "고정비",
  },
  {
    id: 503,
    name: "KT 통신비",
    emoji: "📱",
    date: "05.05 00:01",
    month: "2025-05",
    day: 5,
    amount: -55000,
    type: "out",
    category: "기타",
  },
  {
    id: 504,
    name: "스타벅스",
    emoji: "☕",
    date: "05.28 10:00",
    month: "2025-05",
    day: 28,
    amount: -7500,
    type: "out",
    category: "식비",
  },
  {
    id: 505,
    name: "Spotify",
    emoji: "🎵",
    date: "05.15 00:01",
    month: "2025-05",
    day: 15,
    amount: -10900,
    type: "out",
    category: "고정비",
  },
  {
    id: 506,
    name: "Netflix",
    emoji: "🎬",
    date: "05.20 00:01",
    month: "2025-05",
    day: 20,
    amount: -17000,
    type: "out",
    category: "고정비",
  },
  {
    id: 507,
    name: "무신사",
    emoji: "👗",
    date: "05.14 14:00",
    month: "2025-05",
    day: 14,
    amount: -79000,
    type: "out",
    category: "사치비",
  },
  {
    id: 401,
    name: "급여 입금",
    emoji: "💰",
    date: "04.25 09:00",
    month: "2025-04",
    day: 25,
    amount: 3200000,
    type: "in",
    category: "수입",
  },
  {
    id: 402,
    name: "월세 이서연",
    emoji: "🏠",
    date: "04.01 09:00",
    month: "2025-04",
    day: 1,
    amount: -550000,
    type: "out",
    category: "고정비",
  },
  {
    id: 403,
    name: "KT 통신비",
    emoji: "📱",
    date: "04.05 00:01",
    month: "2025-04",
    day: 5,
    amount: -55000,
    type: "out",
    category: "기타",
  },
  {
    id: 404,
    name: "스타벅스",
    emoji: "☕",
    date: "04.28 09:30",
    month: "2025-04",
    day: 28,
    amount: -7500,
    type: "out",
    category: "식비",
  },
  {
    id: 405,
    name: "Spotify",
    emoji: "🎵",
    date: "04.15 00:01",
    month: "2025-04",
    day: 15,
    amount: -10900,
    type: "out",
    category: "고정비",
  },
  {
    id: 406,
    name: "Netflix",
    emoji: "🎬",
    date: "04.20 00:01",
    month: "2025-04",
    day: 20,
    amount: -17000,
    type: "out",
    category: "고정비",
  },
  {
    id: 407,
    name: "쿠팡 로켓배송",
    emoji: "📦",
    date: "04.18 15:00",
    month: "2025-04",
    day: 18,
    amount: -56000,
    type: "out",
    category: "쇼핑",
  },
  {
    id: 301,
    name: "급여 입금",
    emoji: "💰",
    date: "03.25 09:00",
    month: "2025-03",
    day: 25,
    amount: 3200000,
    type: "in",
    category: "수입",
  },
  {
    id: 302,
    name: "월세 이서연",
    emoji: "🏠",
    date: "03.01 09:00",
    month: "2025-03",
    day: 1,
    amount: -550000,
    type: "out",
    category: "고정비",
  },
  {
    id: 303,
    name: "KT 통신비",
    emoji: "📱",
    date: "03.05 00:01",
    month: "2025-03",
    day: 5,
    amount: -55000,
    type: "out",
    category: "기타",
  },
  {
    id: 304,
    name: "스타벅스",
    emoji: "☕",
    date: "03.28 11:00",
    month: "2025-03",
    day: 28,
    amount: -7500,
    type: "out",
    category: "식비",
  },
  {
    id: 305,
    name: "Spotify",
    emoji: "🎵",
    date: "03.15 00:01",
    month: "2025-03",
    day: 15,
    amount: -10900,
    type: "out",
    category: "고정비",
  },
  {
    id: 306,
    name: "Netflix",
    emoji: "🎬",
    date: "03.20 00:01",
    month: "2025-03",
    day: 20,
    amount: -17000,
    type: "out",
    category: "고정비",
  },
  {
    id: 201,
    name: "급여 입금",
    emoji: "💰",
    date: "02.25 09:00",
    month: "2025-02",
    day: 25,
    amount: 3200000,
    type: "in",
    category: "수입",
  },
  {
    id: 202,
    name: "월세 이서연",
    emoji: "🏠",
    date: "02.01 09:00",
    month: "2025-02",
    day: 1,
    amount: -550000,
    type: "out",
    category: "고정비",
  },
  {
    id: 203,
    name: "KT 통신비",
    emoji: "📱",
    date: "02.05 00:01",
    month: "2025-02",
    day: 5,
    amount: -55000,
    type: "out",
    category: "기타",
  },
  {
    id: 204,
    name: "스타벅스",
    emoji: "☕",
    date: "02.28 10:30",
    month: "2025-02",
    day: 28,
    amount: -7500,
    type: "out",
    category: "식비",
  },
  {
    id: 205,
    name: "Spotify",
    emoji: "🎵",
    date: "02.15 00:01",
    month: "2025-02",
    day: 15,
    amount: -10900,
    type: "out",
    category: "고정비",
  },
  {
    id: 206,
    name: "Netflix",
    emoji: "🎬",
    date: "02.20 00:01",
    month: "2025-02",
    day: 20,
    amount: -17000,
    type: "out",
    category: "고정비",
  },
];
function detectRecurring(txs: TxItem[]) {
  const g: Record<string, Set<string>> = {};
  txs
    .filter((t) => t.type === "out")
    .forEach((tx) => {
      const k = `${tx.name}__${Math.abs(tx.amount)}__${tx.day}`;
      if (!g[k]) g[k] = new Set();
      g[k].add(tx.month);
    });
  return Object.entries(g)
    .filter(([, s]) => s.size >= 2)
    .map(([k]) => {
      const [name, a, d] = k.split("__");
      return { name, amount: parseInt(a), day: parseInt(d) };
    });
}
const billMD = [
  {
    month: "1월",
    amount: 320000,
    cats: [
      { name: "식비", chg: 0 },
      { name: "교통비", chg: 0 },
      { name: "쇼핑", chg: 0 },
    ],
  },
  {
    month: "2월",
    amount: 415000,
    cats: [
      { name: "식비", chg: 20000 },
      { name: "교통비", chg: 5000 },
      { name: "쇼핑", chg: 70000 },
    ],
  },
  {
    month: "3월",
    amount: 280000,
    cats: [
      { name: "식비", chg: -30000 },
      { name: "교통비", chg: -20000 },
      { name: "쇼핑", chg: -85000 },
    ],
  },
  {
    month: "4월",
    amount: 510000,
    cats: [
      { name: "식비", chg: 45000 },
      { name: "교통비", chg: 10000 },
      { name: "쇼핑", chg: 175000 },
    ],
  },
  {
    month: "5월",
    amount: 390000,
    cats: [
      { name: "식비", chg: -30000 },
      { name: "교통비", chg: 10000 },
      { name: "쇼핑", chg: -100000 },
    ],
  },
  {
    month: "6월",
    amount: 847000,
    cats: [
      { name: "식비", chg: 45000 },
      { name: "교통비", chg: 13500 },
      { name: "쇼핑", chg: 175000 },
    ],
  },
];
const accounts = [
  {
    id: 1,
    bank: "신한은행",
    alias: "입출금통장",
    tail: "4200",
    balance: 8200000,
    color: "#0052A3",
  },
  {
    id: 2,
    bank: "카카오뱅크",
    alias: "세이프박스",
    tail: "1234",
    balance: 4650000,
    color: "#FAE100",
  },
];
const autoTxItems = [
  { name: "월세", cycle: "매월 1일", amount: 500000, active: true },
  { name: "보험료", cycle: "매월 10일", amount: 89000, active: true },
  { name: "적금", cycle: "매월 15일", amount: 200000, active: true },
];
const subItems = [
  { name: "Netflix", amount: 13900, active: true },
  { name: "멜론", amount: 10900, active: false },
  { name: "Spotify", amount: 10900, active: true },
];
const budgetItems = [
  { cat: "식비", used: 400000, total: 500000 },
  { cat: "교통비", used: 80000, total: 200000 },
  { cat: "쇼핑", used: 240000, total: 200000 },
];

// ── Shared micro-components ───────────────────────────────────────────────────
function AIAvatar() {
  return (
    <div
      className="w-7 h-7 rounded-full flex items-center justify-center flex-shrink-0 mt-0.5"
      style={{ background: MINT }}
    >
      <Bot size={14} color={NAVY} />
    </div>
  );
}

// Editable field row with dashed mint underline
function ERow({
  label,
  value,
  isEditing,
  onToggle,
  mono = false,
  children,
}: {
  label: string;
  value: string;
  isEditing: boolean;
  onToggle: () => void;
  mono?: boolean;
  children?: React.ReactNode;
}) {
  return (
    <div className="border-b" style={{ borderColor: "rgba(15,30,61,0.06)" }}>
      <button
        className="w-full flex items-center gap-3 py-2.5 text-left hover:opacity-80"
        onClick={onToggle}
      >
        <span
          className="text-xs flex-shrink-0 w-[72px]"
          style={{ color: "#6B7A99", fontFamily: F }}
        >
          {label}
        </span>
        <span
          className="flex-1 text-sm"
          style={{
            color: NAVY,
            fontFamily: mono ? M : F,
            borderBottom: `1.5px dashed ${MINT}`,
            paddingBottom: 1,
          }}
        >
          {value || <span style={{ color: "#B0B8C9" }}>입력</span>}
        </span>
        <Edit2 size={11} color={MINT} />
      </button>
      {isEditing && <div className="pb-1">{children}</div>}
    </div>
  );
}

// Inline category picker badge
function CatBadge({
  cat,
  onEdit,
}: {
  cat: string;
  onEdit: (c: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const [custom, setCustom] = useState("");
  return (
    <span>
      <button
        onClick={() => setOpen((o) => !o)}
        className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-medium"
        style={{ background: "#EFEFEF", color: "#6B7A99", fontFamily: F }}
      >
        <Tag size={9} />
        {cat}
      </button>
      {open && (
        <div
          className="mt-1.5 p-2 rounded-xl"
          style={{ background: "#fff", border: "1px solid rgba(15,30,61,0.1)" }}
        >
          <div className="grid grid-cols-4 gap-1 mb-1.5">
            {CATS.map((c) => (
              <button
                key={c}
                onClick={() => {
                  onEdit(c);
                  setOpen(false);
                }}
                className="py-1 rounded text-[10px] font-medium"
                style={{
                  background: cat === c ? MINT : GRAY_BG,
                  color: cat === c ? NAVY : "#6B7A99",
                  fontFamily: F,
                }}
              >
                {c}
              </button>
            ))}
          </div>
          <div className="flex gap-1">
            <input
              className="flex-1 text-[10px] px-2 py-1 rounded outline-none"
              style={{ background: GRAY_BG, color: NAVY, fontFamily: F }}
              placeholder="직접 입력..."
              value={custom}
              onChange={(e) => setCustom(e.target.value)}
              onKeyDown={(e) =>
                e.key === "Enter" &&
                custom &&
                (onEdit(custom), setOpen(false), setCustom(""))
              }
            />
            {custom && (
              <button
                onClick={() => {
                  onEdit(custom);
                  setOpen(false);
                  setCustom("");
                }}
                className="px-2 rounded text-[10px]"
                style={{ background: MINT, color: NAVY, fontFamily: F }}
              >
                ✓
              </button>
            )}
          </div>
        </div>
      )}
    </span>
  );
}

// AI bubble wrapper
function AIBubble({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex items-start gap-2">
      <AIAvatar />
      <div
        className="flex-1 min-w-0 rounded-2xl p-4 shadow-sm"
        style={{ background: GRAY_BG, borderRadius: "16px 16px 16px 4px" }}
      >
        {children}
      </div>
    </div>
  );
}

// Action chips
function ChipRow({
  chips,
  onChip,
}: {
  chips: string[];
  onChip: (c: string) => void;
}) {
  return (
    <div className="flex flex-wrap gap-2 mt-3">
      {chips.map((c) => (
        <button
          key={c}
          onClick={() => onChip(c)}
          className="px-3 py-1.5 rounded-full text-xs font-medium border hover:opacity-80 transition-opacity"
          style={{
            borderColor: MINT,
            color: NAVY,
            background: "#fff",
            fontFamily: F,
          }}
        >
          {c}
        </button>
      ))}
    </div>
  );
}

// Bar tooltip with item changes
function BarTip({ active, payload, label }: any) {
  if (!active || !payload?.length) return null;
  const d = barData.find((b) => b.name === label);
  if (!d) return null;
  return (
    <div
      className="bg-white rounded-xl p-3 shadow-lg"
      style={{ border: "1px solid rgba(15,30,61,0.1)", minWidth: 200 }}
    >
      <div className="flex justify-between mb-1.5">
        <p className="text-xs font-bold" style={{ color: NAVY, fontFamily: F }}>
          {label}
        </p>
        <p
          className="text-xs font-bold"
          style={{
            color: d.change >= 0 ? "#FF4D4F" : "#3B82F6",
            fontFamily: M,
          }}
        >
          {d.change >= 0 ? "+" : ""}
          {d.change}%
        </p>
      </div>
      <p
        className="text-[10px] mb-2"
        style={{ color: "#6B7A99", fontFamily: M }}
      >
        {d.prev.toLocaleString()} → {d.curr.toLocaleString()}원
      </p>
      {d.added.length > 0 && (
        <>
          <p
            className="text-[10px] font-bold mb-1"
            style={{ color: "#3B82F6", fontFamily: F }}
          >
            + 추가
          </p>
          {d.added.map((it) => (
            <div
              key={it.name}
              className="flex justify-between text-[10px] mb-0.5"
            >
              <span style={{ color: NAVY, fontFamily: F }}>{it.name}</span>
              <span style={{ color: "#3B82F6", fontFamily: M }}>
                +{it.amount.toLocaleString()}원
              </span>
            </div>
          ))}
        </>
      )}
      {d.removed.length > 0 && (
        <>
          <p
            className="text-[10px] font-bold mt-1 mb-1"
            style={{ color: "#FF4D4F", fontFamily: F }}
          >
            − 감소
          </p>
          {d.removed.map((it) => (
            <div
              key={it.name}
              className="flex justify-between text-[10px] mb-0.5"
            >
              <span style={{ color: NAVY, fontFamily: F }}>{it.name}</span>
              <span style={{ color: "#FF4D4F", fontFamily: M }}>
                -{it.amount.toLocaleString()}원
              </span>
            </div>
          ))}
        </>
      )}
    </div>
  );
}

// ── Transfer card (Section 2) ─────────────────────────────────────────────────
function TransferCard({
  prefill,
  onApproval,
}: {
  prefill?: TransferPrefill;
  onApproval: (d: ApprovalData) => void;
}) {
  const [name, setName] = useState(prefill?.name || "");
  const [bank, setBank] = useState(prefill?.bank || "신한은행");
  const [account, setAccount] = useState(prefill?.account || "");
  const [amtRaw, setAmtRaw] = useState(prefill?.amtRaw || "");
  const [timeOpt, setTimeOpt] = useState<"now" | "schedule">(
    prefill?.scheduled ? "schedule" : "now",
  );
  const [schedDT, setSchedDT] = useState(prefill?.scheduled || "");
  const [ef, setEf] = useState<string | null>(null);
  const [done, setDone] = useState(false);
  const amtNum = Number(amtRaw) || 0;

  const handlePaste = (e: React.ClipboardEvent) => {
    const text = e.clipboardData.getData("text");
    const p = parseContactText(text);
    if (p.name || p.bank || p.account) {
      e.preventDefault();
      if (p.name) setName(p.name);
      if (p.bank) setBank(p.bank);
      if (p.account) setAccount(p.account);
    }
  };

  if (done)
    return (
      <div className="flex flex-col items-center py-4 gap-2">
        <div
          className="w-12 h-12 rounded-full flex items-center justify-center"
          style={{ background: "#52C41A" }}
        >
          <Check size={22} color="#fff" strokeWidth={3} />
        </div>
        <p
          className="text-sm font-semibold"
          style={{ color: NAVY, fontFamily: F }}
        >
          송금이 완료되었습니다 ✓
        </p>
        <p className="text-xs" style={{ color: "#6B7A99", fontFamily: F }}>
          {name}님께 {amtNum.toLocaleString()}원 전송됨
        </p>
      </div>
    );

  return (
    <div onPaste={handlePaste}>
      <div className="flex items-center gap-2 mb-3">
        <span className="text-lg">💸</span>
        <p
          className="text-sm font-semibold"
          style={{ color: NAVY, fontFamily: F }}
        >
          송금 확인
        </p>
      </div>

      {/* 받는 사람 */}
      <ERow
        label="받는 사람"
        value={name}
        isEditing={ef === "name"}
        onToggle={() => setEf(ef === "name" ? null : "name")}
      >
        <div className="pl-[84px] pr-2">
          <input
            autoFocus
            className="w-full outline-none text-sm pb-0.5 border-b-2"
            style={{ color: NAVY, fontFamily: F, borderColor: MINT }}
            value={name}
            onChange={(e) => setName(e.target.value)}
            onBlur={() => setEf(null)}
            onKeyDown={(e) => e.key === "Enter" && setEf(null)}
          />
        </div>
      </ERow>

      {/* 은행 */}
      <ERow
        label="은행"
        value={bank}
        isEditing={ef === "bank"}
        onToggle={() => setEf(ef === "bank" ? null : "bank")}
      >
        <div className="pl-[84px] pr-2">
          <div
            className="bg-white rounded-xl overflow-hidden shadow-sm"
            style={{ border: "1px solid rgba(15,30,61,0.08)" }}
          >
            {BANKS.map((b) => (
              <button
                key={b}
                onClick={() => {
                  setBank(b);
                  setEf(null);
                }}
                className="w-full text-left px-3 py-2 text-xs hover:opacity-80 border-b last:border-0"
                style={{
                  color: bank === b ? MINT : NAVY,
                  fontFamily: F,
                  fontWeight: bank === b ? 600 : 400,
                  borderColor: "rgba(15,30,61,0.05)",
                }}
              >
                {b}
              </button>
            ))}
          </div>
        </div>
      </ERow>

      {/* 계좌번호 */}
      <ERow
        label="계좌번호"
        value={account}
        isEditing={ef === "account"}
        onToggle={() => setEf(ef === "account" ? null : "account")}
        mono
      >
        <div className="pl-[84px] pr-2">
          <input
            autoFocus
            className="w-full outline-none text-sm pb-0.5 border-b-2"
            style={{ color: NAVY, fontFamily: M, borderColor: MINT }}
            value={account}
            onChange={(e) => setAccount(e.target.value)}
            onBlur={() => setEf(null)}
            onKeyDown={(e) => e.key === "Enter" && setEf(null)}
            inputMode="numeric"
          />
        </div>
      </ERow>

      {/* 금액 */}
      <ERow
        label="금액"
        value={amtNum > 0 ? amtNum.toLocaleString() + "원" : ""}
        isEditing={ef === "amount"}
        onToggle={() => setEf(ef === "amount" ? null : "amount")}
        mono
      >
        <div className="pl-[84px] pr-2">
          <input
            autoFocus
            className="w-full outline-none text-sm pb-0.5 border-b-2"
            style={{ color: NAVY, fontFamily: M, borderColor: MINT }}
            inputMode="numeric"
            value={fmtAmt(amtRaw)}
            onChange={(e) => setAmtRaw(parseAmtInput(e.target.value))}
            onBlur={() => setEf(null)}
            onKeyDown={(e) => e.key === "Enter" && setEf(null)}
          />
          {amtNum > 0 && (
            <p className="text-xs mt-1" style={{ color: MINT, fontFamily: F }}>
              {kor(amtNum)}
            </p>
          )}
          <div className="flex gap-1.5 mt-2">
            {["10,000", "50,000", "100,000"].map((c) => (
              <button
                key={c}
                onClick={() => setAmtRaw(c.replace(",", ""))}
                className="flex-1 py-1 rounded-lg text-[10px] font-medium"
                style={{ background: GRAY_BG, color: NAVY, fontFamily: F }}
              >
                {c}
              </button>
            ))}
          </div>
        </div>
      </ERow>

      {/* 시간 */}
      <ERow
        label="시간"
        value={
          timeOpt === "now"
            ? "지금 바로"
            : schedDT
              ? formatScheduled(schedDT)
              : "날짜/시간 선택"
        }
        isEditing={ef === "time"}
        onToggle={() => setEf(ef === "time" ? null : "time")}
      >
        <div className="pl-[84px] pr-2 space-y-2">
          <div className="flex gap-2">
            {[
              { k: "now", l: "지금 바로" },
              { k: "schedule", l: "예약 송금" },
            ].map((opt) => (
              <button
                key={opt.k}
                onClick={() => setTimeOpt(opt.k as "now" | "schedule")}
                className="flex-1 py-1.5 rounded-lg text-xs font-medium flex items-center justify-center gap-1"
                style={{
                  background: timeOpt === opt.k ? NAVY : GRAY_BG,
                  color: timeOpt === opt.k ? "#fff" : NAVY,
                  fontFamily: F,
                }}
              >
                <Clock size={11} />
                {opt.l}
              </button>
            ))}
          </div>
          {timeOpt === "schedule" && (
            <input
              type="datetime-local"
              className="w-full py-1.5 px-2 rounded-lg text-xs outline-none"
              style={{ background: GRAY_BG, color: NAVY, fontFamily: M }}
              value={schedDT}
              onChange={(e) => setSchedDT(e.target.value)}
            />
          )}
        </div>
      </ERow>

      <p
        className="text-[10px] py-2"
        style={{ color: "#6B7A99", fontFamily: F }}
      >
        💡 클립보드 텍스트 붙여넣기 자동인식 지원
      </p>

      <div className="flex gap-2">
        <button
          className="flex-1 py-2.5 rounded-xl text-sm border"
          style={{ borderColor: "#CBD5E1", color: "#6B7A99", fontFamily: F }}
        >
          취소
        </button>
        <button
          onClick={() =>
            onApproval({ name, amount: amtNum, onConfirm: () => setDone(true) })
          }
          className="flex-1 py-2.5 rounded-xl text-sm font-semibold hover:opacity-90"
          style={{ background: MINT, color: NAVY, fontFamily: F }}
        >
          송금하기 →
        </button>
      </div>
    </div>
  );
}

// ── Balance card (Section 3) ──────────────────────────────────────────────────
function BalanceCard({ onAddMsg }: { onAddMsg: (m: ChatMsg) => void }) {
  const total = accounts.reduce((s, a) => s + a.balance, 0);
  return (
    <div>
      <div className="flex items-center gap-2 mb-3">
        <span className="text-lg">💳</span>
        <p
          className="text-sm font-semibold"
          style={{ color: NAVY, fontFamily: F }}
        >
          내 자산 현황
        </p>
      </div>
      <p
        className="text-2xl font-bold"
        style={{ color: NAVY, fontFamily: "'DM Sans',sans-serif" }}
      >
        {total.toLocaleString()}원
      </p>
      <p className="text-xs mb-3" style={{ color: "#6B7A99", fontFamily: F }}>
        총 자산
      </p>
      <div className="border-t" style={{ borderColor: "rgba(15,30,61,0.06)" }}>
        {accounts.map((a) => (
          <button
            key={a.id}
            onClick={() =>
              onAddMsg({
                id: mid(),
                from: "ai-account-detail",
                accountId: a.id,
              })
            }
            className="w-full flex items-center gap-3 py-3 border-b text-left hover:opacity-80 transition-opacity"
            style={{ borderColor: "rgba(15,30,61,0.06)" }}
          >
            <div
              className="w-8 h-8 rounded-lg flex items-center justify-center text-white text-xs font-bold flex-shrink-0"
              style={{ background: a.color }}
            >
              {a.bank[0]}
            </div>
            <div className="flex-1">
              <p
                className="text-xs font-medium"
                style={{ color: NAVY, fontFamily: F }}
              >
                {a.bank} <span style={{ color: "#6B7A99" }}>···{a.tail}</span>
              </p>
              <p
                className="text-sm font-bold"
                style={{ color: NAVY, fontFamily: M }}
              >
                {a.balance.toLocaleString()}원
              </p>
            </div>
            <button
              onClick={(e) => {
                e.stopPropagation();
                onAddMsg({ id: mid(), from: "ai-transfer" });
              }}
              className="text-xs px-2.5 py-1 rounded-lg"
              style={{ background: MINT + "20", color: MINT, fontFamily: F }}
            >
              이체
            </button>
          </button>
        ))}
      </div>
      <ChipRow
        chips={["거래내역 보기", "카드 청구서", "계좌 이체"]}
        onChip={(c) => {
          if (c === "거래내역 보기")
            onAddMsg({ id: mid(), from: "ai-transactions" });
          else if (c === "카드 청구서")
            onAddMsg({ id: mid(), from: "ai-bill" });
          else onAddMsg({ id: mid(), from: "ai-transfer" });
        }}
      />
    </div>
  );
}

function AccountDetailCard({ accountId }: { accountId: number }) {
  const a = accounts.find((ac) => ac.id === accountId)!;
  if (!a) return null;
  return (
    <div>
      <div
        className="rounded-2xl p-4 text-white mb-3"
        style={{
          background: "linear-gradient(135deg,#0F1E3D 0%,#1a3a6b 100%)",
        }}
      >
        <p className="text-xs opacity-70 mb-1" style={{ fontFamily: F }}>
          {a.bank} · {a.alias} ···{a.tail}
        </p>
        <p
          className="text-2xl font-bold"
          style={{ fontFamily: "'DM Sans',sans-serif" }}
        >
          {a.balance.toLocaleString()}원
        </p>
      </div>
      <div className="grid grid-cols-4 gap-2 mb-3">
        {["입금", "출금", "이체", "상세"].map((l) => (
          <button
            key={l}
            className="py-2 rounded-xl text-xs font-medium"
            style={{ background: GRAY_BG, color: NAVY, fontFamily: F }}
          >
            {l}
          </button>
        ))}
      </div>
      <p
        className="text-xs font-semibold mb-2"
        style={{ color: "#6B7A99", fontFamily: F }}
      >
        최근 거래
      </p>
      {ALL_TX.filter((t) => t.month === "2025-06")
        .slice(0, 4)
        .map((tx) => (
          <div
            key={tx.id}
            className="flex items-center gap-2 py-2 border-b last:border-0"
            style={{ borderColor: "rgba(15,30,61,0.06)" }}
          >
            <span className="text-sm">{tx.emoji}</span>
            <div className="flex-1">
              <p className="text-xs" style={{ color: NAVY, fontFamily: F }}>
                {tx.name}
              </p>
            </div>
            <p
              className="text-xs font-bold"
              style={{
                color: tx.type === "in" ? "#52C41A" : NAVY,
                fontFamily: M,
              }}
            >
              {tx.type === "in" ? "+" : ""}
              {Math.abs(tx.amount).toLocaleString()}원
            </p>
            <p
              className="text-[10px]"
              style={{ color: "#6B7A99", fontFamily: M }}
            >
              {tx.date}
            </p>
          </div>
        ))}
    </div>
  );
}

// ── Spending card (Section 4) ─────────────────────────────────────────────────
function SpendingCard({ onAddMsg }: { onAddMsg: (m: ChatMsg) => void }) {
  const [tab, setTab] = useState<"donut" | "bar" | "monthly">("donut");
  const [selCat, setSelCat] = useState<string | null>(null);
  const [catEdit, setCatEdit] = useState<Record<string, string>>({});
  const toggle = (name: string) => setSelCat((c) => (c === name ? null : name));

  return (
    <div>
      <div className="flex items-center gap-2 mb-2">
        <span className="text-lg">📊</span>
        <p
          className="text-sm font-semibold"
          style={{ color: NAVY, fontFamily: F }}
        >
          카테고리별 지출
        </p>
      </div>
      <div
        className="flex gap-1 mb-3 rounded-xl"
        style={{ background: "#E8EDF5", padding: "3px" }}
      >
        {[
          { k: "donut" as const, l: "도넛" },
          { k: "bar" as const, l: "막대" },
          { k: "monthly" as const, l: "월별비교" },
        ].map((t) => (
          <button
            key={t.k}
            onClick={() => setTab(t.k)}
            className="flex-1 py-1.5 rounded-lg text-xs font-medium transition-all"
            style={{
              background: tab === t.k ? "#fff" : "transparent",
              color: tab === t.k ? NAVY : "#6B7A99",
              fontFamily: F,
              boxShadow: tab === t.k ? "0 1px 3px rgba(0,0,0,0.1)" : "none",
            }}
          >
            {t.l}
          </button>
        ))}
      </div>

      {tab === "donut" && (
        <div>
          <div className="flex items-center gap-3">
            <div style={{ width: 140, height: 140, flexShrink: 0 }}>
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={pieData}
                    cx="50%"
                    cy="50%"
                    innerRadius={42}
                    outerRadius={62}
                    dataKey="value"
                    paddingAngle={3}
                    onClick={(d: any) => toggle(d.name)}
                    style={{ cursor: "pointer" }}
                  >
                    {pieData.map((d) => (
                      <Cell
                        key={`p-${d.name}`}
                        fill={d.color}
                        opacity={selCat && selCat !== d.name ? 0.3 : 1}
                        stroke={selCat === d.name ? "#fff" : "none"}
                        strokeWidth={selCat === d.name ? 3 : 0}
                      />
                    ))}
                  </Pie>
                </PieChart>
              </ResponsiveContainer>
            </div>
            <div className="flex-1 space-y-2">
              {pieData.map((d) => (
                <button
                  key={d.name}
                  onClick={() => toggle(d.name)}
                  className="w-full flex items-center justify-between px-2 py-0.5 rounded-lg"
                  style={{
                    background: selCat === d.name ? "#fff" : "transparent",
                  }}
                >
                  <div className="flex items-center gap-1.5">
                    <div
                      className="w-2.5 h-2.5 rounded-full flex-shrink-0"
                      style={{ background: d.color }}
                    />
                    <span
                      className="text-xs"
                      style={{ color: "#6B7A99", fontFamily: F }}
                    >
                      {d.name}
                    </span>
                  </div>
                  <div className="text-right">
                    <span
                      className="text-xs font-semibold"
                      style={{ color: NAVY, fontFamily: M }}
                    >
                      {d.value}%
                    </span>
                    <span
                      className="text-[10px] ml-1"
                      style={{ color: "#6B7A99", fontFamily: M }}
                    >
                      {d.amount.toLocaleString()}
                    </span>
                  </div>
                </button>
              ))}
            </div>
          </div>
          {selCat && catTx[selCat] && (
            <div
              className="mt-3 border-t pt-3"
              style={{ borderColor: "rgba(15,30,61,0.08)" }}
            >
              <p
                className="text-xs font-semibold mb-2"
                style={{ color: NAVY, fontFamily: F }}
              >
                {selCat} 거래 내역
              </p>
              {catTx[selCat].map((tx, i) => (
                <div
                  key={i}
                  className="flex items-center gap-2 py-2 border-b last:border-0"
                  style={{ borderColor: "rgba(15,30,61,0.06)" }}
                >
                  <span
                    className="text-[10px] w-10 flex-shrink-0"
                    style={{ color: "#6B7A99", fontFamily: M }}
                  >
                    {tx.date}
                  </span>
                  <span
                    className="flex-1 text-xs"
                    style={{ color: NAVY, fontFamily: F }}
                  >
                    {tx.name}
                  </span>
                  <CatBadge
                    cat={catEdit[`${selCat}-${i}`] || selCat}
                    onEdit={(c) =>
                      setCatEdit((p) => ({ ...p, [`${selCat}-${i}`]: c }))
                    }
                  />
                  <span
                    className="text-xs font-bold"
                    style={{ color: NAVY, fontFamily: M }}
                  >
                    {tx.amount.toLocaleString()}원
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {tab === "bar" && (
        <div>
          <ResponsiveContainer width="100%" height={160}>
            <BarChart
              data={barData}
              margin={{ top: 4, right: 8, left: -20, bottom: 0 }}
              onClick={(d: any) => {
                if (d?.activeLabel && d.activePayload?.length)
                  toggle(d.activeLabel);
              }}
            >
              <CartesianGrid
                strokeDasharray="3 3"
                stroke="rgba(15,30,61,0.06)"
              />
              <XAxis
                dataKey="name"
                tick={{ fontSize: 11, fontFamily: F, fill: "#6B7A99" }}
              />
              <YAxis tick={{ fontSize: 10, fontFamily: M, fill: "#6B7A99" }} />
              <RChartTip content={BarTip} />
              <Bar
                dataKey="change"
                radius={[6, 6, 0, 0]}
                style={{ cursor: "pointer" }}
              >
                {barData.map((d) => (
                  <Cell
                    key={`b-${d.name}`}
                    fill={d.change >= 0 ? "#FF4D4F" : "#3B82F6"}
                    opacity={selCat && selCat !== d.name ? 0.3 : 1}
                  />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
          {selCat &&
            (() => {
              const bd = barData.find((b) => b.name === selCat);
              if (!bd || (!bd.added.length && !bd.removed.length)) return null;
              return (
                <div
                  className="mt-2 p-3 rounded-xl"
                  style={{ background: "#fff" }}
                >
                  <p
                    className="text-xs font-semibold mb-2"
                    style={{ color: NAVY, fontFamily: F }}
                  >
                    {selCat} 전월 대비 변동
                  </p>
                  {bd.added.map((it) => (
                    <div
                      key={it.name}
                      className="flex justify-between text-xs mb-1"
                    >
                      <span className="flex items-center gap-1">
                        <b style={{ color: "#3B82F6" }}>+</b>
                        <span style={{ color: NAVY, fontFamily: F }}>
                          {it.name}
                        </span>
                      </span>
                      <span style={{ color: "#3B82F6", fontFamily: M }}>
                        +{it.amount.toLocaleString()}원
                      </span>
                    </div>
                  ))}
                  {bd.removed.map((it) => (
                    <div
                      key={it.name}
                      className="flex justify-between text-xs mb-1"
                    >
                      <span className="flex items-center gap-1">
                        <b style={{ color: "#FF4D4F" }}>−</b>
                        <span style={{ color: NAVY, fontFamily: F }}>
                          {it.name}
                        </span>
                      </span>
                      <span style={{ color: "#FF4D4F", fontFamily: M }}>
                        -{it.amount.toLocaleString()}원
                      </span>
                    </div>
                  ))}
                </div>
              );
            })()}
        </div>
      )}

      {tab === "monthly" && (
        <ResponsiveContainer width="100%" height={150}>
          <LineChart
            data={monthlySpend}
            margin={{ top: 4, right: 8, left: -20, bottom: 0 }}
          >
            <CartesianGrid strokeDasharray="3 3" stroke="rgba(15,30,61,0.06)" />
            <XAxis
              dataKey="month"
              tick={{ fontSize: 11, fontFamily: F, fill: "#6B7A99" }}
            />
            <YAxis
              tick={{ fontSize: 9, fontFamily: M, fill: "#6B7A99" }}
              tickFormatter={(v) => `${(v / 10000).toFixed(0)}만`}
            />
            <RChartTip
              formatter={(v: number) => [`${v.toLocaleString()}원`, "지출"]}
            />
            <Line
              type="monotone"
              dataKey="amount"
              stroke={MINT}
              strokeWidth={2.5}
              dot={{ fill: MINT, r: 4 }}
              activeDot={{ r: 6, fill: NAVY }}
            />
          </LineChart>
        </ResponsiveContainer>
      )}

      <ChipRow
        chips={["지난달 비교", "예산 설정", "거래 내역 전체"]}
        onChip={(c) => {
          if (c === "거래 내역 전체")
            onAddMsg({ id: mid(), from: "ai-transactions" });
          else if (c === "예산 설정")
            onAddMsg({ id: mid(), from: "ai-budget" });
          else
            onAddMsg({
              id: mid(),
              from: "ai-text",
              text: "지난달 5월 대비 식비 +12%, 교통비 −8%, 고정비 +3%입니다.",
              chips: ["소비 분석", "예산 설정"],
            });
        }}
      />
    </div>
  );
}

// ── Transactions card (Section 5) ─────────────────────────────────────────────
function TransactionsCard() {
  const months = ["2025-06", "2025-05", "2025-04", "2025-03", "2025-02"];
  const ml: Record<string, string> = {
    "2025-06": "6월",
    "2025-05": "5월",
    "2025-04": "4월",
    "2025-03": "3월",
    "2025-02": "2월",
  };
  const [selM, setSelM] = useState("2025-06");
  const [expanded, setExpanded] = useState<number | null>(null);
  const [txCats, setTxCats] = useState<Record<number, string>>({});
  const [dismissed, setDismissed] = useState<string[]>([]);
  const [toasts, setToasts] = useState<string[]>([]);

  const currentTxs = ALL_TX.filter((t) => t.month === selM).sort(
    (a, b) => b.day - a.day,
  );
  const recurring = detectRecurring(ALL_TX);
  const suggestions = recurring.filter((r) => {
    const cur = currentTxs.find(
      (t) =>
        t.name === r.name && Math.abs(t.amount) === r.amount && t.day === r.day,
    );
    if (!cur) return false;
    return (
      (txCats[cur.id] || cur.category) !== "고정비" &&
      !dismissed.includes(r.name)
    );
  });

  const registerFixed = (r: { name: string; amount: number; day: number }) => {
    ALL_TX.filter(
      (t) =>
        t.name === r.name && Math.abs(t.amount) === r.amount && t.day === r.day,
    ).forEach((t) => setTxCats((p) => ({ ...p, [t.id]: "고정비" })));
    setDismissed((p) => [...p, r.name]);
    const msg = `${r.name}가(이) 고정비로 등록되었습니다 ✓`;
    setToasts((p) => [...p, msg]);
    setTimeout(() => setToasts((p) => p.filter((t) => t !== msg)), 3000);
  };

  return (
    <div>
      <div className="flex items-center gap-2 mb-3">
        <span className="text-lg">📋</span>
        <p
          className="text-sm font-semibold"
          style={{ color: NAVY, fontFamily: F }}
        >
          거래 내역
        </p>
      </div>
      <div className="flex gap-1.5 mb-3 overflow-x-auto pb-1">
        {months.map((mo) => (
          <button
            key={mo}
            onClick={() => {
              setSelM(mo);
              setExpanded(null);
            }}
            className="px-3 py-1 rounded-full text-xs font-medium flex-shrink-0"
            style={{
              background: selM === mo ? NAVY : "#E8EDF5",
              color: selM === mo ? "#fff" : "#6B7A99",
              fontFamily: F,
            }}
          >
            {ml[mo]}
          </button>
        ))}
      </div>

      {toasts.map((t, i) => (
        <div
          key={i}
          className="mb-2 px-3 py-2 rounded-xl text-xs font-medium"
          style={{
            background: "#52C41A15",
            color: "#52C41A",
            fontFamily: F,
            border: "1px solid #52C41A30",
          }}
        >
          {t}
        </div>
      ))}

      {suggestions.length > 0 && (
        <div
          className="mb-3 rounded-xl overflow-hidden"
          style={{ border: `1px solid ${MINT}`, background: `${MINT}10` }}
        >
          <div className="flex justify-between items-center px-3 py-2">
            <div className="flex items-center gap-1.5">
              <Bell size={13} color={MINT} />
              <p
                className="text-xs font-semibold"
                style={{ color: NAVY, fontFamily: F }}
              >
                고정비 제안
              </p>
            </div>
            <button
              onClick={() =>
                setDismissed((p) => [...p, ...suggestions.map((s) => s.name)])
              }
            >
              <X size={13} color="#6B7A99" />
            </button>
          </div>
          {suggestions.map((s) => (
            <div
              key={s.name}
              className="border-t px-3 py-2 flex items-start gap-2"
              style={{ borderColor: `${MINT}30` }}
            >
              <div className="flex-1">
                <p className="text-xs" style={{ color: NAVY, fontFamily: F }}>
                  {s.name}({s.amount.toLocaleString()}원)가 매월 {s.day}일
                  반복됩니다. 고정비로 등록할까요?
                </p>
              </div>
              <div className="flex gap-1.5 flex-shrink-0">
                <button
                  onClick={() => registerFixed(s)}
                  className="px-2 py-1 rounded text-[10px] font-semibold"
                  style={{ background: MINT, color: NAVY, fontFamily: F }}
                >
                  고정비 등록
                </button>
                <button
                  onClick={() => setDismissed((p) => [...p, s.name])}
                  className="px-2 py-1 rounded text-[10px]"
                  style={{
                    background: GRAY_BG,
                    color: "#6B7A99",
                    fontFamily: F,
                  }}
                >
                  닫기
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      <div>
        {currentTxs.map((tx) => {
          const effCat = txCats[tx.id] || tx.category;
          const isOpen = expanded === tx.id;
          return (
            <div
              key={tx.id}
              className="border-b"
              style={{ borderColor: "rgba(15,30,61,0.06)" }}
            >
              <button
                className="w-full flex items-center gap-2 py-2.5 text-left"
                onClick={() => setExpanded(isOpen ? null : tx.id)}
              >
                <span className="text-sm flex-shrink-0">{tx.emoji}</span>
                <div className="flex-1 min-w-0">
                  <p
                    className="text-xs font-medium truncate"
                    style={{ color: NAVY, fontFamily: F }}
                  >
                    {tx.name}
                  </p>
                  <div className="flex items-center gap-1.5 mt-0.5">
                    <p
                      className="text-[10px]"
                      style={{ color: "#6B7A99", fontFamily: M }}
                    >
                      {tx.date}
                    </p>
                    {tx.type === "out" && (
                      <CatBadge
                        cat={effCat}
                        onEdit={(c) => setTxCats((p) => ({ ...p, [tx.id]: c }))}
                      />
                    )}
                  </div>
                </div>
                <p
                  className="text-xs font-bold flex-shrink-0"
                  style={{
                    color: tx.type === "in" ? "#52C41A" : NAVY,
                    fontFamily: M,
                  }}
                >
                  {tx.type === "in" ? "+" : ""}
                  {Math.abs(tx.amount).toLocaleString()}원
                </p>
                {isOpen ? (
                  <ChevronUp size={13} color="#6B7A99" />
                ) : (
                  <ChevronDown size={13} color="#6B7A99" />
                )}
              </button>
              {isOpen && (
                <div
                  className="px-4 pb-2 pt-1 space-y-1.5 text-xs rounded-xl mx-2 mb-2"
                  style={{ background: "#fff" }}
                >
                  <div className="flex justify-between items-center">
                    <span style={{ color: "#6B7A99", fontFamily: F }}>
                      거래처
                    </span>
                    <span style={{ color: NAVY, fontFamily: F }}>
                      {tx.name}
                    </span>
                  </div>
                  <div className="flex justify-between items-center">
                    <span style={{ color: "#6B7A99", fontFamily: F }}>
                      카테고리
                    </span>
                    <CatBadge
                      cat={effCat}
                      onEdit={(c) => setTxCats((p) => ({ ...p, [tx.id]: c }))}
                    />
                  </div>
                  <div className="flex justify-between">
                    <span style={{ color: "#6B7A99", fontFamily: F }}>
                      날짜/시간
                    </span>
                    <span style={{ color: NAVY, fontFamily: M }}>
                      {tx.date}
                    </span>
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ── Bill card (Section 6) ─────────────────────────────────────────────────────
function BillCard() {
  const [selMonth, setSelMonth] = useState<string | null>(null);
  const selData = billMD.find((m) => m.month === selMonth);
  const BillTip = ({ active, payload, label }: any) => {
    if (!active || !payload?.length) return null;
    const data = billMD.find((m) => m.month === label);
    if (!data) return null;
    return (
      <div
        className="bg-white rounded-xl p-3 shadow-lg"
        style={{ border: "1px solid rgba(15,30,61,0.1)", minWidth: 150 }}
      >
        <p
          className="text-xs font-bold mb-1.5"
          style={{ color: NAVY, fontFamily: F }}
        >
          {label} · {data.amount.toLocaleString()}원
        </p>
        {data.cats.map((c) => (
          <div key={c.name} className="flex justify-between text-[10px] mb-0.5">
            <span style={{ color: "#6B7A99", fontFamily: F }}>{c.name}</span>
            <span
              style={{
                color:
                  c.chg > 0 ? "#FF4D4F" : c.chg < 0 ? "#3B82F6" : "#6B7A99",
                fontFamily: M,
              }}
            >
              {c.chg === 0
                ? "–"
                : (c.chg > 0 ? "↑" : "↓") +
                  Math.abs(c.chg / 1000).toFixed(0) +
                  "k"}
            </span>
          </div>
        ))}
      </div>
    );
  };
  return (
    <div>
      <div className="flex items-center gap-2 mb-2">
        <span className="text-lg">💳</span>
        <p
          className="text-sm font-semibold"
          style={{ color: NAVY, fontFamily: F }}
        >
          6월 카드 청구서
        </p>
      </div>
      <p
        className="text-2xl font-bold"
        style={{ color: NAVY, fontFamily: "'DM Sans',sans-serif" }}
      >
        847,000원
      </p>
      <p className="text-xs mb-3" style={{ color: "#6B7A99", fontFamily: F }}>
        결제일 7월 15일
      </p>
      <p
        className="text-[10px] mb-1"
        style={{ color: "#6B7A99", fontFamily: F }}
      >
        월 위에 마우스를 올리면 카테고리 변동을, 클릭하면 상세를 볼 수 있어요
      </p>
      <ResponsiveContainer width="100%" height={140}>
        <LineChart
          data={billMD}
          margin={{ top: 4, right: 8, left: -20, bottom: 0 }}
          onClick={(d: any) => {
            if (d?.activePayload?.[0]) {
              const m = d.activePayload[0].payload.month;
              setSelMonth((p) => (p === m ? null : m));
            }
          }}
        >
          <CartesianGrid strokeDasharray="3 3" stroke="rgba(15,30,61,0.06)" />
          <XAxis
            dataKey="month"
            tick={{ fontSize: 11, fontFamily: F, fill: "#6B7A99" }}
          />
          <YAxis
            tick={{ fontSize: 9, fontFamily: M, fill: "#6B7A99" }}
            tickFormatter={(v) => `${(v / 10000).toFixed(0)}만`}
          />
          <RChartTip content={BillTip} />
          <Line
            type="monotone"
            dataKey="amount"
            stroke={MINT}
            strokeWidth={2.5}
            dot={{ fill: MINT, r: 5, cursor: "pointer" }}
            activeDot={{ r: 7, fill: NAVY }}
          />
        </LineChart>
      </ResponsiveContainer>
      {selData && (
        <div
          className="mt-3 p-3 rounded-xl"
          style={{
            background: "#fff",
            border: "1px solid rgba(15,30,61,0.08)",
          }}
        >
          <div className="flex justify-between items-center mb-2">
            <p
              className="text-xs font-semibold"
              style={{ color: NAVY, fontFamily: F }}
            >
              {selData.month} 카테고리 상세
            </p>
            <button onClick={() => setSelMonth(null)}>
              <X size={13} color="#6B7A99" />
            </button>
          </div>
          <p
            className="text-lg font-bold mb-2"
            style={{ color: NAVY, fontFamily: M }}
          >
            {selData.amount.toLocaleString()}원
          </p>
          {selData.cats.map((c) => (
            <div key={c.name} className="flex justify-between text-xs mb-1.5">
              <span style={{ color: NAVY, fontFamily: F }}>{c.name}</span>
              <span
                style={{
                  color: c.chg > 0 ? "#FF4D4F" : c.chg < 0 ? "#3B82F6" : NAVY,
                  fontFamily: M,
                }}
              >
                {c.chg !== 0
                  ? (c.chg > 0 ? "+" : "") + c.chg.toLocaleString() + "원"
                  : "변동없음"}
              </span>
            </div>
          ))}
        </div>
      )}
      <div className="mt-3 space-y-1.5">
        <p
          className="text-xs font-semibold"
          style={{ color: "#6B7A99", fontFamily: F }}
        >
          주요 지출
        </p>
        {[
          { name: "쿠팡", amount: 234000 },
          { name: "스타벅스", amount: 67000 },
        ].map((i) => (
          <div key={i.name} className="flex justify-between text-xs">
            <span style={{ color: NAVY, fontFamily: F }}>{i.name}</span>
            <span style={{ color: NAVY, fontFamily: M }}>
              -{i.amount.toLocaleString()}원
            </span>
          </div>
        ))}
      </div>
      <ChipRow chips={["전체 내역", "이의 제기"]} onChip={() => {}} />
    </div>
  );
}

// ── Budget card (Section 7) ───────────────────────────────────────────────────
function BudgetCard() {
  const [subs, setSubs] = useState(subItems.map((s) => s.active));
  return (
    <div>
      <div className="flex items-center gap-2 mb-3">
        <span className="text-lg">🎯</span>
        <p
          className="text-sm font-semibold"
          style={{ color: NAVY, fontFamily: F }}
        >
          예산 현황
        </p>
      </div>
      <div className="space-y-3 mb-4">
        {budgetItems.map((b) => {
          const pct = Math.round((b.used / b.total) * 100);
          const color =
            pct >= 100 ? "#FF4D4F" : pct >= 80 ? "#F59E0B" : "#52C41A";
          return (
            <div key={b.cat}>
              <div className="flex justify-between items-center mb-1">
                <span
                  className="text-xs font-medium"
                  style={{ color: NAVY, fontFamily: F }}
                >
                  {b.cat}
                  {pct >= 100 && " ⚠️"}
                </span>
                <span
                  className="text-[10px]"
                  style={{ color: "#6B7A99", fontFamily: M }}
                >
                  {b.used.toLocaleString()} / {b.total.toLocaleString()}원
                </span>
              </div>
              <div
                className="w-full h-2.5 rounded-full"
                style={{ background: "#E8EDF5" }}
              >
                <div
                  className="h-2.5 rounded-full"
                  style={{ width: `${Math.min(pct, 100)}%`, background: color }}
                />
              </div>
              <p
                className="text-[10px] text-right mt-0.5 font-bold"
                style={{ color, fontFamily: M }}
              >
                {pct}%
              </p>
            </div>
          );
        })}
      </div>
      <p
        className="text-xs font-semibold mb-2"
        style={{ color: "#6B7A99", fontFamily: F }}
      >
        반복 결제
      </p>
      {subItems.map((s, i) => (
        <div
          key={s.name}
          className="flex items-center justify-between py-2 border-b"
          style={{ borderColor: "rgba(15,30,61,0.06)" }}
        >
          <span className="text-xs" style={{ color: NAVY, fontFamily: F }}>
            {s.name}
          </span>
          <div className="flex items-center gap-2">
            <span
              className="text-xs"
              style={{ color: "#6B7A99", fontFamily: M }}
            >
              {s.amount.toLocaleString()}원/월
            </span>
            <button
              onClick={() =>
                setSubs((p) => {
                  const n = [...p];
                  n[i] = !n[i];
                  return n;
                })
              }
            >
              {subs[i] ? (
                <ToggleRight size={24} color={MINT} />
              ) : (
                <ToggleLeft size={24} color="#CBD5E1" />
              )}
            </button>
          </div>
        </div>
      ))}
      <ChipRow chips={["예산 수정", "구독 추가"]} onChip={() => {}} />
    </div>
  );
}

// ── Guardrail (Section 8) ─────────────────────────────────────────────────────
function GuardrailCard({ onAddMsg }: { onAddMsg: (m: ChatMsg) => void }) {
  return (
    <div>
      <div className="flex items-center gap-2 mb-2">
        <AlertTriangle size={15} color="#FF4D4F" />
        <p
          className="text-sm font-semibold"
          style={{ color: "#FF4D4F", fontFamily: F }}
        >
          금융 서비스 전용 안내
        </p>
      </div>
      <p
        className="text-xs leading-relaxed"
        style={{ color: "#7F1D1D", fontFamily: F }}
      >
        저는 금융 관련 질문만 도와드릴 수 있어요.
        <br />
        예: "잔액 확인", "이번 달 지출", "송금해줘"
      </p>
      <ChipRow
        chips={["잔액 확인", "소비 분석", "송금하기"]}
        onChip={(c) => {
          if (c === "잔액 확인") onAddMsg({ id: mid(), from: "ai-balance" });
          else if (c === "소비 분석")
            onAddMsg({ id: mid(), from: "ai-spending" });
          else onAddMsg({ id: mid(), from: "ai-transfer" });
        }}
      />
    </div>
  );
}

// ── Error message (Section 9) ──────────────────────────────────────────────────
function ErrorMessageCard({ text }: { text: string }) {
  return (
    <div>
      <div className="flex items-center gap-2 mb-2">
        <X size={15} color="#FF4D4F" />
        <p
          className="text-sm font-semibold"
          style={{ color: "#FF4D4F", fontFamily: F }}
        >
          처리 실패
        </p>
      </div>
      <p
        className="text-xs leading-relaxed"
        style={{ color: "#7F1D1D", fontFamily: F }}
      >
        {text}
      </p>
    </div>
  );
}

// ── Auto transfer (Section 9) ─────────────────────────────────────────────────
function AutoTransferCard({ onAddMsg }: { onAddMsg: (m: ChatMsg) => void }) {
  const [toggles, setToggles] = useState(autoTxItems.map((a) => a.active));
  return (
    <div>
      <div className="flex items-center gap-2 mb-3">
        <span className="text-lg">🔄</span>
        <p
          className="text-sm font-semibold"
          style={{ color: NAVY, fontFamily: F }}
        >
          자동 이체 목록
        </p>
      </div>
      {autoTxItems.map((a, i) => (
        <div
          key={a.name}
          className="flex items-center gap-3 py-3 border-b"
          style={{ borderColor: "rgba(15,30,61,0.06)" }}
        >
          <div className="flex-1">
            <p
              className="text-xs font-medium"
              style={{ color: NAVY, fontFamily: F }}
            >
              {a.name}
            </p>
            <p
              className="text-[10px]"
              style={{ color: "#6B7A99", fontFamily: F }}
            >
              {a.cycle}
            </p>
          </div>
          <p
            className="text-xs font-bold"
            style={{ color: NAVY, fontFamily: M }}
          >
            {a.amount.toLocaleString()}원
          </p>
          <button
            onClick={() =>
              setToggles((p) => {
                const n = [...p];
                n[i] = !n[i];
                return n;
              })
            }
          >
            {toggles[i] ? (
              <span className="text-xs font-medium" style={{ color: MINT }}>
                ✓
              </span>
            ) : (
              <span className="text-xs" style={{ color: "#CBD5E1" }}>
                ○
              </span>
            )}
          </button>
        </div>
      ))}
      <button
        onClick={() => onAddMsg({ id: mid(), from: "ai-autotransfer-form" })}
        className="mt-3 w-full py-2.5 rounded-xl text-xs font-medium flex items-center justify-center gap-1.5 border-2"
        style={{ borderColor: MINT, color: MINT, fontFamily: F }}
      >
        <Plus size={13} />
        자동 이체 추가
      </button>
    </div>
  );
}

function AutoTransferFormCard() {
  const [account, setAccount] = useState("");
  const [amtRaw, setAmtRaw] = useState("");
  const [day, setDay] = useState("");
  const [submitted, setSubmitted] = useState(false);
  const amtNum = Number(amtRaw) || 0;
  if (submitted)
    return (
      <div className="flex items-center gap-2 py-2">
        <div
          className="w-6 h-6 rounded-full flex items-center justify-center flex-shrink-0"
          style={{ background: "#52C41A" }}
        >
          <Check size={12} color="#fff" />
        </div>
        <p className="text-sm" style={{ color: NAVY, fontFamily: F }}>
          자동 이체가 등록되었습니다 ✓
        </p>
      </div>
    );
  const fields = [
    {
      label: "받는 계좌",
      value: account,
      set: setAccount,
      ph: "계좌번호 또는 이름",
      mono: false,
    },
    {
      label: "금액",
      value: fmtAmt(amtRaw),
      set: (v: string) => setAmtRaw(parseAmtInput(v)),
      ph: "0원",
      mono: true,
    },
    { label: "날짜", value: day, set: setDay, ph: "매월 ?일", mono: false },
  ];
  return (
    <div>
      <p
        className="text-xs font-semibold mb-2"
        style={{ color: NAVY, fontFamily: F }}
      >
        자동 이체 등록
      </p>
      {fields.map((fd) => (
        <div
          key={fd.label}
          className="flex items-center gap-3 py-2.5 border-b"
          style={{ borderColor: "rgba(15,30,61,0.06)" }}
        >
          <span
            className="text-xs w-[72px] flex-shrink-0"
            style={{ color: "#6B7A99", fontFamily: F }}
          >
            {fd.label}
          </span>
          <input
            className="flex-1 text-sm outline-none border-b-2 pb-0.5"
            style={{
              color: NAVY,
              fontFamily: fd.mono ? M : F,
              borderColor: MINT,
            }}
            placeholder={fd.ph}
            value={fd.value}
            onChange={(e) => fd.set(e.target.value)}
            inputMode={fd.mono ? "numeric" : "text"}
          />
        </div>
      ))}
      {amtNum > 0 && (
        <p
          className="text-xs mt-1 text-right"
          style={{ color: MINT, fontFamily: F }}
        >
          {kor(amtNum)}
        </p>
      )}
      <button
        onClick={() => setSubmitted(true)}
        className="mt-3 w-full py-2.5 rounded-xl text-sm font-semibold"
        style={{ background: MINT, color: NAVY, fontFamily: F }}
      >
        등록하기
      </button>
    </div>
  );
}

// ── Card info card ────────────────────────────────────────────────────────────
function CardInfoCard({ onAddMsg }: { onAddMsg: (m: ChatMsg) => void }) {
  const [activeCard, setActiveCard] = useState(0);
  const cards = [
    {
      name: "신한 Deep Dream",
      num: "5412 3456 7890 1234",
      exp: "11/27",
      bg: "linear-gradient(135deg,#0F1E3D 0%,#1a3a6b 60%,#2DD4BF 100%)",
    },
    {
      name: "카카오 체크카드",
      num: "9432 0011 2345 6789",
      exp: "03/26",
      bg: "linear-gradient(135deg,#FAE100 0%,#F59E0B 100%)",
    },
  ];
  const actions = [
    { e: "🚨", l: "분실신고" },
    { e: "💳", l: "한도설정" },
    {
      e: "📄",
      l: "청구서",
      fn: () => onAddMsg({ id: mid(), from: "ai-bill" }),
    },
    { e: "🔒", l: "카드 정지" },
  ];
  return (
    <div>
      <div className="flex items-center gap-2 mb-3">
        <span className="text-lg">💳</span>
        <p
          className="text-sm font-semibold"
          style={{ color: NAVY, fontFamily: F }}
        >
          내 카드
        </p>
      </div>
      {/* 카드 스택 */}
      <div className="relative mb-3" style={{ height: 130 }}>
        {cards.map((c, i) => (
          <button
            key={c.name}
            onClick={() => setActiveCard(i)}
            className="absolute w-full rounded-2xl p-4 text-white shadow-md transition-all duration-300"
            style={{
              background: c.bg,
              top: i * 12,
              zIndex: activeCard === i ? 10 : 9 - i,
              transform: activeCard === i ? "scale(1)" : "scale(0.96)",
              left: 0,
            }}
          >
            <p
              className="text-xs font-semibold opacity-90 mb-5"
              style={{ fontFamily: F }}
            >
              {c.name}
            </p>
            <p className="font-mono text-sm tracking-widest mb-2">{c.num}</p>
            <div className="flex justify-between items-end">
              <div>
                <p className="text-[9px] opacity-60">VALID THRU</p>
                <p className="text-xs font-mono">{c.exp}</p>
              </div>
              <p className="text-[10px] opacity-60">REALFINANCE</p>
            </div>
          </button>
        ))}
      </div>
      {/* 페이지 도트 */}
      <div className="flex justify-center gap-1.5 mb-3">
        {cards.map((_, i) => (
          <button
            key={i}
            onClick={() => setActiveCard(i)}
            className="h-1.5 rounded-full transition-all"
            style={{
              width: activeCard === i ? 16 : 5,
              background: activeCard === i ? MINT : "#CBD5E1",
            }}
          />
        ))}
      </div>
      {/* 액션 버튼 */}
      <div className="grid grid-cols-4 gap-2">
        {actions.map((a) => (
          <button
            key={a.l}
            onClick={a.fn}
            className="flex flex-col items-center gap-1.5 py-3 rounded-xl hover:opacity-80"
            style={{ background: "#F4F6FA" }}
          >
            <span className="text-xl">{a.e}</span>
            <span
              className="text-[10px] font-medium"
              style={{ color: NAVY, fontFamily: F }}
            >
              {a.l}
            </span>
          </button>
        ))}
      </div>
    </div>
  );
}

// ── Transfer confirm bubble (인라인 편집 + 액션 버튼) ────────────────────────
type TCMsg = Extract<ChatMsg, { from: "ai-transfer-confirm" }>;
function TransferConfirmBubble({
  msg,
  onConfirmSheet,
  onAddMsg,
}: {
  msg: TCMsg;
  onConfirmSheet: (d: ConfirmSheetData) => void;
  onAddMsg: (m: ChatMsg) => void;
}) {
  const [rec, setRec] = useState(msg.recipient);
  const [bank, setBank] = useState(msg.bank);
  const [acct, setAcct] = useState(msg.account);
  const [amtRaw, setAmtRaw] = useState(msg.amount.toString());
  const [ef, setEf] = useState<string | null>(null);
  const [resolved, setResolved] = useState(false);
  const amtNum = Number(amtRaw) || 0;

  // 인라인 편집 가능한 값 컴포넌트
  function IVal({
    field,
    value,
    set,
    mono = false,
  }: {
    field: string;
    value: string;
    set: (v: string) => void;
    mono?: boolean;
  }) {
    return (
      <span className="relative inline-block">
        <button
          onClick={() => setEf(ef === field ? null : field)}
          className="inline-flex items-center gap-0.5 hover:opacity-70 transition-opacity"
        >
          <span
            style={{
              fontFamily: mono ? M : F,
              color: NAVY,
              borderBottom: `1.5px dashed ${MINT}`,
              paddingBottom: 1,
            }}
          >
            {value}
          </span>
          <span style={{ fontSize: 10, color: MINT, marginLeft: 1 }}>✏️</span>
        </button>
        {ef === field && (
          <div
            className="absolute left-0 top-full z-20 mt-1 bg-white rounded-xl shadow-lg p-3"
            style={{ minWidth: 180, border: "1px solid rgba(15,30,61,0.1)" }}
          >
            <input
              autoFocus
              className="w-full text-sm outline-none border-b-2 pb-1"
              style={{
                borderColor: MINT,
                color: NAVY,
                fontFamily: mono ? M : F,
                background: "transparent",
              }}
              value={field === "amt" ? fmtAmt(amtRaw) : value}
              onChange={(e) =>
                field === "amt"
                  ? setAmtRaw(parseAmtInput(e.target.value))
                  : set(e.target.value)
              }
              onBlur={() => setEf(null)}
              onKeyDown={(e) => e.key === "Enter" && setEf(null)}
              inputMode={field === "amt" ? "numeric" : "text"}
            />
            {field === "amt" && amtNum > 0 && (
              <p
                className="text-[10px] mt-1"
                style={{ color: MINT, fontFamily: F }}
              >
                {kor(amtNum)}
              </p>
            )}
          </div>
        )}
      </span>
    );
  }

  const confirmRows = (timeLabel: string) => [
    { label: "받는 사람", value: rec },
    { label: "은행", value: bank },
    { label: "계좌번호", value: acct },
    { label: "금액", value: `${amtNum.toLocaleString()}원` },
    { label: "송금 시각", value: timeLabel },
  ];

  return (
    <div className="flex items-start gap-2">
      <AIAvatar />
      <div className="flex-1 min-w-0">
        {/* 대화형 말풍선 — 두 줄 텍스트, 각 값에 민트 점선 밑줄 + 편집 아이콘 */}
        <div
          className="rounded-2xl px-4 py-3.5 shadow-sm"
          style={{ background: GRAY_BG, borderRadius: "16px 16px 16px 4px" }}
        >
          {/* 첫째 줄: 수신자 정보 */}
          <div
            className="text-sm mb-1"
            style={{ color: NAVY, fontFamily: F, lineHeight: 1.7 }}
          >
            <IVal field="rec" value={rec} set={setRec} />
            <span style={{ color: "#6B7A99" }}>님 · </span>
            <IVal field="bank" value={bank} set={setBank} />
            <span style={{ color: "#6B7A99" }}> · </span>
            <IVal field="acct" value={acct} set={setAcct} mono />
            <span style={{ color: "#6B7A99" }}>에게</span>
          </div>
          {/* 둘째 줄: 금액 + 질문 */}
          <div
            className="text-sm"
            style={{ color: NAVY, fontFamily: F, lineHeight: 1.7 }}
          >
            <IVal
              field="amt"
              value={`${amtNum.toLocaleString()}원`}
              set={setAmtRaw}
              mono
            />
            <span>을 송금하시겠어요?</span>
          </div>
        </div>
        {!resolved && (
          <div className="flex gap-2 mt-2">
            <button
              onClick={() => {
                setResolved(true);
                onConfirmSheet({
                  title: "송금 확인",
                  rows: confirmRows("지금 즉시"),
                  onConfirm: () =>
                    onAddMsg({
                      id: mid(),
                      from: "ai-text",
                      text: `${rec}님께 ${amtNum.toLocaleString()}원 송금이 완료되었습니다 ✓`,
                      chips: ["잔액 확인", "거래 내역"],
                    }),
                });
              }}
              className="flex-1 py-2.5 rounded-xl text-sm font-semibold hover:opacity-90"
              style={{ background: MINT, color: NAVY, fontFamily: F }}
            >
              지금 송금
            </button>
            <button
              onClick={() => {
                setResolved(true);
                onConfirmSheet({
                  title: "예약 송금 확인",
                  rows: confirmRows("예약 (날짜 설정 필요)"),
                  onConfirm: () =>
                    onAddMsg({
                      id: mid(),
                      from: "ai-text",
                      text: `${rec}님께 ${amtNum.toLocaleString()}원 예약 송금이 등록되었습니다 ✓`,
                      chips: ["잔액 확인"],
                    }),
                });
              }}
              className="flex-1 py-2.5 rounded-xl text-sm font-medium border-2 hover:opacity-80"
              style={{ borderColor: MINT, color: MINT, fontFamily: F }}
            >
              예약 송금
            </button>
          </div>
        )}
        {resolved && (
          <p
            className="text-xs mt-1 ml-1"
            style={{ color: "#6B7A99", fontFamily: F }}
          >
            확인 중...
          </p>
        )}
      </div>
    </div>
  );
}

// ── ConfirmBottomSheet (공통 최종 확인 모달) ──────────────────────────────────
function ConfirmBottomSheet({
  data,
  onClose,
}: {
  data: ConfirmSheetData;
  onClose: () => void;
}) {
  const [done, setDone] = useState(false);
  return (
    <div
      className="fixed inset-0 z-50 flex items-end justify-center"
      style={{ background: "rgba(15,30,61,0.55)" }}
      onClick={(e) => e.target === e.currentTarget && onClose()}
    >
      <div
        className="w-full bg-white px-6 pt-5 pb-8 shadow-2xl"
        style={{ maxWidth: 480, borderRadius: "24px 24px 0 0" }}
      >
        {/* Handle */}
        <div className="w-10 h-1 bg-gray-200 rounded-full mx-auto mb-4" />
        {done ? (
          <div className="flex flex-col items-center py-6 gap-3">
            <div
              className="w-14 h-14 rounded-full flex items-center justify-center"
              style={{ background: MINT }}
            >
              <Check size={28} color={NAVY} strokeWidth={3} />
            </div>
            <p
              className="text-base font-bold"
              style={{ color: NAVY, fontFamily: F }}
            >
              완료되었습니다!
            </p>
            <button
              onClick={onClose}
              className="mt-2 px-8 py-3 rounded-2xl text-sm font-semibold"
              style={{ background: NAVY, color: "#fff", fontFamily: F }}
            >
              확인
            </button>
          </div>
        ) : (
          <>
            <p
              className="text-base font-bold text-center mb-5"
              style={{ color: NAVY, fontFamily: F }}
            >
              {data.title}
            </p>
            <div
              className="rounded-2xl p-4 mb-5"
              style={{ background: GRAY_BG }}
            >
              {data.rows.map((r) => (
                <div
                  key={r.label}
                  className="flex justify-between py-2.5 border-b last:border-0"
                  style={{ borderColor: "rgba(15,30,61,0.06)" }}
                >
                  <span
                    className="text-xs"
                    style={{ color: "#6B7A99", fontFamily: F }}
                  >
                    {r.label}
                  </span>
                  <span
                    className="text-sm font-semibold"
                    style={{
                      color: NAVY,
                      fontFamily: ["금액", "계좌번호"].includes(r.label)
                        ? M
                        : F,
                    }}
                  >
                    {r.value}
                  </span>
                </div>
              ))}
            </div>
            <div className="flex flex-col gap-2.5">
              <button
                onClick={() => {
                  setDone(true);
                  data.onConfirm();
                }}
                className="w-full py-3.5 rounded-xl text-sm font-semibold hover:opacity-90"
                style={{ background: MINT, color: NAVY, fontFamily: F }}
              >
                확인
              </button>
              <button
                onClick={onClose}
                className="w-full py-3.5 rounded-xl text-sm font-medium border-2"
                style={{
                  borderColor: "rgba(15,30,61,0.15)",
                  color: "#6B7A99",
                  fontFamily: F,
                }}
              >
                취소
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

// ── Message renderer ──────────────────────────────────────────────────────────
function MsgRenderer({
  msg,
  onAddMsg,
  onApproval,
  onConfirmSheet,
}: {
  msg: ChatMsg;
  onAddMsg: (m: ChatMsg) => void;
  onApproval: (d: ApprovalData) => void;
  onConfirmSheet: (d: ConfirmSheetData) => void;
}) {
  if (msg.from === "user")
    return (
      <div className="flex justify-end">
        <div
          className="max-w-[75%] px-4 py-3 text-sm leading-relaxed"
          style={{
            background: MINT,
            color: "#fff",
            borderRadius: "16px 16px 4px 16px",
            boxShadow: "0 1px 4px rgba(0,0,0,0.12)",
            fontFamily: F,
          }}
        >
          {msg.text}
        </div>
      </div>
    );
  if (msg.from === "ai-greet")
    return (
      <AIBubble>
        <p className="text-sm" style={{ color: NAVY, fontFamily: F }}>
          안녕하세요! 무엇을 도와드릴까요?
        </p>
        <div className="flex flex-wrap gap-2 mt-3">
          {(["송금하기", "잔액 확인", "소비 분석", "카드 청구서"] as const).map(
            (c) => (
              <button
                key={c}
                onClick={() =>
                  onAddMsg({ id: mid(), from: routeMsg(c) as ChatMsg["from"] })
                }
                className="px-3 py-1.5 rounded-full text-xs font-medium border hover:opacity-80"
                style={{
                  borderColor: MINT,
                  color: NAVY,
                  background: "#fff",
                  fontFamily: F,
                }}
              >
                {c}
              </button>
            ),
          )}
        </div>
      </AIBubble>
    );
  if (msg.from === "ai-text")
    return (
      <AIBubble>
        <p
          className="text-sm leading-relaxed"
          style={{ color: NAVY, fontFamily: F }}
        >
          {msg.text}
        </p>
        {msg.chips && (
          <ChipRow
            chips={msg.chips}
            onChip={(c) => {
              onAddMsg({ id: mid(), from: routeMsg(c) as ChatMsg["from"] });
            }}
          />
        )}
      </AIBubble>
    );
  if (msg.from === "ai-guardrail")
    return (
      <AIBubble>
        <GuardrailCard onAddMsg={onAddMsg} />
      </AIBubble>
    );
  if (msg.from === "ai-error")
    return (
      <AIBubble>
        <ErrorMessageCard text={msg.text} />
      </AIBubble>
    );
  if (msg.from === "ai-transfer")
    return (
      <AIBubble>
        <TransferCard prefill={msg.prefill} onApproval={onApproval} />
      </AIBubble>
    );
  if (msg.from === "ai-balance")
    return (
      <AIBubble>
        <BalanceCard onAddMsg={onAddMsg} />
      </AIBubble>
    );
  if (msg.from === "ai-account-detail")
    return (
      <AIBubble>
        <AccountDetailCard accountId={msg.accountId} />
      </AIBubble>
    );
  if (msg.from === "ai-spending")
    return (
      <AIBubble>
        <SpendingCard onAddMsg={onAddMsg} />
      </AIBubble>
    );
  if (msg.from === "ai-transactions")
    return (
      <AIBubble>
        <TransactionsCard />
      </AIBubble>
    );
  if (msg.from === "ai-bill")
    return (
      <AIBubble>
        <BillCard />
      </AIBubble>
    );
  if (msg.from === "ai-budget")
    return (
      <AIBubble>
        <BudgetCard />
      </AIBubble>
    );
  if (msg.from === "ai-autotransfer")
    return (
      <AIBubble>
        <AutoTransferCard onAddMsg={onAddMsg} />
      </AIBubble>
    );
  if (msg.from === "ai-autotransfer-form")
    return (
      <AIBubble>
        <AutoTransferFormCard />
      </AIBubble>
    );
  if (msg.from === "ai-card")
    return (
      <AIBubble>
        <CardInfoCard onAddMsg={onAddMsg} />
      </AIBubble>
    );

  if (msg.from === "ai-transfer-confirm")
    return (
      <TransferConfirmBubble
        msg={msg}
        onConfirmSheet={onConfirmSheet}
        onAddMsg={onAddMsg}
      />
    );

  if (msg.from === "ai-feature-list")
    return (
      <div className="flex items-start gap-2">
        <AIAvatar />
        <div className="flex-1 min-w-0">
          <div
            className="rounded-2xl p-4 shadow-sm mb-2"
            style={{ background: GRAY_BG, borderRadius: "16px 16px 16px 4px" }}
          >
            <p className="text-sm mb-3" style={{ color: NAVY, fontFamily: F }}>
              <b style={{ color: MINT }}>{msg.topic}</b>와 관련해서 아래 기능을
              이용하실 수 있어요.
            </p>
            <div className="space-y-2">
              {msg.features.map((f, i) => (
                <button
                  key={i}
                  onClick={() => {
                    onAddMsg({ id: mid(), from: f.action as ChatMsg["from"] });
                  }}
                  className="w-full flex items-center gap-3 p-3 rounded-xl text-left hover:opacity-80 transition-opacity border"
                  style={{
                    borderColor: "rgba(15,30,61,0.1)",
                    background: "#fff",
                  }}
                >
                  <span className="text-xl flex-shrink-0">{f.icon}</span>
                  <span
                    className="flex-1 text-sm font-medium"
                    style={{ color: NAVY, fontFamily: F }}
                  >
                    {f.label}
                  </span>
                  <ChevronDown
                    size={15}
                    color="#6B7A99"
                    style={{ transform: "rotate(-90deg)", flexShrink: 0 }}
                  />
                </button>
              ))}
            </div>
          </div>
        </div>
      </div>
    );

  return null;
}

// ── App root ──────────────────────────────────────────────────────────────────
export default function App() {
  const [isLoggedIn, setIsLoggedIn] = useState(
    () => sessionStorage.getItem("rf_logged_in") === "1",
  );
  const [msgs, setMsgs] = useState<ChatMsg[]>(() => {
    const saved = sessionStorage.getItem("rf_chat_msgs");
    if (saved) {
      try {
        return JSON.parse(saved);
      } catch {
        /* fall through to default */
      }
    }
    return [{ id: 0, from: "ai-greet" }];
  });
  const [input, setInput] = useState("");
  const [approval, setApproval] = useState<ApprovalData | null>(null);
  const [confirmSheet, setConfirmSheet] = useState<ConfirmSheetData | null>(
    null,
  );
  const [showSidebar, setShowSidebar] = useState(false);
  const chatEndRef = useRef<HTMLDivElement>(null);

  // 미해결 인라인 송금 확인이 있으면 입력 비활성화
  const inputBlocked =
    msgs.some((m) => m.from === "ai-transfer-confirm") &&
    !msgs.some(
      (m) => m.from === "ai-text" && (m as any).text?.includes("완료"),
    );

  useEffect(() => {
    sessionStorage.setItem("rf_chat_msgs", JSON.stringify(msgs));
  }, [msgs]);

  const addMsg = (m: ChatMsg) => setMsgs((prev) => [...prev, m]);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [msgs]);

  const send = () => {
    const text = input.trim();
    if (!text) return;
    setInput("");
    const aid = mid();

    // 연락처 형태 자동 감지: 이름 + 은행 or 이름 + 계좌 or 은행 + 계좌
    const contactInfo = parseContactText(text);
    const isContactInfo =
      (contactInfo.name && (contactInfo.bank || contactInfo.account)) ||
      !!(contactInfo.bank && contactInfo.account);

    const type = isContactInfo ? "ai-transfer" : routeMsg(text);
    const transfer = parseTransferIntent(text);

    setMsgs((prev) => {
      const userMsg: ChatMsg = { id: mid(), from: "user", text };
      let aiMsg: ChatMsg;

      // 기능 발견 쿼리 ("카드 관련해서 뭐 할 수 있어?" 등)
      const discoveryKW = [
        "뭐 할 수 있",
        "어떤 기능",
        "할 수 있어",
        "뭐가 있",
        "관련해서",
      ];
      const isDiscovery = discoveryKW.some((k) => text.includes(k));

      // 에러 메시지 UI 데모 호출 — 구체적인 실패 시나리오 키워드 매칭
      const errorKW = [
        "에러",
        "오류",
        "실패",
        "안 돼",
        "안돼",
        "부족",
        "잘못",
        "틀",
        "한도",
        "네트워크",
        "연결",
      ];
      const isErrorDemo = errorKW.some((k) => text.includes(k));
      const resolveErrorText = (t: string): string => {
        if (t.includes("잔액") && t.includes("부족"))
          return "잔액이 부족합니다.";
        if (t.includes("계좌") && (t.includes("잘못") || t.includes("틀")))
          return "잘못된 계좌번호입니다.";
        if (t.includes("한도")) return "1회 송금 한도를 초과했습니다.";
        if (t.includes("네트워크") || t.includes("연결"))
          return "네트워크 연결을 확인해주세요.";
        return "요청을 처리하지 못했습니다. 다시 시도해주세요.";
      };

      if (isDiscovery) {
        let topic = "금융 서비스";
        let features = CARD_FEATURES;
        if (text.includes("카드")) {
          topic = "카드";
          features = CARD_FEATURES;
        } else if (text.includes("송금") || text.includes("이체")) {
          topic = "이체/송금";
          features = TRANSFER_FEATURES;
        } else if (
          text.includes("계좌") ||
          text.includes("잔액") ||
          text.includes("조회")
        ) {
          topic = "계좌";
          features = ACCOUNT_FEATURES;
        }
        aiMsg = { id: aid, from: "ai-feature-list", topic, features };
      } else if (isErrorDemo) {
        aiMsg = { id: aid, from: "ai-error", text: resolveErrorText(text) };
      } else if (type === "ai-text") {
        aiMsg = {
          id: aid,
          from: "ai-text",
          text: "네, 무엇을 도와드릴까요? 아래에서 선택해주세요.",
          chips: [
            "잔액 확인",
            "소비 분석",
            "송금하기",
            "카드 청구서",
            "거래 내역",
          ],
        };
      } else if (type === "ai-transfer") {
        const name = contactInfo.name || transfer?.name;
        const bank = contactInfo.bank;
        const account = contactInfo.account;
        const amtRaw = transfer?.amtRaw;
        // 이름 + 은행 + 계좌 + 금액 모두 파싱되면 대화형 확인 말풍선
        if (name && bank && account && amtRaw) {
          aiMsg = {
            id: aid,
            from: "ai-transfer-confirm",
            recipient: name,
            bank,
            account,
            amount: Number(amtRaw),
            scheduled: transfer?.scheduled,
          };
        } else {
          const prefill: TransferPrefill = {};
          if (name) prefill.name = name;
          if (bank) prefill.bank = bank;
          if (account) prefill.account = account;
          if (amtRaw) prefill.amtRaw = amtRaw;
          if (transfer?.scheduled) prefill.scheduled = transfer.scheduled;
          aiMsg = {
            id: aid,
            from: "ai-transfer",
            prefill: Object.keys(prefill).length ? prefill : undefined,
          };
        }
      } else {
        aiMsg = { id: aid, from: type as ChatMsg["from"] };
      }
      return [...prev, userMsg, aiMsg];
    });
  };

  return (
    <div
      className="flex h-screen overflow-hidden justify-center"
      style={{ background: isLoggedIn ? "#F0F2F5" : NAVY }}
    >
      {/* 로그인 화면 */}
      {!isLoggedIn && (
        <div className="w-full flex flex-col" style={{ maxWidth: 480 }}>
          <LoginScreen
            onLogin={() => {
              sessionStorage.setItem("rf_logged_in", "1");
              setIsLoggedIn(true);
            }}
          />
        </div>
      )}

      {/* 채팅 화면 (로그인 후) */}
      {
        isLoggedIn && (
          <>
            {/* Main chat column */}
            <div
              className="w-full flex flex-col bg-white overflow-hidden"
              style={{ maxWidth: 480, boxShadow: "0 0 40px rgba(0,0,0,0.08)" }}
            >
              {/* Header */}
              <div
                className="flex items-center justify-between px-5 py-4 flex-shrink-0"
                style={{ background: NAVY }}
              >
                <button
                  onClick={() => setMsgs([{ id: mid(), from: "ai-greet" }])}
                  className="flex items-center gap-2 hover:opacity-80 transition-opacity"
                >
                  <div
                    className="w-8 h-8 rounded-full flex items-center justify-center"
                    style={{ background: MINT }}
                  >
                    <Bot size={18} color={NAVY} />
                  </div>
                  <span
                    className="font-bold text-white text-lg"
                    style={{ fontFamily: "'DM Sans',sans-serif" }}
                  >
                    RealFinance
                  </span>
                </button>
                {/* 햄버거 — 모바일·PC 모두 표시 */}
                <div className="flex items-center gap-3">
                  <button
                    onClick={() => {
                      sessionStorage.removeItem("rf_chat_msgs");
                      setMsgs([{ id: mid(), from: "ai-greet" }]);
                    }}
                    className="text-white/70 hover:text-white transition-colors"
                    aria-label="채팅 로그 지우기"
                  >
                    <Trash2 size={20} />
                  </button>
                  <button
                    onClick={() => setShowSidebar(true)}
                    className="text-white/70 hover:text-white transition-colors"
                    aria-label="메뉴 열기"
                  >
                    <Menu size={22} />
                  </button>
                </div>
              </div>

              {/* Chat stream */}
              <div
                className="flex-1 overflow-y-auto px-4 py-4 space-y-4"
                style={{ background: "#F8F9FB" }}
              >
                {msgs.map((m) => (
                  <MsgRenderer
                    key={m.id}
                    msg={m}
                    onAddMsg={addMsg}
                    onApproval={setApproval}
                    onConfirmSheet={setConfirmSheet}
                  />
                ))}
                <div ref={chatEndRef} />
              </div>

              {/* Input bar */}
              <div
                className="px-4 py-3 bg-white border-t flex-shrink-0 transition-opacity"
                style={{
                  borderColor: "rgba(15,30,61,0.08)",
                  opacity: inputBlocked ? 0.45 : 1,
                  pointerEvents: inputBlocked ? "none" : "auto",
                }}
              >
                <div
                  className="flex items-center gap-2 rounded-2xl px-4 py-2.5"
                  style={{ background: GRAY_BG }}
                >
                  <button>
                    <Mic size={20} color="#6B7A99" />
                  </button>
                  <input
                    className="flex-1 bg-transparent outline-none text-sm"
                    style={{ fontFamily: F, color: NAVY }}
                    placeholder={
                      inputBlocked
                        ? "버튼을 선택해주세요..."
                        : "무엇이든 물어보세요 (예: 이동건 신한 110 222 221 111)"
                    }
                    value={input}
                    onChange={(e) => setInput(e.target.value)}
                    onKeyDown={(e) =>
                      e.key === "Enter" &&
                      !e.shiftKey &&
                      !inputBlocked &&
                      (e.preventDefault(), send())
                    }
                    disabled={inputBlocked}
                  />
                  <button
                    onClick={!inputBlocked ? send : undefined}
                    className="w-8 h-8 rounded-full flex items-center justify-center transition-opacity"
                    style={{
                      background: MINT,
                      opacity: input && !inputBlocked ? 1 : 0.5,
                    }}
                  >
                    <Send size={14} color={NAVY} />
                  </button>
                </div>
              </div>
            </div>

            {/* 사이드바 오버레이 — 모바일·PC 공통 */}
            {showSidebar && (
              <div
                className="fixed inset-0 z-50 flex"
                style={{ background: "rgba(15,30,61,0.5)" }}
                onClick={() => setShowSidebar(false)}
              >
                <div
                  onClick={(e) => e.stopPropagation()}
                  style={{
                    width: "min(320px, 88vw)",
                    height: "100%",
                    animation: "slideInLeft 0.22s ease",
                  }}
                >
                  <SidebarDrawer
                    showCloseButton={true}
                    onClose={() => setShowSidebar(false)}
                    onLogout={() => {
                      sessionStorage.removeItem("rf_logged_in");
                      setShowSidebar(false);
                      setIsLoggedIn(false);
                      setMsgs([{ id: mid(), from: "ai-greet" }]);
                    }}
                    onMenuSelect={(item) => {
                      setShowSidebar(false);
                      const sidebarMsgMap: Record<string, ChatMsg["from"]> = {
                        "월간 소비 분석": "ai-spending",
                        "예산 관리": "ai-budget",
                        "거래 내역 조회": "ai-transactions",
                        "잔액 조회": "ai-balance",
                        "계좌 정보 조회": "ai-balance",
                        "카드 정보 조회": "ai-card",
                        "카드 청구서 확인": "ai-bill",
                        "본인 계좌 이체": "ai-transfer",
                        "타인 송금": "ai-transfer",
                        "자동 이체 설정": "ai-autotransfer",
                      };
                      if (item === "채팅 홈") {
                        setMsgs([{ id: mid(), from: "ai-greet" }]);
                      } else {
                        const msgType = sidebarMsgMap[item];
                        if (msgType) addMsg({ id: mid(), from: msgType });
                      }
                    }}
                  />
                </div>
              </div>
            )}
          </>
        ) /* isLoggedIn end */
      }

      {/* 공통 최종 확인 바텀시트 */}
      {confirmSheet && (
        <ConfirmBottomSheet
          data={confirmSheet}
          onClose={() => setConfirmSheet(null)}
        />
      )}

      {/* Approval bottom sheet overlay */}
      {approval && (
        <div
          className="fixed inset-0 z-50 flex items-end justify-center"
          style={{ background: "rgba(15,30,61,0.5)" }}
          onClick={(e) => e.target === e.currentTarget && setApproval(null)}
        >
          <div
            className="w-full bg-white px-6 pt-5 pb-8"
            style={{ maxWidth: 480, borderRadius: "24px 24px 0 0" }}
          >
            <div className="w-10 h-1 bg-gray-200 rounded-full mx-auto mb-5" />
            <p
              className="text-base font-semibold text-center mb-5"
              style={{ color: NAVY, fontFamily: F }}
            >
              정말 {approval.name}님께 {approval.amount.toLocaleString()}원을
              송금하시겠습니까?
            </p>
            <div
              className="rounded-2xl p-4 mb-5"
              style={{ background: GRAY_BG }}
            >
              <div className="flex justify-between text-sm mb-2">
                <span style={{ color: "#6B7A99", fontFamily: F }}>
                  받는 사람
                </span>
                <span style={{ color: NAVY, fontFamily: F, fontWeight: 600 }}>
                  {approval.name}
                </span>
              </div>
              <div className="flex justify-between text-sm">
                <span style={{ color: "#6B7A99", fontFamily: F }}>금액</span>
                <span style={{ color: NAVY, fontFamily: M, fontWeight: 700 }}>
                  {approval.amount.toLocaleString()}원
                </span>
              </div>
            </div>
            <div className="flex gap-3">
              <button
                onClick={() => setApproval(null)}
                className="flex-1 py-3 rounded-xl text-sm font-medium border-2"
                style={{
                  borderColor: "#CBD5E1",
                  color: "#6B7A99",
                  fontFamily: F,
                }}
              >
                취소
              </button>
              <button
                onClick={() => {
                  approval.onConfirm();
                  setApproval(null);
                  addMsg({
                    id: mid(),
                    from: "ai-text",
                    text: `${approval.name}님께 ${approval.amount.toLocaleString()}원 송금이 완료되었습니다 ✓`,
                    chips: ["잔액 확인", "거래 내역"],
                  });
                }}
                className="flex-1 py-3 rounded-xl text-sm font-semibold hover:opacity-90"
                style={{ background: MINT, color: NAVY, fontFamily: F }}
              >
                확인
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
