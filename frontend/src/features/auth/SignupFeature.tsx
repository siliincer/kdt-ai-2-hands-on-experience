import { useState } from 'react';
import { Eye, EyeOff, ArrowLeft } from 'lucide-react';

import { RobotIcon } from '@/shared/ui/robotIcon';
import { NAVY, MINT } from '@/shared/constants/color';
import { F } from '@/shared/constants/font';

import { signupApi } from '@/entities/user/api/userApi';

interface SignupFeatureProps {
  onSignupSuccess: () => void;
  onBackToLogin: () => void;
}

export default function SignupFeature({
  onSignupSuccess,
  onBackToLogin,
}: SignupFeatureProps) {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [passwordConfirm, setPasswordConfirm] = useState('');
  const [name, setName] = useState('');
  const [showPw, setShowPw] = useState(false);
  const [showPwConfirm, setShowPwConfirm] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [errorMsg, setErrorMsg] = useState('');

  const isFormValid =
    email && password && passwordConfirm && password === passwordConfirm;

  const handleSignup = async () => {
    if (!isFormValid) return;

    // 비밀번호 최소 길이 검증 (백엔드 min_length=8)
    if (password.length < 8) {
      setErrorMsg('비밀번호는 8자 이상이어야 합니다.');
      return;
    }

    if (password !== passwordConfirm) {
      setErrorMsg('비밀번호가 일치하지 않습니다.');
      return;
    }

    setErrorMsg('');
    setIsLoading(true);

    try {
      await signupApi({
        email,
        password,
        name: name || undefined,
      });
      onSignupSuccess();
    } catch (error: unknown) {
      if (error instanceof Error) {
        setErrorMsg(error.message);
      } else {
        setErrorMsg('회원가입 중 오류가 발생했습니다.');
      }
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div
      className="flex flex-col items-center justify-center h-full px-6 pb-8"
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
        <span className="text-sm" style={{ color: 'rgba(255,255,255,0.5)' }}>
          AI 금융 코파일럿
        </span>
      </div>

      {/* Card */}
      <div
        className="w-full bg-white rounded-3xl px-6 py-8"
        style={{ boxShadow: '0 24px 60px rgba(0,0,0,0.3)' }}
      >
        {/* Header with back button */}
        <div className="flex items-center mb-6">
          <button
            type="button"
            onClick={onBackToLogin}
            className="mr-3 hover:opacity-70 transition-opacity"
          >
            <ArrowLeft size={20} color={NAVY} />
          </button>
          <h2
            className="text-xl font-bold"
            style={{ color: NAVY, fontFamily: "'DM Sans',sans-serif" }}
          >
            회원가입
          </h2>
        </div>

        {/* Error message */}
        {errorMsg && (
          <div
            className="mb-4 px-4 py-2.5 rounded-xl text-sm"
            style={{
              background: '#FEF2F2',
              color: '#DC2626',
              fontFamily: F,
            }}
          >
            {errorMsg}
          </div>
        )}

        {/* Email */}
        <div className="mb-4">
          <label
            className="block text-xs font-semibold mb-1.5"
            style={{ color: '#6B7A99', fontFamily: F }}
          >
            이메일
          </label>
          <input
            type="email"
            className="w-full px-4 py-3 rounded-xl text-sm outline-none transition-all"
            style={{
              background: '#F4F6FA',
              color: NAVY,
              fontFamily: F,
              border: '1.5px solid transparent',
            }}
            placeholder="example@email.com"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            onFocus={(e) => (e.target.style.borderColor = MINT)}
            onBlur={(e) => (e.target.style.borderColor = 'transparent')}
          />
        </div>

        {/* Name (optional) */}
        <div className="mb-4">
          <label
            className="block text-xs font-semibold mb-1.5"
            style={{ color: '#6B7A99', fontFamily: F }}
          >
            이름 <span style={{ color: '#A0AEC0' }}>(선택)</span>
          </label>
          <input
            type="text"
            className="w-full px-4 py-3 rounded-xl text-sm outline-none transition-all"
            style={{
              background: '#F4F6FA',
              color: NAVY,
              fontFamily: F,
              border: '1.5px solid transparent',
            }}
            placeholder="홍길동"
            value={name}
            onChange={(e) => setName(e.target.value)}
            onFocus={(e) => (e.target.style.borderColor = MINT)}
            onBlur={(e) => (e.target.style.borderColor = 'transparent')}
          />
        </div>

        {/* Password */}
        <div className="mb-4">
          <label
            className="block text-xs font-semibold mb-1.5"
            style={{ color: '#6B7A99', fontFamily: F }}
          >
            비밀번호
          </label>
          <div className="relative">
            <input
              type={showPw ? 'text' : 'password'}
              className="w-full px-4 py-3 pr-11 rounded-xl text-sm outline-none transition-all"
              style={{
                background: '#F4F6FA',
                color: NAVY,
                fontFamily: F,
                border: '1.5px solid transparent',
              }}
              placeholder="8자 이상 입력하세요"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              onFocus={(e) => (e.target.style.borderColor = MINT)}
              onBlur={(e) => (e.target.style.borderColor = 'transparent')}
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

        {/* Password Confirm */}
        <div className="mb-6">
          <label
            className="block text-xs font-semibold mb-1.5"
            style={{ color: '#6B7A99', fontFamily: F }}
          >
            비밀번호 확인
          </label>
          <div className="relative">
            <input
              type={showPwConfirm ? 'text' : 'password'}
              className="w-full px-4 py-3 pr-11 rounded-xl text-sm outline-none transition-all"
              style={{
                background: '#F4F6FA',
                color: NAVY,
                fontFamily: F,
                border:
                  passwordConfirm && password !== passwordConfirm
                    ? '1.5px solid #DC2626'
                    : '1.5px solid transparent',
              }}
              placeholder="비밀번호를 다시 입력하세요"
              value={passwordConfirm}
              onChange={(e) => setPasswordConfirm(e.target.value)}
              onFocus={(e) => {
                if (!(passwordConfirm && password !== passwordConfirm)) {
                  e.target.style.borderColor = MINT;
                }
              }}
              onBlur={(e) => {
                if (!(passwordConfirm && password !== passwordConfirm)) {
                  e.target.style.borderColor = 'transparent';
                }
              }}
              onKeyDown={(e) => e.key === 'Enter' && handleSignup()}
            />
            <button
              type="button"
              onClick={() => setShowPwConfirm((v) => !v)}
              className="absolute right-3 top-1/2 -translate-y-1/2 hover:opacity-70 transition-opacity"
            >
              {showPwConfirm ? (
                <EyeOff size={18} color="#6B7A99" />
              ) : (
                <Eye size={18} color="#6B7A99" />
              )}
            </button>
          </div>
          {passwordConfirm && password !== passwordConfirm && (
            <p className="text-xs mt-1.5" style={{ color: '#DC2626' }}>
              비밀번호가 일치하지 않습니다.
            </p>
          )}
        </div>

        {/* Signup button */}
        <button
          onClick={handleSignup}
          disabled={!isFormValid || isLoading}
          className="w-full py-3.5 rounded-xl text-sm font-semibold text-white transition-opacity"
          style={{
            background: MINT,
            color: NAVY,
            fontFamily: F,
            opacity: !isFormValid ? 0.5 : 1,
          }}
        >
          {isLoading ? '가입 중...' : '회원가입'}
        </button>

        {/* Login link */}
        <p
          className="text-center text-sm mt-4"
          style={{ color: '#6B7A99', fontFamily: F }}
        >
          이미 계정이 있으신가요?{' '}
          <button
            onClick={onBackToLogin}
            className="font-semibold hover:opacity-70 transition-opacity"
            style={{ color: MINT }}
          >
            로그인
          </button>
        </p>
      </div>
    </div>
  );
}
