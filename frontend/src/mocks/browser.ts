/** @file browser.ts @description Browser Mockの一度だけの起動 */
import { setupWorker } from "msw/browser";
import { createHandlers, scenarios, type Scenario } from "./handlers";
import { createRepository } from "./store";
import { apiBase } from "@/lib/api/client";
export const repository = createRepository(true);
const scenario = (): Scenario => {
  try {
    const value = sessionStorage.getItem("pocket:scenario") as Scenario;
    return scenarios.includes(value) ? value : "success";
  } catch {
    return "success";
  }
};
export const worker = setupWorker(
  ...createHandlers(
    repository,
    scenario,
    apiBase().startsWith("/") ? `*${apiBase()}` : apiBase(),
  ),
);
let started: ReturnType<typeof worker.start> | undefined;
export const startMock = () =>
  (started ??= worker.start({ onUnhandledRequest: "bypass", quiet: true }));
