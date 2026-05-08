import type { LucideIcon } from "lucide-react";

import { cn } from "@/lib/utils";

type Tone = "primary" | "success" | "warning" | "danger" | "info" | "neutral";

const TONE_STYLES: Record<Tone, { ring: string; chip: string; iconBg: string }> = {
  primary: {
    ring: "ring-primary/15",
    chip: "bg-primary-100 text-primary-700",
    iconBg: "bg-primary-100 text-primary-700",
  },
  success: {
    ring: "ring-success/15",
    chip: "bg-success-100 text-success-700",
    iconBg: "bg-success-100 text-success-700",
  },
  warning: {
    ring: "ring-warning/20",
    chip: "bg-warning-100 text-warning-700",
    iconBg: "bg-warning-100 text-warning-700",
  },
  danger: {
    ring: "ring-danger/15",
    chip: "bg-danger-100 text-danger-700",
    iconBg: "bg-danger-100 text-danger-700",
  },
  info: {
    ring: "ring-info/15",
    chip: "bg-info-100 text-info-700",
    iconBg: "bg-info-100 text-info-700",
  },
  neutral: {
    ring: "ring-border",
    chip: "bg-muted text-muted-foreground",
    iconBg: "bg-muted text-muted-foreground",
  },
};

export type StatCardProps = {
  label: string;
  value: string | number;
  hint?: string;
  icon?: LucideIcon;
  tone?: Tone;
  className?: string;
};

export function StatCard({
  label,
  value,
  hint,
  icon: Icon,
  tone = "primary",
  className,
}: StatCardProps) {
  const style = TONE_STYLES[tone];

  return (
    <div
      className={cn(
        "group relative overflow-hidden rounded-xl border bg-card p-5 transition-all hover:shadow-md hover:-translate-y-0.5",
        className,
      )}
    >
      <span
        aria-hidden
        className={cn(
          "pointer-events-none absolute inset-x-0 top-0 h-0.5 opacity-70",
          tone === "primary" && "bg-primary",
          tone === "success" && "bg-success",
          tone === "warning" && "bg-warning",
          tone === "danger" && "bg-danger",
          tone === "info" && "bg-info",
          tone === "neutral" && "bg-border",
        )}
      />
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
            {label}
          </p>
          <p className="mt-1.5 text-2xl font-semibold tracking-tight text-foreground">
            {value}
          </p>
          {hint && (
            <p className="mt-1 text-xs text-muted-foreground line-clamp-1">{hint}</p>
          )}
        </div>
        {Icon && (
          <div
            className={cn(
              "inline-flex size-9 shrink-0 items-center justify-center rounded-lg",
              style.iconBg,
            )}
          >
            <Icon className="size-4" />
          </div>
        )}
      </div>
    </div>
  );
}
