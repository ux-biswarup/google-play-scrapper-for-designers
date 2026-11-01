// Apply the saved theme before first paint to avoid a flash.
try {
  const saved = localStorage.getItem("ri.theme");
  if (saved === "dark" || (!saved && matchMedia("(prefers-color-scheme: dark)").matches)) {
    document.documentElement.classList.add("dark");
  }
} catch {}
