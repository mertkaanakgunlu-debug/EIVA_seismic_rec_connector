import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import { startRendererDiagnostics } from "./lib/diagnostics";

startRendererDiagnostics();
createRoot(document.getElementById("root")!).render(<StrictMode><App /></StrictMode>);
