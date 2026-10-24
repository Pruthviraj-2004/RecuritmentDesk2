import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { Button } from "@/components/ui/button";
import { Field, Input, Select, Textarea } from "@/components/ui/form";
import { api } from "@/lib/api";
import { titleCase } from "@/lib/utils";
import { candidateKeys, useAction } from "@/services/hooks";
import { CANDIDATE_STATUSES, type Candidate, type CandidateInput, type CandidateStatus } from "@/types/api";

const optNum = (min = 0, max = 1_000_000_000) => z.string().trim().refine((v) => v === "" || (!Number.isNaN(Number(v)) && Number(v) >= min && Number(v) <= max), `Enter a number between ${min} and ${max}`);
const optUrl = z.string().trim().refine((v) => v === "" || /^https?:\/\/\S+$/i.test(v), "Must start with http:// or https://");

export const candidateSchema = z.object({
  // mandatory
  first_name: z.string().trim().min(1, "Name is required").max(120),
  email: z.string().trim().min(1, "Email is required").email("Enter a valid email address"),
  phone: z.string().trim().min(1, "Phone number is required").refine((v) => v.replace(/\D/g, "").length >= 7, "Enter a phone number with at least 7 digits"),
  // optional
  last_name: z.string().trim().max(120), current_title: z.string().trim().max(200), current_company: z.string().trim().max(200),
  total_experience: optNum(0, 60), relevant_experience: optNum(0, 60), skills: z.string(), current_location: z.string().trim().max(200), preferred_locations: z.string(),
  willing_to_relocate: z.enum(["", "yes", "no"]), notice_period: z.string().trim().max(100), current_ctc: optNum(), expected_ctc: optNum(), currency: z.string().trim().max(8),
  education: z.string().trim().max(500), certifications: z.string(), work_authorization: z.string().trim().max(100), linkedin_url: optUrl, resume_url: optUrl,
  summary: z.string().max(5000), source: z.string().trim().max(60), status: z.enum(CANDIDATE_STATUSES as [CandidateStatus, ...CandidateStatus[]]), rating: z.enum(["", "1", "2", "3", "4", "5"]),
  tags: z.string(), initial_note: z.string().max(5000),
});
export type CandidateFormValues = z.infer<typeof candidateSchema>;

const list = (s: string) => s.split(/[,;\n|]/).map((x) => x.trim()).filter(Boolean);
const num = (s: string) => (s === "" ? null : Number(s));
const nul = (s: string) => (s.trim() === "" ? null : s.trim());

export function toDefaults(c?: Candidate): CandidateFormValues {
  const s = (v: string | number | null | undefined) => (v == null ? "" : String(v));
  return {
    first_name: s(c?.first_name), email: s(c?.email), phone: s(c?.phone), last_name: s(c?.last_name), current_title: s(c?.current_title), current_company: s(c?.current_company),
    total_experience: s(c?.total_experience), relevant_experience: s(c?.relevant_experience), skills: (c?.skills ?? []).join(", "), current_location: s(c?.current_location),
    preferred_locations: (c?.preferred_locations ?? []).join(", "), willing_to_relocate: c?.willing_to_relocate == null ? "" : c.willing_to_relocate ? "yes" : "no",
    notice_period: s(c?.notice_period), current_ctc: s(c?.current_ctc), expected_ctc: s(c?.expected_ctc), currency: s(c?.currency), education: s(c?.education),
    certifications: (c?.certifications ?? []).join(", "), work_authorization: s(c?.work_authorization), linkedin_url: s(c?.linkedin_url), resume_url: s(c?.resume_url),
    summary: s(c?.summary), source: s(c?.source ?? "manual"), status: c?.status ?? "new", rating: s(c?.rating) as CandidateFormValues["rating"], tags: (c?.tags ?? []).join(", "), initial_note: "",
  };
}

export function toPayload(v: CandidateFormValues, creating: boolean): CandidateInput {
  const p: CandidateInput = {
    first_name: v.first_name.trim(), email: v.email.trim(), phone: v.phone.trim(), last_name: nul(v.last_name), current_title: nul(v.current_title), current_company: nul(v.current_company),
    total_experience: num(v.total_experience), relevant_experience: num(v.relevant_experience), skills: list(v.skills), current_location: nul(v.current_location),
    preferred_locations: list(v.preferred_locations), willing_to_relocate: v.willing_to_relocate === "" ? null : v.willing_to_relocate === "yes", notice_period: nul(v.notice_period),
    current_ctc: num(v.current_ctc), expected_ctc: num(v.expected_ctc), currency: nul(v.currency.toUpperCase()), education: nul(v.education), certifications: list(v.certifications),
    work_authorization: nul(v.work_authorization), linkedin_url: nul(v.linkedin_url), resume_url: nul(v.resume_url), summary: nul(v.summary), source: nul(v.source) ?? "manual",
    status: v.status, rating: v.rating === "" ? null : Number(v.rating), tags: list(v.tags),
  };
  if (creating && v.initial_note.trim()) p.initial_note = v.initial_note.trim();
  return p;
}

type Props = { mode: "create"; candidate?: undefined; onDone: (id: string) => void; onCancel: () => void } | { mode: "edit"; candidate: Candidate; onDone: (id: string) => void; onCancel: () => void };

