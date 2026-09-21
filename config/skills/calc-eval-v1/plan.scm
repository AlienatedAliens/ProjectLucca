(rule "calc-eval-v1"
  :when (transcript-has? "calculate")
  :plan (if (= (entity-str "expr") "")
            (list (yield-to-core "calc: no expression" :need "expr"))
            (list (tool "run_python" :code (entity-str "expr"))))
  :priority 10)
