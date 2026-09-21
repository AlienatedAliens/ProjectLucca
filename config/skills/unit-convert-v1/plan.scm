(rule "unit-convert-v1"
  :when (transcript-has? "convert")
  :plan (if (= (entity-str "expr") "")
            (list (yield-to-core "convert: no expression" :need "expr"))
            (list (tool "run_python" :code (entity-str "expr"))))
  :priority 10)
