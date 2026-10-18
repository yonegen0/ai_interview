/** @file star.ts @description STAR補助APIと共有Mockのstrict契約。 */
import { z } from "zod";
const id = z.uuid();
const bounded = (maximum: number) =>
  z
    .string()
    .refine(
      (v) => Array.from(v).length <= maximum,
      `${maximum}文字以内で入力してください。`,
    );
export const targetCategories = {
  corporate_sales: "法人営業",
  consumer_sales: "個人営業",
  office_reception: "事務・受付",
  retail_service: "接客・販売・サービス",
  it_engineering: "IT・エンジニア",
  manufacturing_technical: "製造・技術",
  construction_management: "建設・施工管理",
  healthcare_welfare: "医療・介護・福祉",
  planning_management: "企画・管理",
  other: "その他",
} as const;
export const targetCategorySchema = z.enum(
  Object.keys(targetCategories) as [
    keyof typeof targetCategories,
    ...(keyof typeof targetCategories)[],
  ],
);
export const starNotesSchema = z
  .object({
    S: bounded(2000),
    T: bounded(2000),
    A: bounded(2000),
    R: bounded(2000),
  })
  .strict();
export const starCandidateSchema = z
  .object({
    id: z.enum(["A", "B", "C"]),
    style: z.enum(["conclusion", "action", "conversational"]),
    text: bounded(400),
  })
  .strict();
const candidates = z
  .array(starCandidateSchema)
  .max(3)
  .refine(
    (v) =>
      v.length === 0 ||
      (v.length === 3 &&
        v.every(
          (c, i) =>
            c.id === ["A", "B", "C"][i] &&
            c.style === ["conclusion", "action", "conversational"][i],
        )),
  );
export const starInputSchema = z
  .object({
    notes: starNotesSchema,
    targetCategory: targetCategorySchema.nullable(),
    industry: bounded(100),
    company: bounded(200),
    candidates,
    selectedCandidateId: z.enum(["A", "B", "C"]).nullable(),
    generationId: id.nullable(),
  })
  .strict()
  .refine(
    (v) =>
      Boolean(v.candidates.length) === Boolean(v.generationId) &&
      (!v.selectedCandidateId ||
        v.candidates.some((c) => c.id === v.selectedCandidateId)),
  );
export const starResultSchema = z
  .object({
    status: z.enum(["ready", "needs_information"]),
    candidates,
    missingInformation: z.array(bounded(200)).max(4),
  })
  .strict()
  .refine((v) =>
    v.status === "ready"
      ? v.candidates.length === 3 && v.candidates.every((c) => !!c.text.trim())
      : v.candidates.length === 0 && v.missingInformation.length > 0,
  );
export const starReceiptSchema = z
  .object({
    id,
    version: z.number().int().positive(),
    updatedAt: z.number().int().nonnegative(),
    expiresAt: z.number().int().nonnegative(),
  })
  .strict();
export const answerDraftSchema = starReceiptSchema.extend({
  answer: bounded(16000),
  applicationId: id.nullable(),
});
export const starDraftSchema = starReceiptSchema
  .extend(starInputSchema.shape)
  .extend({
    originalCandidates: candidates,
    generationTargetCategory: targetCategorySchema.nullable(),
  })
  .refine(
    (v) =>
      starInputSchema.safeParse({
        notes: v.notes,
        targetCategory: v.targetCategory,
        industry: v.industry,
        company: v.company,
        candidates: v.candidates,
        selectedCandidateId: v.selectedCandidateId,
        generationId: v.generationId,
      }).success,
  );
export const draftsSchema = z
  .object({
    answerDraft: answerDraftSchema.nullable(),
    starDraft: starDraftSchema.nullable(),
  })
  .strict();
export const answerValueSchema = z
  .object({ answer: bounded(16000), applicationId: id.nullable().optional() })
  .strict();
export const answerUpdateSchema = answerValueSchema.extend({
  expectedVersion: z.number().int().positive(),
});
export const starUpdateSchema = starInputSchema.safeExtend({
  expectedVersion: z.number().int().positive(),
});
export const contextRequestSchema = z
  .object({
    operationKind: z.enum([
      "initial_answer",
      "coaching_answer",
      "retry_attempt",
    ]),
    questionId: id,
    fromAttemptId: id.nullable().optional(),
    fromEvaluationId: id.nullable().optional(),
  })
  .strict()
  .refine((v) =>
    v.operationKind === "initial_answer"
      ? !v.fromAttemptId && !v.fromEvaluationId
      : !!v.fromAttemptId && !!v.fromEvaluationId,
  );
