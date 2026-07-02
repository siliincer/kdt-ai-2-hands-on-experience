import { useState } from "react";
import { useNavigate } from "react-router";

const NAVY = "#0F1E3D";
const MINT = "#2DD4BF";
const F = "'Noto Sans KR',sans-serif";

// ── CardInfoCard ──────────────────────────────────────────────────────────────
function CardInfoCard({ onNavigate }: { onNavigate: (path: string) => void }) {
  const [activeCard, setActiveCard] = useState(0);
  const cards = [
    { name: "신한 Deep Dream", num: "5412 3456 7890 1234", exp: "11/27", bg: "linear-gradient(135deg,#0F1E3D 0%,#1a3a6b 60%,#2DD4BF 100%)" },
    { name: "카카오 체크카드", num: "9432 0011 2345 6789", exp: "03/26", bg: "linear-gradient(135deg,#FAE100 0%,#F59E0B 100%)" },
  ];
  const actions = [
    { e: "🚨", l: "분실신고", fn: undefined as (() => void) | undefined },
    { e: "💳", l: "한도설정", fn: undefined as (() => void) | undefined },
    { e: "📄", l: "청구서", fn: () => onNavigate("/bill") },
    { e: "🔒", l: "카드 정지", fn: undefined as (() => void) | undefined },
  ];
  return (
    <div>
      <div className="flex items-center gap-2 mb-3"><span className="text-lg">💳</span><p className="text-sm font-semibold" style={{ color: NAVY, fontFamily: F }}>내 카드</p></div>
      {/* 카드 스택 */}
      <div className="relative mb-3" style={{ height: 130 }}>
        {cards.map((c, i) => (
          <button key={c.name} onClick={() => setActiveCard(i)}
            className="absolute w-full rounded-2xl p-4 text-white shadow-md transition-all duration-300"
            style={{ background: c.bg, top: i * 12, zIndex: activeCard === i ? 10 : 9 - i, transform: activeCard === i ? "scale(1)" : "scale(0.96)", left: 0 }}>
            <p className="text-xs font-semibold opacity-90 mb-5" style={{ fontFamily: F }}>{c.name}</p>
            <p className="font-mono text-sm tracking-widest mb-2">{c.num}</p>
            <div className="flex justify-between items-end">
              <div><p className="text-[9px] opacity-60">VALID THRU</p><p className="text-xs font-mono">{c.exp}</p></div>
              <p className="text-[10px] opacity-60">REALFINANCE</p>
            </div>
          </button>
        ))}
      </div>
      {/* 페이지 도트 */}
      <div className="flex justify-center gap-1.5 mb-3">
        {cards.map((_, i) => <button key={i} onClick={() => setActiveCard(i)} className="h-1.5 rounded-full transition-all" style={{ width: activeCard === i ? 16 : 5, background: activeCard === i ? MINT : "#CBD5E1" }} />)}
      </div>
      {/* 액션 버튼 */}
      <div className="grid grid-cols-4 gap-2">
        {actions.map(a => (
          <button key={a.l} onClick={a.fn} className="flex flex-col items-center gap-1.5 py-3 rounded-xl hover:opacity-80" style={{ background: "#F4F6FA" }}>
            <span className="text-xl">{a.e}</span>
            <span className="text-[10px] font-medium" style={{ color: NAVY, fontFamily: F }}>{a.l}</span>
          </button>
        ))}
      </div>
    </div>
  );
}

// ── Route ─────────────────────────────────────────────────────────────────────
export default function CardRoute() {
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
            💳 카드 정보
          </span>
        </div>
        <div className="flex-1 overflow-y-auto px-4 py-4">
          <CardInfoCard onNavigate={navigate} />
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
