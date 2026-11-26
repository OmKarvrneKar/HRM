"""
CaptchaService — Dynamic Server-Side CAPTCHA Generator & Verifier.

Provides cryptographically random, single-use, timed CAPTCHAs for AISamrat HRMS authentication.
Renders SVG images with noise lines, rotation, and distortion for crisp browser rendering.
Enforces strict server-side validation to prevent brute-force attacks and bypass attempts.
"""

import base64
import random
import secrets
import threading
import time
from typing import Tuple

# Disambiguated alphanumeric character set (omits confusing 0, O, 1, I, l)
CAPTCHA_CHARSET = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"


class CaptchaService:
    _captchas: dict[str, dict] = {}
    _lock = threading.Lock()
    EXPIRY_SECONDS = 300  # 5 minutes validity
    CODE_LENGTH = 5

    @classmethod
    def _clean_expired(cls) -> None:
        """Removes expired CAPTCHA entries from in-memory cache."""
        now = time.time()
        expired_keys = [k for k, v in cls._captchas.items() if now - v.get("created_at", 0) > cls.EXPIRY_SECONDS]
        for k in expired_keys:
            cls._captchas.pop(k, None)

    @classmethod
    def generate_captcha(cls) -> Tuple[str, str]:
        """
        Generates a new random CAPTCHA.
        Returns:
            (captcha_id, image_data_uri)
        """
        # 1. Generate 5-character random code
        code = "".join(secrets.choice(CAPTCHA_CHARSET) for _ in range(cls.CODE_LENGTH))
        captcha_id = secrets.token_hex(16)

        # 2. Store securely with timestamp
        with cls._lock:
            cls._clean_expired()
            cls._captchas[captcha_id] = {
                "code": code,
                "created_at": time.time(),
                "attempts": 0
            }

        # 3. Render vector SVG and convert to Data URI
        svg_content = cls._render_svg(code)
        b64_svg = base64.b64encode(svg_content.encode("utf-8")).decode("utf-8")
        data_uri = f"data:image/svg+xml;base64,{b64_svg}"

        return captcha_id, data_uri

    @classmethod
    def verify(cls, captcha_id: str | None, user_answer: str | None) -> Tuple[bool, str]:
        """
        Performs strict server-side verification.
        Single-use: CAPTCHA is consumed upon verification attempt.
        Returns (success: bool, error_message: str).
        """
        if not captcha_id or not isinstance(captcha_id, str):
            return False, "Security CAPTCHA verification is required."

        if not user_answer or not isinstance(user_answer, str) or not user_answer.strip():
            return False, "Please enter the security verification code."

        with cls._lock:
            cls._clean_expired()
            item = cls._captchas.pop(captcha_id.strip(), None)

        if not item:
            return False, "CAPTCHA expired or already used. Please click reload for a new code."

        now = time.time()
        if now - item.get("created_at", 0) > cls.EXPIRY_SECONDS:
            return False, "Security CAPTCHA has expired. Please refresh the code."

        # Case-insensitive comparison
        if user_answer.strip().upper() != item.get("code", "").upper():
            return False, "Incorrect CAPTCHA code. Please try again."

        return True, "CAPTCHA verified successfully."

    @classmethod
    def get_solution_for_testing(cls, captcha_id: str) -> str | None:
        """Helper for automated testing verification without bypassing server validation."""
        with cls._lock:
            item = cls._captchas.get(captcha_id)
            return item["code"] if item else None

    @classmethod
    def _render_svg(cls, code: str) -> str:
        """
        Generates an SVG CAPTCHA image with distortion lines, background noise,
        and individually positioned/rotated characters.
        """
        width = 110
        height = 32

        # Color palettes for character glyphs (dark contrasting corporate tones)
        char_colors = ["#0f172a", "#1e3a8a", "#0369a1", "#1e293b", "#2563eb", "#0284c7"]
        line_colors = ["#cbd5e1", "#94a3b8", "#64748b", "#38bdf8", "#60a5fa"]

        # Background gradient & subtle noise
        svg_parts = [
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
            '<defs>',
            '  <linearGradient id="cbg" x1="0%" y1="0%" x2="100%" y2="100%">',
            '    <stop offset="0%" stop-color="#f8fafc" />',
            '    <stop offset="100%" stop-color="#e2e8f0" />',
            '  </linearGradient>',
            '</defs>',
            f'<rect width="{width}" height="{height}" rx="5" fill="url(#cbg)" stroke="#cbd5e1" stroke-width="1" />'
        ]

        # 1. Random noise dots
        rng = random.Random()
        for _ in range(16):
            nx = rng.randint(3, width - 3)
            ny = rng.randint(3, height - 3)
            nr = rng.uniform(0.7, 1.8)
            op = rng.uniform(0.3, 0.65)
            dot_color = rng.choice(line_colors)
            svg_parts.append(f'<circle cx="{nx}" cy="{ny}" r="{nr:.1f}" fill="{dot_color}" opacity="{op:.2f}" />')

        # 2. Subtle interference curves
        for _ in range(2):
            y1 = rng.randint(6, height - 6)
            y2 = rng.randint(6, height - 6)
            cx = rng.randint(30, width - 30)
            cy = rng.randint(4, height - 4)
            c_stroke = rng.choice(line_colors)
            svg_parts.append(f'<path d="M 4 {y1} Q {cx} {cy} {width - 4} {y2}" stroke="{c_stroke}" stroke-width="1.2" fill="none" opacity="0.5" />')

        # 3. Individually positioned & rotated glyphs
        num_chars = len(code)
        spacing = (width - 16) / num_chars

        for i, char in enumerate(code):
            x = 10 + i * spacing + rng.uniform(-1.5, 1.5)
            y = 23 + rng.uniform(-2.0, 2.0)
            angle = rng.uniform(-14, 14)
            color = rng.choice(char_colors)
            font_size = rng.randint(18, 20)
            weight = "800" if rng.random() > 0.4 else "700"

            svg_parts.append(
                f'<text x="{x:.1f}" y="{y:.1f}" fill="{color}" '
                f'font-family="system-ui, -apple-system, monospace, \'Courier New\', sans-serif" '
                f'font-size="{font_size}" font-weight="{weight}" '
                f'transform="rotate({angle:.1f} {x:.1f} {y:.1f})">{char}</text>'
            )

        svg_parts.append('</svg>')
        return "".join(svg_parts)
