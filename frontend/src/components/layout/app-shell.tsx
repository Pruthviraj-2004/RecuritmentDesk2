import {
  AlertTriangle, BarChart3, Bell, BriefcaseBusiness, Copy, FileSpreadsheet, History, LayoutDashboard, LogOut, Mail, Menu, Monitor, Moon, Plus, RefreshCw, Search,
  Settings, Sun, Zap, Activity, CheckCircle2, PanelLeftClose, PanelLeftOpen, UserPlus, Users,
} from "lucide-react";
import { useEffect, useState, type FormEvent } from "react";
import { Link, NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "@/app/auth";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent } from "@/components/ui/dialog";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel, DropdownMenuSeparator, DropdownMenuTrigger } from "@/components/ui/dropdown";
import { Input } from "@/components/ui/form";
import { Tip } from "@/components/ui/tooltip";
import { useConnectGmail, useSyncAll } from "@/hooks/use-gmail";
import { useTheme } from "@/hooks/use-theme";
import { api } from "@/lib/api";
import { cn, fmtRelative } from "@/lib/utils";
import { useAccounts, useAction, useJobsSummary, useJobs, useNotifications } from "@/services/hooks";

const NAV = [
  { to: "/", label: "Overview", icon: LayoutDashboard, end: true },
  { to: "/requirements", label: "Recruitment Requirements", icon: BriefcaseBusiness },
  { to: "/candidates", label: "Candidate Profiles", icon: Users },
  { to: "/duplicates", label: "Duplicate Review", icon: Copy },
  { to: "/accounts", label: "Connected Accounts", icon: Mail },
  { to: "/sync-jobs", label: "Synchronization Jobs", icon: RefreshCw },
  { to: "/exports", label: "Exports & Deliveries", icon: FileSpreadsheet },
  { to: "/audit", label: "Activity & Audit Logs", icon: History },
  { to: "/analytics", label: "Analytics", icon: BarChart3 },
  { to: "/settings", label: "Settings", icon: Settings },
];

function Brand({ collapsed = false }: { collapsed?: boolean }) {
  return (
    <Link to="/" aria-label="RecruitmentDesk home" className={cn("flex items-center gap-2 px-2 font-semibold tracking-tight", collapsed && "justify-center px-0")}>
      <span className="grid size-7 shrink-0 place-items-center rounded-md bg-primary text-primary-foreground transition-transform duration-200 hover:rotate-6"><BriefcaseBusiness className="size-4" /></span>
      {!collapsed && <span className="truncate">RecruitmentDesk</span>}
    </Link>
  );
}

function NavList({ onNavigate, collapsed = false }: { onNavigate?: () => void; collapsed?: boolean }) {
  return (
    <nav aria-label="Main" className="flex flex-col gap-0.5 px-2">
      {NAV.map(({ to, label, icon: Icon, end }) => {
        const link = (
          <NavLink key={to} to={to} end={end} onClick={onNavigate} aria-label={collapsed ? label : undefined}
            className={({ isActive }) => cn("group flex items-center gap-2.5 rounded-md px-2.5 py-2 text-sm font-medium text-sidebar-foreground/80 transition-all duration-150 hover:bg-accent hover:text-accent-foreground",
              collapsed && "justify-center px-0", isActive && "bg-accent text-accent-foreground")}>
            <Icon className="size-4 shrink-0 transition-transform duration-150 group-hover:scale-110" />
            {!collapsed && <span className="truncate transition-transform duration-150 group-hover:translate-x-0.5">{label}</span>}
          </NavLink>
        );
        return collapsed ? <Tip key={to} label={label}>{link}</Tip> : link;
      })}
    </nav>
  );
}

const COLLAPSE_KEY = "rd-sidebar-collapsed";
function useCollapsed(): [boolean, () => void] {
  const [c, setC] = useState(() => { try { return localStorage.getItem(COLLAPSE_KEY) === "1"; } catch { return false; } });
  const toggle = () => setC((v) => { const n = !v; try { localStorage.setItem(COLLAPSE_KEY, n ? "1" : "0"); } catch { /* preference only */ } return n; });
  return [c, toggle];
}

function SyncStatus() {
  const jobs = useJobs({ status: "active", page_size: 5 });
  const summary = useJobsSummary();
  const accounts = useAccounts();
  const active = jobs.data?.total ?? 0;
  const last = accounts.data?.map((a) => a.last_synced_at).filter(Boolean).sort().pop() ?? null;
  const label = active > 0 ? `Syncing (${active})` : `Synced ${fmtRelative(last)}`;
  return (
    <Tip label={active > 0 ? `${active} active job(s)` : last ? `Last successful sync ${fmtRelative(last)}` : "No successful sync yet"}>
      <Link to="/sync-jobs" className="hidden items-center gap-1.5 rounded-md border px-2.5 py-1.5 text-xs text-muted-foreground hover:bg-accent md:flex" aria-label="Synchronization status">
        {active > 0 ? <RefreshCw className="size-3.5 animate-spin text-primary" /> : (summary.data?.extraction_failed ?? 0) > 0 ? <AlertTriangle className="size-3.5 text-warning" /> : <CheckCircle2 className="size-3.5 text-success" />}
        <span>{label}</span>
      </Link>
    </Tip>
  );
}

