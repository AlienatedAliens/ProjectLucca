(rule "recent-context-v1"
  :when (transcript-has? "recent context")
  :plan (if (= (entity-str "topic") "")
            (list (yield-to-core "recent-context: no topic" :need "topic"))
            (list (tool "memory_search" :query (entity-str "topic"))))
  :priority 10)
