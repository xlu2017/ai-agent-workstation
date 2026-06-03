import React, { useState } from "react";

export default function UserForm() {
  const [formData, setFormData] = useState({ name: "", email: "", role: "developer" });
  const [submitted, setSubmitted] = useState(false);

  const handleSubmit = (e) => {
    e.preventDefault();
    setSubmitted(true);
  };

  const handleChange = (e) => {
    setFormData({ ...formData, [e.target.name]: e.target.value });
  };

  if (submitted) {
    return (
      <div style={{ padding: 20, background: "#ecfdf5", borderRadius: 8 }}>
        <h3>Form Submitted</h3>
        <p>Name: {formData.name}</p>
        <p>Email: {formData.email}</p>
        <p>Role: {formData.role}</p>
        <button onClick={() => setSubmitted(false)} style={{ padding: "8px 16px", cursor: "pointer" }}>
          Reset
        </button>
      </div>
    );
  }

  return (
    <form onSubmit={handleSubmit} style={{ display: "flex", flexDirection: "column", gap: 16, maxWidth: 400 }}>
      <h2>User Registration</h2>
      <FormField label="Name" name="name" value={formData.name} onChange={handleChange} placeholder="Enter your name" />
      <FormField label="Email" name="email" type="email" value={formData.email} onChange={handleChange} placeholder="you@example.com" />
      <SelectField label="Role" name="role" value={formData.role} onChange={handleChange}
        options={[
          { value: "developer", label: "Developer" },
          { value: "designer", label: "Designer" },
          { value: "manager", label: "Manager" },
        ]}
      />
      <button type="submit" style={{ padding: "10px 20px", background: "#4f46e5", color: "white", border: "none", borderRadius: 6, cursor: "pointer", fontSize: 14 }}>
        Submit
      </button>
    </form>
  );
}

function FormField({ label, name, type = "text", value, onChange, placeholder }) {
  return (
    <div>
      <label style={{ display: "block", marginBottom: 4, fontWeight: 500 }}>{label}</label>
      <input
        type={type}
        name={name}
        value={value}
        onChange={onChange}
        placeholder={placeholder}
        style={{ width: "100%", padding: 8, border: "1px solid #d1d5db", borderRadius: 4, fontSize: 14 }}
      />
    </div>
  );
}

function SelectField({ label, name, value, onChange, options }) {
  return (
    <div>
      <label style={{ display: "block", marginBottom: 4, fontWeight: 500 }}>{label}</label>
      <select name={name} value={value} onChange={onChange} style={{ width: "100%", padding: 8, border: "1px solid #d1d5db", borderRadius: 4, fontSize: 14 }}>
        {options.map((opt) => (
          <option key={opt.value} value={opt.value}>{opt.label}</option>
        ))}
      </select>
    </div>
  );
}
