"""
Project Lucca — Event Taxonomy
Spec 11 §2 (`lucca.core.events`)
"""

from enum import StrEnum


class EventName(StrEnum):
    # Boot events
    BOOT_START = "boot.start"
    BOOT_STEP = "boot.step"
    BOOT_READY = "boot.ready"
    BOOT_FAIL = "boot.fail"

    # Turn lifecycle events
    TURN_START = "turn.start"
    TURN_PTT_PRESSED = "turn.ptt_pressed"
    TURN_PTT_RELEASED = "turn.ptt_released"
    TURN_FIRST_TOKEN = "turn.first_token"
    TURN_FIRST_SAMPLE = "turn.first_sample"
    TURN_INTERRUPTED = "turn.interrupted"
    TURN_END = "turn.end"

    # ASR events
    ASR_START = "asr.start"
    ASR_RESULT = "asr.result"
    ASR_FAIL = "asr.fail"

    # TTS events
    TTS_CHUNK_START = "tts.chunk_start"
    TTS_CHUNK_DONE = "tts.chunk_done"
    TTS_ABORT = "tts.abort"
    TTS_FAIL = "tts.fail"
    TTS_QUEUE_OVERFLOW = "tts_queue_overflow"

    # LLM events
    LLM_REQUEST = "llm.request"
    LLM_TOKEN = "llm.token"
    LLM_DONE = "llm.done"
    LLM_ABORT = "llm.abort"
    LLM_FAIL = "llm.fail"

    # Memory events
    MEM_COMMIT = "mem.commit"
    MEM_REJECT = "mem.reject"
    MEM_SEARCH = "mem.search"
    MEM_SUPERSEDE = "mem.supersede"
    MEM_FORGET = "mem.forget"

    # Rule events
    RULE_EVAL = "rule.eval"
    RULE_FIRED = "rule.fired"
    RULE_PROMOTED = "rule.promoted"
    RULE_DEMOTED = "rule.demoted"

    # Router events
    ROUTER_DECIDE = "router.decide"
    ROUTER_FALLBACK = "router.fallback"
    ROUTER_LABEL = "router.label"

    # Sandbox events
    SBX_EXEC_START = "sbx.exec_start"
    SBX_EXEC_DONE = "sbx.exec_done"
    SBX_RESET = "sbx.reset"
    SBX_FAIL = "sbx.fail"

    # UI events
    UI_STATE = "ui.state"
    UI_CONFIRM = "ui.confirm"
    UI_CONFIRM_RESULT = "ui.confirm_result"
    UI_CAPTION = "ui.caption"

    # System events
    SYS_PING = "sys.ping"
    SYS_PONG = "sys.pong"
    SYS_DEGRADED = "sys.degraded"
    SYS_RESTART = "sys.restart"
