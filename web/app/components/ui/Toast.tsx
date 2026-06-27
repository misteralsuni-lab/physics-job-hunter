"use client";

// Lightweight toast notifications. A small Zustand store holds the queue so any
// component (including server-action callbacks) can surface a transient
// message. Toasts auto-dismiss and are announced politely via aria-live.
import { useEffect } from "react";
import { create } from "zustand";
import { CheckCircle2, AlertCircle, Info, X } from "lucide-react";
import { cn } from "@/lib/utils/cn";

export type ToastKind = "success" | "error" | "info";

export interface Toast {
  id: number;
  kind: ToastKind;
  message: string;
}

interface ToastStore {
  toasts: Toast[];
  push: (kind: ToastKind, message: string) => void;
  dismiss: (id: number) => void;
}

let nextId = 1;

export const useToastStore = create<ToastStore>((set) => ({
  toasts: [],
  push: (kind, message) =>
    set((s) => {
      // Generate the id inline — keeping the ``++`` outside the updater
      // avoids the React strict-mode double-invocation bug, which would
      // otherwise leave ``nextId`` ahead of ``toasts.length`` by 1 and
      // produce visibly out-of-sequence numeric ids in the UI.
      const id = nextId++;
      return { toasts: [...s.toasts, { id, kind, message }] };
    }),
  dismiss: (id) =>
    set((s) => ({ toasts: s.toasts.filter((t) => t.id !== id) })),
}));

/** Convenience helpers usable from any client component. */
export const toast = {
  success: (m: string) => useToastStore.getState().push("success", m),
  error: (m: string) => useToastStore.getState().push("error", m),
  info: (m: string) => useToastStore.getState().push("info", m),
};

const KIND_ICON = {
  success: CheckCircle2,
  error: AlertCircle,
  info: Info,
} as const;

const KIND_CLASS = {
  success: "text-status-active",
  error: "text-status-error",
  info: "text-brand",
} as const;

export function ToastViewport() {
  const toasts = useToastStore((s) => s.toasts);
  const dismiss = useToastStore((s) => s.dismiss);

  return (
    <div
      className="pointer-events-none fixed inset-x-0 top-4 z-50 flex flex-col items-center gap-2 px-4"
      aria-live="polite"
      aria-atomic="false"
    >
      {toasts.map((t) => (
        <ToastItem key={t.id} toast={t} onDismiss={dismiss} />
      ))}
    </div>
  );
}

function ToastItem({
  toast,
  onDismiss,
}: {
  toast: Toast;
  onDismiss: (id: number) => void;
}) {
  useEffect(() => {
    const timer = setTimeout(() => onDismiss(toast.id), 4000);
    return () => clearTimeout(timer);
  }, [toast.id, onDismiss]);

  const Icon = KIND_ICON[toast.kind];
  return (
    <div
      role="status"
      className={cn(
        "pointer-events-auto flex w-full max-w-sm items-start gap-3 rounded-xl border border-line bg-surface-raised p-3 shadow-raised",
        "animate-slide-up",
      )}
    >
      <Icon className={cn("mt-0.5 h-5 w-5 shrink-0", KIND_CLASS[toast.kind])} aria-hidden="true" />
      <p className="flex-1 text-sm text-ink">{toast.message}</p>
      <button
        type="button"
        onClick={() => onDismiss(toast.id)}
        aria-label="Dismiss notification"
        className="tap-target -mr-1 -mt-1 rounded text-ink-faint hover:bg-surface-muted"
      >
        <X className="h-4 w-4" aria-hidden="true" />
      </button>
    </div>
  );
}
