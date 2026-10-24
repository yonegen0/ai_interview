mock_provider "aws" {
  mock_resource "aws_cloudfront_function" {
    defaults = { arn = "arn:aws:cloudfront::123456789012:function/synthetic-routes" }
  }
  mock_resource "aws_cloudfront_distribution" {
    defaults = { arn = "arn:aws:cloudfront::123456789012:distribution/SYNTHETIC", domain_name = "synthetic.cloudfront.net" }
  }
}
variables { bucket_name = "ai-interview-static-test" }

run "closed_private_frontend" {
  command = plan
  assert {
    condition     = !aws_cloudfront_distribution.assets.enabled && !aws_s3_bucket.assets.force_destroy
    error_message = "Default deployment must remain closed and preserve assets."
  }
  assert {
    condition     = aws_s3_bucket_public_access_block.assets.block_public_acls && aws_s3_bucket_public_access_block.assets.block_public_policy && aws_s3_bucket_public_access_block.assets.ignore_public_acls && aws_s3_bucket_public_access_block.assets.restrict_public_buckets
    error_message = "S3 must remain private with every public-access block enabled."
  }
  assert {
    condition     = aws_cloudfront_origin_access_control.assets.signing_behavior == "always" && aws_cloudfront_origin_access_control.assets.signing_protocol == "sigv4"
    error_message = "Origin access must always be authenticated and use HTTPS."
  }
  assert {
    condition     = aws_cloudfront_distribution.assets.default_cache_behavior[0].viewer_protocol_policy == "redirect-to-https" && toset(aws_cloudfront_distribution.assets.default_cache_behavior[0].allowed_methods) == toset(["GET", "HEAD"])
    error_message = "Frontend cannot proxy API mutations or accept plain HTTP."
  }
}
run "exact_distribution_policy" {
  command = apply
  assert {
    condition     = jsondecode(aws_s3_bucket_policy.assets.policy).Statement[0].Principal.Service == "cloudfront.amazonaws.com" && jsondecode(aws_s3_bucket_policy.assets.policy).Statement[0].Action == "s3:GetObject" && jsondecode(aws_s3_bucket_policy.assets.policy).Statement[0].Condition.StringEquals["AWS:SourceArn"] == aws_cloudfront_distribution.assets.arn
    error_message = "Only the exact CloudFront distribution may read assets."
  }
  assert {
    condition     = jsondecode(aws_s3_bucket_policy.assets.policy).Statement[1].Effect == "Deny" && jsondecode(aws_s3_bucket_policy.assets.policy).Statement[1].Condition.Bool["aws:SecureTransport"] == "false"
    error_message = "Non-TLS bucket access must be denied."
  }
}
