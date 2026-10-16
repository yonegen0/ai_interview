variable "worker_ai_environment" {
  type    = map(string)
  default = {}
}
variable "worker_wif_enabled" {
  type    = bool
  default = false
}
variable "worker_bedrock_enabled" {
  type    = bool
  default = false
}
