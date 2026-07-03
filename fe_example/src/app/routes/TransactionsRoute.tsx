import { useState } from "react";
import { useNavigate } from "react-router";
import { Bell, X, ChevronDown, ChevronUp, Tag } from "lucide-react";

const NAVY = "#0F1E3D";
const MINT = "#2DD4BF";
const F = "'Noto Sans KR',sans-serif";
const M = "'DM Mono',monospace";
const GRAY_BG = "#F4F6FA";

// ── Data ──────────────────────────────────────────────────────────────────────
const CATS = ["식비", "교통비", "고정비", "사치비", "쇼핑", "의료", "교육", "기타"];

interface TxItem { id: number; name: string; emoji: string; date: string; month: string; day: number; amount: number; type: "in" | "out"; category: string; }

const ALL_TX: TxItem[] = [
  { id: 601, name: "급여 입금", emoji: "💰", date: "06.25 09:00", month: "2025-06", day: 25, amount: 3200000, type: "in", category: "수입" },
  { id: 602, name: "월세 이서연", emoji: "🏠", date: "06.01 09:00", month: "2025-06", day: 1, amount: -550000, type: "out", category: "고정비" },
  { id: 603, name: "KT 통신비", emoji: "📱", date: "06.05 00:01", month: "2025-06", day: 5, amount: -55000, type: "out", category: "기타" },
  { id: 604, name: "스타벅스", emoji: "☕", date: "06.28 14:23", month: "2025-06", day: 28, amount: -7500, type: "out", category: "식비" },
  { id: 605, name: "카카오T 택시", emoji: "🚕", date: "06.24 22:41", month: "2025-06", day: 24, amount: -13200, type: "out", category: "교통비" },
  { id: 606, name: "쿠팡 로켓배송", emoji: "📦", date: "06.23 11:05", month: "2025-06", day: 23, amount: -42800, type: "out", category: "쇼핑" },
  { id: 607, name: "Spotify", emoji: "🎵", date: "06.15 00:01", month: "2025-06", day: 15, amount: -10900, type: "out", category: "고정비" },
  { id: 608, name: "Netflix", emoji: "🎬", date: "06.20 00:01", month: "2025-06", day: 20, amount: -17000, type: "out", category: "고정비" },
  { id: 609, name: "올리브영", emoji: "💄", date: "06.21 15:30", month: "2025-06", day: 21, amount: -85000, type: "out", category: "사치비" },
  { id: 501, name: "급여 입금", emoji: "💰", date: "05.25 09:00", month: "2025-05", day: 25, amount: 3200000, type: "in", category: "수입" },
  { id: 502, name: "월세 이서연", emoji: "🏠", date: "05.01 09:00", month: "2025-05", day: 1, amount: -550000, type: "out", category: "고정비" },
  { id: 503, name: "KT 통신비", emoji: "📱", date: "05.05 00:01", month: "2025-05", day: 5, amount: -55000, type: "out", category: "기타" },
  { id: 504, name: "스타벅스", emoji: "☕", date: "05.28 10:00", month: "2025-05", day: 28, amount: -7500, type: "out", category: "식비" },
  { id: 505, name: "Spotify", emoji: "🎵", date: "05.15 00:01", month: "2025-05", day: 15, amount: -10900, type: "out", category: "고정비" },
  { id: 506, name: "Netflix", emoji: "🎬", date: "05.20 00:01", month: "2025-05", day: 20, amount: -17000, type: "out", category: "고정비" },
  { id: 507, name: "무신사", emoji: "👗", date: "05.14 14:00", month: "2025-05", day: 14, amount: -79000, type: "out", category: "사치비" },
  { id: 401, name: "급여 입금", emoji: "💰", date: "04.25 09:00", month: "2025-04", day: 25, amount: 3200000, type: "in", category: "수입" },
  { id: 402, name: "월세 이서연", emoji: "🏠", date: "04.01 09:00", month: "2025-04", day: 1, amount: -550000, type: "out", category: "고정비" },
  { id: 403, name: "KT 통신비", emoji: "📱", date: "04.05 00:01", month: "2025-04", day: 5, amount: -55000, type: "out", category: "기타" },
  { id: 404, name: "스타벅스", emoji: "☕", date: "04.28 09:30", month: "2025-04", day: 28, amount: -7500, type: "out", category: "식비" },
  { id: 405, name: "Spotify", emoji: "🎵", date: "04.15 00:01", month: "2025-04", day: 15, amount: -10900, type: "out", category: "고정비" },
  { id: 406, name: "Netflix", emoji: "🎬", date: "04.20 00:01", month: "2025-04", day: 20, amount: -17000, type: "out", category: "고정비" },
  { id: 407, name: "쿠팡 로켓배송", emoji: "📦", date: "04.18 15:00", month: "2025-04", day: 18, amount: -56000, type: "out", category: "쇼핑" },
  { id: 301, name: "급여 입금", emoji: "💰", date: "03.25 09:00", month: "2025-03", day: 25, amount: 3200000, type: "in", category: "수입" },
  { id: 302, name: "월세 이서연", emoji: "🏠", date: "03.01 09:00", month: "2025-03", day: 1, amount: -550000, type: "out", category: "고정비" },
  { id: 303, name: "KT 통신비", emoji: "📱", date: "03.05 00:01", month: "2025-03", day: 5, amount: -55000, type: "out", category: "기타" },
  { id: 304, name: "스타벅스", emoji: "☕", date: "03.28 11:00", month: "2025-03", day: 28, amount: -7500, type: "out", category: "식비" },
  { id: 305, name: "Spotify", emoji: "🎵", date: "03.15 00:01", month: "2025-03", day: 15, amount: -10900, type: "out", category: "고정비" },
  { id: 306, name: "Netflix", emoji: "🎬", date: "03.20 00:01", month: "2025-03", day: 20, amount: -17000, type: "out", category: "고정비" },
  { id: 201, name: "급여 입금", emoji: "💰", date: "02.25 09:00", month: "2025-02", day: 25, amount: 3200000, type: "in", category: "수입" },
  { id: 202, name: "월세 이서연", emoji: "🏠", date: "02.01 09:00", month: "2025-02", day: 1, amount: -550000, type: "out", category: "고정비" },
  { id: 203, name: "KT 통신비", emoji: "📱", date: "02.05 00:01", month: "2025-02", day: 5, amount: -55000, type: "out", category: "기타" },
  { id: 204, name: "스타벅스", emoji: "☕", date: "02.28 10:30", month: "2025-02", day: 28, amount: -7500, type: "out", category: "식비" },
  { id: 205, name: "Spotify", emoji: "🎵", date: "02.15 00:01", month: "2025-02", day: 15, amount: -10900, type: "out", category: "고정비" },
  { id: 206, name: "Netflix", emoji: "🎬", date: "02.20 00:01", month: "2025-02", day: 20, amount: -17000, type: "out", category: "고정비" },
];

