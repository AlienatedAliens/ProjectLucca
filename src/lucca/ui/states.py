"""
Project Lucca — Avatar Visual States & Themes
Spec 01 §1, ADR-005
"""

from typing import NamedTuple


class AvatarTheme(NamedTuple):
    primary_color: str
    glow_color: str
    eye_color: str
    mouth_color: str
    pulse_speed: float


THEMES: dict[str, AvatarTheme] = {
    "idle": AvatarTheme(
        primary_color="#6366F1",  # Indigo
        glow_color="#818CF8",
        eye_color="#FFFFFF",
        mouth_color="#4F46E5",
        pulse_speed=0.03,
    ),
    "listening": AvatarTheme(
        primary_color="#06B6D4",  # Cyan
        glow_color="#22D3EE",
        eye_color="#FFFFFF",
        mouth_color="#0891B2",
        pulse_speed=0.08,
    ),
    "thinking": AvatarTheme(
        primary_color="#F59E0B",  # Amber/Gold
        glow_color="#FBBF24",
        eye_color="#FFFFFF",
        mouth_color="#D97706",
        pulse_speed=0.12,
    ),
    "speaking": AvatarTheme(
        primary_color="#10B981",  # Emerald Green
        glow_color="#34D399",
        eye_color="#FFFFFF",
        mouth_color="#059669",
        pulse_speed=0.05,
    ),
    "confirm": AvatarTheme(
        primary_color="#EF4444",  # Rose/Red
        glow_color="#F87171",
        eye_color="#FFFFFF",
        mouth_color="#DC2626",
        pulse_speed=0.15,
    ),
    "offline": AvatarTheme(
        primary_color="#64748B",  # Slate Gray
        glow_color="#94A3B8",
        eye_color="#CBD5E1",
        mouth_color="#475569",
        pulse_speed=0.01,
    ),
    "degraded": AvatarTheme(
        primary_color="#854D0E",  # Dark Yellow
        glow_color="#A16207",
        eye_color="#FEF08A",
        mouth_color="#713F12",
        pulse_speed=0.04,
    ),
    "epistemic_verified": AvatarTheme(
        primary_color="#0284C7",  # Sky Blue / Sapphire
        glow_color="#38BDF8",
        eye_color="#FFFFFF",
        mouth_color="#0369A1",
        pulse_speed=0.07,
    ),
    "epistemic_speculation": AvatarTheme(
        primary_color="#7C3AED",  # Violet
        glow_color="#A78BFA",
        eye_color="#EDE9FE",
        mouth_color="#6D28D9",
        pulse_speed=0.035,
    ),
}


def get_epistemic_theme(epistemic_status: str) -> AvatarTheme:
    """Returns visual avatar sprite theme mapped to verified epistemic status (Milestone 36.4)."""
    if epistemic_status == "CHECKED_FORMALIZATION_AGREED":
        return THEMES["epistemic_verified"]
    if epistemic_status == "SPECULATION":
        return THEMES["epistemic_speculation"]
    return THEMES["speaking"]
