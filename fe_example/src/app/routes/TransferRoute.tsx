import { useState } from "react";
import { useNavigate } from "react-router";
import { Edit2, Check, Clock } from "lucide-react";

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

function formatScheduled(dt: string): string {
  const d = new Date(dt); const now = new Date(); const tm = new Date(now); tm.setDate(tm.getDate() + 1);
  const day = d.toDateString() === now.toDateString() ? "오늘" : d.toDateString() === tm.toDateString() ? "내일" : `${d.getMonth() + 1}월 ${d.getDate()}일`;
  const h = d.getHours(); const ampm = h < 12 ? "오전" : "오후"; const hour = h === 0 ? 12 : h > 12 ? h - 12 : h;
  return `${day} ${ampm} ${hour}시${d.getMinutes() > 0 ? ` ${d.getMinutes()}분` : ""}`;
}

const BANKS = ["카카오뱅크", "토스뱅크", "케이뱅크", "신한은행", "국민은행", "하나은행", "우리은행", "농협은행", "SC제일은행", "신한", "국민", "하나", "우리", "농협", "기업"];
const BANK_KOR: Record<string, string> = {
  신한: "신한은행", 국민: "국민은행", 하나: "하나은행", 우리: "우리은행", 농협: "NH농협은행",
  기업: "IBK기업은행", 카카오뱅크: "카카오뱅크", 토스뱅크: "토스뱅크", 케이뱅크: "케이뱅크",
  "신한은행": "신한은행", "국민은행": "국민은행", "하나은행": "하나은행", "우리은행": "우리은행",
};

function parseContactText(text: string) {
  const r: { name?: string; bank?: string; account?: string } = {};
  const sorted = [...BANKS].sort((a, b) => b.length - a.length);
  for (const b of sorted) { if (text.includes(b)) { r.bank = BANK_KOR[b] || b; break; } }
  const am = text.match(/\d[\d\s-]{9,}\d/); if (am) r.account = am[0].trim().replace(/\s+/g, "-").replace(/-{2,}/g, "-");
  const bankChars = BANKS.flatMap(b => b.match(/[가-힣]+/g) || []);
  const name = (text.match(/[가-힣]{2,4}/g) || []).find(w => !bankChars.some(bc => bc === w || bc.includes(w)));
  if (name) r.name = name;
  return r;
}

// ── ERow ──────────────────────────────────────────────────────────────────────
function ERow({ label, value, isEditing, onToggle, mono = false, children }: {
  label: string; value: string; isEditing: boolean; onToggle: () => void; mono?: boolean; children?: React.ReactNode;
}) {
  return (
    <div className="border-b" style={{ borderColor: "rgba(15,30,61,0.06)" }}>
      <button className="w-full flex items-center gap-3 py-2.5 text-left hover:opacity-80" onClick={onToggle}>
        <span className="text-xs flex-shrink-0 w-[72px]" style={{ color: "#6B7A99", fontFamily: F }}>{label}</span>
        <span className="flex-1 text-sm" style={{ color: NAVY, fontFamily: mono ? M : F, borderBottom: `1.5px dashed ${MINT}`, paddingBottom: 1 }}>
          {value || <span style={{ color: "#B0B8C9" }}>입력</span>}
        </span>
        <Edit2 size={11} color={MINT} />
      </button>
      {isEditing && <div className="pb-1">{children}</div>}
    </div>
  );
}

// ── TransferCard ──────────────────────────────────────────────────────────────
interface TransferPrefill { name?: string; bank?: string; account?: string; amtRaw?: string; scheduled?: string; }

