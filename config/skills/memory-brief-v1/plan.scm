(rule "memory-brief-v1"
  :when (transcript-has? "memory about")
  :plan (if (= (entity-str "query") "")
            (list (yield-to-core "memory-brief: no query" :need "query"))
            (list (tool "memory_search" :query (entity-str "query"))))
  :priority 10)
