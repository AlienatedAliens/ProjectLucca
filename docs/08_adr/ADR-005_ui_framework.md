# ADR-005 — UI: PyQt6 overlay in its own process; RMS-envelope lip-sync in Phase 1

**Status:** Accepted 2026-09-17 (D-15)
**Supersedes:** docs 00/05 leaving the framework as "Pygame / PyQt6 / Raylib".

## Context

Requirements: transparent, click-through (except on the sprite), always-on-top 2D companion on Windows 11; mouth animation synced to TTS; ≤ 80 MB RAM; must never block the audio callback or the orchestrator. Kokoro's public APIs (`kokoro-onnx`) emit audio only — no phoneme timings (research 5.4).

## Decision

- **PyQt6** in a dedicated process `lucca-ui`. Window flags: `FramelessWindowHint | WindowStaysOnTopHint | Tool`, `WA_TranslucentBackground`, `WA_TransparentForMouseEvents` toggled per-pixel via a hit-mask so only the sprite is clickable. Rendering via `QPainter` on a `QOpenGLWidget` or plain `QWidget` at 30 fps max; idle at 5 fps.
- **Lip-sync Phase 1:** `lucca-audio` publishes an RMS envelope (20 ms frames) of the *played* buffer over ZMQ; `lucca-ui` maps RMS → 3 mouth states (closed < −40 dBFS, half < −25 dBFS, open) with 40 ms hysteresis. Latency from speaker to mouth ≤ 60 ms.
- **Phase 7+:** phoneme→viseme mapping using the native `kokoro` package's duration predictor (research 5.4) if acquired.
- States to render: idle, listening (PTT held), thinking (waiting first token), speaking, error/offline, confirm-prompt (WRITE/LAUNCH question).

## Consequences

- Qt adds ~50–70 MB RSS; acceptable and isolated in its own process (crash of UI ≠ crash of voice).
- No GIL sharing with the audio callback.
- PyQt6 is GPL/commercial-licensed; for a personal local-first project this is fine. If distribution is ever planned, switch to PySide6 (LGPL) — API-identical, noted as the alternative.

## Alternatives

| Option | Why not |
|---|---|
| Pygame | No native transparent/click-through window support; hacks via Win32 required. |
| Raylib (pyray) | Good perf; transparent window support exists but click-through and per-pixel hit-testing are manual; smaller ecosystem for widgets (confirm dialogs). |
| Tauri/Electron web UI | Node/Rust toolchain, 150–300 MB RSS; over budget. |
| Live2D / VRM (as Open-LLM-VTuber, Amica) | Attractive later; Phase 7+ once 2D sprite loop is proven. |
