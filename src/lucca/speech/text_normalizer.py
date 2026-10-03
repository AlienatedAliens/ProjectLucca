"""
Project Lucca — Advanced Text Normalizer for Speech Synthesis (KittenTTS Pipeline)
Spec 07 §5, WO-30

Provides comprehensive text normalization handling:
- Currencies ($, €, £, ¥, with dollars, cents, pounds, pence)
- Dates (ISO 2026-10-03, 10/03/2026, Oct 3, 2026)
- Times (10:30 PM, 21:40, 9:15 AM)
- Percentages (99.5%, -0.2%)
- Ordinals (1st, 2nd, 3rd, 42nd)
- Numbers with commas & decimals (1,250, 3.1415)
- Abbreviations (Dr., Mr., Mrs., Ms., approx., e.g., i.e., etc., vs.)
- Tech acronyms and units (CPU, GPU, NPU, VRAM, RAM, GB, MB, KB, ms, fps, kHz, GHz)
"""

from __future__ import annotations

import re

# Small numbers 0-19
_ONES = [
    "zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine",
    "ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen",
    "seventeen", "eighteen", "nineteen"
]

# Tens 20-90
_TENS = ["", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety"]

# Ordinals 1st-19th
_ORDINALS_ONES = [
    "zeroth", "first", "second", "third", "fourth", "fifth", "sixth", "seventh", "eighth",
    "ninth", "tenth", "eleventh", "twelfth", "thirteenth", "fourteenth", "fifteenth",
    "sixteenth", "seventeenth", "eighteenth", "nineteenth"
]

_ORDINALS_TENS = [
    "", "", "twentieth", "thirtieth", "fortieth", "fiftieth", "sixtieth",
    "seventieth", "eightieth", "ninetieth"
]

_MONTHS = {
    1: "January", 2: "February", 3: "March", 4: "April", 5: "May", 6: "June",
    7: "July", 8: "August", 9: "September", 10: "October", 11: "November", 12: "December"
}

_MONTH_NAMES = {
    "jan": "January", "january": "January",
    "feb": "February", "february": "February",
    "mar": "March", "march": "March",
    "apr": "April", "april": "April",
    "may": "May",
    "jun": "June", "june": "June",
    "jul": "July", "july": "July",
    "aug": "August", "august": "August",
    "sep": "September", "sept": "September", "september": "September",
    "oct": "October", "october": "October",
    "nov": "November", "november": "November",
    "dec": "December", "december": "December",
}


def num_to_words(n: int) -> str:
    """Converts an integer (up to 999,999,999,999) to English words."""
    if n < 0:
        return f"negative {num_to_words(-n)}"
    if n < 20:
        return _ONES[n]
    if n < 100:
        ten, rem = divmod(n, 10)
        return f"{_TENS[ten]}-{_ONES[rem]}" if rem else _TENS[ten]
    if n < 1000:
        hundred, rem = divmod(n, 100)
        res = f"{_ONES[hundred]} hundred"
        return f"{res} {num_to_words(rem)}" if rem else res
    if n < 1_000_000:
        thousand, rem = divmod(n, 1000)
        res = f"{num_to_words(thousand)} thousand"
        return f"{res} {num_to_words(rem)}" if rem else res
    if n < 1_000_000_000:
        million, rem = divmod(n, 1_000_000)
        res = f"{num_to_words(million)} million"
        return f"{res} {num_to_words(rem)}" if rem else res
    if n < 1_000_000_000_000:
        billion, rem = divmod(n, 1_000_000_000)
        res = f"{num_to_words(billion)} billion"
        return f"{res} {num_to_words(rem)}" if rem else res
    return str(n)


def num_to_ordinal(n: int) -> str:
    """Converts an integer to English ordinal words (e.g. 1 -> first, 42 -> forty-second)."""
    if n < 0:
        return f"negative {num_to_ordinal(-n)}"
    if n < 20:
        return _ORDINALS_ONES[n]
    if n < 100:
        ten, rem = divmod(n, 10)
        if rem == 0:
            return _ORDINALS_TENS[ten]
        return f"{_TENS[ten]}-{_ORDINALS_ONES[rem]}"
    cardinal = num_to_words(n)
    # Replace terminal word with ordinal
    words = cardinal.split()
    last = words[-1]
    if "-" in last:
        prefix, sub = last.rsplit("-", 1)
        sub_ord = _ORDINALS_ONES[_ONES.index(sub)] if sub in _ONES else sub + "th"
        words[-1] = f"{prefix}-{sub_ord}"
    elif last in _ONES:
        words[-1] = _ORDINALS_ONES[_ONES.index(last)]
    elif last.endswith("y"):
        words[-1] = last[:-1] + "ieth"
    elif last.endswith("hundred") or last.endswith("thousand") or last.endswith("million") or last.endswith("billion"):
        words[-1] = last + "th"
    return " ".join(words)


def year_to_words(year: int) -> str:
    """Formats years naturally (e.g. 2026 -> twenty twenty-six, 1999 -> nineteen ninety-nine)."""
    if 2000 <= year <= 2009:
        return f"two thousand {num_to_words(year - 2000)}" if year > 2000 else "two thousand"
    if 1000 <= year <= 2999:
        century = year // 100
        rem = year % 100
        century_words = num_to_words(century)
        if rem == 0:
            return f"{century_words} hundred"
        rem_words = f"oh-{_ONES[rem]}" if rem < 10 else num_to_words(rem)
        return f"{century_words} {rem_words}"
    return num_to_words(year)


class KittenTextNormalizer:
    """
    Robust text normalization pipeline designed for KittenTTS ONNX CPU synthesis.
    Eliminates pronunciation glitches across currency, dates, numbers, and tech abbreviations.
    """

    # Static abbreviation mapping
    ABBREVIATIONS: dict[str, str] = {
        r"\bDr\.(?=\s|[.,!?;:]|$)": "Doctor",
        r"\bMr\.(?=\s|[.,!?;:]|$)": "Mister",
        r"\bMrs\.(?=\s|[.,!?;:]|$)": "Missus",
        r"\bMs\.(?=\s|[.,!?;:]|$)": "Miz",
        r"\bProf\.(?=\s|[.,!?;:]|$)": "Professor",
        r"\be\.g\.(?=\s|[.,!?;:]|$)": "for example",
        r"\bi\.e\.(?=\s|[.,!?;:]|$)": "that is",
        r"\betc\.(?=\s|[.,!?;:]|$)": "etcetera",
        r"\bvs\.(?=\s|[.,!?;:]|$)": "versus",
        r"\bapprox\.(?=\s|[.,!?;:]|$)": "approximately",
        r"\bdept\.(?=\s|[.,!?;:]|$)": "department",
        r"\bavg\.(?=\s|[.,!?;:]|$)": "average",
        r"\bmin\.(?=\s|[.,!?;:]|$)": "minutes",
        r"\bsec\.(?=\s|[.,!?;:]|$)": "seconds",
        r"\bhr\.(?=\s|[.,!?;:]|$)": "hour",
        r"\bhrs\.(?=\s|[.,!?;:]|$)": "hours",
        r"\bno\.(?=\s|[.,!?;:]|$)": "number",
        r"\bvol\.(?=\s|[.,!?;:]|$)": "volume",
        r"\best\.(?=\s|[.,!?;:]|$)": "estimated",
    }

    # Tech acronyms & units to expand or space for clean phoneme pronunciation
    TECH_TERMS: dict[str, str] = {
        r"\bCPU\b": "C P U",
        r"\bGPU\b": "G P U",
        r"\bNPU\b": "N P U",
        r"\bVRAM\b": "V-RAM",
        r"\bRAM\b": "ram",
        r"\bONNX\b": "on-nix",
        r"\bTTS\b": "T T S",
        r"\bASR\b": "A S R",
        r"\bLLM\b": "L L M",
        r"\bGGUF\b": "G-G-U-F",
        r"\bIPC\b": "I P C",
        r"\bUI\b": "U I",
        r"\bCLI\b": "C L I",
        r"\bAPI\b": "A P I",
        r"\bSDK\b": "S D K",
        r"\bURL\b": "U R L",
        r"\bJSON\b": "jay-son",
        r"\bJSONL\b": "jay-son-L",
    }

    UNITS: list[tuple[str, str, str]] = [
        (r"(\d+(?:\.\d+)?)\s*GB\b", "gigabyte", "gigabytes"),
        (r"(\d+(?:\.\d+)?)\s*MB\b", "megabyte", "megabytes"),
        (r"(\d+(?:\.\d+)?)\s*KB\b", "kilobyte", "kilobytes"),
        (r"(\d+(?:\.\d+)?)\s*TB\b", "terabyte", "terabytes"),
        (r"(\d+(?:\.\d+)?)\s*ms\b", "millisecond", "milliseconds"),
        (r"(\d+(?:\.\d+)?)\s*s\b", "second", "seconds"),
        (r"(\d+(?:\.\d+)?)\s*fps\b", "frame per second", "frames per second"),
        (r"(\d+(?:\.\d+)?)\s*kHz\b", "kilohertz", "kilohertz"),
        (r"(\d+(?:\.\d+)?)\s*MHz\b", "megahertz", "megahertz"),
        (r"(\d+(?:\.\d+)?)\s*GHz\b", "gigahertz", "gigahertz"),
        (r"(\d+(?:\.\d+)?)\s*km/h\b", "kilometer per hour", "kilometers per hour"),
    ]

    def normalize(self, text: str) -> str:
        """Applies complete normalization pipeline to text string."""
        if not text or not text.strip():
            return text

        # Skip raw code blocks
        if "```" in text:
            return text

        out = text

        # 1. Abbreviations
        for pattern, repl in self.ABBREVIATIONS.items():
            out = re.sub(pattern, repl, out, flags=re.IGNORECASE)

        # 2. Currency ($19.99, €50, £12.50, ¥1000)
        out = self._normalize_currency(out)

        # 3. Percentages (99.5%, -10%)
        out = self._normalize_percentages(out)

        # 4. Dates (2026-10-03, 10/03/2026, Oct 3, 2026)
        out = self._normalize_dates(out)

        # 5. Times (10:30 PM, 21:40)
        out = self._normalize_times(out)

        # 6. Units (16 GB, 24000 Hz, 60 ms)
        out = self._normalize_units(out)

        # 7. Ordinals (1st, 2nd, 3rd, 42nd)
        out = self._normalize_ordinals(out)

        # 8. Large numbers with commas and decimals (1,250, 3.14)
        out = self._normalize_numbers(out)

        # 9. Tech Acronyms
        for pattern, repl in self.TECH_TERMS.items():
            out = re.sub(pattern, repl, out)

        return out

    def _normalize_currency(self, text: str) -> str:
        # USD $
        def repl_usd(match: re.Match) -> str:
            val_str = match.group(1).replace(",", "")
            if "." in val_str:
                dollars, cents = val_str.split(".", 1)
                d_int = int(dollars) if dollars else 0
                c_int = int(cents[:2]) if cents else 0
                d_word = num_to_words(d_int)
                c_word = num_to_words(c_int)
                d_unit = "dollar" if d_int == 1 else "dollars"
                c_unit = "cent" if c_int == 1 else "cents"
                if d_int > 0 and c_int > 0:
                    return f"{d_word} {d_unit} and {c_word} {c_unit}"
                elif d_int > 0:
                    return f"{d_word} {d_unit}"
                else:
                    return f"{c_word} {c_unit}"
            else:
                d_int = int(val_str)
                d_unit = "dollar" if d_int == 1 else "dollars"
                return f"{num_to_words(d_int)} {d_unit}"

        text = re.sub(r"\$(\d{1,3}(?:,\d{3})*(?:\.\d{1,2})?|\d+(?:\.\d{1,2})?)", repl_usd, text)

        # EUR €
        def repl_eur(match: re.Match) -> str:
            val_str = match.group(1).replace(",", "")
            if "." in val_str:
                euros, cents = val_str.split(".", 1)
                e_int = int(euros) if euros else 0
                c_int = int(cents[:2]) if cents else 0
                return f"{num_to_words(e_int)} euros and {num_to_words(c_int)} cents"
            return f"{num_to_words(int(val_str))} euros"

        text = re.sub(r"€(\d{1,3}(?:,\d{3})*(?:\.\d{1,2})?|\d+(?:\.\d{1,2})?)", repl_eur, text)

        # GBP £
        def repl_gbp(match: re.Match) -> str:
            val_str = match.group(1).replace(",", "")
            if "." in val_str:
                pounds, pence = val_str.split(".", 1)
                p_int = int(pounds) if pounds else 0
                c_int = int(pence[:2]) if pence else 0
                p_unit = "pound" if p_int == 1 else "pounds"
                return f"{num_to_words(p_int)} {p_unit} and {num_to_words(c_int)} pence"
            p_int = int(val_str)
            p_unit = "pound" if p_int == 1 else "pounds"
            return f"{num_to_words(p_int)} {p_unit}"

        text = re.sub(r"£(\d{1,3}(?:,\d{3})*(?:\.\d{1,2})?|\d+(?:\.\d{1,2})?)", repl_gbp, text)

        # YEN ¥
        def repl_yen(match: re.Match) -> str:
            val_str = match.group(1).replace(",", "")
            return f"{num_to_words(int(float(val_str)))} yen"

        text = re.sub(r"¥(\d{1,3}(?:,\d{3})*|\d+)", repl_yen, text)
        return text

    def _normalize_percentages(self, text: str) -> str:
        def repl_pct(match: re.Match) -> str:
            num = match.group(1)
            if "." in num:
                whole, dec = num.split(".", 1)
                w_words = num_to_words(int(whole))
                d_words = " ".join(_ONES[int(digit)] for digit in dec)
                return f"{w_words} point {d_words} percent"
            return f"{num_to_words(int(num))} percent"

        return re.sub(r"(\b\d+(?:\.\d+)?)%", repl_pct, text)

    def _normalize_dates(self, text: str) -> str:
        # ISO format: YYYY-MM-DD
        def repl_iso(match: re.Match) -> str:
            y, m, d = int(match.group(1)), int(match.group(2)), int(match.group(3))
            m_name = _MONTHS.get(m, "")
            if m_name and 1 <= d <= 31:
                return f"{m_name} {num_to_ordinal(d)}, {year_to_words(y)}"
            return match.group(0)

        text = re.sub(r"\b(\d{4})-(\d{2})-(\d{2})\b", repl_iso, text)

        # Named month date: Oct 3, 2026 or October 3, 2026
        def repl_named(match: re.Match) -> str:
            m_str, d, y = match.group(1).lower(), int(match.group(2)), int(match.group(3))
            m_name = _MONTH_NAMES.get(m_str)
            if m_name and 1 <= d <= 31:
                return f"{m_name} {num_to_ordinal(d)}, {year_to_words(y)}"
            return match.group(0)

        text = re.sub(
            r"\b([A-Za-z]+)\s+(\d{1,2}),\s*(\d{4})\b",
            repl_named,
            text,
        )
        return text

    def _normalize_times(self, text: str) -> str:
        def repl_time(match: re.Match) -> str:
            h, m, ampm = int(match.group(1)), int(match.group(2)), match.group(3)
            h_words = num_to_words(h)
            if m == 0:
                m_words = "o'clock" if not ampm else ""
            elif m < 10:
                m_words = f"oh-{_ONES[m]}"
            else:
                m_words = num_to_words(m)
            ampm_str = f" {ampm.upper()}" if ampm else ""
            res = f"{h_words} {m_words}".strip()
            return f"{res}{ampm_str}"

        return re.sub(r"\b(\d{1,2}):(\d{2})(?:\s*(am|pm|AM|PM))?\b", repl_time, text)

    def _normalize_units(self, text: str) -> str:
        out = text
        for pattern, singular, plural in self.UNITS:
            def repl(match: re.Match) -> str:
                val = match.group(1)
                num_f = float(val)
                unit_str = singular if num_f == 1.0 else plural
                if "." in val:
                    whole, dec = val.split(".", 1)
                    w_words = num_to_words(int(whole))
                    d_words = " ".join(_ONES[int(digit)] for digit in dec)
                    return f"{w_words} point {d_words} {unit_str}"
                return f"{num_to_words(int(val))} {unit_str}"

            out = re.sub(pattern, repl, out, flags=re.IGNORECASE)
        return out

    def _normalize_ordinals(self, text: str) -> str:
        def repl_ord(match: re.Match) -> str:
            n = int(match.group(1))
            return num_to_ordinal(n)

        return re.sub(r"\b(\d+)(?:st|nd|rd|th)\b", repl_ord, text)

    def _normalize_numbers(self, text: str) -> str:
        # Numbers with commas: 1,250
        def repl_comma(match: re.Match) -> str:
            cleaned = match.group(0).replace(",", "")
            return num_to_words(int(cleaned))

        text = re.sub(r"\b\d{1,3}(?:,\d{3})+\b", repl_comma, text)

        # Standalone decimals: 3.14
        def repl_dec(match: re.Match) -> str:
            whole, dec = match.group(1), match.group(2)
            w_words = num_to_words(int(whole))
            d_words = " ".join(_ONES[int(digit)] for digit in dec)
            return f"{w_words} point {d_words}"

        text = re.sub(r"\b(\d+)\.(\d+)\b", repl_dec, text)
        return text


_NORMALIZER = KittenTextNormalizer()


def normalize_text(text: str) -> str:
    """Convenience helper to apply KittenTTS text normalization."""
    return _NORMALIZER.normalize(text)
