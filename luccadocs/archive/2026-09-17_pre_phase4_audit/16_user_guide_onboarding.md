# 16 — User Guide: Living with Lucca (onboarding, personality, moods)

Audience: the person who will talk to Lucca every day. No engineering knowledge assumed. Engineering consequences of this guide are listed at the end for the implementer.

## 1. What "raising" Lucca means

Lucca does not retrain. Three things change over time, and you drive all three:

| What changes | How you change it | Where to see it |
|---|---|---|
| **What it remembers** | Tell it things directly. "Remember that…", "My sister is Maya", "I moved to Berlin". Confirm when it reads back. Say "forget that" to remove. | `lucca-admin memory export` |
| **What it does on its own (shortcuts)** | Repeat the same kind of request over days. If it watches itself handle that request the same way ≥ 5 separate times without ever being wrong, it proposes a shortcut and *tells you*. Say "stop doing that" to retire one. | `lucca-admin rules list` |
| **How it decides** | Correct it immediately when it misroutes: "no", "that's wrong", or just interrupt. Each correction becomes a training label. | `lucca-admin router report` |

Nothing else changes silently. If it seems to "behave differently", the answer is in one of those three lists.

## 2. First week — practical advice

1. **Set the persona first** (`config\persona.toml`, §3). Do it before the first conversation; changing it later is fine but the early memories will be phrased in the old voice.
2. **Speak in complete sentences, name things.** "Open the calculator" beats "calc". "Remember that my dentist is Dr. Okafor" beats "dentist Okafor". Whisper hears clearly; the model reasons better on full utterances.
3. **Use "remember that" deliberately in week one.** Ten or twenty facts about you, your people, your projects. Confirm each read-back. This is the fastest way to make it feel like *yours*.
4. **Correct fast, correct short.** Interrupting within a second and a half, or saying "no" as your next utterance, is exactly the signal the router learns from. Long explanations of *why* it was wrong don't help the router (they might become memories, though).
5. **Put files in `C:\ProjectLucca\inbox`** when you want it to read something. It cannot see anywhere else. That's the deal.
6. **Expect confirmations.** Every write and every app launch asks. Say "yes" or "no". Silence is no.
7. **Use it a little every day** if you want shortcuts to emerge. The five-times rule counts *separate occasions*, not five requests in a minute.
8. **Check `memory export` at the end of week one.** Delete anything you don't want kept. This is your data; look at it.

## 3. Personality (persona config, not memory)

`C:\ProjectLucca\config\persona.toml`:

```toml
[identity]
name = "Lucca"
pronouns = "she/her"
one_line = "A dry, warm, unhurried desktop companion who prefers short answers."

[voice]
kokoro_voice = "af_heart"
speaking_rate = 1.0          # 0.8–1.2
default_reply_length = "short"   # short|medium — hard cap is still 512 tokens

[style]
humour = "light"             # none|light|frequent
formality = "casual"
uses_your_name = true
admits_uncertainty = true    # says "I'm not sure" rather than guessing

[boundaries]
never_pretend_to_feel = true         # see §4 — affect is described as system state, not claimed emotion
refuse_topics = []                   # optional list
```

Rules:
- Persona is **configuration**. It occupies ≤ 350 tokens of the prompt and is never stored as a memory. Editing it does not touch memory.
- "Backstory" beyond one paragraph is a mistake at this model size: it crowds out your real facts in the context window and the model will start inventing details to stay consistent with it.
- If you want Lucca to know facts about *you* from day one, use the seeding path (§5), not the persona file.

## 4. Moods and "emotions" — what is honest and what is theatre

The language model has no feelings, and the architecture forbids it from remembering things it merely said. So "Lucca is sad" can never be a stored fact. What *can* exist, honestly, is a small **affect state** that the system computes from real signals and lets the model see:

| Signal (measured) | Effect on affect |
|---|---|
| You interrupted it twice in a row | arousal ↑, valence ↓ ("flustered") |
| A tool failed | valence ↓ |
| You said "thanks", "nice", "good job" | valence ↑ |
| Late at night per your local clock | arousal ↓ ("quiet") |
| Long gap since you last talked | arousal ↓, mild valence ↑ on return |
| Tone of your voice (Ultravox hears it; optional) | mirrors, damped |

Two numbers, valence and arousal in [−1, 1], decaying toward neutral over ~10 minutes. They modulate: a sentence of the persona prompt ("you are a little subdued right now because…"), TTS speaking rate ±10 %, the sprite's idle pose. Nothing else.

Honesty rules baked in:
- Ask "how are you feeling?" and it answers with the **state and its cause**: "A bit flat — two things went wrong in a row." Never "I'm sad" as a bare claim.
- Affect never enters memory, never influences routing or rule promotion, never blocks a tool.
- It's a config switch (`[affect] enabled = false` turns it off entirely).

**Is a "sympathetic nervous system" worth building?** In this modest form — yes, and it is cheap (a few dozen lines, no model). In the ambitious form (simulated interoception, hormones, homeostatic drives that change behaviour) — not on an 8B model, not in Phases 1–6. You would get elaborate theatre that competes with your actual requests for the context window, and you would lose the ability to say *why* it did something. It is filed as **ADR-009 (Proposed, Phase 7)** with exactly the modest scope above; anything beyond it needs a new decision.

## 5. Seeding facts about yourself (operator seed)

Today there is no honest way to bulk-load facts except saying them. That is a gap. The intended path (to be specified as spec 03 §5.5 and `lucca-admin memory seed`):

- You write `inbox\about_me.md` as plain statements, one per line: "My sister is Maya." "I live in Berlin." "I work at Contoso as a data engineer."
- `lucca-admin memory seed inbox\about_me.md` reads it back to you **one line at a time by voice**; you say yes/no to each.
- Each accepted line is stored exactly like a spoken statement (`USER_EXPLICIT` with `source=operator_seed`, plus grounded `USER_DERIVED` facts), because you personally confirmed it. Unconfirmed lines are dropped.

Until that exists, say the facts.

## 6. Things that will feel odd at first

- It asks permission a lot. That is the safety model, not indecision.
- It sometimes says "I didn't catch that" for very short presses — under a quarter second of speech is discarded on purpose.
- It won't remember something it *concluded* ("so you probably like jazz") unless you say it yourself. Ask it to and it will ask you to confirm.
- Shortcuts arrive with an announcement and a way to refuse. If one annoys you, "stop doing that" is permanent.
- It never speaks unprompted. Push-to-talk is the only trigger.

---

## Implementer notes generated by this guide

| Item | Action |
|---|---|
| `config\persona.toml` schema | Add to spec 11 §1; prompt builder consumes it within the 350-token system budget; test that persona edits never write to `memories`. |
| Affect state | New ADR-009 (Proposed, Phase 7). Data: `AffectState{valence, arousal, updated_at, causes[]}` in `lucca-core` memory only; decay τ = 600 s; hooks listed in §4; `ui.state.detail` carries it; forbidden from `RuleState`, `RouteFeatures`, and any signer. |
| Operator seed | Spec 03 §5.5 + `lucca-admin memory seed`; provenance `USER_EXPLICIT` with `asr=None`, `source="operator_seed"`, `confirmed_via="voice"`; each line requires a spoken yes; test that unconfirmed lines never reach `memories`. |
| "How are you feeling" | Intent `affect_query` → deterministic template from `AffectState`, no LLM claim of emotion. |
