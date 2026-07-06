import { useNavigate } from 'react-router';
import LoginFeature from '@/features/auth/LoginFeature';

export default function LoginPage() {
  const navigate = useNavigate();

  return (
    <div className="min-h-screen bg-slate-950 text-slate-50 flex items-center justify-center px-4 py-8">
      <div className="w-full flex flex-col" style={{ maxWidth: 480 }}>
        <LoginFeature
          onLogin={() => {
            sessionStorage.setItem('rf_logged_in', '1');
            navigate('/');
          }}
        />
      </div>
    </div>
  );
}
