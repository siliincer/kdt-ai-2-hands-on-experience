import { useState } from "react";
import { useNavigate } from "react-router";
import { Tag } from "lucide-react";
import {
  PieChart, Pie, Cell, Tooltip as RChartTip,
  BarChart, Bar, XAxis, YAxis, CartesianGrid,
  LineChart, Line, ResponsiveContainer,
} from "recharts";

const NAVY = "#0F1E3D";
const MINT = "#2DD4BF";
const F = "'Noto Sans KR',sans-serif";
const M = "'DM Mono',monospace";
const GRAY_BG = "#F4F6FA";

// ── Data ──────────────────────────────────────────────────────────────────────
const CATS = ["식비", "교통비", "고정비", "사치비", "쇼핑", "의료", "교육", "기타"];

interface BarCatData { name: string; change: number; prev: number; curr: number; added: { name: string; amount: number }[]; removed: { name: string; amount: number }[]; }
const barData: BarCatData[] = [
  { name: "식비", change: 12, prev: 406714, curr: 455520, added: [{ name: "배달의민족", amount: 28500 }, { name: "맥도날드 (신규)", amount: 12400 }], removed: [{ name: "CU 편의점", amount: 8000 }] },
  { name: "교통비", change: -8, prev: 278511, curr: 256230, added: [], removed: [{ name: "택시 이용 감소", amount: 15000 }, { name: "주유비 감소", amount: 8000 }] },
  { name: "고정비", change: 3, prev: 483713, curr: 498225, added: [{ name: "삼성화재 보험", amount: 15000 }], removed: [] },
  { name: "사치비", change: -22, prev: 274007, curr: 213525, added: [], removed: [{ name: "무신사 쇼핑", amount: 35000 }, { name: "올리브영 감소", amount: 25000 }] },
];
const pieData = [
  { name: "식비", value: 38, color: MINT, amount: 474000 },
  { name: "교통비", value: 22, color: "#3B82F6", amount: 274000 },
  { name: "고정비", value: 28, color: NAVY, amount: 349000 },
  { name: "사치비", value: 12, color: "#F97316", amount: 150000 },
];
const monthlySpend = [
  { month: "1월", amount: 1100000 }, { month: "2월", amount: 980000 },
  { month: "3월", amount: 1350000 }, { month: "4월", amount: 1420000 },
  { month: "5월", amount: 1120000 }, { month: "6월", amount: 1247000 },
];
const catTx: Record<string, { name: string; date: string; amount: number }[]> = {
  "식비": [{ name: "스타벅스", date: "06.28", amount: 7500 }, { name: "배달의민족", date: "06.22", amount: 28500 }, { name: "맥도날드", date: "06.15", amount: 12400 }, { name: "GS25", date: "06.10", amount: 4200 }],
  "교통비": [{ name: "카카오T 택시", date: "06.24", amount: 13200 }, { name: "T-money 충전", date: "06.20", amount: 30000 }, { name: "GS칼텍스", date: "06.05", amount: 65000 }],
  "고정비": [{ name: "월세", date: "06.01", amount: 550000 }, { name: "KT 통신비", date: "06.05", amount: 55000 }, { name: "전기·가스", date: "06.10", amount: 89000 }],
  "사치비": [{ name: "올리브영", date: "06.21", amount: 85000 }, { name: "무신사", date: "06.08", amount: 79000 }],
};

// ── CatBadge ──────────────────────────────────────────────────────────────────
function CatBadge({ cat, onEdit }: { cat: string; onEdit: (c: string) => void }) {
  const [open, setOpen] = useState(false);
  const [custom, setCustom] = useState("");
  return (
    <span>
      <button onClick={() => setOpen(o => !o)} className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-medium" style={{ background: "#EFEFEF", color: "#6B7A99", fontFamily: F }}>
        <Tag size={9} />{cat}
      </button>
      {open && (
        <div className="mt-1.5 p-2 rounded-xl" style={{ background: "#fff", border: "1px solid rgba(15,30,61,0.1)" }}>
          <div className="grid grid-cols-4 gap-1 mb-1.5">
            {CATS.map(c => (
              <button key={c} onClick={() => { onEdit(c); setOpen(false); }} className="py-1 rounded text-[10px] font-medium" style={{ background: cat === c ? MINT : GRAY_BG, color: cat === c ? NAVY : "#6B7A99", fontFamily: F }}>{c}</button>
            ))}
          </div>
          <div className="flex gap-1">
            <input className="flex-1 text-[10px] px-2 py-1 rounded outline-none" style={{ background: GRAY_BG, color: NAVY, fontFamily: F }} placeholder="직접 입력..." value={custom} onChange={e => setCustom(e.target.value)} onKeyDown={e => e.key === "Enter" && custom && (onEdit(custom), setOpen(false), setCustom(""))} />
            {custom && <button onClick={() => { onEdit(custom); setOpen(false); setCustom(""); }} className="px-2 rounded text-[10px]" style={{ background: MINT, color: NAVY, fontFamily: F }}>✓</button>}
          </div>
        </div>
      )}
    </span>
  );
}

