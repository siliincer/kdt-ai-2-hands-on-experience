import { createBrowserRouter, Navigate, RouterProvider } from 'react-router';
import ErrorFallback from '../pages/ErrorFallback';
import HomePage from '../pages/HomePage';
import TransferPage from '../pages/TransferPage';
import SpendingPage from '../pages/SpendingPage';
import TransactionsPage from '../pages/TransactionsPage';
import BudgetPage from '../pages/BudgetPage';
import BalancePage from '../pages/BalancePage';
import AutoTransferPage from '../pages/AutoTransferPage';
import CardPage from '../pages/CardPage';
import LoginPage from '../pages/LoginPage';

const router = createBrowserRouter([
  {
    path: '/login',
    element: <LoginPage />,
  },
  {
    path: '/',
    element: <HomePage />,
    errorElement: (
      <ErrorFallback
        error={new Error('페이지를 불러오지 못했습니다.')}
        resetErrorBoundary={() => window.location.reload()}
      />
    ),
  },
  {
    path: '/transfer',
    element: <TransferPage />,
  },
  {
    path: '/spending',
    element: <SpendingPage />,
  },
  {
    path: '/transactions',
    element: <TransactionsPage />,
  },
  {
    path: '/budget',
    element: <BudgetPage />,
  },
  {
    path: '/balance',
    element: <BalancePage />,
  },
  {
    path: '/autotransfer',
    element: <AutoTransferPage />,
  },
  {
    path: '/card',
    element: <CardPage />,
  },
  {
    path: '*',
    element: <Navigate to="/" replace />,
  },
]);

export function AppRouter() {
  return <RouterProvider router={router} />;
}
