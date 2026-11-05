import { Link, useLocation, useNavigate } from "react-router-dom";
import {
  ChevronRight,
  Database,
  Plus,
  Settings,
} from "lucide-react";
import { BrandMark } from "../common/BrandMark";
import { ConversationList } from "../conversations/ConversationList";
import { useApp } from "../../context/AppContext";
import { vi } from "../../i18n/vi";
import { API_BASE_URL } from "../../api/client";
export function Sidebar({ onNavigate }: { onNavigate: () => void }) {
  const navigate = useNavigate();
  const location = useLocation();
  const { status } = useApp();
  return (
    <div className="sidebar-inner">
      <Link to="/chat" className="brand" onClick={onNavigate}>
        <BrandMark />
        <strong>{vi.brand}</strong>
      </Link>
      <button
        className="new-chat-button"
        onClick={() => {
          navigate("/chat", { state: { reset: Date.now() } });
          onNavigate();
        }}
      >
        <Plus size={19} />
        {vi.newChat}
      </button>
      <div className="sidebar-section-label">
        CUỘC TRÒ CHUYỆN <span>{status.mode === "mock" ? "DEMO" : ""}</span>
      </div>
      <ConversationList onNavigate={onNavigate} />
      <div className="sidebar-bottom">
        <a href={`${API_BASE_URL}/data?return_to=${encodeURIComponent(window.location.origin)}`} className="settings-link" onClick={onNavigate}>
          <Database size={18} /> Quản lý dữ liệu <ChevronRight size={16} />
        </a>
        <Link
          to="/settings"
          onClick={onNavigate}
          className={`settings-link ${location.pathname === "/settings" ? "active" : ""}`}
        >
          <Settings size={18} />
          {vi.settings}
          <ChevronRight size={16} />
        </Link>
      </div>
    </div>
  );
}
