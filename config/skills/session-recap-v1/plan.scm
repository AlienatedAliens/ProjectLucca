(rule "session-recap-v1"
  :when (transcript-has? "session recap")
  :plan (if (= (entity-str "query") "")
            (list (yield-to-core "session-recap: no query" :need "query"))
            (list (tool "memory_search" :query (entity-str "query"))))
  :priority 10)
