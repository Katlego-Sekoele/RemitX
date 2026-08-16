locals {
  cap           = var.monthly_budget_cap
  segment_size  = 5
  segment_count = local.cap / local.segment_size

  segments = {
    for i in range(1, local.segment_count + 1) :
    i => {
      amount  = i * local.segment_size
      dollars = range((i - 1) * local.segment_size + 1, i * local.segment_size + 1)
    }
  }
}
