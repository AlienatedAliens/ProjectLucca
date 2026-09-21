(rule "note-take-v1"
  :when (transcript-has? "take note")
  :plan (if (= (entity-str "content") "")
            (list (yield-to-core "note-take: no content" :need "content"))
            (list (tool "note_write" :name "scratchpad.txt" :content (entity-str "content"))
                  (say "Saved to your notes.")))
  :priority 10)
