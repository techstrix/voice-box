import { NavLink } from "react-router-dom";
import { UploadCloud, Building2, Sun, Moon } from "lucide-react";
import { useTheme } from "../theme/ThemeContext";
import "./Sidebar.css";

export default function Sidebar({ onCompanyClick }) {
  const { theme, toggleTheme } = useTheme();

  return (
    <aside className="sidebar">
      <div className="sidebar-brand">Voice-Box</div>

      <nav aria-label="Primary">
        <NavLink to="/upload" className="sidebar-link">
          <UploadCloud size={20} aria-hidden="true" />
          <span>Upload</span>
        </NavLink>

        <button className="sidebar-link sidebar-link-button" onClick={onCompanyClick}>
          <Building2 size={20} aria-hidden="true" />
          <span>Company</span>
        </button>
      </nav>

      <button
        className="theme-toggle"
        onClick={toggleTheme}
        aria-pressed={theme === "dark"}
      >
        {theme === "light" ? <Moon size={18} /> : <Sun size={18} />}
        <span>{theme === "light" ? "Dark mode" : "Light mode"}</span>
      </button>
    </aside>
  );
}