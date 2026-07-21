import { clsx, type ClassValue } from 'clsx'
import { twMerge } from 'tailwind-merge'

/** className 병합 — clsx + tailwind-merge */
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}
