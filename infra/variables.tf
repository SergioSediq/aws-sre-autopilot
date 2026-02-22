variable "gemini_api_key" {
  description = "API Key for Google Gemini"
  type        = string
  sensitive   = true
}

variable "gemini_model" {
  description = "Google Gemini Model Name"
  type        = string
  default     = "gemini-1.5-pro"
}
