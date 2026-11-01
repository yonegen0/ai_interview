import { test } from "node:test";
import assert from "node:assert/strict";
import { assessAudit, assessResult } from "./audit-known-exceptions.mjs";

const NOW = Date.parse("2026-11-01T00:00:00Z");
const allow = {
  glob: "GHSA-3g3m-2fjr-6pw4",
  minimatch: "GHSA-g3hv-75wg-m249",
};
function direct(name, id = allow[name], severity = "moderate") {
  return { name, severity, url: `https://github.com/advisories/${id}` };
}
function node(name, via, severity = "moderate") {
  return { name, severity, via };
}
function report(vulnerabilities) {
  const counts = { info: 0, low: 0, moderate: 0, high: 0, critical: 0, total: 0 };
  for (const value of Object.values(vulnerabilities)) {
    counts[value.severity]++;
    counts.total++;
  }
  return { auditReportVersion: 2, metadata: { vulnerabilities: counts }, vulnerabilities };
}
const baseline = () => report({
  glob: node("glob", [direct("glob"), "minimatch"]),
  minimatch: node("minimatch", [direct("minimatch")]),
  "@storybook/react-vite": node("@storybook/react-vite", ["glob"]),
  eslint: node("eslint", ["minimatch"]),
});

test("only two approved advisories, including transitive meta-vulnerabilities", () => {
  assert.deepEqual(assessResult(1, baseline(), NOW), {
    vulnerabilityCount: 4, advisories: [allow.glob, allow.minimatch].sort(),
  });
});
test("clean audit passes even after review deadline", () => {
  assert.equal(assessResult(0, report({}), Date.parse("2027-01-01T00:00:00Z"))
    .vulnerabilityCount, 0);
});
test("exception expires at start of November 15 UTC", () => {
  assert.throws(() => assessAudit(baseline(), Date.parse("2026-11-15T00:00:00Z")),
    /expired/);
});
test("any new unrelated moderate advisory fails", () => {
  const x = baseline();
  x.vulnerabilities.newlib = node("newlib", [direct("newlib", "GHSA-aaaa-bbbb-cccc")]);
  x.metadata.vulnerabilities.moderate++;
  x.metadata.vulnerabilities.total++;
  assert.throws(() => assessAudit(x, NOW), /Unaccepted direct advisory/);
});
test("new direct advisory added to approved package fails", () => {
  const x = baseline();
  x.vulnerabilities.minimatch.via.push(direct("minimatch", "GHSA-xxxx-yyyy-zzzz"));
  assert.throws(() => assessAudit(x, NOW), /Unaccepted direct advisory/);
});
test("higher severity on approved direct advisory fails", () => {
  const x = baseline();
  x.vulnerabilities.minimatch.via[0].severity = "high";
  assert.throws(() => assessAudit(x, NOW), /Unaccepted direct advisory/);
});
test("higher severity on a meta-vulnerable package fails", () => {
  const x = baseline();
  x.vulnerabilities.eslint.severity = "high";
  x.metadata.vulnerabilities.moderate--;
  x.metadata.vulnerabilities.high++;
  assert.throws(() => assessAudit(x, NOW), /Unaccepted severity/);
});
test("a new low-severity advisory is also rejected", () => {
  const x = baseline();
  x.vulnerabilities.other = node("other", [direct("other", "GHSA-abcd-abcd-abcd", "low")], "low");
  x.metadata.vulnerabilities.low++;
  x.metadata.vulnerabilities.total++;
  assert.throws(() => assessAudit(x, NOW), /Unaccepted severity/);
});
test("missing referenced meta-vulnerability fails closed", () => {
  const x = baseline();
  x.vulnerabilities.eslint.via.push("unknown");
  assert.throws(() => assessAudit(x, NOW), /Missing meta-vulnerability/);
});
test("cycles with roots at known advisories are supported", () => {
  const x = baseline();
  x.vulnerabilities.glob.via.push("@storybook/react-vite");
  assert.equal(assessAudit(x, NOW).vulnerabilityCount, 4);
});
test("a cycle with no identified advisory is rejected", () => {
  const x = report({
    first: node("first", ["second"]),
    second: node("second", ["first"]),
  });
  assert.throws(() => assessAudit(x, NOW), /Unexplained vulnerability/);
});
test("advisory package identity may not be substituted", () => {
  const x = baseline();
  x.vulnerabilities.glob.via[0].name = "minimatch";
  assert.throws(() => assessAudit(x, NOW), /Unaccepted direct advisory/);
});
test("npm registry audit errors reject all exceptions", () => {
  const x = baseline();
  x.error = { code: "ENOAUDIT" };
  assert.throws(() => assessAudit(x, NOW), /contains an error/);
});
test("missing npm audit report fails", () => {
  assert.throws(() => assessResult(1, null, NOW), /report missing/);
});
test("unexpected audit schema version fails", () => {
  const x = baseline();
  x.auditReportVersion = 3;
  assert.throws(() => assessAudit(x, NOW), /Unexpected npm audit report version/);
});
test("inconsistent severity totals fail", () => {
  const x = baseline();
  x.metadata.vulnerabilities.total++;
  assert.throws(() => assessAudit(x, NOW), /Inconsistent/);
});
test("npm claims no vulnerabilities while reporting them: fail", () => {
  assert.throws(() => assessResult(0, baseline(), NOW), /exit\/report mismatch/);
});
test("npm returns nonzero on a clean report: fail", () => {
  assert.throws(() => assessResult(1, report({}), NOW), /exit\/report mismatch/);
});
test("unexpected npm audit exit status fails", () => {
  assert.throws(() => assessResult(2, baseline(), NOW), /exited unexpectedly/);
});
