"""Existing Plan Role qualification; explicitly no bootstrap/namespace claims."""

from cloud_aws_readonly import ReadonlyReader
from cloud_controller_core import ACCOUNT, FLAGS, REGION, require


class DevReader(ReadonlyReader):
    def versions(self, key):
        # Existing Role has GetObjectVersion, not ListBucketVersions. This proves
        # only the pinned current version, never the complete version inventory.
        require(key == "dev/terraform.tfstate", "DevStateOnly")
        return [self.current_version_proof]

    def snapshot_key(self, key, expected):
        require(key == "dev/terraform.tfstate", "DevStateOnly")
        s3 = self.session.client("s3")
        head = s3.head_object(Bucket=self.scope.state_bucket, Key=key, ExpectedBucketOwner=ACCOUNT)
        require(head.get("VersionId") == expected["version_id"], "PinnedDevStateChanged")
        self.current_version_proof = {
            "kind": "Versions",
            "version_id": head["VersionId"],
            "size": head["ContentLength"],
            "evidence": "pinned current HEAD and exact-version GET; all-history NOT inspected",
        }
        return super().snapshot_key(key, expected)

    def snapshot(self, label):
        require(
            label in {"before", "after", "independent"} and label not in self.batches,
            "ReadBatchAlreadyConsumed",
        )
        self.batches.add(label)
        self.active_label = label
        if label in {"before", "independent"}:
            self.session.fresh_identity()
        dev = self.snapshot_key("dev/terraform.tfstate", self.scope.a.x["dev_state_identity"])
        manifest = dev["state"]["outputs"]["manifest"]["value"]
        require(
            manifest["account_id"] == ACCOUNT
            and manifest["region"] == REGION
            and manifest["run_id"] == ""
            and all(manifest["configuration"][key] is False for key in FLAGS),
            "ClosedDevStateRequired",
        )
        from cloud_configuration_contract import (
            normalize_configuration,
            validate_manifest,
            verify_live,
        )

        old = manifest["artifact"]
        package = {
            "artifact_" + key: old[key] for key in ("bucket", "key", "version", "sha256_base64")
        }
        x = self.scope.a.x
        normalized = normalize_configuration(
            x["configuration"], package, x["configuration_contract"]
        )
        readback = validate_manifest(
            manifest,
            normalized,
            x["configuration_contract"],
            self.scope.j.path / f"manifest-{label}.private.json",
        )
        verify_live(
            self.session,
            manifest,
            readback,
            journal=self.scope.j,
            state_identity=dev["identity"],
            state=dev["state"],
        )
        self.verify_no_alarms()
        from cloud_artifact_binding import verify_artifact

        verify_artifact(self.session.client("s3"), old, x, self.scope.j, label, dev["identity"])
        return {
            "dev": dev,
            "closed": True,
            "active_lock": False,
            "managed_manifest_live_verified": True,
            "bootstrap_state_and_live": "UNCONFIRMED; not in existing Plan Role permission scope",
            "outside_dev_resource_inventory": "UNCONFIRMED; no full namespace enumeration",
            "all_state_version_inventory": "UNCONFIRMED; pinned current version verified",
        }
