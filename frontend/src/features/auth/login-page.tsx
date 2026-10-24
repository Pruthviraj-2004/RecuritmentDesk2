import { zodResolver } from "@hookform/resolvers/zod";
import { BriefcaseBusiness } from "lucide-react";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { Navigate, useLocation, useNavigate } from "react-router-dom";
import { z } from "zod";
import { useAuth } from "@/app/auth";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Field, Input } from "@/components/ui/form";
import { errorMessage } from "@/lib/api";

const schema = z.object({ email: z.string().trim().min(1, "Enter your email").email("Enter a valid email address"), password: z.string().min(1, "Enter your password") });
type Values = z.infer<typeof schema>;

export function LoginPage() {
  const { me, login, loading } = useAuth();
  const nav = useNavigate();
  const loc = useLocation();
  const [error, setError] = useState<string | null>(null);
  const { register, handleSubmit, formState: { errors, isSubmitting } } = useForm<Values>({ resolver: zodResolver(schema) });
  const dest = (loc.state as { from?: string } | null)?.from ?? "/";
  if (!loading && me) return <Navigate to={dest} replace />;

  const onSubmit = async (v: Values) => {
    setError(null);
    try { await login(v.email, v.password); nav(dest, { replace: true }); } catch (e) { setError(errorMessage(e)); }
  };
  return (
    <div className="grid min-h-screen place-items-center bg-background p-4">
      <div className="w-full max-w-sm">
        <div className="mb-6 flex items-center justify-center gap-2 text-lg font-semibold">
          <span className="grid size-9 place-items-center rounded-lg bg-primary text-primary-foreground"><BriefcaseBusiness className="size-5" /></span> RecruitmentDesk
        </div>
        <Card><CardContent className="p-6">
          <h1 className="text-lg font-semibold">Sign in</h1>
          <p className="mb-4 mt-1 text-sm text-muted-foreground">Recruitment email intelligence for your connected Gmail accounts.</p>
          <form onSubmit={handleSubmit(onSubmit)} className="space-y-4" noValidate>
            {error && <div role="alert" className="rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive">{error}</div>}
            <Field label="Email" htmlFor="email" error={errors.email?.message}><Input id="email" type="email" autoComplete="username" autoFocus aria-invalid={!!errors.email} {...register("email")} /></Field>
            <Field label="Password" htmlFor="password" error={errors.password?.message}><Input id="password" type="password" autoComplete="current-password" aria-invalid={!!errors.password} {...register("password")} /></Field>
            <Button type="submit" className="w-full" loading={isSubmitting}>Sign in</Button>
          </form>
          <p className="mt-4 text-xs text-muted-foreground">No account yet? An administrator is created with <code className="rounded bg-muted px-1">python -m app.cli create-admin</code> (see the setup guide).</p>
        </CardContent></Card>
      </div>
    </div>
  );
}
