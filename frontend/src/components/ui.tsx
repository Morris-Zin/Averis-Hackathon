"use client";

import * as DialogPrimitive from "@radix-ui/react-dialog";
import * as SelectPrimitive from "@radix-ui/react-select";
import { Check, ChevronDown, X } from "lucide-react";
import type {
  ButtonHTMLAttributes,
  InputHTMLAttributes,
  ReactNode,
  TextareaHTMLAttributes,
} from "react";
import { forwardRef } from "react";
import { twMerge } from "tailwind-merge";
import { clsx, type ClassValue } from "clsx";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "secondary" | "ghost" | "danger";
  size?: "sm" | "md";
};

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  function Button(
    { className, variant = "secondary", size = "md", ...props },
    ref,
  ) {
    return (
      <button
        ref={ref}
        className={cn(
          "button",
          `button-${variant}`,
          `button-${size}`,
          className,
        )}
        {...props}
      />
    );
  },
);

export const Input = forwardRef<
  HTMLInputElement,
  InputHTMLAttributes<HTMLInputElement>
>(function Input({ className, ...props }, ref) {
  return <input ref={ref} className={cn("input", className)} {...props} />;
});

export const Textarea = forwardRef<
  HTMLTextAreaElement,
  TextareaHTMLAttributes<HTMLTextAreaElement>
>(function Textarea({ className, ...props }, ref) {
  return (
    <textarea ref={ref} className={cn("textarea", className)} {...props} />
  );
});

export function Select({
  value,
  onValueChange,
  label,
  children,
  disabled,
}: {
  value: string;
  onValueChange: (value: string) => void;
  label: string;
  children: ReactNode;
  disabled?: boolean;
}) {
  return (
    <SelectPrimitive.Root
      value={value}
      onValueChange={onValueChange}
      disabled={disabled}
    >
      <SelectPrimitive.Trigger className="select-trigger" aria-label={label}>
        <SelectPrimitive.Value />
        <SelectPrimitive.Icon>
          <ChevronDown size={15} />
        </SelectPrimitive.Icon>
      </SelectPrimitive.Trigger>
      <SelectPrimitive.Portal>
        <SelectPrimitive.Content
          className="select-content"
          position="popper"
          sideOffset={5}
        >
          <SelectPrimitive.Viewport>{children}</SelectPrimitive.Viewport>
        </SelectPrimitive.Content>
      </SelectPrimitive.Portal>
    </SelectPrimitive.Root>
  );
}

export function SelectItem({
  value,
  children,
}: {
  value: string;
  children: ReactNode;
}) {
  return (
    <SelectPrimitive.Item value={value} className="select-item">
      <SelectPrimitive.ItemText>{children}</SelectPrimitive.ItemText>
      <SelectPrimitive.ItemIndicator>
        <Check size={14} />
      </SelectPrimitive.ItemIndicator>
    </SelectPrimitive.Item>
  );
}

export function Dialog({
  open,
  onOpenChange,
  title,
  description,
  children,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description?: string;
  children: ReactNode;
}) {
  return (
    <DialogPrimitive.Root open={open} onOpenChange={onOpenChange}>
      <DialogPrimitive.Portal>
        <DialogPrimitive.Overlay className="dialog-overlay" />
        <DialogPrimitive.Content className="dialog-content">
          <div>
            <DialogPrimitive.Title className="dialog-title">
              {title}
            </DialogPrimitive.Title>
            {description ? (
              <DialogPrimitive.Description className="dialog-description">
                {description}
              </DialogPrimitive.Description>
            ) : null}
          </div>
          {children}
          <DialogPrimitive.Close
            className="dialog-close"
            aria-label="Close dialog"
          >
            <X size={18} />
          </DialogPrimitive.Close>
        </DialogPrimitive.Content>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  );
}

export function Spinner({ label = "Loading" }: { label?: string }) {
  return (
    <span className="spinner" role="status">
      <span className="spinner-mark" aria-hidden="true" />
      {label}
    </span>
  );
}
