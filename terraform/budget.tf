data "google_project" "this" {}

resource "google_billing_budget" "budget" {
  billing_account = var.billing_account_id
  display_name    = "RagOps Budget"
  budget_filter {
    projects = [
      "projects/${data.google_project.this.number}"
    ]
  }
  amount {
    specified_amount {
      currency_code = "USD"
      units         = var.budget_amount
    }
  }
  threshold_rules {
    threshold_percent = 0.4
    spend_basis       = "CURRENT_SPEND"
  }
  threshold_rules {
    threshold_percent = 1.0
    spend_basis       = "CURRENT_SPEND"
  }
}