function detectRecurring(txs: TxItem[]) {
  const g: Record<string, Set<string>> = {};
  txs.filter(t => t.type === "out").forEach(tx => { const k = `${tx.name}__${Math.abs(tx.amount)}__${tx.day}`; if (!g[k]) g[k] = new Set(); g[k].add(tx.month); });
  return Object.entries(g).filter(([, s]) => s.size >= 2).map(([k]) => { const [name, a, d] = k.split("__"); return { name, amount: parseInt(a), day: parseInt(d) }; });
}

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

// ── TransactionsCard ──────────────────────────────────────────────────────────
function TransactionsCard() {
  const months = ["2025-06", "2025-05", "2025-04", "2025-03", "2025-02"];
  const ml: Record<string, string> = { "2025-06": "6월", "2025-05": "5월", "2025-04": "4월", "2025-03": "3월", "2025-02": "2월" };
  const [selM, setSelM] = useState("2025-06");
  const [expanded, setExpanded] = useState<number | null>(null);
  const [txCats, setTxCats] = useState<Record<number, string>>({});
  const [dismissed, setDismissed] = useState<string[]>([]);
  const [toasts, setToasts] = useState<string[]>([]);

  const currentTxs = ALL_TX.filter(t => t.month === selM).sort((a, b) => b.day - a.day);
  const recurring = detectRecurring(ALL_TX);
  const suggestions = recurring.filter(r => {
    const cur = currentTxs.find(t => t.name === r.name && Math.abs(t.amount) === r.amount && t.day === r.day);
    if (!cur) return false;
    return (txCats[cur.id] || cur.category) !== "고정비" && !dismissed.includes(r.name);
  });

  const registerFixed = (r: { name: string; amount: number; day: number }) => {
    ALL_TX.filter(t => t.name === r.name && Math.abs(t.amount) === r.amount && t.day === r.day)
      .forEach(t => setTxCats(p => ({ ...p, [t.id]: "고정비" })));
    setDismissed(p => [...p, r.name]);
    const msg = `${r.name}가(이) 고정비로 등록되었습니다 ✓`;
    setToasts(p => [...p, msg]);
    setTimeout(() => setToasts(p => p.filter(t => t !== msg)), 3000);
  };

  return (
    <div>
      <div className="flex items-center gap-2 mb-3"><span className="text-lg">📋</span><p className="text-sm font-semibold" style={{ color: NAVY, fontFamily: F }}>거래 내역</p></div>
      <div className="flex gap-1.5 mb-3 overflow-x-auto pb-1">
        {months.map(mo => <button key={mo} onClick={() => { setSelM(mo); setExpanded(null); }} className="px-3 py-1 rounded-full text-xs font-medium flex-shrink-0" style={{ background: selM === mo ? NAVY : "#E8EDF5", color: selM === mo ? "#fff" : "#6B7A99", fontFamily: F }}>{ml[mo]}</button>)}
      </div>

      {toasts.map((t, i) => <div key={i} className="mb-2 px-3 py-2 rounded-xl text-xs font-medium" style={{ background: "#52C41A15", color: "#52C41A", fontFamily: F, border: "1px solid #52C41A30" }}>{t}</div>)}

      {suggestions.length > 0 && (
        <div className="mb-3 rounded-xl overflow-hidden" style={{ border: `1px solid ${MINT}`, background: `${MINT}10` }}>
          <div className="flex justify-between items-center px-3 py-2"><div className="flex items-center gap-1.5"><Bell size={13} color={MINT} /><p className="text-xs font-semibold" style={{ color: NAVY, fontFamily: F }}>고정비 제안</p></div><button onClick={() => setDismissed(p => [...p, ...suggestions.map(s => s.name)])}><X size={13} color="#6B7A99" /></button></div>
          {suggestions.map(s => (
            <div key={s.name} className="border-t px-3 py-2 flex items-start gap-2" style={{ borderColor: `${MINT}30` }}>
              <div className="flex-1"><p className="text-xs" style={{ color: NAVY, fontFamily: F }}>{s.name}({s.amount.toLocaleString()}원)가 매월 {s.day}일 반복됩니다. 고정비로 등록할까요?</p></div>
              <div className="flex gap-1.5 flex-shrink-0">
                <button onClick={() => registerFixed(s)} className="px-2 py-1 rounded text-[10px] font-semibold" style={{ background: MINT, color: NAVY, fontFamily: F }}>고정비 등록</button>
                <button onClick={() => setDismissed(p => [...p, s.name])} className="px-2 py-1 rounded text-[10px]" style={{ background: GRAY_BG, color: "#6B7A99", fontFamily: F }}>닫기</button>
              </div>
            </div>
          ))}
        </div>
      )}

      <div>
        {currentTxs.map(tx => {
          const effCat = txCats[tx.id] || tx.category;
          const isOpen = expanded === tx.id;
          return (
            <div key={tx.id} className="border-b" style={{ borderColor: "rgba(15,30,61,0.06)" }}>
              <button className="w-full flex items-center gap-2 py-2.5 text-left" onClick={() => setExpanded(isOpen ? null : tx.id)}>
                <span className="text-sm flex-shrink-0">{tx.emoji}</span>
                <div className="flex-1 min-w-0">
                  <p className="text-xs font-medium truncate" style={{ color: NAVY, fontFamily: F }}>{tx.name}</p>
                  <div className="flex items-center gap-1.5 mt-0.5">
                    <p className="text-[10px]" style={{ color: "#6B7A99", fontFamily: M }}>{tx.date}</p>
                    {tx.type === "out" && <CatBadge cat={effCat} onEdit={c => setTxCats(p => ({ ...p, [tx.id]: c }))} />}
                  </div>
                </div>
                <p className="text-xs font-bold flex-shrink-0" style={{ color: tx.type === "in" ? "#52C41A" : NAVY, fontFamily: M }}>
                  {tx.type === "in" ? "+" : ""}{Math.abs(tx.amount).toLocaleString()}원
                </p>
                {isOpen ? <ChevronUp size={13} color="#6B7A99" /> : <ChevronDown size={13} color="#6B7A99" />}
              </button>
              {isOpen && (
                <div className="px-4 pb-2 pt-1 space-y-1.5 text-xs rounded-xl mx-2 mb-2" style={{ background: "#fff" }}>
                  <div className="flex justify-between items-center"><span style={{ color: "#6B7A99", fontFamily: F }}>거래처</span><span style={{ color: NAVY, fontFamily: F }}>{tx.name}</span></div>
                  <div className="flex justify-between items-center"><span style={{ color: "#6B7A99", fontFamily: F }}>카테고리</span><CatBadge cat={effCat} onEdit={c => setTxCats(p => ({ ...p, [tx.id]: c }))} /></div>
                  <div className="flex justify-between"><span style={{ color: "#6B7A99", fontFamily: F }}>날짜/시간</span><span style={{ color: NAVY, fontFamily: M }}>{tx.date}</span></div>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ── Route ─────────────────────────────────────────────────────────────────────
export default function TransactionsRoute() {
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
            📋 거래 내역
          </span>
        </div>
        <div className="flex-1 overflow-y-auto px-4 py-4">
          <TransactionsCard />
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
