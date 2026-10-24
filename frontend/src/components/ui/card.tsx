import * as React from "react";
import { cn } from "@/lib/utils";

export const Card = ({ className, ...p }: React.HTMLAttributes<HTMLDivElement>) => <div className={cn("rounded-lg border bg-card text-card-foreground shadow-sm transition-all duration-200 hover:border-primary/30 hover:shadow-md", className)} {...p} />;
export const CardHeader = ({ className, ...p }: React.HTMLAttributes<HTMLDivElement>) => <div className={cn("flex flex-col gap-1 p-4 pb-2", className)} {...p} />;
export const CardTitle = ({ className, ...p }: React.HTMLAttributes<HTMLHeadingElement>) => <h3 className={cn("text-sm font-semibold leading-none", className)} {...p} />;
export const CardDescription = ({ className, ...p }: React.HTMLAttributes<HTMLParagraphElement>) => <p className={cn("text-xs text-muted-foreground", className)} {...p} />;
export const CardContent = ({ className, ...p }: React.HTMLAttributes<HTMLDivElement>) => <div className={cn("p-4 pt-2", className)} {...p} />;

export const Skeleton = ({ className, ...p }: React.HTMLAttributes<HTMLDivElement>) => <div aria-hidden className={cn("animate-pulse rounded-md bg-muted", className)} {...p} />;
