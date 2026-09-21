(rule "quick-fact-v1"
  :when (transcript-has? "fact about")
  :plan (if (= (entity-str "topic") "")
            (list (yield-to-core "fact: no topic" :need "topic"))
            (list (tool "search_web" :query (entity-str "topic"))))
  :priority 10)
