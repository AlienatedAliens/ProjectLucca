(rule "define-term-v1"
  :when (transcript-has? "what is")
  :plan (if (= (entity-str "term") "")
            (list (yield-to-core "define: no term" :need "term"))
            (list (tool "search_web" :query (entity-str "term"))))
  :priority 10)
