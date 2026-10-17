variable "aws_region" {
  description = "Region for every pipeline resource."
  type        = string
  default     = "eu-west-3"
}

variable "project_name" {
  description = "Short resource name prefix."
  type        = string
  default     = "graduation-images"
  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{2,29}$", var.project_name))
    error_message = "Use 3-30 lowercase letters, digits, or hyphens, starting with a letter."
  }
}

variable "bucket_suffix" {
  description = "Unique lowercase suffix to choose before future deployment. Not a secret."
  type        = string
  validation {
    condition     = can(regex("^[a-z0-9]{6,12}$", var.bucket_suffix))
    error_message = "Use 6-12 lowercase letters or digits."
  }
}

variable "lambda_zip_path" {
  description = "Application ZIP containing Python handlers (Pillow is a separate layer)."
  type        = string
  default     = "../build/application.zip"
}

variable "enable_processing" {
  description = "Leave false until future deployment and processing are authorized."
  type        = bool
  default     = false
}

variable "pillow_layer_path" {
  description = "Linux Python 3.12 x86_64 Pillow layer ZIP with python/ at its root."
  type        = string
  default     = "../build/pillow-layer.zip"
}

variable "enable_delivery" {
  description = "Leave CloudFront delivery disabled until future deployment is authorized."
  type        = bool
  default     = false
}
