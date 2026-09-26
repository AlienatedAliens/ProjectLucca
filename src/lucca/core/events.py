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

    # Audio & Hardware wire events
    AUDIO_FIRST_SAMPLE_PLAYED = "audio.first_sample_played"
    AUDIO_RMS = "audio.rms"
    AUDIO_PLAYBACK_DONE = "audio.playback_done"
    AUDIO_UNDERRUN = "audio.underrun"

    # Audio playback ctl events
    PLAY_BEGIN = "play.begin"
    PLAY_ABORT = "play.abort"

    # PTT wire events
    PTT_PRESSED = "ptt.pressed"
    PTT_RELEASED = "ptt.released"

    # TTS events
    TTS_CHUNK_START = "tts.chunk_start"
    TTS_CHUNK_DONE = "tts.chunk_done"
    TTS_DONE = "tts.done"
    TTS_ABORT = "tts.abort"
    TTS_ABORTED = "tts.aborted"
    TTS_FAIL = "tts.fail"
    TTS_QUEUE_OVERFLOW = "tts_queue_overflow"

    # NPU / Inference events
    EMBED_RESULT = "embed.result"
    INTENT_RESULT = "intent.result"

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
    UI_USER_TEXT = "ui.user_text"
    UI_CONFIG_UPDATE = "ui.config_update"
    UI_TALK_PRESS = "ui.talk_press"
    UI_TALK_RELEASE = "ui.talk_release"
    UI_QUIT = "ui.quit"

    # System events
    SYS_PING = "sys.ping"
    SYS_PONG = "sys.pong"
    SYS_DEGRADED = "sys.degraded"
    SYS_RESTART = "sys.restart"
    SYS_SHUTDOWN = "sys.shutdown"
    SYS_SELFTEST_RESULT = "sys.selftest_result"


VALID_EVENT_PREFIXES: frozenset[str] = frozenset({
    "boot",
    "turn",
    "asr",
    "audio",
    "play",
    "ptt",
    "tts",
    "embed",
    "intent",
    "llm",
    "mem",
    "rule",
    "router",
    "sbx",
    "ui",
    "sys",
    "test",
})


def is_valid_event_name(name: str) -> bool:
    """Checks whether an event name belongs to EventName enum or has a valid taxonomy prefix."""
    try:
        EventName(name)
        return True
    except ValueError:
        prefix = name.split(".")[0] if "." in name else name
        return prefix in VALID_EVENT_PREFIXES


def validate_event_name(name: str) -> EventName:
    """Validates and coerces string to an EventName enum member."""
    return EventName(name)
