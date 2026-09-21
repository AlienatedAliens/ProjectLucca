(rule "plan-decompose-v1"
  :when (transcript-has? "step by step")
  :plan (list (yield-to-core "multi-step task" :mode "plan"))
  :priority 10)
