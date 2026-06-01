import { NavLink, Route, Routes, useLocation } from "react-router-dom";
import CurrentSessionPage from "./pages/CurrentSessionPage";
import HistoryPage from "./pages/HistoryPage";
import SessionDetailPage from "./pages/SessionDetailPage";
import StatsPage from "./pages/StatsPage";
import StatusBanner from "./components/StatusBanner";
import WideScreenToggle from "./components/WideScreenToggle";
import { useLayout } from "./context/LayoutContext";

function NavItem({ to, children }: { to: string; children: React.ReactNode }) {
  return (
    <NavLink
      to={to}
      className={({ isActive }) =>
        `px-3 py-2 rounded-md text-sm font-medium ${
          isActive ? "bg-accent/20 text-accent" : "text-muted hover:text-white"
        }`
      }
    >
      {children}
    </NavLink>
  );
}

export default function App() {
  const { wideScreen } = useLayout();
  const location = useLocation();
  const fillViewport = location.pathname === "/";
  const shellWidth = wideScreen ? "w-full max-w-none px-6" : "w-full max-w-7xl mx-auto px-4";

  return (
    <div className="h-full flex flex-col overflow-hidden">
      <header className="shrink-0 border-b border-slate-700/60 bg-panel/80 backdrop-blur z-10">
        <div className={`${shellWidth} py-3 flex items-center justify-between gap-4`}>
          <div>
            <h1 className="text-lg font-semibold text-white">VG Agent Dashboard</h1>
            <p className="text-xs text-amber-200/80">
              Traces may contain redacted-but-sensitive data. Local use only.
            </p>
            <StatusBanner />
          </div>
          <div className="flex items-center gap-2">
            <WideScreenToggle />
            <nav className="flex gap-1">
              <NavItem to="/">Current</NavItem>
              <NavItem to="/history">History</NavItem>
              <NavItem to="/stats">Statistics</NavItem>
            </nav>
          </div>
        </div>
      </header>
      <main className={`flex-1 min-h-0 flex flex-col overflow-hidden ${shellWidth} py-4`}>
        <div
          className={
            fillViewport
              ? "flex-1 min-h-0 flex flex-col overflow-hidden"
              : "flex-1 min-h-0 overflow-y-auto"
          }
        >
          <Routes>
            <Route path="/" element={<CurrentSessionPage />} />
            <Route path="/history" element={<HistoryPage />} />
            <Route path="/history/:sessionId" element={<SessionDetailPage />} />
            <Route path="/stats" element={<StatsPage />} />
          </Routes>
        </div>
      </main>
    </div>
  );
}
