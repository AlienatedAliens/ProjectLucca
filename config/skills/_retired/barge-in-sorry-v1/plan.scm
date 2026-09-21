(rule "barge-in-sorry-v1"
  :when (or (last-tool= "interrupt") (intent= "barge_in"))
  :plan (list (say "Sorry — you were saying?"))
  :priority 10)
