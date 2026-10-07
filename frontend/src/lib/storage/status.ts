/** @file status.ts @description 保存不可の共通通知。秘密情報を含めない。 */
let available = true;
const listeners = new Set<() => void>();
export const storageAvailable = () => available;
export const subscribeStorage = (listener: () => void) => {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
};
export const markStorageUnavailable = () => {
  available = false;
  listeners.forEach((listener) => listener());
};
