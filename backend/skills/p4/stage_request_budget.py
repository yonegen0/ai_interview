"""Bound Python SDK/HTTP calls in Stage recovery; Terraform Go traffic is not metered.

This is an orchestration limit, not a global AWS request or billing hard cap.
Existing Terraform process/session/time limits govern the separate Go processes.
"""

import threading

from interview_backend.deployment import DeploymentError

LIMIT = 512


class Meter:
    def __init__(self, record):
        from botocore.client import BaseClient
        from botocore.httpsession import URLLib3Session

        self.record = record
        self.sdk = self.http = 0
        self.lock = threading.Lock()
        self.local = threading.local()
        self.closed = False
        self.base, self.transport = BaseClient, URLLib3Session
        self.old_call, self.old_send = BaseClient._make_api_call, URLLib3Session.send
        self.record(
            "stage-request-meter-started",
            sdk_limit=LIMIT,
            http_limit=LIMIT,
            scope="python-orchestration-only;terraform-go-unmetered",
        )

        def call(client, operation, params):
            with self.lock:
                if self.closed or self.sdk >= LIMIT:
                    raise DeploymentError("StageRecoverySdkBudgetExceeded")
                self.sdk += 1
                sequence = self.sdk
            self.record(
                "stage-sdk-request",
                sequence=sequence,
                service=client.meta.service_model.service_name,
                operation=operation,
            )
            stack = getattr(self.local, "stack", None)
            if stack is None:
                stack = self.local.stack = []
            stack.append(0)
            try:
                return self.old_call(client, operation, params)
            finally:
                stack.pop()

        def send(transport, request):
            stack = getattr(self.local, "stack", [])
            with self.lock:
                if self.closed or not stack or stack[-1] != 0 or self.http >= LIMIT:
                    raise DeploymentError("StageRecoveryHttpBudgetOrRetryRejected")
                stack[-1] += 1
                self.http += 1
            return self.old_send(transport, request)

        BaseClient._make_api_call, URLLib3Session.send = call, send

    def close(self):
        if self.closed:
            return
        self.base._make_api_call, self.transport.send = self.old_call, self.old_send
        self.closed = True
        self.record(
            "stage-request-meter-completed",
            sdk_requests=self.sdk,
            http_attempts=self.http,
            scope="python-orchestration-only;terraform-go-unmetered",
        )


def install(record):
    return Meter(record)
