import base64
import json
import random
import secrets
import string
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import quote

GAME1_URL = "https://gameforge.com/tra/game1.js"

CONSTANT_VERSION = 11
BLACKBOX_PREFIX = "tra:"

TIMEZONE = "Europe/Madrid"
LANGUAGES = "es"

WINDOWS_CHROME_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/108.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/112.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/109.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 6.1; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/86.0.4240.198 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/106.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/105.0.0.0 Safari/537.36",
]

MAC_CHROME_USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/109.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/108.0.0.0 Safari/537.36",
]

WINDOWS_WEBGL = [
    "Google Inc. (NVIDIA),ANGLE (NVIDIA, NVIDIA GeForce GTX 1060 Direct3D11 vs_5_0 ps_5_0, D3D11)",
    "Google Inc. (Intel),ANGLE (Intel, Intel(R) HD Graphics 530 Direct3D11 vs_5_0 ps_5_0, D3D11)",
    "Google Inc. (AMD),ANGLE (AMD, Radeon RX 580 Series Direct3D11 vs_5_0 ps_5_0, D3D11)",
    "Google Inc. (AMD),ANGLE (AMD, Radeon (TM) RX 480 Graphics Direct3D11 vs_5_0 ps_5_0, D3D11)",
    "Google Inc. (NVIDIA),ANGLE (NVIDIA, NVIDIA GeForce RTX 3090 Direct3D11 vs_5_0 ps_5_0, D3D11)",
    "Google Inc. (NVIDIA),ANGLE (NVIDIA, NVIDIA GeForce GTX 1080 Direct3D11 vs_5_0 ps_5_0, D3D11)",
    "Google Inc. (AMD),ANGLE (AMD, AMD Radeon(TM) Vega 8 Graphics Direct3D11 vs_5_0 ps_5_0, D3D11)",
    "Google Inc. (Intel),ANGLE (Intel, Intel(R) UHD Graphics Direct3D11 vs_5_0 ps_5_0, D3D11)",
    "Google Inc. (NVIDIA),ANGLE (NVIDIA, NVIDIA GeForce RTX 3060 Ti Direct3D11 vs_5_0 ps_5_0, D3D11)",
    "Google Inc. (Intel),ANGLE (Intel, Intel(R) HD Graphics Family Direct3D11 vs_5_0 ps_5_0, D3D11)",
]

MAC_WEBGL = [
    "Google Inc. (Apple),ANGLE (Apple, ANGLE Metal Renderer: Apple M1, Unspecified Version)",
    "Google Inc. (Apple),ANGLE (Apple, ANGLE Metal Renderer: Apple M2, Unspecified Version)",
    "Google Inc. (Intel),ANGLE (Intel, Intel(R) Iris(TM) Plus Graphics 655, OpenGL 4.1)",
    "Google Inc. (Apple),ANGLE (Apple, ANGLE Metal Renderer: Apple M1 Pro, Unspecified Version)",
]

WINDOWS_SCREENS = [
    (2560, 1080), (1920, 1050), (1366, 738), (1680, 1010), (1280, 672),
    (1920, 1040), (1858, 1080), (3840, 1032), (1440, 860), (1920, 1160),
    (1280, 680), (1920, 1080), (1536, 834), (1304, 768), (1366, 736),
    (3440, 1440), (3153, 1276), (1504, 955), (1360, 720), (1280, 720),
    (1440, 870), (2560, 1392), (1920, 1032), (1366, 728), (1280, 920),
    (1600, 900), (1280, 728), (2560, 1400), (3440, 1392), (2195, 1235),
    (1536, 864), (1280, 994), (2560, 1080), (1600, 860), (1536, 824),
    (1366, 768), (2560, 1032), (2560, 1410),
]

MAC_SCREENS = [
    (1800, 1070), (1440, 875), (1680, 951), (1680, 967), (1440, 803),
    (2560, 1322), (1920, 1080), (2560, 1440), (1710, 1112), (2056, 1329),
]

WINDOWS_HARDWARE = [2, 3, 6, 8, 12, 16, 24]
MAC_HARDWARE = [4, 8, 12]

PSEUDO_B64_CHARS = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_="


def random_user_agent():
    return random.choice(WINDOWS_CHROME_USER_AGENTS + MAC_CHROME_USER_AGENTS)


