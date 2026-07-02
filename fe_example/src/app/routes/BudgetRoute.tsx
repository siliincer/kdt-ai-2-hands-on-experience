import { useState } from "react";
import { useNavigate } from "react-router";
import { ToggleLeft, ToggleRight } from "lucide-react";

const NAVY = "#0F1E3D";
const MINT = "#2DD4BF";
const F = "'Noto Sans KR',sans-serif";
const M = "'DM Mono',monospace";

// ── Data ──────────────────────────────────────────────────────────────────────
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

// ── BudgetCard ────────────────────────────────────────────────────────────────
function BudgetCard() {
  const [subs, setSubs] = useState(subItems.map(s => s.active));
  return (
    <div>
      <div className="flex items-center gap-2 mb-3"><span className="text-lg">🎯</span><p className="text-sm font-semibold" style={{ color: NAVY, fontFamily: F }}>예산 현황</p></div>
      <div className="space-y-3 mb-4">
        {budgetItems.map(b => {
          const pct = Math.round((b.used / b.total) * 100);
          const color = pct >= 100 ? "#FF4D4F" : pct >= 80 ? "#F59E0B" : "#52C41A";
          return (
            <div key={b.cat}>
              <div className="flex justify-between items-center mb-1">
                <span className="text-xs font-medium" style={{ color: NAVY, fontFamily: F }}>{b.cat}{pct >= 100 && " ⚠️"}</span>
                <span className="text-[10px]" style={{ color: "#6B7A99", fontFamily: M }}>{b.used.toLocaleString()} / {b.total.toLocaleString()}원</span>
              </div>
              <div className="w-full h-2.5 rounded-full" style={{ background: "#E8EDF5" }}>
                <div className="h-2.5 rounded-full" style={{ width: `${Math.min(pct, 100)}%`, background: color }} />
              </div>
              <p className="text-[10px] text-right mt-0.5 font-bold" style={{ color, fontFamily: M }}>{pct}%</p>
            </div>
          );
        })}
      </div>
      <p className="text-xs font-semibold mb-2" style={{ color: "#6B7A99", fontFamily: F }}>반복 결제</p>
      {subItems.map((s, i) => (
        <div key={s.name} className="flex items-center justify-between py-2 border-b" style={{ borderColor: "rgba(15,30,61,0.06)" }}>
          <span className="text-xs" style={{ color: NAVY, fontFamily: F }}>{s.name}</span>
          <div className="flex items-center gap-2">
            <span className="text-xs" style={{ color: "#6B7A99", fontFamily: M }}>{s.amount.toLocaleString()}원/월</span>
            <button onClick={() => setSubs(p => { const n = [...p]; n[i] = !n[i]; return n; })}>
              {subs[i] ? <ToggleRight size={24} color={MINT} /> : <ToggleLeft size={24} color="#CBD5E1" />}
            </button>
          </div>
        </div>
      ))}
      <div className="flex flex-wrap gap-2 mt-3">
        <button className="px-3 py-1.5 rounded-full text-xs font-medium border hover:opacity-80 transition-opacity" style={{ borderColor: MINT, color: NAVY, background: "#fff", fontFamily: F }}>예산 수정</button>
        <button className="px-3 py-1.5 rounded-full text-xs font-medium border hover:opacity-80 transition-opacity" style={{ borderColor: MINT, color: NAVY, background: "#fff", fontFamily: F }}>구독 추가</button>
      </div>
    </div>
  );
}

// ── Route ─────────────────────────────────────────────────────────────────────
export default function BudgetRoute() {
  const navigate = useNavigate();
  return (
    <div className="flex h-screen overflow-hidden justify-center" style={{ background: "#F0F2F5" }}>
      <div className="w-full flex flex-col bg-white" style={{ maxWidth: 480, boxShadow: "0 0 40px rgba(0,0,0,0.08)" }}>
        <div className="flex items-center gap-3 px-5 py-4 flex-shrink-0" style={{ background: NAVY }}>
          <button
            onClick={() => navigate(-1)}
            className="text-white/70 hover:text-white transition-colors"
            aria-label="뒤로가기"
          >
            ←
          </button>
          <span className="font-bold text-white text-base" style={{ fontFamily: "'DM Sans',sans-serif" }}>
            🎯 예산 관리
          </span>
        </div>
        <div className="flex-1 overflow-y-auto px-4 py-4">
          <BudgetCard />
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
            onClick={() => { /* stub: 채팅 초기화 — no persistence wired */ }}
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
