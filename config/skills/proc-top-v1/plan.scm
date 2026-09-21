(rule "proc-top-v1"
  :when (transcript-has? "top processes")
  :plan (list (tool "sys_info" :limit 25)
              (say "Listing active host processes."))
  :priority 10)
