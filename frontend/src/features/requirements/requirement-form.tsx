import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { Button } from "@/components/ui/button";
import { Field, Input, Select, Textarea } from "@/components/ui/form";
import { api } from "@/lib/api";
import { reqKeys, useAction, useUpdateRequirement } from "@/services/hooks";
import type { RequirementDetail, RequirementInput } from "@/types/api";

const optNum = (min = 0, max = 1_000_000_000) => z.string().trim().refine((v) => v === "" || (!Number.isNaN(Number(v)) && Number(v) >= min && Number(v) <= max), `Enter a number between ${min} and ${max}`);
const optEmail = z.string().trim().refine((v) => v === "" || z.string().email().safeParse(v).success, "Enter a valid email address");

export const requirementSchema = z.object({
  job_title: z.string().trim().max(300), client_name: z.string().trim().max(300), job_reference_id: z.string().trim().max(100),
  job_description: z.string().max(60000), required_skills: z.string(), preferred_skills: z.string(),
  minimum_experience: optNum(0, 60), maximum_experience: optNum(0, 60), seniority: z.string().trim().max(50), education: z.string().trim().max(500),
  salary_min: optNum(), salary_max: optNum(), salary_currency: z.string().trim().max(8), salary_period: z.enum(["", "hour", "day", "month", "year"]),
  employment_type: z.string().trim().max(50), notice_period: z.string().trim().max(100), number_of_openings: optNum(1, 10000),
  location: z.string().trim().max(300), city: z.string().trim().max(120), state: z.string().trim().max(120), country: z.string().trim().max(120),
  work_mode: z.enum(["unknown", "remote", "hybrid", "onsite"]),
  recruiter_name: z.string().trim().max(200), recruiter_email: optEmail, recruiter_phone: z.string().trim().max(50),
  submission_email: optEmail, submission_instructions: z.string().max(5000),
}).superRefine((v, ctx) => {
  if (v.minimum_experience && v.maximum_experience && Number(v.maximum_experience) < Number(v.minimum_experience)) ctx.addIssue({ code: "custom", path: ["maximum_experience"], message: "Must be at least the minimum" });
  if (v.salary_min && v.salary_max && Number(v.salary_max) < Number(v.salary_min)) ctx.addIssue({ code: "custom", path: ["salary_max"], message: "Must be at least the minimum" });
});
export type RequirementFormValues = z.infer<typeof requirementSchema>;

const list = (s: string) => s.split(/[,;\n]/).map((x) => x.trim()).filter(Boolean);
const num = (s: string) => (s === "" ? null : Number(s));
const nul = (s: string) => (s === "" ? null : s);

export function toDefaults(r?: RequirementDetail): RequirementFormValues {
  const s = (v: string | number | null | undefined) => (v == null ? "" : String(v));
  return {
    job_title: s(r?.job_title), client_name: s(r?.client_name), job_reference_id: s(r?.job_reference_id), job_description: s(r?.job_description),
    required_skills: (r?.required_skills ?? []).join(", "), preferred_skills: (r?.preferred_skills ?? []).join(", "),
    minimum_experience: s(r?.minimum_experience), maximum_experience: s(r?.maximum_experience), seniority: s(r?.seniority), education: s(r?.education),
    salary_min: s(r?.salary_min), salary_max: s(r?.salary_max), salary_currency: s(r?.salary_currency), salary_period: (r?.salary_period as RequirementFormValues["salary_period"]) ?? "",
    employment_type: s(r?.employment_type), notice_period: s(r?.notice_period), number_of_openings: s(r?.number_of_openings),
    location: s(r?.location), city: s(r?.city), state: s(r?.state), country: s(r?.country), work_mode: r?.work_mode ?? "unknown",
    recruiter_name: s(r?.recruiter_name), recruiter_email: s(r?.recruiter_email), recruiter_phone: s(r?.recruiter_phone),
    submission_email: s(r?.submission_email), submission_instructions: s(r?.submission_instructions),
  };
}

export function toPayload(v: RequirementFormValues): RequirementInput {
  return {
    job_title: nul(v.job_title), client_name: nul(v.client_name), job_reference_id: nul(v.job_reference_id), job_description: nul(v.job_description),
    required_skills: list(v.required_skills), preferred_skills: list(v.preferred_skills),
    minimum_experience: num(v.minimum_experience), maximum_experience: num(v.maximum_experience), seniority: nul(v.seniority), education: nul(v.education),
    salary_min: num(v.salary_min), salary_max: num(v.salary_max), salary_currency: nul(v.salary_currency.toUpperCase()), salary_period: v.salary_period === "" ? null : v.salary_period,
    employment_type: nul(v.employment_type), notice_period: nul(v.notice_period), number_of_openings: num(v.number_of_openings),
    location: nul(v.location), city: nul(v.city), state: nul(v.state), country: nul(v.country), work_mode: v.work_mode,
    recruiter_name: nul(v.recruiter_name), recruiter_email: nul(v.recruiter_email), recruiter_phone: nul(v.recruiter_phone),
    submission_email: nul(v.submission_email), submission_instructions: nul(v.submission_instructions),
  };
}

