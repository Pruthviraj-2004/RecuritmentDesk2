import { useState } from "react";

/** Skill chips never overflow their column: each chip truncates (full text on hover) and "+N" expands the rest inline. */
export function SkillChips({ skills, limit = 4, width = 260 }: { skills: string[]; limit?: number; width?: number }) {
  const [open, setOpen] = useState(false);
  if (skills.length === 0) return <span className="text-muted-foreground">—</span>;
  const shown = open ? skills : skills.slice(0, limit);
  const hidden = skills.length - limit;
  return (
    <div className="flex max-w-full flex-wrap gap-1" style={{ width }}>
      {shown.map((s) => (
        <span key={s} title={s} className="inline-flex max-w-full items-center rounded-full bg-secondary px-2 py-0.5 text-xs font-medium text-secondary-foreground transition-colors hover:bg-accent hover:text-accent-foreground">
          <span className="truncate">{s}</span>
        </span>
      ))}
      {hidden > 0 && (
        <button type="button" aria-expanded={open} aria-label={open ? "Show fewer skills" : `Show ${hidden} more skills`} onClick={() => setOpen((o) => !o)}
          className="inline-flex items-center rounded-full bg-muted px-2 py-0.5 text-xs font-medium text-muted-foreground transition-all hover:bg-primary hover:text-primary-foreground active:scale-95">
          {open ? "Show less" : `+${hidden}`}
        </button>
      )}
    </div>
  );
}
