"""One approved direct Worker invoke; never expose JWTs or invoke Responses."""

import hashlib
import json
from pathlib import Path

from botocore.config import Config
from closure_adapter import write
from manifest import verify_live_manifest


def invoke_worker_smoke(session, manifest, approval_raw, approved_sha256, journal):
    if hashlib.sha256(approval_raw).hexdigest() != approved_sha256:
        raise ValueError("SmokeApprovalHashMismatch")
    approval = json.loads(approval_raw)
    env = manifest.get("worker_ai_environment", {})
    expected = {
        "status": "WORKER_WIF_SMOKE_VERIFIED",
        "issuer": env.get("INTERVIEW_OPENAI_AWS_ISSUER"),
        "audience": "https://api.openai.com/v1",
        "subject": f"arn:aws:iam::{manifest['account_id']}:role/ai-interview-dev-worker-runtime",
        "signature_verified_locally": False,
        "openai_exchange_verified": True,
        "paid_responses_calls": 0,
    }
    if (
        approval.get("wif_smoke_authorized") is not True
        or approval.get("account_id") != manifest["account_id"]
        or approval.get("region") != "ap-northeast-1"
        or manifest["region"] != "ap-northeast-1"
        or manifest.get("worker_wif_enabled") is not True
        or approval.get("run_id") != env.get("INTERVIEW_WIF_SMOKE_RUN_ID")
        or approval.get("expected") != expected
    ):
        raise ValueError("ExplicitObservedWorkerSmokeBindingRequired")
    path = Path(journal).resolve()
    if not path.is_relative_to((Path(__file__).resolve().parents[2] / ".p4-artifacts").resolve()):
        raise ValueError("PrivateSmokeJournalRequired")
    verify_live_manifest(session, manifest, require_api_enabled=False)
    attempts = Path(__file__).resolve().parents[2] / ".p4-artifacts/wif-smoke-attempts"
    attempts.mkdir(exist_ok=True)
    write(attempts / (approved_sha256 + ".json"), {"journal": str(path)})
    write(path, {"status": "INVOKE_STARTED", "approval_sha256": approved_sha256})
    client = session.client(
        "lambda",
        region_name=manifest["region"],
        config=Config(retries={"total_max_attempts": 1}, connect_timeout=5, read_timeout=65),
    )
    reply = client.invoke(
        FunctionName=manifest["aliases"]["worker"],
        InvocationType="RequestResponse",
        Payload=json.dumps({"operation": "wif_smoke", "run_id": approval["run_id"]}).encode(),
    )
    with reply["Payload"] as stream:
        raw = stream.read(8193)
    if reply.get("FunctionError") or len(raw) > 8192:
        raise ValueError("WorkerSmokeFailedNoReplay")
    result = json.loads(raw)
    if (
        set(result) != set(expected) | {"ttl_seconds"}
        or any(type(result.get(k)) is not type(v) or result[k] != v for k, v in expected.items())
        or type(result["ttl_seconds"]) is not int
        or not 1 <= result["ttl_seconds"] <= 300
    ):
        raise ValueError("WorkerClaimsOrMappingReadbackMismatch")
    write(path.with_suffix(".verified.json"), result)
    return result
