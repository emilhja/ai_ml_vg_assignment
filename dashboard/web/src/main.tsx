import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter } from "react-router-dom";
import App from "./App";
import { LayoutProvider } from "./context/LayoutContext";
import "./index.css";

const queryClient = new QueryClient({
  defaultOptions: { queries: { staleTime: 5_000, retry: 1 } },
});

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <LayoutProvider>
          <App />
        </LayoutProvider>
      </BrowserRouter>
    </QueryClientProvider>
  </StrictMode>,
);
