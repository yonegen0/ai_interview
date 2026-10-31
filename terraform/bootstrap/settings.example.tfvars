# Terraform CLI用の記入前テンプレート。settings.tfvarsへコピーして実値を記入してください。
# AWS Credential・Tokenは記載しません。Terraformは.env.localを直接読み込みません。
# settings.tfvarsはGit管理外。-var-file=settings.tfvarsで明示的に読み込みます。

# 配備先として確認した12桁のAWS Account ID。
account_id = "REPLACE_ME_ACCOUNT_ID"
region     = "ap-northeast-1"

# 空文字はProviderの新規作成。既存Providerを使う場合は確認済みARNを記入します。
oidc_provider_arn = ""

# OIDC Claim確認workflowで実際に確認したdev Subjectを各Roleに記入します。
# Subjectを推測したり、OIDC Token本文を貼り付けたりしないでください。
oidc_subjects = {
  artifact = "REPLACE_ME_VERIFIED_DEV_SUBJECT"
  plan     = "REPLACE_ME_VERIFIED_DEV_SUBJECT"
  deploy   = "REPLACE_ME_VERIFIED_DEV_SUBJECT"
  test     = "REPLACE_ME_VERIFIED_DEV_SUBJECT"
}

# 承認済み方式を "email" または "domain" で指定します。
ses_identity_type = "REPLACE_ME"
# 承認済みの送信元メールアドレス。
ses_from_email = "REPLACE_ME_SENDER_EMAIL"
# email方式は空文字。domain方式は送信元メールと一致する所有ドメイン。
ses_domain = ""

# Existing dev mapping tag-read maintenance only: supply the separately approved
# bootstrap-plan-tag-read.tfvars.json together with settings.tfvars. It pins the
# exact Worker/Streams mapping ARNs; do not substitute a wildcard or omit the
# approved file after the IAM grant has been installed. Empty is initial setup.
# plan_event_source_mapping_arns = []

# Claude直接API用Secretの読み取り権限は、既存Runtime Boundaryでは明示的に未許可。
# 空文字は権限追加なし。実際のSecret ARN確定後、Bootstrap Plan/Applyを別途承認して設定。
# IAM許可はdev Workerと対象Secret ARNにだけ限定。APIキーの値は絶対に書かない。
worker_anthropic_secret_arn = ""
