import React, { lazy, Suspense } from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import { AppShell, Skeleton, ToastProvider } from "@ui";
import { api } from "@lib/api";
import { useApi } from "@lib/hooks";
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

function App() {
  const inbox = useApi(api.inbox, [], () => 4000);
  const health = useApi(api.health, []);
  return (
    <AppShell inboxCount={inbox.data?.length ?? 0} llm={health.data?.llm}>
      <Suspense fallback={<Skeleton height={320} />}>
      <Routes>
        <Route path="/" element={<Overview />} />
        <Route path="/contracts" element={<Contracts />} />
        <Route path="/contracts/:id" element={<ContractDetail onChange={inbox.reload} />} />
        <Route path="/new" element={<NewContract />} />
        <Route path="/inbox" element={<Inbox onChange={inbox.reload} />} />
        <Route path="/ledger" element={<Ledger />} />
        <Route path="/annotate" element={<Annotate />} />
        <Route path="/evaluation" element={<Evaluation />} />
        <Route path="/architecture" element={<Architecture />} />
        <Route path="/ui" element={<Gallery />} />
        <Route path="*" element={<Overview />} />
      </Routes>
      </Suspense>
    </AppShell>
  );
}

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <BrowserRouter>
      <ToastProvider>
        <App />
      </ToastProvider>
    </BrowserRouter>
  </React.StrictMode>,
);