// Bar tooltip with item changes
function BarTip({ active, payload, label }: any) {
  if (!active || !payload?.length) return null;
  const d = barData.find(b => b.name === label); if (!d) return null;
  return (
    <div className="bg-white rounded-xl p-3 shadow-lg" style={{ border: "1px solid rgba(15,30,61,0.1)", minWidth: 200 }}>
      <div className="flex justify-between mb-1.5"><p className="text-xs font-bold" style={{ color: NAVY, fontFamily: F }}>{label}</p><p className="text-xs font-bold" style={{ color: d.change >= 0 ? "#FF4D4F" : "#3B82F6", fontFamily: M }}>{d.change >= 0 ? "+" : ""}{d.change}%</p></div>
      <p className="text-[10px] mb-2" style={{ color: "#6B7A99", fontFamily: M }}>{d.prev.toLocaleString()} → {d.curr.toLocaleString()}원</p>
      {d.added.length > 0 && <><p className="text-[10px] font-bold mb-1" style={{ color: "#3B82F6", fontFamily: F }}>+ 추가</p>{d.added.map(it => <div key={it.name} className="flex justify-between text-[10px] mb-0.5"><span style={{ color: NAVY, fontFamily: F }}>{it.name}</span><span style={{ color: "#3B82F6", fontFamily: M }}>+{it.amount.toLocaleString()}원</span></div>)}</>}
      {d.removed.length > 0 && <><p className="text-[10px] font-bold mt-1 mb-1" style={{ color: "#FF4D4F", fontFamily: F }}>− 감소</p>{d.removed.map(it => <div key={it.name} className="flex justify-between text-[10px] mb-0.5"><span style={{ color: NAVY, fontFamily: F }}>{it.name}</span><span style={{ color: "#FF4D4F", fontFamily: M }}>-{it.amount.toLocaleString()}원</span></div>)}</>}
    </div>
  );
}

