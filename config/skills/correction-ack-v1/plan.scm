(rule "correction-ack-v1"
  :when (or (transcript-has? "no,") (transcript-has? "actually"))
  :plan (list (yield-to-core "operator correction" :salience "high"))
  :priority 10)
