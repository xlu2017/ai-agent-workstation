import React, { useState } from "react";

const INITIAL_TASKS = [
  { id: 1, text: "Set up UI bridge service", done: true },
  { id: 2, text: "Create browser extension", done: true },
  { id: 3, text: "Implement source mapping", done: false },
  { id: 4, text: "Test end-to-end flow", done: false },
  { id: 5, text: "Connect to OpenHands", done: false },
];

export default function TaskList() {
  const [tasks, setTasks] = useState(INITIAL_TASKS);
  const [newTask, setNewTask] = useState("");

  const toggleTask = (id) => {
    setTasks(tasks.map((t) => t.id === id ? { ...t, done: !t.done } : t));
  };

  const addTask = (e) => {
    e.preventDefault();
    if (!newTask.trim()) return;
    setTasks([...tasks, { id: Date.now(), text: newTask, done: false }]);
    setNewTask("");
  };

  const completed = tasks.filter((t) => t.done).length;

  return (
    <div>
      <h2>Task Manager</h2>
      <ProgressBar completed={completed} total={tasks.length} />
      <ul style={{ listStyle: "none", padding: 0 }}>
        {tasks.map((task) => (
          <TaskItem key={task.id} task={task} onToggle={() => toggleTask(task.id)} />
        ))}
      </ul>
      <form onSubmit={addTask} style={{ display: "flex", gap: 8, marginTop: 16 }}>
        <input
          value={newTask}
          onChange={(e) => setNewTask(e.target.value)}
          placeholder="Add a new task..."
          style={{ flex: 1, padding: 8, border: "1px solid #d1d5db", borderRadius: 4 }}
        />
        <button type="submit" style={{ padding: "8px 16px", background: "#059669", color: "white", border: "none", borderRadius: 4, cursor: "pointer" }}>
          Add
        </button>
      </form>
    </div>
  );
}

function TaskItem({ task, onToggle }) {
  return (
    <li style={{ padding: "10px 12px", margin: "4px 0", background: "#f8fafc", borderRadius: 4, display: "flex", alignItems: "center", gap: 12 }}>
      <input type="checkbox" checked={task.done} onChange={onToggle} style={{ width: 18, height: 18 }} />
      <span style={{ textDecoration: task.done ? "line-through" : "none", color: task.done ? "#94a3b8" : "#1e293b" }}>
        {task.text}
      </span>
    </li>
  );
}

function ProgressBar({ completed, total }) {
  const pct = total > 0 ? Math.round((completed / total) * 100) : 0;
  return (
    <div style={{ marginBottom: 16 }}>
      <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 4, fontSize: 13, color: "#64748b" }}>
        <span>{completed} of {total} complete</span>
        <span>{pct}%</span>
      </div>
      <div style={{ height: 8, background: "#e2e8f0", borderRadius: 4, overflow: "hidden" }}>
        <div style={{ height: "100%", width: `${pct}%`, background: "#059669", borderRadius: 4, transition: "width 0.3s" }} />
      </div>
    </div>
  );
}
