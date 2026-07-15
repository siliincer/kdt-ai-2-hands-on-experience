import { useState } from "react";
import { useNavigate } from "react-router";

const NAVY = "#0F1E3D";
const MINT = "#2DD4BF";
const F = "'Noto Sans KR',sans-serif";
const M = "'DM Mono',monospace";

// ── Data ──────────────────────────────────────────────────────────────────────
const accounts = [
  { id: 1, bank: "신한은행", alias: "입출금통장", tail: "4200", balance: 8200000, color: "#0052A3" },
  { id: 2, bank: "카카오뱅크", alias: "세이프박스", tail: "1234", balance: 4650000, color: "#FAE100" },
];

const ALL_TX = [
  { id: 601, name: "급여 입금", emoji: "💰", date: "06.25 09:00", month: "2025-06", day: 25, amount: 3200000, type: "in" as const },
  { id: 602, name: "월세 이서연", emoji: "🏠", date: "06.01 09:00", month: "2025-06", day: 1, amount: -550000, type: "out" as const },
  { id: 603, name: "KT 통신비", emoji: "📱", date: "06.05 00:01", month: "2025-06", day: 5, amount: -55000, type: "out" as const },
  { id: 604, name: "스타벅스", emoji: "☕", date: "06.28 14:23", month: "2025-06", day: 28, amount: -7500, type: "out" as const },
];

// ── AccountDetailCard ─────────────────────────────────────────────────────────
function AccountDetailCard({ accountId, onNavigate }: { accountId: number; onNavigate: (path: string) => void }) {
  const a = accounts.find(ac => ac.id === accountId)!;
  if (!a) return null;
  return (
    <div>
      <div className="rounded-2xl p-4 text-white mb-3" style={{ background: "linear-gradient(135deg,#0F1E3D 0%,#1a3a6b 100%)" }}>
        <p className="text-xs opacity-70 mb-1" style={{ fontFamily: F }}>{a.bank} · {a.alias} ···{a.tail}</p>
        <p className="text-2xl font-bold" style={{ fontFamily: "'DM Sans',sans-serif" }}>{a.balance.toLocaleString()}원</p>
      </div>
      <div className="grid grid-cols-4 gap-2 mb-3">
        {["입금", "출금", "이체", "상세"].map(l => (
          <button key={l} onClick={l === "이체" ? () => onNavigate("/transfer") : undefined} className="py-2 rounded-xl text-xs font-medium" style={{ background: "#F4F6FA", color: NAVY, fontFamily: F }}>{l}</button>
        ))}
      </div>
      <p className="text-xs font-semibold mb-2" style={{ color: "#6B7A99", fontFamily: F }}>최근 거래</p>
      {ALL_TX.filter(t => t.month === "2025-06").slice(0, 4).map(tx => (
        <div key={tx.id} className="flex items-center gap-2 py-2 border-b last:border-0" style={{ borderColor: "rgba(15,30,61,0.06)" }}>
          <span className="text-sm">{tx.emoji}</span>
          <div className="flex-1"><p className="text-xs" style={{ color: NAVY, fontFamily: F }}>{tx.name}</p></div>
          <p className="text-xs font-bold" style={{ color: tx.type === "in" ? "#52C41A" : NAVY, fontFamily: M }}>{tx.type === "in" ? "+" : ""}{Math.abs(tx.amount).toLocaleString()}원</p>
          <p className="text-[10px]" style={{ color: "#6B7A99", fontFamily: M }}>{tx.date}</p>
        </div>
      ))}
    </div>
  );
}

