;; Seed Skill #1: calc-open-with-expr (Studio Capability Roadmap §2.3)
;; Triggers on arithmetic / calculate intent in transcript, launches calculator, and speaks interpretation.
(rule "calc-open-with-expr-v1"
  :when (transcript-has? "calculate")
  :plan (list (tool "launch_app" :app_name "calc")
              (say "Opening calculator for expression."))
  :priority 10)
