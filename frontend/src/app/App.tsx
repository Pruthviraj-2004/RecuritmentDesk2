import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { lazy, Suspense, type ReactNode } from "react";
import { BrowserRouter, Navigate, Route, Routes, useLocation } from "react-router-dom";
import { Toaster } from "sonner";
import { AuthProvider, useAuth } from "@/app/auth";
import { LoadingRows } from "@/components/common/common";
import { AppShell } from "@/components/layout/app-shell";
import { TooltipProvider } from "@/components/ui/tooltip";
import { ApiError } from "@/lib/api";
import { LoginPage } from "@/features/auth/login-page";

const Overview = lazy(() => import("@/features/dashboard/overview-page").then((m) => ({ default: m.OverviewPage })));
const Requirements = lazy(() => import("@/features/requirements/requirements-page").then((m) => ({ default: m.RequirementsPage })));
const RequirementDetail = lazy(() => import("@/features/requirements/requirement-detail-page").then((m) => ({ default: m.RequirementDetailPage })));
const Candidates = lazy(() => import("@/features/candidates/candidates-page").then((m) => ({ default: m.CandidatesPage })));
const CandidateDetail = lazy(() => import("@/features/candidates/candidate-detail-page").then((m) => ({ default: m.CandidateDetailPage })));
const Duplicates = lazy(() => import("@/features/duplicates/duplicates-page").then((m) => ({ default: m.DuplicatesPage })));
const Accounts = lazy(() => import("@/features/accounts/accounts-page").then((m) => ({ default: m.AccountsPage })));
const SyncJobs = lazy(() => import("@/features/sync-jobs/sync-jobs-page").then((m) => ({ default: m.SyncJobsPage })));
const Exports = lazy(() => import("@/features/exports/exports-page").then((m) => ({ default: m.ExportsPage })));
const Audit = lazy(() => import("@/features/audit/audit-page").then((m) => ({ default: m.AuditPage })));
const Analytics = lazy(() => import("@/features/analytics/analytics-page").then((m) => ({ default: m.AnalyticsPage })));
const Settings = lazy(() => import("@/features/settings/settings-page").then((m) => ({ default: m.SettingsPage })));

export const makeQueryClient = () => new QueryClient({
  defaultOptions: {
    queries: { staleTime: 15_000, refetchOnWindowFocus: false, retry: (n, e) => !(e instanceof ApiError && e.status >= 400 && e.status < 500) && n < 2 },
  },
});

function Protected({ children }: { children: ReactNode }) {
  const { me, loading } = useAuth();
  const loc = useLocation();
  if (loading) return <div className="p-8"><LoadingRows rows={4} /></div>;
  if (!me) return <Navigate to="/login" replace state={{ from: loc.pathname + loc.search }} />;
  return <>{children}</>;
}

export function AppRoutes() {
  return (
    <Suspense fallback={<div className="p-6"><LoadingRows rows={5} /></div>}>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route element={<Protected><AppShell /></Protected>}>
          <Route index element={<Overview />} />
          <Route path="requirements" element={<Requirements />} />
          <Route path="requirements/:id" element={<RequirementDetail />} />
          <Route path="candidates" element={<Candidates />} />
          <Route path="candidates/:id" element={<CandidateDetail />} />
          <Route path="duplicates" element={<Duplicates />} />
          <Route path="accounts" element={<Accounts />} />
          <Route path="sync-jobs" element={<SyncJobs />} />
          <Route path="exports" element={<Exports />} />
          <Route path="audit" element={<Audit />} />
          <Route path="analytics" element={<Analytics />} />
          <Route path="settings" element={<Settings />} />
          <Route path="*" element={<div className="py-16 text-center"><h1 className="text-lg font-semibold">Page not found</h1></div>} />
        </Route>
      </Routes>
    </Suspense>
  );
}

export default function App() {
  const qc = makeQueryClient();
  return (
    <QueryClientProvider client={qc}>
      <TooltipProvider>
        <AuthProvider>
          <BrowserRouter><AppRoutes /></BrowserRouter>
          <Toaster position="top-right" richColors closeButton />
        </AuthProvider>
      </TooltipProvider>
    </QueryClientProvider>
  );
}
