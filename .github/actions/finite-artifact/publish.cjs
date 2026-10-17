'use strict';
// GitHub Results protocol from actions/toolkit. Deliberately no SDK/retry layer.
const fs = require('node:fs');
const path = require('node:path');
const https = require('node:https');
const crypto = require('node:crypto');

function need(x) { if (!x) throw Error('ArtifactRefused'); }
function sha(x) { return crypto.createHash('sha256').update(x).digest('hex'); }
function checkedUrl(value, suffix) {
  const u = new URL(value);
  need(u.protocol === 'https:' && !u.username && !u.password && !u.hash);
  need(!u.port || u.port === '443');
  need(u.hostname.endsWith(suffix) && u.hostname.length > suffix.length);
  return u;
}
function crc32(data) {
  let n = 0xffffffff;
  for (const byte of data) {
    n ^= byte;
    for (let i = 0; i < 8; i++) n = (n >>> 1) ^ ((n & 1) ? 0xedb88320 : 0);
  }
  return (n ^ 0xffffffff) >>> 0;
}
function zip(data) {
  const name = Buffer.from('result.json');
  const local = Buffer.alloc(30), central = Buffer.alloc(46), end = Buffer.alloc(22);
  const crc = crc32(data);
  local.writeUInt32LE(0x04034b50); local.writeUInt16LE(20, 4);
  local.writeUInt32LE(crc, 14); local.writeUInt32LE(data.length, 18);
  local.writeUInt32LE(data.length, 22); local.writeUInt16LE(name.length, 26);
  central.writeUInt32LE(0x02014b50); central.writeUInt16LE(20, 4); central.writeUInt16LE(20, 6);
  central.writeUInt32LE(crc, 16); central.writeUInt32LE(data.length, 20);
  central.writeUInt32LE(data.length, 24); central.writeUInt16LE(name.length, 28);
  end.writeUInt32LE(0x06054b50); end.writeUInt16LE(1, 8); end.writeUInt16LE(1, 10);
  end.writeUInt32LE(central.length + name.length, 12);
  end.writeUInt32LE(local.length + name.length + data.length, 16);
  return Buffer.concat([local, name, data, central, name, end]);
}
function request(url, method, headers, body) {
  return new Promise((resolve, reject) => {
    const req = https.request(url, {method, headers, agent: false, timeout: 15000}, res => {
      const chunks = []; let size = 0;
      res.on('data', c => { size += c.length; if (size > 65536) req.destroy(Error('Large')); else chunks.push(c); });
      res.on('end', () => resolve({status: res.statusCode, raw: Buffer.concat(chunks)}));
      res.on('error', reject);
    });
    req.on('timeout', () => req.destroy(Error('Timeout'))); req.on('error', reject);
    req.end(body);
  });
}
async function publish(env, send = request) {
  need(env.GITHUB_RUN_ATTEMPT === '1' && env.GITHUB_EVENT_NAME === 'workflow_dispatch');
  need(env.GITHUB_REPOSITORY === 'yonegen0/ai_interview' && env.GITHUB_REF === 'refs/heads/main');
  need(env.P4_AWS_EXECUTION_READY === 'false');
  const raw = Buffer.from(env.P4_TAG_PROBE_PACKAGE || '');
  need(sha(raw) === env.P4_TAG_PROBE_SHA256);
  const p = JSON.parse(raw);
  need(p.kind === 'PR17_EXACT_MAPPING_LISTTAGS_ONLY' && p.source_sha === env.GITHUB_SHA);
  const now = Date.now(), issued = Date.parse(p.issued_at_utc), expiry = Date.parse(p.expires_at_utc);
  need(expiry - issued === 72 * 3600000 && issued <= now && now < expiry - 60000);
  for (const name of Object.keys(p.files)) {
    need(!path.isAbsolute(name) && !name.split('/').includes('..'));
    need(sha(fs.readFileSync(path.join(env.GITHUB_WORKSPACE, name))) === p.files[name]);
  }
  need(p.files['.github/actions/finite-artifact/publish.cjs']);
  const input = fs.readFileSync(path.join(env.RUNNER_TEMP, 'p4-tag-probe', 'result.json'));
  need(input.length < 32768);
  const result = JSON.parse(input);
  need(result.READY === false && result.formal_resume_ready === false);
  const fields = new Set(['passed', 'reason', 'READY', 'formal_resume_ready', 'approval_sha256',
    'source_sha', 'run_id', 'run_attempt', 'plan_role_identity_verified', 'listtags', 'aws_requests',
    'sdk_before_send_counts', 'oidc_gets', 'retry', 'terraform_calls', 'aws_mutations', 'finished_at_utc']);
  need(Object.keys(result).every(k => fields.has(k)));
  if (result.reason !== undefined) need(result.reason === 'ProbeFailedNoRetry');
  if (result.listtags !== undefined) need(Array.isArray(result.listtags) && result.listtags.length === 2 &&
    result.listtags.every(r => Object.keys(r).sort().join() === 'http_status,request_id,resource_sha256'));
  const bytes = zip(input);
  const token = env.ACTIONS_RUNTIME_TOKEN;
  const claims = JSON.parse(Buffer.from(token.split('.')[1], 'base64url'));
  need(typeof claims.exp === 'number' && claims.exp * 1000 > now + 60000);
  const scopes = claims.scp.split(' ').filter(s => s.startsWith('Actions.Results:'));
  need(scopes.length === 1);
  const ids = scopes[0].split(':');
  need(ids.length === 3 && ids.slice(1).every(s => /^[0-9a-f-]{36}$/i.test(s)));
  const service = checkedUrl(env.ACTIONS_RESULTS_URL, '.actions.githubusercontent.com');
  const name = `mapping-tag-probe-${env.GITHUB_RUN_ID}-1`;
  need(/^[0-9]+$/.test(env.GITHUB_RUN_ID));
  const common = {workflowRunBackendId: ids[1], workflowJobRunBackendId: ids[2], name};
  const journal = path.join(env.RUNNER_TEMP, 'p4-tag-probe');
  async function once(label, url, method, headers, body, status) {
    need(Date.now() < expiry - 30000);
    const fd = fs.openSync(path.join(journal, `${label}.started`), 'wx');
    try { fs.writeFileSync(fd, JSON.stringify({operation: label, body_sha256: sha(body)})); fs.fsyncSync(fd); }
    finally { fs.closeSync(fd); }
    const response = await send(url, method, headers, body);
    need(response.status === status); // Unknown/failed response never gets resent.
    return response.raw;
  }
  function endpoint(method) { return new URL(`/twirp/github.actions.results.api.v1.ArtifactService/${method}`, service); }
  const headers = {'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json'};
  const created = JSON.parse(await once('create', endpoint('CreateArtifact'), 'POST', headers,
    Buffer.from(JSON.stringify({...common, version: 4, expiresAt: new Date(now + 7 * 86400000).toISOString()})), 200));
  need(created.ok === true);
  const signed = checkedUrl(created.signedUploadUrl || created.signed_upload_url, '.blob.core.windows.net');
  await once('blob', signed, 'PUT', {'x-ms-blob-type': 'BlockBlob', 'Content-Type': 'application/zip', 'Content-Length': String(bytes.length)}, bytes, 201);
  const final = JSON.parse(await once('finalize', endpoint('FinalizeArtifact'), 'POST', headers,
    Buffer.from(JSON.stringify({...common, size: String(bytes.length), hash: `sha256:${sha(bytes)}`})), 200));
  need(final.ok === true && /^[0-9]+$/.test(String(final.artifactId || final.artifact_id)));
  return {requests: 3, artifact_id: String(final.artifactId || final.artifact_id), archive_sha256: sha(bytes)};
}
module.exports = {publish, zip, checkedUrl};
if (require.main === module) publish(process.env).then(() => console.log('Finite artifact: PASS'), () => {
  console.log('Finite artifact: FAIL (no retry)'); process.exitCode = 1;
});
