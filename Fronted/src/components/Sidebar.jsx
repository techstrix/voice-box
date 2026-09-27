import { NavLink } from "react-router-dom";
import { UploadCloud, Building2, Phone, Sun, Moon } from "lucide-react";
import { useTheme } from "../theme/ThemeContext";
import "./Sidebar.css";

export default function Sidebar({ onCompanyClick }) {
  const { theme, toggleTheme } = useTheme();

  return (
    <aside className="sidebar">
      <div className="sidebar-brand">
        <span className="sidebar-brand-full">Voice-Box</span>
        <span className="sidebar-brand-mark" aria-hidden="true">V</span>
      </div>

      <nav aria-label="Primary">
        <NavLink to="/upload" className="sidebar-link" aria-label="Upload" title="Upload">
          <UploadCloud size={20} aria-hidden="true" />
          <span>Upload</span>
        </NavLink>

        <NavLink to="/call-test" className="sidebar-link" aria-label="Call test" title="Call test">
          <Phone size={20} aria-hidden="true" />
          <span>Call test</span>
        </NavLink>

        <button className="sidebar-link sidebar-link-button" onClick={onCompanyClick} aria-label="Company" title="Company">
          <Building2 size={20} aria-hidden="true" />
          <span>Company</span>
        </button>
      </nav>

      <button
        className="theme-toggle"
        onClick={toggleTheme}
        aria-pressed={theme === "dark"}
        aria-label={`Switch to ${theme === "light" ? "dark" : "light"} mode`}
        title={`Switch to ${theme === "light" ? "dark" : "light"} mode`}
      >
        {theme === "light" ? <Moon size={18} /> : <Sun size={18} />}
        <span>{theme === "light" ? "Dark mode" : "Light mode"}</span>
      </button>
    </aside>
  );
}