import * as DialogPrimitive from "@radix-ui/react-dialog";
import { X } from "lucide-react";
import * as React from "react";
import { cn } from "@/lib/utils";

export const Dialog = DialogPrimitive.Root;
export const DialogTrigger = DialogPrimitive.Trigger;
export const DialogClose = DialogPrimitive.Close;

const Overlay = React.forwardRef<HTMLDivElement, React.ComponentPropsWithoutRef<typeof DialogPrimitive.Overlay>>(({ className, ...p }, ref) => (
  <DialogPrimitive.Overlay ref={ref} className={cn("fixed inset-0 z-50 bg-black/50", className)} {...p} />
));
Overlay.displayName = "Overlay";

interface ContentProps extends React.ComponentPropsWithoutRef<typeof DialogPrimitive.Content> {
  title: string;
  description?: string;
  /** "center" dialog or right-hand "drawer" */
  variant?: "center" | "drawer";
  size?: "sm" | "md" | "lg" | "xl";
}
const sizes = { sm: "max-w-md", md: "max-w-xl", lg: "max-w-3xl", xl: "max-w-5xl" };

export const DialogContent = React.forwardRef<HTMLDivElement, ContentProps>(({ className, children, title, description, variant = "center", size = "md", ...props }, ref) => (
  <DialogPrimitive.Portal>
    <Overlay />
    <DialogPrimitive.Content
      ref={ref}
      aria-describedby={description ? undefined : undefined}
      className={cn(
        "fixed z-50 flex flex-col gap-4 border bg-card p-5 shadow-lg focus:outline-none",
        variant === "center" && cn("left-1/2 top-1/2 max-h-[90vh] w-[calc(100%-2rem)] -translate-x-1/2 -translate-y-1/2 overflow-y-auto rounded-lg", sizes[size]),
        variant === "drawer" && cn("right-0 top-0 h-full w-full overflow-y-auto sm:max-w-xl", size === "xl" && "sm:max-w-3xl"),
        className,
      )}
      {...props}
    >
      <div className="flex items-start justify-between gap-4">
        <div className="space-y-1">
          <DialogPrimitive.Title className="text-base font-semibold leading-tight">{title}</DialogPrimitive.Title>
          {description ? <DialogPrimitive.Description className="text-sm text-muted-foreground">{description}</DialogPrimitive.Description> : null}
        </div>
        <DialogPrimitive.Close className="rounded-sm p-1 opacity-70 hover:opacity-100" aria-label="Close"><X className="size-4" /></DialogPrimitive.Close>
      </div>
      {children}
    </DialogPrimitive.Content>
  </DialogPrimitive.Portal>
));
DialogContent.displayName = "DialogContent";

export const DialogFooter = ({ className, ...p }: React.HTMLAttributes<HTMLDivElement>) => <div className={cn("flex flex-col-reverse gap-2 sm:flex-row sm:justify-end", className)} {...p} />;