function Group({ title, children }: { title: string; children: React.ReactNode }) {
  return <fieldset className="space-y-3"><legend className="mb-1 border-b pb-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground w-full">{title}</legend><div className="grid gap-3 sm:grid-cols-2">{children}</div></fieldset>;
}

export function CandidateForm(props: Props) {
  const creating = props.mode === "create";
  const { register, handleSubmit, formState: { errors, isDirty } } = useForm<CandidateFormValues>({ resolver: zodResolver(candidateSchema), defaultValues: toDefaults(props.candidate) });
  const save = useAction<CandidateInput, Candidate>({
    fn: (b) => (creating ? api.post<Candidate>("/candidates", b) : api.patch<Candidate>(`/candidates/${props.candidate!.id}`, b)),
    invalidate: candidateKeys, success: creating ? "Candidate added" : "Candidate saved",
  });
  const e = (k: keyof CandidateFormValues) => errors[k]?.message as string | undefined;
  const T = (k: keyof CandidateFormValues, label: string, o?: { type?: string; hint?: string; placeholder?: string; required?: boolean }) => (
    <Field label={o?.required ? `${label} *` : label} htmlFor={`cf-${k}`} error={e(k)} hint={o?.hint}>
      <Input id={`cf-${k}`} type={o?.type ?? "text"} step={o?.type === "number" ? "any" : undefined} placeholder={o?.placeholder} aria-required={o?.required} aria-invalid={!!e(k)} {...register(k)} />
    </Field>
  );
  const submit = handleSubmit((v) => save.mutate(toPayload(v, creating), { onSuccess: (c) => props.onDone(c.id) }));

  return (
    <form onSubmit={submit} className="space-y-5" noValidate>
      <p className="text-xs text-muted-foreground">Fields marked * are required. Everything else is optional and can be added later.</p>
      <Group title="Required">
        {T("first_name", "Name", { required: true, placeholder: "First name (add surname below)" })}
        {T("email", "Email", { type: "email", required: true, hint: "Used to detect duplicates" })}
        {T("phone", "Phone", { required: true, hint: "Any format; used to detect duplicates" })}
        {T("last_name", "Surname")}
      </Group>
      <Group title="Professional">
        {T("current_title", "Current title")}{T("current_company", "Current company")}{T("total_experience", "Total experience (years)", { type: "number" })}{T("relevant_experience", "Relevant experience (years)", { type: "number" })}
        <Field label="Skills" htmlFor="cf-skills" className="sm:col-span-2" hint="Comma separated, e.g. Python, Django, AWS"><Textarea id="cf-skills" rows={2} {...register("skills")} /></Field>
        {T("education", "Education")}{T("certifications", "Certifications", { hint: "Comma separated" })}
      </Group>
      <Group title="Location & availability">
        {T("current_location", "Current location")}{T("preferred_locations", "Preferred locations", { hint: "Comma separated" })}
        <Field label="Willing to relocate" htmlFor="cf-willing_to_relocate"><Select id="cf-willing_to_relocate" {...register("willing_to_relocate")}><option value="">Not specified</option><option value="yes">Yes</option><option value="no">No</option></Select></Field>
        {T("notice_period", "Notice period", { placeholder: "e.g. 30 days, Immediate" })}{T("work_authorization", "Work authorization / visa")}
      </Group>
      <Group title="Compensation">
        {T("current_ctc", "Current CTC", { type: "number" })}{T("expected_ctc", "Expected CTC", { type: "number" })}{T("currency", "Currency", { placeholder: "INR, USD…" })}
      </Group>
      <Group title="Profile & tracking">
        <Field label="Status" htmlFor="cf-status"><Select id="cf-status" {...register("status")}>{CANDIDATE_STATUSES.map((s) => <option key={s} value={s}>{titleCase(s)}</option>)}</Select></Field>
        <Field label="Rating" htmlFor="cf-rating"><Select id="cf-rating" {...register("rating")}><option value="">Not rated</option>{[1, 2, 3, 4, 5].map((n) => <option key={n} value={n}>{"★".repeat(n)} ({n})</option>)}</Select></Field>
        {T("tags", "Tags", { hint: "Comma separated, e.g. referral, priority" })}{T("source", "Source", { placeholder: "LinkedIn, referral, job portal…" })}
        {T("linkedin_url", "LinkedIn URL", { placeholder: "https://…" })}{T("resume_url", "Resume link", { placeholder: "https://…", hint: "Link to the resume (files are not uploaded)" })}
        <Field label="Summary" htmlFor="cf-summary" className="sm:col-span-2" error={e("summary")}><Textarea id="cf-summary" rows={3} {...register("summary")} /></Field>
        {creating && <Field label="First note" htmlFor="cf-initial_note" className="sm:col-span-2" hint="Saved on the candidate's timeline"><Textarea id="cf-initial_note" rows={2} {...register("initial_note")} /></Field>}
      </Group>
      <div className="flex justify-end gap-2 border-t pt-4">
        <Button variant="outline" onClick={props.onCancel}>Cancel</Button>
        <Button type="submit" loading={save.isPending} disabled={!creating && !isDirty}>{creating ? "Add candidate" : "Save changes"}</Button>
      </div>
    </form>
  );
}
