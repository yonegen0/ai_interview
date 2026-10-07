/** @file navigation.ts @description Typed view models and validation for navigation. */
export type FeedbackNavigationView = {
  loading: boolean;
  error: Error | null;
  mutationError: Error | null;
  canRetry: boolean;
  canNext: boolean;
  hasNext: boolean;
  total?: number;
  recovering: boolean;
  pending: boolean;
  sessionUrl: string;
  retryUrl: string;
};
export type FeedbackNavigationActions = {
  next: () => Promise<void>;
  refresh: () => void;
};
