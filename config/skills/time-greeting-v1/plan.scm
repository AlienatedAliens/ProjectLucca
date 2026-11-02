(rule "time-greeting-v1"
  :when (and (intent= "chit_chat") (hour-between? 5 11) (not (session-turns>= 1)))
  :plan (list (say "Good morning! How can I help you today?"))
  :priority 10)