def _profile_for(user_agent):
    if "Macintosh" in user_agent:
        return {
            "os_name": "Mac OS X",
            "os_version": "10_15_7",
            "memory": 8,
            "hardware": MAC_HARDWARE,
            "screens": MAC_SCREENS,
            "webgl": MAC_WEBGL,
        }
    return {
        "os_name": "Windows",
        "os_version": "7" if "NT 6.1" in user_agent else "10",
        "memory": 8,
        "hardware": WINDOWS_HARDWARE,
        "screens": WINDOWS_SCREENS,
        "webgl": WINDOWS_WEBGL,
    }


def _rand_char():
    return chr(32 + int(random.random() * 94))


def _base36(value):
    digits = string.digits + string.ascii_lowercase
    if value == 0:
        return "0"
    out = ""
    while value:
        value, rem = divmod(value, 36)
        out = digits[rem] + out
    return out


def _gen_27_rand_chars(blocks=3):
    out = ""
    for _ in range(blocks):
        out += _base36(random.getrandbits(64))[:9]
    return out.lower()


def _rand_fake_hash():
    return secrets.token_hex(32)


def _js_iso(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%S") + ".%03dZ" % (dt.microsecond // 1000)


def get_game1_js(session):
    before = time.monotonic()
    resp = session.get(GAME1_URL, timeout=30)
    elapsed = int((time.monotonic() - before) * 1000)
    if resp.status_code != 200:
        raise RuntimeError(f"game1.js status {resp.status_code}")
    date_header = resp.headers.get("date")
    parsed = parsedate_to_datetime(date_header).astimezone(timezone.utc)
    return _js_iso(parsed), elapsed


def build_fingerprint(user_agent, game1_date_iso, calc_delta_ms):
    profile = _profile_for(user_agent)
    x_vec = "".join(_rand_char() for _ in range(100)) + " " + str(int(time.time() * 1000))
    arr = [
        CONSTANT_VERSION,
        TIMEZONE,
        profile["os_name"],
        "Chrome",
        "Google Inc.",
        profile["memory"],
        random.choice(profile["hardware"]),
        LANGUAGES,
        _rand_fake_hash(),
        random.choice(profile["webgl"]),
        _rand_fake_hash(),
        _rand_fake_hash(),
        random.choice(profile["screens"])[0],
        random.choice(profile["screens"])[1],
        _rand_fake_hash(),
        _rand_fake_hash(),
        _rand_fake_hash(),
        _rand_fake_hash(),
        round(random.uniform(123.8, 124.9), 4),
        _rand_fake_hash(),
        random.randint(261334512, 1902830807),
        _js_iso(datetime.now(timezone.utc)),
        _gen_27_rand_chars(3),
        calc_delta_ms,
        profile["os_version"],
        base64.b64encode(x_vec.encode()).decode(),
        user_agent,
        game1_date_iso,
        None,
    ]
    return json.dumps(arr, separators=(",", ":"))


def encrypt_blackbox(raw):
    escaped = quote(raw, safe="").replace("%20", "+")
    data = escaped.encode("utf-8")
    sb = bytearray(len(data))
    sb[0] = data[0]
    for i in range(1, len(data)):
        sb[i] = (sb[i - 1] + data[i]) & 0xFF
    extra_padding = (3 - len(sb) % 3) % 3
    padded = bytes(sb) + b"\x00" * extra_padding
    out = []
    mask = 0b111111
    for i in range(0, len(padded), 3):
        packed = padded[i] << 16 | padded[i + 1] << 8 | padded[i + 2]
        out.append(PSEUDO_B64_CHARS[(packed >> 18) & mask])
        out.append(PSEUDO_B64_CHARS[(packed >> 12) & mask])
        out.append(PSEUDO_B64_CHARS[(packed >> 6) & mask])
        out.append(PSEUDO_B64_CHARS[packed & mask])
    return "".join(out)[: len(out) - extra_padding]


def generate_blackbox(session, user_agent):
    game1_date_iso, elapsed = get_game1_js(session)
    fingerprint = build_fingerprint(user_agent, game1_date_iso, elapsed)
    return BLACKBOX_PREFIX + encrypt_blackbox(fingerprint)
