(rule "barge-in-sorry-v1"
  :when (interrupted?)
  :plan (list (say "Sorry — you were saying?"))
  :priority 10)