function TransferCard({ prefill }: { prefill?: TransferPrefill }) {
  const [name, setName] = useState(prefill?.name || "");
  const [bank, setBank] = useState(prefill?.bank || "신한은행");
  const [account, setAccount] = useState(prefill?.account || "");
  const [amtRaw, setAmtRaw] = useState(prefill?.amtRaw || "");
  const [timeOpt, setTimeOpt] = useState<"now" | "schedule">(prefill?.scheduled ? "schedule" : "now");
  const [schedDT, setSchedDT] = useState(prefill?.scheduled || "");
  const [ef, setEf] = useState<string | null>(null);
  const [done, setDone] = useState(false);
  const amtNum = Number(amtRaw) || 0;

  const handlePaste = (e: React.ClipboardEvent) => {
    const text = e.clipboardData.getData("text");
    const p = parseContactText(text);
    if (p.name || p.bank || p.account) { e.preventDefault(); if (p.name) setName(p.name); if (p.bank) setBank(p.bank); if (p.account) setAccount(p.account); }
  };

  if (done) return (
    <div className="flex flex-col items-center py-4 gap-2">
      <div className="w-12 h-12 rounded-full flex items-center justify-center" style={{ background: "#52C41A" }}><Check size={22} color="#fff" strokeWidth={3} /></div>
      <p className="text-sm font-semibold" style={{ color: NAVY, fontFamily: F }}>송금이 완료되었습니다 ✓</p>
      <p className="text-xs" style={{ color: "#6B7A99", fontFamily: F }}>{name}님께 {amtNum.toLocaleString()}원 전송됨</p>
    </div>
  );

  return (
    <div onPaste={handlePaste}>
      <div className="flex items-center gap-2 mb-3"><span className="text-lg">💸</span><p className="text-sm font-semibold" style={{ color: NAVY, fontFamily: F }}>송금 확인</p></div>

      {/* 받는 사람 */}
      <ERow label="받는 사람" value={name} isEditing={ef === "name"} onToggle={() => setEf(ef === "name" ? null : "name")}>
        <div className="pl-[84px] pr-2">
          <input autoFocus className="w-full outline-none text-sm pb-0.5 border-b-2" style={{ color: NAVY, fontFamily: F, borderColor: MINT }} value={name} onChange={e => setName(e.target.value)} onBlur={() => setEf(null)} onKeyDown={e => e.key === "Enter" && setEf(null)} />
        </div>
      </ERow>

      {/* 은행 */}
      <ERow label="은행" value={bank} isEditing={ef === "bank"} onToggle={() => setEf(ef === "bank" ? null : "bank")}>
        <div className="pl-[84px] pr-2">
          <div className="bg-white rounded-xl overflow-hidden shadow-sm" style={{ border: "1px solid rgba(15,30,61,0.08)" }}>
            {BANKS.map(b => (
              <button key={b} onClick={() => { setBank(b); setEf(null); }} className="w-full text-left px-3 py-2 text-xs hover:opacity-80 border-b last:border-0" style={{ color: bank === b ? MINT : NAVY, fontFamily: F, fontWeight: bank === b ? 600 : 400, borderColor: "rgba(15,30,61,0.05)" }}>{b}</button>
            ))}
          </div>
        </div>
      </ERow>

      {/* 계좌번호 */}
      <ERow label="계좌번호" value={account} isEditing={ef === "account"} onToggle={() => setEf(ef === "account" ? null : "account")} mono>
        <div className="pl-[84px] pr-2">
          <input autoFocus className="w-full outline-none text-sm pb-0.5 border-b-2" style={{ color: NAVY, fontFamily: M, borderColor: MINT }} value={account} onChange={e => setAccount(e.target.value)} onBlur={() => setEf(null)} onKeyDown={e => e.key === "Enter" && setEf(null)} inputMode="numeric" />
        </div>
      </ERow>

      {/* 금액 */}
      <ERow label="금액" value={amtNum > 0 ? amtNum.toLocaleString() + "원" : ""} isEditing={ef === "amount"} onToggle={() => setEf(ef === "amount" ? null : "amount")} mono>
        <div className="pl-[84px] pr-2">
          <input autoFocus className="w-full outline-none text-sm pb-0.5 border-b-2" style={{ color: NAVY, fontFamily: M, borderColor: MINT }} inputMode="numeric" value={fmtAmt(amtRaw)} onChange={e => setAmtRaw(parseAmtInput(e.target.value))} onBlur={() => setEf(null)} onKeyDown={e => e.key === "Enter" && setEf(null)} />
          {amtNum > 0 && <p className="text-xs mt-1" style={{ color: MINT, fontFamily: F }}>{kor(amtNum)}</p>}
          <div className="flex gap-1.5 mt-2">
            {["10,000", "50,000", "100,000"].map(c => (
              <button key={c} onClick={() => setAmtRaw(c.replace(",", ""))} className="flex-1 py-1 rounded-lg text-[10px] font-medium" style={{ background: GRAY_BG, color: NAVY, fontFamily: F }}>{c}</button>
            ))}
          </div>
        </div>
      </ERow>

      {/* 시간 */}
      <ERow label="시간" value={timeOpt === "now" ? "지금 바로" : schedDT ? formatScheduled(schedDT) : "날짜/시간 선택"} isEditing={ef === "time"} onToggle={() => setEf(ef === "time" ? null : "time")}>
        <div className="pl-[84px] pr-2 space-y-2">
          <div className="flex gap-2">
            {[{ k: "now", l: "지금 바로" }, { k: "schedule", l: "예약 송금" }].map(opt => (
              <button key={opt.k} onClick={() => setTimeOpt(opt.k as "now" | "schedule")} className="flex-1 py-1.5 rounded-lg text-xs font-medium flex items-center justify-center gap-1" style={{ background: timeOpt === opt.k ? NAVY : GRAY_BG, color: timeOpt === opt.k ? "#fff" : NAVY, fontFamily: F }}>
                <Clock size={11} />{opt.l}
              </button>
            ))}
          </div>
          {timeOpt === "schedule" && <input type="datetime-local" className="w-full py-1.5 px-2 rounded-lg text-xs outline-none" style={{ background: GRAY_BG, color: NAVY, fontFamily: M }} value={schedDT} onChange={e => setSchedDT(e.target.value)} />}
        </div>
      </ERow>

      <p className="text-[10px] py-2" style={{ color: "#6B7A99", fontFamily: F }}>💡 클립보드 텍스트 붙여넣기 자동인식 지원</p>

      <div className="flex gap-2">
        <button className="flex-1 py-2.5 rounded-xl text-sm border" style={{ borderColor: "#CBD5E1", color: "#6B7A99", fontFamily: F }}>취소</button>
        {/* stub: onApproval gate (ConfirmBottomSheet) — deferred */}
        <button onClick={() => { /* stub: approval flow wired in next iteration */ }} className="flex-1 py-2.5 rounded-xl text-sm font-semibold hover:opacity-90" style={{ background: MINT, color: NAVY, fontFamily: F }}>송금하기 →</button>
      </div>
    </div>
  );
}

// ── Route ─────────────────────────────────────────────────────────────────────
export default function TransferRoute() {
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
            💸 송금
          </span>
        </div>
        <div className="flex-1 overflow-y-auto px-4 py-4">
          <TransferCard />
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
