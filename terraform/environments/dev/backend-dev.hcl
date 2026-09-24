# Public partial configuration only. Bucket and allowed_account_ids MUST come
# from the reviewed private recovery-generated backend-dev.hcl, not this file.
# See docs/P4_TERRAFORM_RUNBOOK.md section 5.1. Do not initialize this file alone.
key = "dev/terraform.tfstate"
region = "ap-northeast-1"
encrypt = true
use_lockfile = true
