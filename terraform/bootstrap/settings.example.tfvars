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
