/**
 * Temporary exception for two reviewed, dev-tool-only npm advisories.
 * npm audit still executes at its strictest threshold. Unknown advisories,
 * audit/network failures, invalid reports, or an expired exception fail closed.
 */
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import path from "node:path";

export const EXCEPTION_REVIEW_UTC = "2026-11-15T00:00:00.000Z";
export const ALLOWED = Object.freeze({
  "GHSA-g3hv-75wg-m249": "minimatch",
  "GHSA-3g3m-2fjr-6pw4": "glob",
});
const SEVERITIES = ["info", "low", "moderate", "high", "critical"];

function ensure(condition, message) {
  if (!condition) throw new Error(message);
}
function object(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

/**
 * Validate the entire npm audit v2 vulnerability graph. npm emits both direct
 * GHSA objects and meta-vulnerable package references (which can form cycles).
 * Resolve every meta-vulnerability to one of the two explicitly approved roots.
 */
export function assessAudit(report, now = Date.now()) {
  ensure(object(report) && !report.error, "Audit report missing or contains an error");
  ensure(report.auditReportVersion === 2, "Unexpected npm audit report version");
  ensure(object(report.vulnerabilities), "Missing vulnerability graph");
  const counts = report.metadata?.vulnerabilities;
  ensure(object(counts), "Missing npm audit severity totals");
  const vulnerabilities = report.vulnerabilities;
  const names = Object.keys(vulnerabilities);
  ensure(SEVERITIES.every((s) => Number.isSafeInteger(counts[s]) && counts[s] >= 0),
    "Invalid npm audit severity totals");
  ensure(Number.isSafeInteger(counts.total)
    && counts.total === names.length
    && SEVERITIES.reduce((sum, s) => sum + counts[s], 0) === names.length,
    "Inconsistent npm audit vulnerability totals");

  // npm's meta-vulnerability graph can contain cycles. Propagate approved
  // direct advisory IDs until a fixed point is reached.
  const references = new Map();
  const findings = new Map();
  for (const name of names) {
    const node = vulnerabilities[name];
    ensure(object(node) && node.name === name && Array.isArray(node.via) && node.via.length > 0,
      `Invalid audit node: ${name}`);
    ensure(node.severity === "moderate", `Unaccepted severity for ${name}: ${node.severity}`);
    const refs = [];
    const roots = new Set();
    for (const via of node.via) {
      if (typeof via === "string") {
        ensure(Object.hasOwn(vulnerabilities, via), `Missing meta-vulnerability target: ${via}`);
        refs.push(via);
      } else {
        ensure(object(via) && typeof via.url === "string",
          `Unknown direct advisory for ${name}`);
        const match = /^https:\/\/github\.com\/advisories\/(GHSA-[a-z0-9-]+)$/.exec(via.url);
        const id = match?.[1];
        ensure(Object.hasOwn(ALLOWED, id ?? "") && ALLOWED[id] === name
          && via.name === name && via.severity === "moderate",
          `Unaccepted direct advisory for ${name}: ${via.url}`);
        roots.add(id);
      }
    }
    references.set(name, refs);
    findings.set(name, roots);
  }
  for (let round = 0; round < names.length; round++) {
    let changed = false;
    for (const name of names) {
      const dest = findings.get(name);
      for (const target of references.get(name)) {
        for (const id of findings.get(target)) {
          if (!dest.has(id)) {
            dest.add(id);
            changed = true;
          }
        }
      }
    }
    if (!changed) break;
  }
  const observed = new Set();
  for (const name of names) {
    ensure(findings.get(name).size > 0, `Unexplained vulnerability: ${name}`);
    for (const id of findings.get(name)) observed.add(id);
  }
  ensure(counts.high === 0 && counts.critical === 0 && counts.low === 0
    && counts.info === 0, "Unexpected vulnerability severity totals");
  if (observed.size) {
    ensure(Number.isFinite(now) && now < Date.parse(EXCEPTION_REVIEW_UTC),
      `Exception expired: manual review required by ${EXCEPTION_REVIEW_UTC}`);
  }
  return { vulnerabilityCount: names.length, advisories: [...observed].sort() };
}

export function assessResult(status, report, now = Date.now()) {
  ensure(status === 0 || status === 1, `npm audit exited unexpectedly: ${status}`);
  const result = assessAudit(report, now);
  ensure((status === 0) === (result.vulnerabilityCount === 0),
    `npm audit exit/report mismatch: ${status}`);
  return result;
}

function main() {
  const proc = spawnSync("npm", ["audit", "--include=dev", "--audit-level=low", "--json"], {
    encoding: "utf8", maxBuffer: 16 * 1024 * 1024,
  });
  if (proc.error) throw proc.error;
  let audit;
  try { audit = JSON.parse(proc.stdout); }
  catch { throw new Error("npm audit did not return valid JSON"); }
  const result = assessResult(proc.status, audit);
  console.log(`Full dev+prod npm audit: ${result.vulnerabilityCount} affected packages, `
    + `only reviewed advisories: ${result.advisories.join(", ") || "none"}.`);
  if (result.advisories.length) {
    console.log(`TEMPORARY EXCEPTION: reassess by ${EXCEPTION_REVIEW_UTC}; `
      + "all new advisories remain CI-blocking.");
  }
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  try { main(); }
  catch (error) { console.error(`SECURITY AUDIT FAILED: ${error.message}`); process.exitCode = 1; }
}
