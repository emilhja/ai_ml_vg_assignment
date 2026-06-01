import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { loadWideScreen, saveWideScreen } from "../lib/layoutPrefs";

type LayoutContextValue = {
  wideScreen: boolean;
  setWideScreen: (enabled: boolean) => void;
  toggleWideScreen: () => void;
};

const LayoutContext = createContext<LayoutContextValue | null>(null);

export function LayoutProvider({ children }: { children: ReactNode }) {
  const [wideScreen, setWideScreenState] = useState(loadWideScreen);

  const setWideScreen = useCallback((enabled: boolean) => {
    setWideScreenState(enabled);
    saveWideScreen(enabled);
  }, []);

  const toggleWideScreen = useCallback(() => {
    setWideScreenState((prev) => {
      const next = !prev;
      saveWideScreen(next);
      return next;
    });
  }, []);

  useEffect(() => {
    document.documentElement.classList.toggle("wide-screen", wideScreen);
  }, [wideScreen]);

  return (
    <LayoutContext.Provider value={{ wideScreen, setWideScreen, toggleWideScreen }}>
      {children}
    </LayoutContext.Provider>
  );
}

export function useLayout(): LayoutContextValue {
  const ctx = useContext(LayoutContext);
  if (!ctx) throw new Error("useLayout must be used within LayoutProvider");
  return ctx;
}
