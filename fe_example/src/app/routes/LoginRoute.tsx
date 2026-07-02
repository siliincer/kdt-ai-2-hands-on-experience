import { useNavigate } from "react-router";
import LoginScreen from "../components/LoginScreen";

export default function LoginRoute() {
  const navigate = useNavigate();
  return (
    <div className="w-full h-screen flex flex-col justify-center" style={{ maxWidth: 480, margin: "0 auto" }}>
      <LoginScreen onLogin={() => navigate("/", { replace: true })} />
    </div>
  );
}
