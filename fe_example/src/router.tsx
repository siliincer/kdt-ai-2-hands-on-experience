import { createHashRouter } from "react-router";
import App from "./app/App";
import LoginRoute from "./app/routes/LoginRoute";
import TransferRoute from "./app/routes/TransferRoute";
import BalanceRoute from "./app/routes/BalanceRoute";
import SpendingRoute from "./app/routes/SpendingRoute";
import TransactionsRoute from "./app/routes/TransactionsRoute";
import BillRoute from "./app/routes/BillRoute";
import BudgetRoute from "./app/routes/BudgetRoute";
import AutoTransferRoute from "./app/routes/AutoTransferRoute";
import CardRoute from "./app/routes/CardRoute";
import ErrorMessageRoute from "./app/routes/ErrorMessageRoute";
import ErrorRoute from "./app/routes/ErrorRoute";

export const router = createHashRouter([
  { path: "/login", element: <LoginRoute /> },
  { path: "/", element: <App /> },
  { path: "/transfer", element: <TransferRoute /> },
  { path: "/balance", element: <BalanceRoute /> },
  { path: "/spending", element: <SpendingRoute /> },
  { path: "/transactions", element: <TransactionsRoute /> },
  { path: "/bill", element: <BillRoute /> },
  { path: "/budget", element: <BudgetRoute /> },
  { path: "/autotransfer", element: <AutoTransferRoute /> },
  { path: "/card", element: <CardRoute /> },
  { path: "/error", element: <ErrorMessageRoute /> },
  { path: "*", element: <ErrorRoute /> },
]);