// ── BalanceCard ───────────────────────────────────────────────────────────────
function BalanceCard({ onSelectAccount, onNavigate }: { onSelectAccount: (id: number) => void; onNavigate: (path: string) => void }) {
  const total = accounts.reduce((s, a) => s + a.balance, 0);
  return (
    <div>
      <div className="flex items-center gap-2 mb-3"><span className="text-lg">💳</span><p className="text-sm font-semibold" style={{ color: NAVY, fontFamily: F }}>내 자산 현황</p></div>
      <p className="text-2xl font-bold" style={{ color: NAVY, fontFamily: "'DM Sans',sans-serif" }}>{total.toLocaleString()}원</p>
      <p className="text-xs mb-3" style={{ color: "#6B7A99", fontFamily: F }}>총 자산</p>
      <div className="border-t" style={{ borderColor: "rgba(15,30,61,0.06)" }}>
        {accounts.map(a => (
          <button key={a.id} onClick={() => onSelectAccount(a.id)}
            className="w-full flex items-center gap-3 py-3 border-b text-left hover:opacity-80 transition-opacity" style={{ borderColor: "rgba(15,30,61,0.06)" }}>
            <div className="w-8 h-8 rounded-lg flex items-center justify-center text-white text-xs font-bold flex-shrink-0" style={{ background: a.color }}>{a.bank[0]}</div>
            <div className="flex-1">
              <p className="text-xs font-medium" style={{ color: NAVY, fontFamily: F }}>{a.bank} <span style={{ color: "#6B7A99" }}>···{a.tail}</span></p>
              <p className="text-sm font-bold" style={{ color: NAVY, fontFamily: M }}>{a.balance.toLocaleString()}원</p>
            </div>
            <button onClick={e => { e.stopPropagation(); onNavigate("/transfer"); }} className="text-xs px-2.5 py-1 rounded-lg" style={{ background: MINT + "20", color: MINT, fontFamily: F }}>이체</button>
          </button>
        ))}
      </div>
      <div className="flex flex-wrap gap-2 mt-3">
        <button onClick={() => onNavigate("/transactions")} className="px-3 py-1.5 rounded-full text-xs font-medium border hover:opacity-80 transition-opacity" style={{ borderColor: MINT, color: NAVY, background: "#fff", fontFamily: F }}>거래내역 보기</button>
        <button onClick={() => onNavigate("/bill")} className="px-3 py-1.5 rounded-full text-xs font-medium border hover:opacity-80 transition-opacity" style={{ borderColor: MINT, color: NAVY, background: "#fff", fontFamily: F }}>카드 청구서</button>
        <button onClick={() => onNavigate("/transfer")} className="px-3 py-1.5 rounded-full text-xs font-medium border hover:opacity-80 transition-opacity" style={{ borderColor: MINT, color: NAVY, background: "#fff", fontFamily: F }}>계좌 이체</button>
      </div>
    </div>
  );
}

// ── Route ─────────────────────────────────────────────────────────────────────
export default function BalanceRoute() {
  const navigate = useNavigate();
  const [selectedAccountId, setSelectedAccountId] = useState<number | null>(null);

  return (
    <div className="flex h-screen overflow-hidden justify-center" style={{ background: "#F0F2F5" }}>
      <div className="w-full flex flex-col bg-white" style={{ maxWidth: 480, boxShadow: "0 0 40px rgba(0,0,0,0.08)" }}>
        <div className="flex items-center gap-3 px-5 py-4 flex-shrink-0" style={{ background: NAVY }}>
          <button
            onClick={() => selectedAccountId ? setSelectedAccountId(null) : navigate(-1)}
            className="text-white/70 hover:text-white transition-colors"
            aria-label="뒤로가기"
          >
            ←
          </button>
          <span className="font-bold text-white text-base" style={{ fontFamily: "'DM Sans',sans-serif" }}>
            💳 {selectedAccountId ? "계좌 상세" : "잔액 조회"}
          </span>
        </div>
        <div className="flex-1 overflow-y-auto px-4 py-4">
          {selectedAccountId
            ? <AccountDetailCard accountId={selectedAccountId} onNavigate={navigate} />
            : <BalanceCard onSelectAccount={setSelectedAccountId} onNavigate={navigate} />
          }
        </div>
        {/* AC4: return-to-chat nav + 채팅 초기화 stub */}
        <div className="flex gap-2 px-4 py-3 border-t flex-shrink-0" style={{ borderColor: "rgba(15,30,61,0.08)" }}>
          <button
            onClick={() => navigate("/")}
            className="flex-1 py-2 rounded-xl text-xs font-medium border"
            style={{ borderColor: MINT, color: NAVY, fontFamily: F }}
          >
            채팅으로 돌아가기
          </button>
          <button
            onClick={() => { sessionStorage.removeItem('rf_chat_msgs'); navigate("/"); }}
            className="flex-1 py-2 rounded-xl text-xs font-medium"
            style={{ background: "#F4F6FA", color: "#6B7A99", fontFamily: F }}
          >
            채팅 초기화
          </button>
        </div>
      </div>
    </div>
  );
}
