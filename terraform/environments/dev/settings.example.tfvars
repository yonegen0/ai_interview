# Terraform CLI用の記入前テンプレート。settings.tfvarsへコピーして実値を記入してください。
# AWS Credential・Tokenは記載しません。Terraformは.env.localを直接読み込みません。
# settings.tfvarsはGit管理外。S3 backend設定はinit時に別途指定します。

# 配備先として確認した12桁のAWS Account ID。
account_id = "REPLACE_ME_ACCOUNT_ID"
region     = "ap-northeast-1"

# bootstrapで作成・確認したpermissions boundaryの出力boundary_arn。
boundary_arn = "REPLACE_ME_BOUNDARY_ARN"

# 配備するLambda ZIPのS3格納先。Bucketはbootstrapのartifact_bucket出力を確認します。
artifact_bucket = "REPLACE_ME_ARTIFACT_BUCKET"
artifact_key    = "REPLACE_ME_ARTIFACT_KEY"
# 既存CIのLinux ZIP作成・import検証・upload後、同一成果物のkey/VersionId/hashを同時に転記。
# 同一ZIPのS3 VersionIdと、ZIPバイト列のSHA-256をBase64化した値。
# ETagや16進数hashではありません。別のZIPの値を混在させないでください。
artifact_version       = "REPLACE_ME_ARTIFACT_VERSION_ID"
artifact_sha256_base64 = "REPLACE_ME_ARTIFACT_SHA256_BASE64"

# 承認済み送信元と、bootstrapで作成・確認したSES Identity ARN。
ses_email        = "REPLACE_ME_SENDER_EMAIL"
ses_identity_arn = "REPLACE_ME_SES_IDENTITY_ARN"
# 承認済みの通知先メールアドレス。
alarm_email = "REPLACE_ME_ALARM_EMAIL"

# 実際のFrontend originを文字列リストで記入します（schemeとhost、必要ならport）。
# ワイルドカード・パス・末尾スラッシュは含めません。空リストはvalidationで拒否されます。
cors_origins = []
# 月3,000円 / 160円 per USD = 18.75 USD。FX基準日: 2026-09-17。
monthly_budget_usd = 18.75

# 初回dev配備は閉鎖状態。段階的有効化は別のP4手順で扱います。
worker_enabled    = false
streams_enabled   = false
scheduler_enabled = false
api_enabled       = false
