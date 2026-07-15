import { useState } from "react";
import { Eye, EyeOff } from "lucide-react";
import svgPaths from "../../imports/SideBar-1/svg-jp1mz49a91";

const NAVY = "#0F1E3D";
const MINT = "#2DD4BF";
const F = "'Noto Sans KR',sans-serif";

function RobotIcon() {
  return (
    <svg
      fill="none"
      viewBox="0 0 18 18"
      style={{ width: "100%", height: "100%" }}
    >
      <path
        d="M9 6V3H6"
        stroke={NAVY}
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth="1.5"
      />
      <path
        d={svgPaths.p3e254b00}
        stroke={NAVY}
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth="1.5"
      />
      <path
        d="M1.5 10.5H3"
        stroke={NAVY}
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth="1.5"
      />
      <path
        d="M15 10.5H16.5"
        stroke={NAVY}
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth="1.5"
      />
      <path
        d="M11.25 9.75V11.25"
        stroke={NAVY}
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth="1.5"
      />
      <path
        d="M6.75 9.75V11.25"
        stroke={NAVY}
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth="1.5"
      />
    </svg>
  );
}

interface LoginScreenProps {
  onLogin: () => void;
}

export default function LoginScreen({ onLogin }: LoginScreenProps) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPw, setShowPw] = useState(false);
  const [loading, setLoading] = useState(false);

  const handleLogin = () => {
    if (!email || !password) return;
    setLoading(true);
    setTimeout(() => {
      setLoading(false);
      onLogin();
    }, 500);
  };

  return (
    <div
      className="flex flex-col items-center justify-center h-full px-6"
      style={{ background: NAVY, fontFamily: F }}
    >
      {/* Logo */}
      <div className="flex flex-col items-center mb-10">
        <div
          className="flex items-center justify-center rounded-full mb-4"
          style={{ width: 64, height: 64, background: MINT }}
        >
          <div style={{ width: 32, height: 32 }}>
            <RobotIcon />
          </div>
        </div>
        <span
          className="font-bold text-white text-2xl mb-1.5"
          style={{ fontFamily: "'DM Sans', sans-serif" }}
        >
          RealFinance
        </span>
        <span className="text-sm" style={{ color: "rgba(255,255,255,0.5)" }}>
          AI 금융 코파일럿
        </span>
      </div>

      {/* Card */}
      <div
        className="w-full bg-white rounded-3xl px-6 py-8"
        style={{ boxShadow: "0 24px 60px rgba(0,0,0,0.3)" }}
      >
        <h2
          className="text-xl font-bold mb-6"
          style={{ color: NAVY, fontFamily: "'DM Sans',sans-serif" }}
        >
          로그인
        </h2>

        {/* Email */}
        <div className="mb-4">
          <label
            className="block text-xs font-semibold mb-1.5"
            style={{ color: "#6B7A99", fontFamily: F }}
          >
            이메일
          </label>
          <input
            type="email"
            className="w-full px-4 py-3 rounded-xl text-sm outline-none transition-all"
            style={{
              background: "#F4F6FA",
              color: NAVY,
              fontFamily: F,
              border: "1.5px solid transparent",
            }}
            placeholder="example@email.com"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            onFocus={(e) => (e.target.style.borderColor = MINT)}
            onBlur={(e) => (e.target.style.borderColor = "transparent")}
            onKeyDown={(e) => e.key === "Enter" && handleLogin()}
          />
        </div>

        {/* Password */}
        <div className="mb-6">
          <label
            className="block text-xs font-semibold mb-1.5"
            style={{ color: "#6B7A99", fontFamily: F }}
          >
            비밀번호
          </label>
          <div className="relative">
            <input
              type={showPw ? "text" : "password"}
              className="w-full px-4 py-3 pr-11 rounded-xl text-sm outline-none transition-all"
              style={{
                background: "#F4F6FA",
                color: NAVY,
                fontFamily: F,
                border: "1.5px solid transparent",
              }}
              placeholder="비밀번호를 입력하세요"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              onFocus={(e) => (e.target.style.borderColor = MINT)}
              onBlur={(e) => (e.target.style.borderColor = "transparent")}
              onKeyDown={(e) => e.key === "Enter" && handleLogin()}
            />
            <button
              type="button"
              onClick={() => setShowPw((v) => !v)}
              className="absolute right-3 top-1/2 -translate-y-1/2 hover:opacity-70 transition-opacity"
            >
              {showPw ? (
                <EyeOff size={18} color="#6B7A99" />
              ) : (
                <Eye size={18} color="#6B7A99" />
              )}
            </button>
          </div>
        </div>

        {/* Login button */}
        <button
          onClick={handleLogin}
          disabled={!email || !password || loading}
          className="w-full py-3.5 rounded-xl text-sm font-semibold text-white transition-opacity"
          style={{
            background: MINT,
            color: NAVY,
            fontFamily: F,
            opacity: !email || !password ? 0.5 : 1,
          }}
        >
          {loading ? "로그인 중..." : "로그인"}
        </button>

        {/* Sign up link */}
        <p
          className="text-center text-sm mt-4"
          style={{ color: "#6B7A99", fontFamily: F }}
        >
          계정이 없으신가요?{" "}
          <button
            className="font-semibold hover:opacity-70 transition-opacity"
            style={{ color: MINT }}
          >
            회원가입
          </button>
        </p>
      </div>
    </div>
  );
}
