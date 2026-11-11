import React, { lazy, Suspense } from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import { AppShell, Skeleton, ToastProvider } from "@ui";
import { api } from "@lib/api";
import { readPalette, readTheme, useApi } from "@lib/hooks";
import { AuthProvider, useAuth } from "@lib/auth";
import SignIn, { ForgotPassword, ResetPassword, SignUp, VerifyEmail } from "./pages/SignIn";
import Landing from "./pages/Landing";
import Overview from "./pages/Overview";
import Contracts from "./pages/Contracts";
import NewContract from "./pages/NewContract";
import ContractDetail from "./pages/ContractDetail";
import Inbox from "./pages/Inbox";
import Ledger from "./pages/Ledger";
import Evaluation from "./pages/Evaluation";
const Architecture = lazy(() => import("./pages/Architecture"));
const Gallery = lazy(() => import("./pages/Gallery"));
const Annotate = lazy(() => import("./pages/Annotate"));
const Settings = lazy(() => import("./pages/Settings"));
const Themes = lazy(() => import("./pages/Themes"));

function App() {
  const { user, signOut } = useAuth();
  const inbox = useApi(api.inbox, [], () => 4000);
  const health = useApi(api.health, []);
  return (
    <AppShell inboxCount={inbox.data?.length ?? 0} llm={health.data?.llm} user={user} onSignOut={signOut}>
      <Suspense fallback={<Skeleton height={320} />}>
      <Routes>
        <Route path="/" element={<Overview />} />
        <Route path="/contracts" element={<Contracts />} />
        <Route path="/contracts/:id" element={<ContractDetail onChange={inbox.reload} />} />
        <Route path="/new" element={<NewContract />} />
        <Route path="/inbox" element={<Inbox onChange={inbox.reload} />} />
        <Route path="/ledger" element={<Ledger />} />
        <Route path="/annotate" element={<Annotate />} />
        <Route path="/settings" element={<Settings />} />
        <Route path="/themes" element={<Themes />} />
        <Route path="/evaluation" element={<Evaluation />} />
        <Route path="/architecture" element={<Architecture />} />
        <Route path="/ui" element={<Gallery />} />
        <Route path="*" element={<Overview />} />
      </Routes>
      </Suspense>
    </AppShell>
  );
}

// apply the saved colour palette before the first paint
document.documentElement.setAttribute("data-palette", readPalette());
document.documentElement.setAttribute("data-theme", readTheme());

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <BrowserRouter>
      <ToastProvider>
        <AuthProvider gate={(status, onSignedIn, error) => (
          // signed out: public website at "/", sign-in everywhere else (first-run setup always shows sign-in)
          <Routes>
            {!status?.setup_required && <Route path="/" element={<Landing status={status} onSignedIn={onSignedIn} />} />}
            <Route path="/signup" element={<SignUp status={status} onSignedIn={onSignedIn} />} />
            <Route path="/verify" element={<VerifyEmail status={status} onSignedIn={onSignedIn} />} />
            <Route path="/forgot" element={<ForgotPassword status={status} onSignedIn={onSignedIn} />} />
            <Route path="/reset" element={<ResetPassword status={status} onSignedIn={onSignedIn} />} />
            <Route path="*" element={<SignIn status={status} onSignedIn={onSignedIn} error={error} />} />
          </Routes>
        )}>
          <App />
        </AuthProvider>
      </ToastProvider>
    </BrowserRouter>
  </React.StrictMode>,
);
