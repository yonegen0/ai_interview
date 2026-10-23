/** @file transactions.ts @description Shared Mock V4 commits and preserved legacy imports. */
import type { Repository, MockState } from "./store";
import { createRepository, parseLegacySnapshot, parseMockState } from "./store";
import { canonical, sha256 } from "./starHash";
import { fakeStarResult, finishStarJob, startStarJob } from "./star";
export type Migration = {
  version: 4;
  sourceHash: string | null;
  sourceVersion: 1 | 2 | 3 | null;
  state: MockState;
};
const DB = "pocket:mock:v4";
const STORE = "state";
function legacy() {
  const source =
    sessionStorage.getItem("pocket:mock:v3") ??
    sessionStorage.getItem("pocket:mock:v2") ??
    sessionStorage.getItem("pocket:mock:v1");
  return {
    state: source
      ? parseLegacySnapshot(JSON.parse(source))
      : createRepository().read(),
    sourceHash: source ? sha256(source) : null,
    sourceVersion: source
      ? (JSON.parse(source) as { version: 1 | 2 | 3 }).version
      : null,
  };
}
function readEnvelope(raw: unknown): Migration {
  if (
    !raw ||
    typeof raw !== "object" ||
    !("version" in raw) ||
    raw.version !== 4 ||
    !("state" in raw) ||
    !("sourceHash" in raw) ||
    !("sourceVersion" in raw) ||
    ![null, 1, 2, 3].includes(raw.sourceVersion as null | number) ||
    (raw.sourceHash !== null &&
      (typeof raw.sourceHash !== "string" ||
        !/^[0-9a-f]{64}$/.test(raw.sourceHash))) ||
    Object.keys(raw).sort().join(",") !==
      "sourceHash,sourceVersion,state,version"
  )
    throw new Error(
      "体験版V4データを復元できません。旧データは保持しています。",
    );
  return {
    version: 4,
    sourceHash: raw.sourceHash as string | null,
    sourceVersion: raw.sourceVersion as 1 | 2 | 3 | null,
    state: parseMockState(raw.state),
  };
}
export function createIndexedRepository(): Repository {
  let cached = createRepository().read();
  let opening: Promise<IDBDatabase> | null = null;
  let unmerged = false;
  const channel =
    typeof BroadcastChannel === "undefined" ? null : new BroadcastChannel(DB);
  const open = () =>
    (opening ??= new Promise((resolve, reject) => {
      const request = indexedDB.open(DB, 1);
      request.onupgradeneeded = () => request.result.createObjectStore(STORE);
      request.onsuccess = () => resolve(request.result);
      request.onerror = () =>
        reject(new Error("共有保存を利用できません。入力は保持しています。"));
      request.onblocked = () =>
        reject(new Error("共有保存の更新が別タブで停止しています。"));
    }));
  const repository: Repository = {
    read: () => structuredClone(cached),
    write: () => {
      throw new Error("SharedMockRequiresTransaction");
    },
    reset: () => {
      throw new Error("SharedMockResetRequiresExplicitTransaction");
    },
    async transaction<T>(operation: (snapshot: Repository) => T): Promise<T> {
      const db = await open();
      return new Promise((resolve, reject) => {
        const transaction = db.transaction(STORE, "readwrite"),
          store = transaction.objectStore(STORE),
          read = store.get("current");
        let result: T;
        let error: unknown;
        let committed: MockState;
        let changed = false;
        read.onsuccess = () => {
          try {
            const imported = read.result === undefined ? legacy() : null;
            const envelope = imported
              ? { version: 4 as const, ...imported }
              : readEnvelope(read.result);
            if (!imported) {
              const raw =
                sessionStorage.getItem("pocket:mock:v3") ??
                sessionStorage.getItem("pocket:mock:v2") ??
                sessionStorage.getItem("pocket:mock:v1");
              unmerged = raw !== null && sha256(raw) !== envelope.sourceHash;
              if (unmerged)
                sessionStorage.setItem("pocket:mock:v4:unmerged", "true");
            }
            let current = structuredClone(envelope.state);
            const before = canonical(current);
            const facade: Repository = {
              read: () => structuredClone(current),
              write: (v) => {
                current = parseMockState(v);
              },
              reset: () => {
                current = createRepository().read();
              },
              transaction: () => {
                throw new Error("NestedMockTransaction");
              },
            };
            result = operation(facade);
            if (result instanceof Promise)
              throw new Error("AsyncWorkInsideIndexedTransaction");
            committed = parseMockState(current);
            changed = !!imported || before !== canonical(committed);
            if (changed)
              store.put({ ...envelope, state: committed }, "current");
          } catch (cause) {
            error = cause;
            transaction.abort();
          }
        };
        transaction.oncomplete = () => {
          cached = committed;
          if (changed) channel?.postMessage("changed");
          resolve(result);
        };
        transaction.onabort = () =>
          reject(error ?? new Error("共有保存に失敗しました。"));
        transaction.onerror = () =>
          reject(error ?? new Error("共有保存に失敗しました。"));
      });
    },
    migrationWarning: () =>
      unmerged
        ? "未統合の旧体験版データがあります。元データは保持しています。"
        : null,
  };
  return repository;
}
/** Explicit local worker pump outside HTTP reads and IndexedDB transactions. */
export async function pumpStarJobs(repository: Repository) {
  const ids = await repository.transaction((r) =>
    Object.values(r.read().star.generations)
      .filter((j) => j.expiresAt === null)
      .map((j) => j.generationId),
  );
  for (const id of ids) {
    const lease = await repository.transaction((r) => {
      const state = r.read();
      const value = startStarJob(state, id, Date.now());
      r.write(state);
      return value;
    });
    if (!lease) continue;
    const result = fakeStarResult(lease);
    await repository.transaction((r) => {
      const state = r.read();
      finishStarJob(state, lease, result, Date.now());
      r.write(state);
    });
  }
}
