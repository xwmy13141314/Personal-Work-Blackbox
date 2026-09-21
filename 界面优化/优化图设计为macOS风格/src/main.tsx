
  import { createRoot } from "react-dom/client";
  import App from "./app/App.tsx";
  import { initFontSize } from "./app/lib/fontSize";
  import "./styles/index.css";

  initFontSize();

  createRoot(document.getElementById("root")!).render(<App />);
  