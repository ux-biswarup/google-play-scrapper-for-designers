import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Navigate, Route, Routes } from "react-router";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ConnectionProvider, ThemeProvider } from "./lib/settings";
import { Shell } from "./components/Shell";
import { NewAnalysisPage } from "./pages/NewAnalysis";
import { RunPage } from "./pages/RunPage";
import { SettingsPage } from "./pages/Settings";
import { ConnectPage } from "./pages/Connect";
import { AboutPage } from "./pages/About";
import { BenchmarkDetailPage, BenchmarksPage } from "./pages/Benchmark";
import "./index.css";

const queryClient = new QueryClient({
  defaultOptions: { queries: { refetchOnWindowFocus: false, retry: 1 } },
});

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <ThemeProvider>
        <ConnectionProvider>
          <BrowserRouter>
            <Routes>
              <Route element={<Shell />}>
                <Route index element={<Navigate to="/new" replace />} />
                <Route path="new" element={<NewAnalysisPage />} />
                <Route path="settings" element={<SettingsPage />} />
                <Route path="connect" element={<ConnectPage />} />
                <Route path="about" element={<AboutPage />} />
                <Route path="runs/:id" element={<RunPage />} />
                <Route path="benchmark" element={<BenchmarksPage />} />
                <Route path="benchmark/:id" element={<BenchmarkDetailPage />} />
                <Route path="*" element={<Navigate to="/new" replace />} />
              </Route>
            </Routes>
          </BrowserRouter>
        </ConnectionProvider>
      </ThemeProvider>
    </QueryClientProvider>
  </StrictMode>,
);
