import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./app/App";
import "./theme/tokens.css";

const root = document.getElementById("root");
if (root === null) {
  throw new Error("The #root element is missing from index.html");
}

createRoot(root).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
