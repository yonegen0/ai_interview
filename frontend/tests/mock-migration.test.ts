/** @file mock-migration.test.ts @description 旧21問の原本保全とスナップショット復旧。 */
import { beforeEach, expect, it, vi } from "vitest";
import { createRepository } from "@/mocks/store";
import { legacyQuestions, questions } from "@/mocks/data/questions";
const id="10000000-0000-4000-8000-000000000099";
beforeEach(()=>sessionStorage.clear());
function oldState(question=legacyQuestions[0]) {return {version:1,sessions:{[id]:{sessionId:id,question,questionNumber:4,activeAttempt:null}},attempts:{},requests:{},consumed:[]};}
it("copies valid legacy state without rewriting the v1 original",()=>{
  const raw=JSON.stringify(oldState());sessionStorage.setItem("pocket:mock:v1",raw);
  const state=createRepository(true).read();expect(state.version).toBe(2);
  expect(state.sessionQuestions[id]).toEqual(legacyQuestions.filter(q=>q.category==="job_change"));
  expect(state.sessions[id].question).toEqual(legacyQuestions[0]);expect(state.bank.questions).toEqual(questions);
  expect(sessionStorage.getItem("pocket:mock:v1")).toBe(raw);expect(sessionStorage.getItem("pocket:mock:v2")).not.toBeNull();
});
it("preserves an inconsistent v1 original and refuses to mix new questions",()=>{
  const raw=JSON.stringify(oldState({...legacyQuestions[0],question:"変更された古い本文"}));sessionStorage.setItem("pocket:mock:v1",raw);
  expect(()=>createRepository(true).read()).toThrow("復元できません");expect(sessionStorage.getItem("pocket:mock:v1")).toBe(raw);expect(sessionStorage.getItem("pocket:mock:v2")).toBeNull();
});

it("continues in memory when sessionStorage cannot be read or written",()=>{
  const read=vi.spyOn(Storage.prototype,"getItem").mockImplementation(()=>{throw new Error("unavailable");});
  const write=vi.spyOn(Storage.prototype,"setItem").mockImplementation(()=>{throw new Error("unavailable");});
  try {
    const repo=createRepository(true);const state=repo.read();state.bank={version:1,updatedAt:"2026-10-06T00:00:00.000Z",questions:[questions[0]]};repo.write(state);
    expect(repo.read().bank.questions).toEqual([questions[0]]);
  } finally {read.mockRestore();write.mockRestore();}
});