type Props = { mode: "create"; onDone: (id: string) => void; onCancel: () => void; requirement?: undefined } | { mode: "edit"; requirement: RequirementDetail; onDone: (id: string) => void; onCancel: () => void };

export function RequirementForm(props: Props) {
  const { register, handleSubmit, formState: { errors, isDirty } } = useForm<RequirementFormValues>({ resolver: zodResolver(requirementSchema), defaultValues: toDefaults(props.requirement) });
  const update = useUpdateRequirement(props.requirement?.id ?? "");
  const create = useAction<RequirementInput, RequirementDetail>({ fn: (b) => api.post("/requirements", b), invalidate: reqKeys, success: "Requirement created" });
  const busy = update.isPending || create.isPending;

  const submit = handleSubmit((v) => {
    const payload = toPayload(v);
    if (props.mode === "create") {
      if (!payload.job_title && !payload.job_reference_id) return;
      create.mutate(payload, { onSuccess: (r) => props.onDone(r.id) });
    } else {
      update.mutate(payload, { onSuccess: (r) => props.onDone(r.id) });
    }
  });
  const e = (k: keyof RequirementFormValues) => errors[k]?.message;
  const T = (k: keyof RequirementFormValues, label: string, extra?: { type?: string; hint?: string; placeholder?: string }) => (
    <Field label={label} htmlFor={k} error={e(k)} hint={extra?.hint}><Input id={k} type={extra?.type ?? "text"} step={extra?.type === "number" ? "any" : undefined} placeholder={extra?.placeholder} aria-invalid={!!e(k)} {...register(k)} /></Field>
  );

  return (
    <form onSubmit={submit} className="space-y-5" noValidate>
      <section className="grid gap-3 sm:grid-cols-2">
        {T("job_title", "Job title *")}{T("client_name", "Client")}{T("job_reference_id", "Job reference ID")}{T("number_of_openings", "Number of openings", { type: "number" })}
        <Field label="Job description" htmlFor="job_description" className="sm:col-span-2" error={e("job_description")}><Textarea id="job_description" rows={5} {...register("job_description")} /></Field>
      </section>
      <section className="grid gap-3 sm:grid-cols-2">
        <Field label="Required skills" htmlFor="required_skills" hint="Comma or line separated"><Textarea id="required_skills" rows={2} {...register("required_skills")} /></Field>
        <Field label="Preferred skills" htmlFor="preferred_skills" hint="Comma or line separated"><Textarea id="preferred_skills" rows={2} {...register("preferred_skills")} /></Field>
        {T("minimum_experience", "Minimum experience (years)", { type: "number" })}{T("maximum_experience", "Maximum experience (years)", { type: "number" })}
        {T("seniority", "Seniority")}{T("education", "Education")}
      </section>
      <section className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {T("salary_min", "Salary minimum", { type: "number" })}{T("salary_max", "Salary maximum", { type: "number" })}{T("salary_currency", "Currency", { placeholder: "INR, USD…" })}
        <Field label="Pay period" htmlFor="salary_period"><Select id="salary_period" {...register("salary_period")}><option value="">—</option><option value="hour">Hour</option><option value="day">Day</option><option value="month">Month</option><option value="year">Year</option></Select></Field>
        {T("employment_type", "Employment type", { placeholder: "Contract, Permanent…" })}{T("notice_period", "Notice period")}
      </section>
      <section className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {T("city", "City")}{T("state", "State / region")}{T("country", "Country")}{T("location", "Location (display)", { hint: "Defaults to city, state, country" })}
        <Field label="Work mode" htmlFor="work_mode"><Select id="work_mode" {...register("work_mode")}><option value="unknown">Not specified</option><option value="remote">Remote</option><option value="hybrid">Hybrid</option><option value="onsite">On-site</option></Select></Field>
      </section>
      <section className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {T("recruiter_name", "Recruiter name")}{T("recruiter_email", "Recruiter email", { type: "email" })}{T("recruiter_phone", "Recruiter phone")}{T("submission_email", "Submission email", { type: "email" })}
        <Field label="Submission instructions" htmlFor="submission_instructions" className="sm:col-span-2" error={e("submission_instructions")}><Textarea id="submission_instructions" rows={2} {...register("submission_instructions")} /></Field>
      </section>
      <div className="flex justify-end gap-2 border-t pt-4">
        <Button variant="outline" onClick={props.onCancel}>Cancel</Button>
        <Button type="submit" loading={busy} disabled={props.mode === "edit" && !isDirty}>{props.mode === "create" ? "Create requirement" : "Save changes"}</Button>
      </div>
    </form>
  );
}
