import { useCallback, useEffect, useState } from "react";

export type Theme = "light" | "dark" | "system";
const KEY = "rd-theme";

function apply(theme: Theme) {
  const dark = theme === "dark" || (theme === "system" && window.matchMedia("(prefers-color-scheme: dark)").matches);
  document.documentElement.classList.toggle("dark", dark);
}
function read(): Theme {
  try { const v = localStorage.getItem(KEY); return v === "light" || v === "dark" || v === "system" ? v : "system"; } catch { return "system"; }
}

/** Theme preference is a per-device convenience, so localStorage is appropriate (no credentials are stored). */
export function useTheme() {
  const [theme, setThemeState] = useState<Theme>(read);
  useEffect(() => { apply(theme); }, [theme]);
  useEffect(() => {
    if (theme !== "system") return;
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    const h = () => apply("system");
    mq.addEventListener?.("change", h);
    return () => mq.removeEventListener?.("change", h);
  }, [theme]);
  const setTheme = useCallback((t: Theme) => {
    try { localStorage.setItem(KEY, t); } catch { /* storage unavailable: still apply for this session */ }
    setThemeState(t);
  }, []);
  return { theme, setTheme };
}
