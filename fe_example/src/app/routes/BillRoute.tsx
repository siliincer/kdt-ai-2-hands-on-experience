import { useState } from "react";
import { useNavigate } from "react-router";
import { X } from "lucide-react";
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid,
  Tooltip as RChartTip, ResponsiveContainer,
} from "recharts";

const NAVY = "#0F1E3D";
const MINT = "#2DD4BF";
const F = "'Noto Sans KR',sans-serif";
const M = "'DM Mono',monospace";

// ── Data ──────────────────────────────────────────────────────────────────────
const billMD = [
  { month: "1월", amount: 320000, cats: [{ name: "식비", chg: 0 }, { name: "교통비", chg: 0 }, { name: "쇼핑", chg: 0 }] },
  { month: "2월", amount: 415000, cats: [{ name: "식비", chg: 20000 }, { name: "교통비", chg: 5000 }, { name: "쇼핑", chg: 70000 }] },
  { month: "3월", amount: 280000, cats: [{ name: "식비", chg: -30000 }, { name: "교통비", chg: -20000 }, { name: "쇼핑", chg: -85000 }] },
  { month: "4월", amount: 510000, cats: [{ name: "식비", chg: 45000 }, { name: "교통비", chg: 10000 }, { name: "쇼핑", chg: 175000 }] },
  { month: "5월", amount: 390000, cats: [{ name: "식비", chg: -30000 }, { name: "교통비", chg: 10000 }, { name: "쇼핑", chg: -100000 }] },
  { month: "6월", amount: 847000, cats: [{ name: "식비", chg: 45000 }, { name: "교통비", chg: 13500 }, { name: "쇼핑", chg: 175000 }] },
];

// ── BillCard ──────────────────────────────────────────────────────────────────
function BillCard() {
  const [selMonth, setSelMonth] = useState<string | null>(null);
  const selData = billMD.find(m => m.month === selMonth);

  const BillTip = ({ active, payload, label }: any) => {
    if (!active || !payload?.length) return null;
    const data = billMD.find(m => m.month === label); if (!data) return null;
    return (
      <div className="bg-white rounded-xl p-3 shadow-lg" style={{ border: "1px solid rgba(15,30,61,0.1)", minWidth: 150 }}>
        <p className="text-xs font-bold mb-1.5" style={{ color: NAVY, fontFamily: F }}>{label} · {data.amount.toLocaleString()}원</p>
        {data.cats.map(c => <div key={c.name} className="flex justify-between text-[10px] mb-0.5"><span style={{ color: "#6B7A99", fontFamily: F }}>{c.name}</span><span style={{ color: c.chg > 0 ? "#FF4D4F" : c.chg < 0 ? "#3B82F6" : "#6B7A99", fontFamily: M }}>{c.chg === 0 ? "–" : (c.chg > 0 ? "↑" : "↓") + Math.abs(c.chg / 1000).toFixed(0) + "k"}</span></div>)}
      </div>
    );
  };

  return (
    <div>
      <div className="flex items-center gap-2 mb-2"><span className="text-lg">💳</span><p className="text-sm font-semibold" style={{ color: NAVY, fontFamily: F }}>6월 카드 청구서</p></div>
      <p className="text-2xl font-bold" style={{ color: NAVY, fontFamily: "'DM Sans',sans-serif" }}>847,000원</p>
      <p className="text-xs mb-3" style={{ color: "#6B7A99", fontFamily: F }}>결제일 7월 15일</p>
      <p className="text-[10px] mb-1" style={{ color: "#6B7A99", fontFamily: F }}>월 위에 마우스를 올리면 카테고리 변동을, 클릭하면 상세를 볼 수 있어요</p>
      <ResponsiveContainer width="100%" height={140}>
        <LineChart data={billMD} margin={{ top: 4, right: 8, left: -20, bottom: 0 }}
          onClick={(d: any) => { if (d?.activePayload?.[0]) { const m = d.activePayload[0].payload.month; setSelMonth(p => p === m ? null : m); } }}>
          <CartesianGrid strokeDasharray="3 3" stroke="rgba(15,30,61,0.06)" />
          <XAxis dataKey="month" tick={{ fontSize: 11, fontFamily: F, fill: "#6B7A99" }} />
          <YAxis tick={{ fontSize: 9, fontFamily: M, fill: "#6B7A99" }} tickFormatter={v => `${(v / 10000).toFixed(0)}만`} />
          <RChartTip content={BillTip} />
          <Line type="monotone" dataKey="amount" stroke={MINT} strokeWidth={2.5} dot={{ fill: MINT, r: 5, cursor: "pointer" }} activeDot={{ r: 7, fill: NAVY }} />
        </LineChart>
      </ResponsiveContainer>
      {selData && (
        <div className="mt-3 p-3 rounded-xl" style={{ background: "#fff", border: "1px solid rgba(15,30,61,0.08)" }}>
          <div className="flex justify-between items-center mb-2">
            <p className="text-xs font-semibold" style={{ color: NAVY, fontFamily: F }}>{selData.month} 카테고리 상세</p>
            <button onClick={() => setSelMonth(null)}><X size={13} color="#6B7A99" /></button>
          </div>
          <p className="text-lg font-bold mb-2" style={{ color: NAVY, fontFamily: M }}>{selData.amount.toLocaleString()}원</p>
          {selData.cats.map(c => (
            <div key={c.name} className="flex justify-between text-xs mb-1.5">
              <span style={{ color: NAVY, fontFamily: F }}>{c.name}</span>
              <span style={{ color: c.chg > 0 ? "#FF4D4F" : c.chg < 0 ? "#3B82F6" : NAVY, fontFamily: M }}>
                {c.chg !== 0 ? (c.chg > 0 ? "+" : "") + c.chg.toLocaleString() + "원" : "변동없음"}
              </span>
            </div>
          ))}
        </div>
      )}
      <div className="mt-3 space-y-1.5">
        <p className="text-xs font-semibold" style={{ color: "#6B7A99", fontFamily: F }}>주요 지출</p>
        {[{ name: "쿠팡", amount: 234000 }, { name: "스타벅스", amount: 67000 }].map(i => (
          <div key={i.name} className="flex justify-between text-xs">
            <span style={{ color: NAVY, fontFamily: F }}>{i.name}</span>
            <span style={{ color: NAVY, fontFamily: M }}>-{i.amount.toLocaleString()}원</span>
          </div>
        ))}
      </div>
      <div className="flex flex-wrap gap-2 mt-3">
        <button className="px-3 py-1.5 rounded-full text-xs font-medium border hover:opacity-80 transition-opacity" style={{ borderColor: MINT, color: NAVY, background: "#fff", fontFamily: F }}>전체 내역</button>
        <button className="px-3 py-1.5 rounded-full text-xs font-medium border hover:opacity-80 transition-opacity" style={{ borderColor: MINT, color: NAVY, background: "#fff", fontFamily: F }}>이의 제기</button>
      </div>
    </div>
  );
}

// ── Route ─────────────────────────────────────────────────────────────────────
export default function BillRoute() {
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
            💳 카드 청구서
          </span>
        </div>
        <div className="flex-1 overflow-y-auto px-4 py-4">
          <BillCard />
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
