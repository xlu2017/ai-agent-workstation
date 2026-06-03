import React from "react";

export default function Header({ onNavigate, currentView }) {
  const navStyle = (view) => ({
    padding: "8px 16px",
    cursor: "pointer",
    borderRadius: 4,
    border: "none",
    background: currentView === view ? "#4f46e5" : "#f1f5f9",
    color: currentView === view ? "white" : "#374151",
    fontWeight: currentView === view ? 600 : 400,
  });

  return (
    <header style={{ borderBottom: "1px solid #e2e8f0", paddingBottom: 16 }}>
      <h1 style={{ margin: "0 0 12px", fontSize: 24 }}>UI Bridge Test App</h1>
      <nav style={{ display: "flex", gap: 8 }}>
        <button style={navStyle("tasks")} onClick={() => onNavigate("tasks")}>Tasks</button>
        <button style={navStyle("form")} onClick={() => onNavigate("form")}>User Form</button>
        <button style={navStyle("about")} onClick={() => onNavigate("about")}>About</button>
      </nav>
    </header>
  );
}
