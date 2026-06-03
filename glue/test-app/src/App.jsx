import React, { useState } from "react";
import Header from "./components/Header.jsx";
import UserForm from "./components/UserForm.jsx";
import TaskList from "./components/TaskList.jsx";
import Footer from "./components/Footer.jsx";

export default function App() {
  const [view, setView] = useState("tasks");

  return (
    <div style={{ maxWidth: 800, margin: "0 auto", padding: 20, fontFamily: "system-ui" }}>
      <Header onNavigate={setView} currentView={view} />
      <main style={{ minHeight: 400, padding: "20px 0" }}>
        {view === "tasks" && <TaskList />}
        {view === "form" && <UserForm />}
        {view === "about" && <AboutSection />}
      </main>
      <Footer />
    </div>
  );
}

function AboutSection() {
  return (
    <section>
      <h2>About This App</h2>
      <p>This is a test application for the UI-to-Code bridge. It demonstrates multiple nested
      components, forms, buttons, and route-like views that the browser extension can inspect.</p>
      <p>Try right-clicking any element and selecting "Inspect element for agent" or
      "Send selection to agent" from the context menu.</p>
    </section>
  );
}
