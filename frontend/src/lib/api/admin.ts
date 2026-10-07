/** @file admin.ts @description 管理者質問一覧の取得と同じ保存要求の再確認。 */
import { request } from "./client";
import {
  bankSchema,
  bankReceiptSchema,
  bankSaveSchema,
  type BankSave,
} from "./schemas";
export const getQuestionBank = (signal?: AbortSignal) =>
  request("/admin/question-bank", bankSchema, { signal });
export const saveQuestionBank = (body: BankSave, key: string) =>
  request("/admin/question-bank", bankReceiptSchema, {
    method: "POST",
    key,
    body: bankSaveSchema.parse(body),
  });
