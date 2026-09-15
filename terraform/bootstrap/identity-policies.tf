resource "aws_iam_role_policy" "identity_read" {
  for_each = { for name, role in aws_iam_role.ci : name => role if name != "artifact" }
  role     = each.value.id
  name     = "identity-read"
  policy = jsonencode({ Version = "2012-10-17", Statement = [
    { Effect = "Allow", Action = ["apigateway:GET"], Resource = ["arn:aws:apigateway:${var.region}::/apis/*", "arn:aws:apigateway:${var.region}::/tags/*"] },
    { Effect = "Allow", Action = ["cognito-idp:DescribeUserPool", "cognito-idp:DescribeUserPoolClient", "cognito-idp:GetGroup", "cognito-idp:ListTagsForResource"], Resource = ["arn:aws:cognito-idp:${var.region}:${var.account_id}:userpool/*"], Condition = { StringEquals = { "aws:ResourceTag/Project" = "ai-interview" } } },
    { Effect = "Allow", Action = ["budgets:ViewBudget", "budgets:ListTagsForResource"], Resource = ["arn:aws:budgets::${var.account_id}:budget/ai-interview-dev-*"] }
  ] })
}
resource "aws_iam_role_policy" "identity_deploy" {
  for_each = { for name, role in aws_iam_role.ci : name => role if contains(["deploy", "test"], name) }
  role     = each.value.id
  name     = "identity-deploy"
  policy = jsonencode({ Version = "2012-10-17", Statement = [
    { Effect = "Allow", Action = ["apigateway:POST"], Resource = ["arn:aws:apigateway:${var.region}::/apis"], Condition = { StringLike = { "apigateway:Request/ApiName" = "${local.ci_prefix[each.key]}-api" }, StringEquals = { "aws:RequestTag/Project" = "ai-interview" } } },
    { Effect = "Allow", Action = ["apigateway:POST", "apigateway:PATCH", "apigateway:PUT", "apigateway:DELETE"], Resource = ["arn:aws:apigateway:${var.region}::/apis/*", "arn:aws:apigateway:${var.region}::/tags/*"], Condition = { StringEquals = { "aws:ResourceTag/Project" = "ai-interview", "aws:ResourceTag/Environment" = each.key == "test" ? "test" : "dev" } } },
    { Effect = "Allow", Action = ["cognito-idp:CreateUserPool"], Resource = ["*"], Condition = { StringEquals = { "aws:RequestTag/Project" = "ai-interview", "aws:RequestTag/Environment" = each.key == "test" ? "test" : "dev" } } },
    { Effect = "Allow", Action = ["cognito-idp:UpdateUserPool", "cognito-idp:DeleteUserPool", "cognito-idp:CreateUserPoolClient", "cognito-idp:UpdateUserPoolClient", "cognito-idp:DeleteUserPoolClient", "cognito-idp:CreateGroup", "cognito-idp:UpdateGroup", "cognito-idp:DeleteGroup", "cognito-idp:TagResource", "cognito-idp:UntagResource"], Resource = ["arn:aws:cognito-idp:${var.region}:${var.account_id}:userpool/*"], Condition = { StringEquals = { "aws:ResourceTag/Project" = "ai-interview", "aws:ResourceTag/Environment" = each.key == "test" ? "test" : "dev" } } },
    { Effect = "Allow", Action = ["iam:CreateServiceLinkedRole"], Resource = ["arn:aws:iam::${var.account_id}:role/aws-service-role/email.cognito-idp.amazonaws.com/*"], Condition = { StringEquals = { "iam:AWSServiceName" = "email.cognito-idp.amazonaws.com" } } },
    { Effect = "Allow", Action = ["budgets:ModifyBudget"], Resource = each.key == "deploy" ? ["arn:aws:budgets::${var.account_id}:budget/ai-interview-dev-*"] : ["arn:aws:budgets::${var.account_id}:budget/ai-interview-test-*"] }
  ] })
}
