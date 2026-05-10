"use client";

import { useEffect, useRef } from "react";

type Props = {
  open: boolean;
  title: string;
  description?: string;
  confirmLabel?: string;
  cancelLabel?: string;
  destructive?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
};

/**
 * Accessible confirmation modal. Replaces ad-hoc window.confirm() so the dialog
 * lives inside the React tree, supports custom destructive styling, focuses the
 * Cancel button on open (safer default), and traps Escape / backdrop clicks.
 */
export function ConfirmDialog({
  open,
  title,
  description,
  confirmLabel = "Onayla",
  cancelLabel = "Vazgeç",
  destructive = false,
  onConfirm,
  onCancel,
}: Props) {
  const cancelRef = useRef<HTMLButtonElement>(null);
  const previouslyFocused = useRef<HTMLElement | null>(null);

  useEffect(() => {
    if (!open) return;
    previouslyFocused.current = document.activeElement as HTMLElement | null;
    cancelRef.current?.focus();

    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault();
        onCancel();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("keydown", onKey);
      previouslyFocused.current?.focus?.();
    };
  }, [open, onCancel]);

  if (!open) return null;

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="confirm-dialog-title"
      aria-describedby={description ? "confirm-dialog-desc" : undefined}
      onClick={onCancel}
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4"
    >
      <div
        onClick={(e) => e.stopPropagation()}
        className="border border-border-strong bg-bg-elevated p-6 max-w-md w-full font-mono"
      >
        <h2
          id="confirm-dialog-title"
          className={`text-sm tracking-widest uppercase mb-3 ${
            destructive ? "text-accent-red" : "text-text-primary"
          }`}
        >
          {title}
        </h2>
        {description && (
          <p
            id="confirm-dialog-desc"
            className="text-[11px] text-text-secondary mb-5 leading-relaxed"
          >
            {description}
          </p>
        )}
        <div className="flex justify-end gap-2">
          <button
            ref={cancelRef}
            type="button"
            onClick={onCancel}
            className="
              h-10 px-4
              border border-text-muted
              bg-bg
              font-mono text-[11px] tracking-widest text-text-secondary
              uppercase
              transition-colors
              hover:bg-text-muted/10 hover:text-text-primary
            "
          >
            {cancelLabel}
          </button>
          <button
            type="button"
            onClick={onConfirm}
            className={
              destructive
                ? "h-10 px-4 border border-accent-red bg-bg font-mono text-[11px] tracking-widest text-accent-red uppercase transition-colors hover:bg-accent-red/10"
                : "h-10 px-4 border border-accent-green bg-bg font-mono text-[11px] tracking-widest text-accent-green uppercase transition-colors hover:bg-accent-green/10"
            }
          >
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
