/** @file practiceStart.ts @description Typed view models and validation for practiceStart. */
import type { z } from "zod";
import { practiceOptionsSchema, type Category } from "@/lib/api/schemas";
export type PracticeStartView = {
  mode: "full" | "category";
  category: Category | null;
  options?: z.infer<typeof practiceOptionsSchema>;
  loading: boolean;
  optionsError: Error | null;
  error: Error | null;
  disabled: boolean;
  canStart: boolean;
  starting: boolean;
  recovering: boolean;
};
export type PracticeStartActions = {
  selectMode: (mode: "full" | "category") => void;
  selectCategory: (category: Category) => void;
  start: () => Promise<void>;
  refresh: () => void;
};
