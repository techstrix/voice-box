import { BrowserRouter, Routes, Route } from "react-router-dom";
import { useState } from "react";
import { ThemeProvider } from "./theme/ThemeContext";
import Sidebar from "./components/Sidebar";
import Home from "./pages/Home";
import Upload from "./pages/Upload";
import "./index.css";

export default function App() {
  const [showCompanyPanel, setShowCompanyPanel] = useState(false);

  return (
    <ThemeProvider>
      <BrowserRouter>
        <div className="app-shell">
          <Sidebar onCompanyClick={() => setShowCompanyPanel(true)} />
          <div className="main-content">
            <Routes>
              <Route path="/" element={<Home />} />
              <Route path="/upload" element={<Upload />} />
            </Routes>
          </div>
        </div>

        {showCompanyPanel && (
          <div className="modal-overlay" role="dialog" aria-modal="true" aria-label="Company information">
            <div className="modal">
              <h2>Company</h2>
              <p>A short blurb about Voice-Box goes here.</p>
              <button className="btn" onClick={() => setShowCompanyPanel(false)}>Close</button>
            </div>
          </div>
        )}
      </BrowserRouter>
    </ThemeProvider>
  );
}