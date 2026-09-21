(rule "resource-report-v1"
  :when (transcript-has? "resource report")
  :plan (list (tool "self_metrics")
              (say "Checking system resources now."))
  :priority 10)
