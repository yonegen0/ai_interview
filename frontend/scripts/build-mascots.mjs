/** @file build-mascots.mjs @description 元PNGを保持し、静的配信用512px WebPを生成する。 */
import { constants } from "node:fs";
import { copyFile, readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import sharp from "sharp";

for (const variant of [
  "default",
  "welcome",
  "thinking",
  "success",
  "retry",
  "error",
]) {
  const base = new URL(
    `../public/images/mascot/mascot-${variant}`,
    import.meta.url,
  );
  const source = new URL(`${base.href}.png`);
  const target = new URL(`${base.href}.webp`);
  let input;
  try {
    input = await readFile(source);
  } catch (error) {
    if (error.code !== "ENOENT") throw error;
    // Recover the original PNG bytes from the historically misnamed asset once.
    input = await readFile(target);
    if ((await sharp(input).metadata()).format !== "png") {
      throw new Error(`Original PNG required: ${variant}`);
    }
    await copyFile(target, source, constants.COPYFILE_EXCL);
  }
  const original = await sharp(input).metadata();
  if (
    original.format !== "png" ||
    original.width !== original.height ||
    original.width < 512
  ) {
    throw new Error(`Invalid original PNG: ${variant}`);
  }
  await sharp(input)
    .resize(512, 512, { fit: "inside", withoutEnlargement: true })
    .webp({ quality: 90, alphaQuality: 100 })
    .toFile(fileURLToPath(target));
  console.log(`${variant}: 512x512 WebP generated`);
}
