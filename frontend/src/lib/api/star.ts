/** @file star.ts @description STAR補助API。本文を冪等receiptに保持しない。 */
import { z } from "zod";
import { request } from "./client";
import {
  draftsSchema,
  preferencesSchema,
  quotaSchema,
  generationSchema,
  requestReceiptSchema,
  type StarOperation,
} from "./schemas/star";
export const getDrafts = (id: string, signal?: AbortSignal) =>
  request(`/answer-contexts/${id}/drafts`, draftsSchema, { signal });
export const getPreferences = (signal?: AbortSignal) =>
  request("/star-assist/preferences", preferencesSchema, { signal });
export const getQuota = (signal?: AbortSignal) =>
  request("/star-assist/quota", quotaSchema, { signal });
export const getGeneration = (id: string, signal?: AbortSignal) =>
  request(`/star-assist/generations/${id}`, generationSchema, { signal });
export const getStarRequest = (key: string) =>
  request(`/star-assist/requests/${key}`, requestReceiptSchema);
export const executeStarOperation = <T>(
  operation: StarOperation,
  schema: z.ZodType<T>,
) =>
  request(operation.path, schema, {
    method: operation.method,
    key: operation.key,
    body: operation.body,
  });
