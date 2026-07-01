import { useState } from "react";
import { useNavigate } from "react-router";
import { Check, Plus } from "lucide-react";

const NAVY = "#0F1E3D";
const MINT = "#2DD4BF";
const F = "'Noto Sans KR',sans-serif";
const M = "'DM Mono',monospace";
const GRAY_BG = "#F4F6FA";

// ── Utils ─────────────────────────────────────────────────────────────────────
const fmtAmt = (r: string) => (r ? Number(r).toLocaleString() : "");
const parseAmtInput = (v: string) => v.replace(/,/g, "").replace(/[^0-9]/g, "").replace(/^0+(?!$)/, "");

function kor(n: number): string {
  if (!n) return "";
  const d = ["", "일", "이", "삼", "사", "오", "육", "칠", "팔", "구"];
  const p = ["", "십", "백", "천"];
  const u = ["", "만", "억", "조"];
  const chunk = (c: number) => { let s = ""; for (let i = 3; i >= 0; i--) { const x = Math.floor(c / 10 ** i) % 10; if (!x) continue; s += (x === 1 && i > 0 ? "" : d[x]) + p[i]; } return s; };
  let res = "", rem = n, ui = 0;
  while (rem > 0) { const c = rem % 10000; if (c) res = chunk(c) + u[ui] + res; rem = Math.floor(rem / 10000); ui++; }
  return res + "원";
}

// ── Data ──────────────────────────────────────────────────────────────────────
const autoTxItems = [
  { name: "월세", cycle: "매월 1일", amount: 500000, active: true },
  { name: "보험료", cycle: "매월 10일", amount: 89000, active: true },
  { name: "적금", cycle: "매월 15일", amount: 200000, active: true },
];

// ── AutoTransferFormCard ──────────────────────────────────────────────────────
function AutoTransferFormCard({ onDone }: { onDone: () => void }) {
  const [account, setAccount] = useState("");
  const [amtRaw, setAmtRaw] = useState("");
  const [day, setDay] = useState("");
  const [submitted, setSubmitted] = useState(false);
  const amtNum = Number(amtRaw) || 0;

  if (submitted) return (
    <div className="flex items-center gap-2 py-2">
      <div className="w-6 h-6 rounded-full flex items-center justify-center flex-shrink-0" style={{ background: "#52C41A" }}><Check size={12} color="#fff" /></div>
      <p className="text-sm" style={{ color: NAVY, fontFamily: F }}>자동 이체가 등록되었습니다 ✓</p>
    </div>
  );

  const fields = [
    { label: "받는 계좌", value: account, set: setAccount, ph: "계좌번호 또는 이름", mono: false },
    { label: "금액", value: fmtAmt(amtRaw), set: (v: string) => setAmtRaw(parseAmtInput(v)), ph: "0원", mono: true },
    { label: "날짜", value: day, set: setDay, ph: "매월 ?일", mono: false },
  ];

  return (
    <div>
      <div className="flex items-center justify-between mb-2">
        <p className="text-xs font-semibold" style={{ color: NAVY, fontFamily: F }}>자동 이체 등록</p>
        <button onClick={onDone} className="text-xs" style={{ color: "#6B7A99", fontFamily: F }}>취소</button>
      </div>
      {fields.map(fd => (
        <div key={fd.label} className="flex items-center gap-3 py-2.5 border-b" style={{ borderColor: "rgba(15,30,61,0.06)" }}>
          <span className="text-xs w-[72px] flex-shrink-0" style={{ color: "#6B7A99", fontFamily: F }}>{fd.label}</span>
          <input className="flex-1 text-sm outline-none border-b-2 pb-0.5" style={{ color: NAVY, fontFamily: fd.mono ? M : F, borderColor: MINT }} placeholder={fd.ph} value={fd.value} onChange={e => fd.set(e.target.value)} inputMode={fd.mono ? "numeric" : "text"} />
        </div>
      ))}
      {amtNum > 0 && <p className="text-xs mt-1 text-right" style={{ color: MINT, fontFamily: F }}>{kor(amtNum)}</p>}
      <button onClick={() => setSubmitted(true)} className="mt-3 w-full py-2.5 rounded-xl text-sm font-semibold" style={{ background: MINT, color: NAVY, fontFamily: F }}>등록하기</button>
    </div>
  );
}

// ── AutoTransferCard ──────────────────────────────────────────────────────────
function AutoTransferCard({ onShowForm }: { onShowForm: () => void }) {
  const [toggles, setToggles] = useState(autoTxItems.map(a => a.active));
  return (
    <div>
      <div className="flex items-center gap-2 mb-3"><span className="text-lg">🔄</span><p className="text-sm font-semibold" style={{ color: NAVY, fontFamily: F }}>자동 이체 목록</p></div>
      {autoTxItems.map((a, i) => (
        <div key={a.name} className="flex items-center gap-3 py-3 border-b" style={{ borderColor: "rgba(15,30,61,0.06)" }}>
          <div className="flex-1">
            <p className="text-xs font-medium" style={{ color: NAVY, fontFamily: F }}>{a.name}</p>
            <p className="text-[10px]" style={{ color: "#6B7A99", fontFamily: F }}>{a.cycle}</p>
          </div>
          <p className="text-xs font-bold" style={{ color: NAVY, fontFamily: M }}>{a.amount.toLocaleString()}원</p>
          <button onClick={() => setToggles(p => { const n = [...p]; n[i] = !n[i]; return n; })}>
            {toggles[i] ? <span className="text-xs font-medium" style={{ color: MINT }}>✓</span> : <span className="text-xs" style={{ color: "#CBD5E1" }}>○</span>}
          </button>
        </div>
      ))}
      <button onClick={onShowForm} className="mt-3 w-full py-2.5 rounded-xl text-xs font-medium flex items-center justify-center gap-1.5 border-2" style={{ borderColor: MINT, color: MINT, fontFamily: F }}>
        <Plus size={13} />자동 이체 추가
      </button>
    </div>
  );
}

// ── Route ─────────────────────────────────────────────────────────────────────
export default function AutoTransferRoute() {
  const navigate = useNavigate();
  const [showForm, setShowForm] = useState(false);

  return (
    <div className="flex h-screen overflow-hidden justify-center" style={{ background: "#F0F2F5" }}>
      <div className="w-full flex flex-col bg-white" style={{ maxWidth: 480, boxShadow: "0 0 40px rgba(0,0,0,0.08)" }}>
        <div className="flex items-center gap-3 px-5 py-4 flex-shrink-0" style={{ background: NAVY }}>
          <button
            onClick={() => showForm ? setShowForm(false) : navigate(-1)}
            className="text-white/70 hover:text-white transition-colors"
            aria-label="뒤로가기"
          >
            ←
          </button>
          <span className="font-bold text-white text-base" style={{ fontFamily: "'DM Sans',sans-serif" }}>
            🔄 자동 이체
          </span>
        </div>
        <div className="flex-1 overflow-y-auto px-4 py-4">
          {showForm
            ? <AutoTransferFormCard onDone={() => setShowForm(false)} />
            : <AutoTransferCard onShowForm={() => setShowForm(true)} />
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
