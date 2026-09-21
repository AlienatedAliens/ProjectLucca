(rule "self-health-v1"
  :when (transcript-has? "self health")
  :plan (list (tool "self_metrics")
              (say "Here is my current hardware telemetry."))
  :priority 10)
