import { clsx } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: Array<string | undefined | null | boolean>) {
  return twMerge(clsx(inputs));
}
