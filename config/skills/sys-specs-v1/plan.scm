(rule "sys-specs-v1"
  :when (transcript-has? "system specs")
  :plan (list (tool "sys_info" :limit 10)
              (say "Gathering system specifications."))
  :priority 10)
