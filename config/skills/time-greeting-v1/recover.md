# Recovery Protocol for time-greeting-v1

- Trigger behavior: To prevent over-firing on every turn during morning hours, this skill strictly fires only on the first turn of a session (`(not (session-turns>= 1))`) between 05:00 and 11:00.
- Fallback behavior: On subsequent turns or outside morning hours, this rule does not fire, allowing normal dialogue routing.