function NotificationsMenu() {
  const { data } = useNotifications();
  const nav = useNavigate();
  const markAll = useAction({ fn: () => api.post("/notifications/read-all"), invalidate: [["notifications"]] });
  const unread = data?.unread ?? 0;
  return (
    <DropdownMenu onOpenChange={(o) => { if (!o && unread) markAll.mutate(); }}>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="icon" aria-label={`Notifications${unread ? `, ${unread} unread` : ""}`} className="relative">
          <Bell />
          {unread > 0 && <span className="absolute right-1.5 top-1.5 size-2 rounded-full bg-primary" />}
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent className="w-80">
        <DropdownMenuLabel>Notifications</DropdownMenuLabel>
        {(data?.items.length ?? 0) === 0 && <p className="px-2 py-6 text-center text-sm text-muted-foreground">You are all caught up.</p>}
        {data?.items.slice(0, 8).map((n) => (
          <DropdownMenuItem key={n.id} className="flex-col items-start gap-0.5" onSelect={() => n.link && nav(n.link)}>
            <span className={cn("text-sm", !n.read_at && "font-semibold")}>{n.title}</span>
            {n.body && <span className="line-clamp-2 text-xs text-muted-foreground">{n.body}</span>}
            <span className="text-[11px] text-muted-foreground">{fmtRelative(n.created_at)}</span>
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

function ThemeMenu() {
  const { theme, setTheme } = useTheme();
  const Icon = theme === "dark" ? Moon : theme === "light" ? Sun : Monitor;
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild><Button variant="ghost" size="icon" aria-label="Change theme"><Icon /></Button></DropdownMenuTrigger>
      <DropdownMenuContent>
        {(["light", "dark", "system"] as const).map((t) => (
          <DropdownMenuItem key={t} onSelect={() => setTheme(t)} aria-checked={theme === t} className={cn(theme === t && "font-semibold")}>
            {t === "light" ? <Sun /> : t === "dark" ? <Moon /> : <Monitor />} <span className="capitalize">{t}</span>
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

function QuickActions() {
  const nav = useNavigate();
  const { can } = useAuth();
  const sync = useSyncAll();
  const connect = useConnectGmail();
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild><Button size="sm"><Zap /> <span className="hidden sm:inline">Quick actions</span></Button></DropdownMenuTrigger>
      <DropdownMenuContent className="w-60">
        <DropdownMenuLabel>Quick actions</DropdownMenuLabel>
        <DropdownMenuItem disabled={!can("member")} onSelect={() => sync.mutate()}><RefreshCw /> Sync all accounts</DropdownMenuItem>
        <DropdownMenuItem onSelect={() => nav("/accounts")}><Mail /> Sync a selected account…</DropdownMenuItem>
        <DropdownMenuItem disabled={!can("admin")} onSelect={() => connect.mutate()}><Plus /> Connect Gmail account</DropdownMenuItem>
        <DropdownMenuSeparator />
        <DropdownMenuItem onSelect={() => nav("/requirements?review_status=needs_review")}><BriefcaseBusiness /> Review new requirements</DropdownMenuItem>
        <DropdownMenuItem onSelect={() => nav("/duplicates")}><Copy /> Review possible duplicates</DropdownMenuItem>
        <DropdownMenuSeparator />
        <DropdownMenuItem disabled={!can("member")} onSelect={() => nav("/candidates?add=1")}><UserPlus /> Add candidate</DropdownMenuItem>
        <DropdownMenuItem disabled={!can("member")} onSelect={() => nav("/candidates?import=1")}><Users /> Import candidates</DropdownMenuItem>
        <DropdownMenuSeparator />
        <DropdownMenuItem onSelect={() => nav("/requirements")}><FileSpreadsheet /> Export selected requirements</DropdownMenuItem>
        <DropdownMenuItem onSelect={() => nav("/exports?compose=1")}><Mail /> Compose an export email</DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

function UserMenu() {
  const { me, logout } = useAuth();
  const nav = useNavigate();
  if (!me) return null;
  const initials = me.user.display_name.split(" ").map((p) => p[0]).slice(0, 2).join("").toUpperCase();
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="icon" aria-label="User menu" className="rounded-full"><span className="grid size-8 place-items-center rounded-full bg-accent text-xs font-semibold text-accent-foreground">{initials}</span></Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent className="w-60">
        <div className="px-2 py-1.5">
          <p className="truncate text-sm font-medium">{me.user.display_name}</p>
          <p className="truncate text-xs text-muted-foreground">{me.user.email}</p>
          <Badge variant="secondary" className="mt-1.5 capitalize">{me.role}</Badge>
        </div>
        <DropdownMenuSeparator />
        <DropdownMenuItem onSelect={() => nav("/settings")}><Settings /> Settings</DropdownMenuItem>
        <DropdownMenuItem onSelect={async () => { await logout(); nav("/login"); }}><LogOut /> Sign out</DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

function GlobalSearch() {
  const nav = useNavigate();
  const loc = useLocation();
  const [q, setQ] = useState("");
  useEffect(() => { if (!loc.pathname.startsWith("/requirements")) setQ(""); }, [loc.pathname]);
  const submit = (e: FormEvent) => { e.preventDefault(); const v = q.trim(); nav(v ? `/requirements?q=${encodeURIComponent(v)}` : "/requirements"); };
  return (
    <form onSubmit={submit} role="search" className="relative hidden w-full max-w-sm sm:block">
      <Search className="pointer-events-none absolute left-2.5 top-2.5 size-4 text-muted-foreground" />
      <Input aria-label="Search requirements" placeholder="Search requirements, clients, skills…" className="pl-8" value={q} onChange={(e) => setQ(e.target.value)} />
    </form>
  );
}

function AccountWarning() {
  const { data } = useAccounts();
  const bad = data?.filter((a) => a.connection_status === "expired" || a.connection_status === "error") ?? [];
  if (!bad.length) return null;
  return (
    <div role="alert" className="flex flex-wrap items-center gap-2 border-b border-warning/30 bg-warning/10 px-4 py-2 text-sm">
      <AlertTriangle className="size-4 text-warning" />
      <span>{bad.length === 1 ? `${bad[0].email_address} needs attention` : `${bad.length} Gmail accounts need attention`}: synchronization is paused until reauthorized.</span>
      <Link to="/accounts" className="font-medium text-primary underline-offset-2 hover:underline">Fix now</Link>
    </div>
  );
}

export function AppShell() {
  const [open, setOpen] = useState(false);
  const [collapsed, toggleCollapsed] = useCollapsed();
  const loc = useLocation();
  useEffect(() => { setOpen(false); window.scrollTo(0, 0); }, [loc.pathname]);
  return (
    <div className={cn("min-h-screen transition-[grid-template-columns] duration-200 lg:grid", collapsed ? "lg:grid-cols-[64px_1fr]" : "lg:grid-cols-[256px_1fr]")}>
      <aside aria-label="Sidebar" data-collapsed={collapsed} className="sticky top-0 hidden h-screen flex-col gap-4 overflow-x-hidden overflow-y-auto border-r border-sidebar-border bg-sidebar py-4 lg:flex">
        <Brand collapsed={collapsed} />
        <NavList collapsed={collapsed} />
        <div className={cn("mt-auto flex items-center px-2", collapsed ? "justify-center" : "justify-between")}>
          {!collapsed && <p className="px-2 text-xs text-muted-foreground"><Activity className="mr-1 inline size-3" />v1.0</p>}
          <Tip label={collapsed ? "Expand sidebar" : "Collapse sidebar"}>
            <Button variant="ghost" size="icon" aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"} aria-expanded={!collapsed} onClick={toggleCollapsed}>
              {collapsed ? <PanelLeftOpen /> : <PanelLeftClose />}
            </Button>
          </Tip>
        </div>
      </aside>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent title="Navigation" variant="drawer" className="max-w-xs p-3 sm:max-w-xs lg:hidden"><NavList onNavigate={() => setOpen(false)} /></DialogContent>
      </Dialog>
      <div className="flex min-w-0 flex-col">
        <header className="sticky top-0 z-30 flex h-14 items-center gap-2 border-b bg-background/90 px-3 backdrop-blur sm:px-4">
          <Button variant="ghost" size="icon" className="lg:hidden" aria-label="Open navigation" onClick={() => setOpen(true)}><Menu /></Button>
          <div className="lg:hidden"><Brand /></div>
          <GlobalSearch />
          <div className="ml-auto flex items-center gap-1.5">
            <SyncStatus />
            <QuickActions />
            <NotificationsMenu />
            <ThemeMenu />
            <UserMenu />
          </div>
        </header>
        <AccountWarning />
        <main className="mx-auto w-full max-w-[1400px] flex-1 p-4 sm:p-6"><Outlet /></main>
      </div>
    </div>
  );
}
