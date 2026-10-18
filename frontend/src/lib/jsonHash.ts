/** @file jsonHash.ts @description Pure canonical hashes inside IndexedDB transactions. */
export function canonical(value: unknown): string {
  if (typeof value === "string")
    return JSON.stringify(value).replace(
      /[\u007f-\uffff]/g,
      (c) => `\\u${c.charCodeAt(0).toString(16).padStart(4, "0")}`,
    );
  if (value === null || typeof value === "number" || typeof value === "boolean")
    return JSON.stringify(value);
  if (Array.isArray(value)) return `[${value.map(canonical).join(", ")}]`;
  if (typeof value === "object")
    return `{${Object.entries(value as Record<string, unknown>)
      .filter(([, v]) => v !== undefined)
      .sort(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0))
      .map(([k, v]) => `${canonical(k)}: ${canonical(v)}`)
      .join(", ")}}`;
  throw new Error("NonJsonValue");
}
function bytes(value: string): number[] {
  const output: number[] = [];
  for (const c of value) {
    const p = c.codePointAt(0)!;
    if (p < 128) output.push(p);
    else if (p < 2048) output.push(192 | (p >> 6), 128 | (p & 63));
    else if (p < 65536)
      output.push(224 | (p >> 12), 128 | ((p >> 6) & 63), 128 | (p & 63));
    else
      output.push(
        240 | (p >> 18),
        128 | ((p >> 12) & 63),
        128 | ((p >> 6) & 63),
        128 | (p & 63),
      );
  }
  return output;
}
const rot = (v: number, n: number) => (v >>> n) | (v << (32 - n));
const constants = [
  0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1,
  0x923f82a4, 0xab1c5ed5, 0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3,
  0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174, 0xe49b69c1, 0xefbe4786,
  0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
  0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147,
  0x06ca6351, 0x14292967, 0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13,
  0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85, 0xa2bfe8a1, 0xa81a664b,
  0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
  0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a,
  0x5b9cca4f, 0x682e6ff3, 0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208,
  0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2,
];
function words(raw: number[]) {
  const data = [...raw],
    size = data.length * 8;
  data.push(128);
  while (data.length % 64 !== 56) data.push(0);
  data.push(
    0,
    0,
    0,
    0,
    size >>> 24,
    (size >>> 16) & 255,
    (size >>> 8) & 255,
    size & 255,
  );
  const w: number[] = [];
  for (let i = 0; i < data.length; i += 4)
    w.push(
      (data[i] << 24) | (data[i + 1] << 16) | (data[i + 2] << 8) | data[i + 3],
    );
  return w;
}
export function sha256(value: string): string {
  const w = words(bytes(value)),
    h = [
      0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a, 0x510e527f, 0x9b05688c,
      0x1f83d9ab, 0x5be0cd19,
    ];
  for (let offset = 0; offset < w.length; offset += 16) {
    const x = w.slice(offset, offset + 16);
    for (let i = 16; i < 64; i++)
      x[i] =
        (x[i - 16] +
          (rot(x[i - 15], 7) ^ rot(x[i - 15], 18) ^ (x[i - 15] >>> 3)) +
          x[i - 7] +
          (rot(x[i - 2], 17) ^ rot(x[i - 2], 19) ^ (x[i - 2] >>> 10))) |
        0;
    let [a, b, c, d, e, f, g, j] = h;
    for (let i = 0; i < 64; i++) {
      const t =
        (j +
          (rot(e, 6) ^ rot(e, 11) ^ rot(e, 25)) +
          ((e & f) ^ (~e & g)) +
          constants[i] +
          x[i]) |
        0;
      const u =
        ((rot(a, 2) ^ rot(a, 13) ^ rot(a, 22)) +
          ((a & b) ^ (a & c) ^ (b & c))) |
        0;
      j = g;
      g = f;
      f = e;
      e = (d + t) | 0;
      d = c;
      c = b;
      b = a;
      a = (t + u) | 0;
    }
    [a, b, c, d, e, f, g, j].forEach((v, i) => {
      h[i] = (h[i] + v) | 0;
    });
  }
  return h.map((v) => (v >>> 0).toString(16).padStart(8, "0")).join("");
}
export function contextUuid(value: string): string {
  const namespace = "6ba7b8119dad11d180b400c04fd430c8"
    .match(/../g)!
    .map((v) => parseInt(v, 16));
  const w = words([
      ...namespace,
      ...bytes("ai-interview/star-context/v1/" + value),
    ]),
    h = [0x67452301, 0xefcdab89, 0x98badcfe, 0x10325476, 0xc3d2e1f0];
  for (let offset = 0; offset < w.length; offset += 16) {
    const x = w.slice(offset, offset + 16);
    for (let i = 16; i < 80; i++)
      x[i] = rot(x[i - 3] ^ x[i - 8] ^ x[i - 14] ^ x[i - 16], 31);
    let [a, b, c, d, e] = h;
    for (let i = 0; i < 80; i++) {
      const f =
        i < 20
          ? (b & c) | (~b & d)
          : i < 40
            ? b ^ c ^ d
            : i < 60
              ? (b & c) | (b & d) | (c & d)
              : b ^ c ^ d;
      const k =
        i < 20
          ? 0x5a827999
          : i < 40
            ? 0x6ed9eba1
            : i < 60
              ? 0x8f1bbcdc
              : 0xca62c1d6;
      const t = (rot(a, 27) + f + e + k + x[i]) | 0;
      e = d;
      d = c;
      c = rot(b, 2);
      b = a;
      a = t;
    }
    [a, b, c, d, e].forEach((v, i) => {
      h[i] = (h[i] + v) | 0;
    });
  }
  const raw = h
    .map((v) => (v >>> 0).toString(16).padStart(8, "0"))
    .join("")
    .slice(0, 32)
    .split("");
  raw[12] = "5";
  raw[16] = ((parseInt(raw[16], 16) & 3) | 8).toString(16);
  const s = raw.join("");
  return `${s.slice(0, 8)}-${s.slice(8, 12)}-${s.slice(12, 16)}-${s.slice(16, 20)}-${s.slice(20)}`;
}