// ── SpendingCard ──────────────────────────────────────────────────────────────
function SpendingCard({ onNavigate }: { onNavigate: (path: string) => void }) {
  const [tab, setTab] = useState<"donut" | "bar" | "monthly">("donut");
  const [selCat, setSelCat] = useState<string | null>(null);
  const [catEdit, setCatEdit] = useState<Record<string, string>>({});
  const toggle = (name: string) => setSelCat(c => c === name ? null : name);

  return (
    <div>
      <div className="flex items-center gap-2 mb-2"><span className="text-lg">📊</span><p className="text-sm font-semibold" style={{ color: NAVY, fontFamily: F }}>카테고리별 지출</p></div>
      <div className="flex gap-1 mb-3 rounded-xl" style={{ background: "#E8EDF5", padding: "3px" }}>
        {[{ k: "donut" as const, l: "도넛" }, { k: "bar" as const, l: "막대" }, { k: "monthly" as const, l: "월별비교" }].map(t => (
          <button key={t.k} onClick={() => setTab(t.k)} className="flex-1 py-1.5 rounded-lg text-xs font-medium transition-all" style={{ background: tab === t.k ? "#fff" : "transparent", color: tab === t.k ? NAVY : "#6B7A99", fontFamily: F, boxShadow: tab === t.k ? "0 1px 3px rgba(0,0,0,0.1)" : "none" }}>{t.l}</button>
        ))}
      </div>

      {tab === "donut" && (
        <div>
          <div className="flex items-center gap-3">
            <div style={{ width: 140, height: 140, flexShrink: 0 }}>
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie data={pieData} cx="50%" cy="50%" innerRadius={42} outerRadius={62} dataKey="value" paddingAngle={3} onClick={(d: any) => toggle(d.name)} style={{ cursor: "pointer" }}>
                    {pieData.map(d => <Cell key={`p-${d.name}`} fill={d.color} opacity={selCat && selCat !== d.name ? 0.3 : 1} stroke={selCat === d.name ? "#fff" : "none"} strokeWidth={selCat === d.name ? 3 : 0} />)}
                  </Pie>
                </PieChart>
              </ResponsiveContainer>
            </div>
            <div className="flex-1 space-y-2">
              {pieData.map(d => (
                <button key={d.name} onClick={() => toggle(d.name)} className="w-full flex items-center justify-between px-2 py-0.5 rounded-lg" style={{ background: selCat === d.name ? "#fff" : "transparent" }}>
                  <div className="flex items-center gap-1.5"><div className="w-2.5 h-2.5 rounded-full flex-shrink-0" style={{ background: d.color }} /><span className="text-xs" style={{ color: "#6B7A99", fontFamily: F }}>{d.name}</span></div>
                  <div className="text-right"><span className="text-xs font-semibold" style={{ color: NAVY, fontFamily: M }}>{d.value}%</span><span className="text-[10px] ml-1" style={{ color: "#6B7A99", fontFamily: M }}>{d.amount.toLocaleString()}</span></div>
                </button>
              ))}
            </div>
          </div>
          {selCat && catTx[selCat] && (
            <div className="mt-3 border-t pt-3" style={{ borderColor: "rgba(15,30,61,0.08)" }}>
              <p className="text-xs font-semibold mb-2" style={{ color: NAVY, fontFamily: F }}>{selCat} 거래 내역</p>
              {catTx[selCat].map((tx, i) => (
                <div key={i} className="flex items-center gap-2 py-2 border-b last:border-0" style={{ borderColor: "rgba(15,30,61,0.06)" }}>
                  <span className="text-[10px] w-10 flex-shrink-0" style={{ color: "#6B7A99", fontFamily: M }}>{tx.date}</span>
                  <span className="flex-1 text-xs" style={{ color: NAVY, fontFamily: F }}>{tx.name}</span>
                  <CatBadge cat={catEdit[`${selCat}-${i}`] || selCat} onEdit={c => setCatEdit(p => ({ ...p, [`${selCat}-${i}`]: c }))} />
                  <span className="text-xs font-bold" style={{ color: NAVY, fontFamily: M }}>{tx.amount.toLocaleString()}원</span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {tab === "bar" && (
        <div>
          <ResponsiveContainer width="100%" height={160}>
            <BarChart data={barData} margin={{ top: 4, right: 8, left: -20, bottom: 0 }} onClick={(d: any) => { if (d?.activeLabel && d.activePayload?.length) toggle(d.activeLabel); }}>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(15,30,61,0.06)" />
              <XAxis dataKey="name" tick={{ fontSize: 11, fontFamily: F, fill: "#6B7A99" }} />
              <YAxis tick={{ fontSize: 10, fontFamily: M, fill: "#6B7A99" }} />
              <RChartTip content={BarTip} />
              <Bar dataKey="change" radius={[6, 6, 0, 0]} style={{ cursor: "pointer" }}>
                {barData.map(d => <Cell key={`b-${d.name}`} fill={d.change >= 0 ? "#FF4D4F" : "#3B82F6"} opacity={selCat && selCat !== d.name ? 0.3 : 1} />)}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
          {selCat && (() => { const bd = barData.find(b => b.name === selCat); if (!bd || (!bd.added.length && !bd.removed.length)) return null; return (
            <div className="mt-2 p-3 rounded-xl" style={{ background: "#fff" }}>
              <p className="text-xs font-semibold mb-2" style={{ color: NAVY, fontFamily: F }}>{selCat} 전월 대비 변동</p>
              {bd.added.map(it => <div key={it.name} className="flex justify-between text-xs mb-1"><span className="flex items-center gap-1"><b style={{ color: "#3B82F6" }}>+</b><span style={{ color: NAVY, fontFamily: F }}>{it.name}</span></span><span style={{ color: "#3B82F6", fontFamily: M }}>+{it.amount.toLocaleString()}원</span></div>)}
              {bd.removed.map(it => <div key={it.name} className="flex justify-between text-xs mb-1"><span className="flex items-center gap-1"><b style={{ color: "#FF4D4F" }}>−</b><span style={{ color: NAVY, fontFamily: F }}>{it.name}</span></span><span style={{ color: "#FF4D4F", fontFamily: M }}>-{it.amount.toLocaleString()}원</span></div>)}
            </div>
          ); })()}
        </div>
      )}

      {tab === "monthly" && (
        <ResponsiveContainer width="100%" height={150}>
          <LineChart data={monthlySpend} margin={{ top: 4, right: 8, left: -20, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="rgba(15,30,61,0.06)" />
            <XAxis dataKey="month" tick={{ fontSize: 11, fontFamily: F, fill: "#6B7A99" }} />
            <YAxis tick={{ fontSize: 9, fontFamily: M, fill: "#6B7A99" }} tickFormatter={v => `${(v / 10000).toFixed(0)}만`} />
            <RChartTip formatter={(v: number) => [`${v.toLocaleString()}원`, "지출"]} />
            <Line type="monotone" dataKey="amount" stroke={MINT} strokeWidth={2.5} dot={{ fill: MINT, r: 4 }} activeDot={{ r: 6, fill: NAVY }} />
          </LineChart>
        </ResponsiveContainer>
      )}

      <div className="flex flex-wrap gap-2 mt-3">
        {/* 지난달 비교: stub — no chat state yet */}
        <button className="px-3 py-1.5 rounded-full text-xs font-medium border hover:opacity-80 transition-opacity" style={{ borderColor: MINT, color: NAVY, background: "#fff", fontFamily: F }}>지난달 비교</button>
        <button onClick={() => onNavigate("/budget")} className="px-3 py-1.5 rounded-full text-xs font-medium border hover:opacity-80 transition-opacity" style={{ borderColor: MINT, color: NAVY, background: "#fff", fontFamily: F }}>예산 설정</button>
        <button onClick={() => onNavigate("/transactions")} className="px-3 py-1.5 rounded-full text-xs font-medium border hover:opacity-80 transition-opacity" style={{ borderColor: MINT, color: NAVY, background: "#fff", fontFamily: F }}>거래 내역 전체</button>
      </div>
    </div>
  );
}

// ── Route ─────────────────────────────────────────────────────────────────────
export default function SpendingRoute() {
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
            📊 소비 분석
          </span>
        </div>
        <div className="flex-1 overflow-y-auto px-4 py-4">
          <SpendingCard onNavigate={navigate} />
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