export const contextReceiptSchema = z
  .object({
    contextId: id,
    operationKind: z.enum([
      "initial_answer",
      "coaching_answer",
      "retry_attempt",
    ]),
  })
  .strict();
const expected = {
  expectedVersion: z.number().int().nonnegative(),
  expectedGeneration: id.nullable(),
};
export const preferencesRequestSchema = z
  .object({
    category: z
      .object({ ...expected, targetCategory: targetCategorySchema })
      .strict()
      .nullable()
      .optional(),
    details: z
      .object({ ...expected, industry: bounded(100), company: bounded(200) })
      .strict()
      .nullable()
      .optional(),
  })
  .strict()
  .refine((v) => !!v.category || !!v.details);
export const preferencesSchema = z
  .object({
    category: starReceiptSchema
      .extend({ generationId: id, targetCategory: targetCategorySchema })
      .nullable(),
    details: starReceiptSchema
      .extend({
        generationId: id,
        industry: bounded(100),
        company: bounded(200),
      })
      .nullable(),
  })
  .strict();
export const preferencesReceiptSchema = z
  .object({
    category: starReceiptSchema.optional(),
    details: starReceiptSchema.optional(),
  })
  .strict();
export const generationRequestSchema = z
  .object({ starDraftId: id, expectedVersion: z.number().int().positive() })
  .strict();
export const generationReceiptSchema = z
  .object({ generationId: id, status: z.literal("QUEUED") })
  .strict();
export const generationSchema = z
  .object({
    generationId: id,
    status: z.enum([
      "QUEUED",
      "PREPARED",
      "STARTED",
      "SUCCEEDED",
      "NEEDS_INFORMATION",
      "CANCELLED",
      "FAILED_BEFORE_START",
      "FAILED_AFTER_START",
      "OUTCOME_UNKNOWN",
    ]),
    generationTargetCategory: targetCategorySchema,
    result: starResultSchema.nullable(),
  })
  .strict();
export const applyRequestSchema = z
  .object({
    expectedVersion: z.number().int().positive(),
    candidateId: z.enum(["A", "B", "C"]),
    answerDraftId: id,
    expectedAnswerVersion: z.number().int().positive(),
  })
  .strict();
export const applyReceiptSchema = starReceiptSchema.extend({
  applicationId: id,
  answerHash: z.string().regex(/^[0-9a-f]{64}$/),
});
const bucket = z
  .object({
    reserved: z.number().int().nonnegative(),
    consumed: z.number().int().nonnegative(),
    remaining: z.number().int().nonnegative(),
  })
  .strict();
export const quotaSchema = z
  .object({
    month: z.string().regex(/^\d{4}-(0[1-9]|1[0-2])$/),
    user: bucket,
    global: bucket,
  })
  .strict();
export const requestReceiptSchema = z
  .object({
    requestHash: z.string(),
    method: z.enum(["POST", "PUT"]),
    path: z.string(),
    status: z.number().int(),
    receipt: z.record(z.string(), z.unknown()),
  })
  .strict();
export const starOperationRecoverySchema = z
  .object({
    version: z.literal(1),
    key: id,
    path: z.string(),
    method: z.enum(["POST", "PUT"]),
    body: z.unknown(),
    contextId: id.nullable(),
    editGeneration: z.number().int().nonnegative(),
  })
  .strict();
export type StarInput = z.infer<typeof starInputSchema>;
export type StarDraft = z.infer<typeof starDraftSchema>;
export type Drafts = z.infer<typeof draftsSchema>;
export type StarReceipt = z.infer<typeof starReceiptSchema>;
export type StarContextInput = z.infer<typeof contextRequestSchema>;
export type StarOperation = z.infer<typeof starOperationRecoverySchema>;
export const emptyStarInput = (): StarInput => ({
  notes: { S: "", T: "", A: "", R: "" },
  targetCategory: null,
  industry: "",
  company: "",
  candidates: [],
  selectedCandidateId: null,
  generationId: null,
});
export const starValue = (v: StarInput): StarInput => ({
  notes: v.notes,
  targetCategory: v.targetCategory,
  industry: v.industry,
  company: v.company,
  candidates: v.candidates,
  selectedCandidateId: v.selectedCandidateId,
  generationId: v.generationId,
});
