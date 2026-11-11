import re
from datetime import datetime
import random

from log_generator import build_event, format_event

LOG_RE = re.compile(
    r'^(?P<ip>\d{1,3}(?:\.\d{1,3}){3}) - - '
    r'\[(?P<ts>\d{2}/[A-Z][a-z]{2}/\d{4}:\d{2}:\d{2}:\d{2} [+-]\d{4})\] '
    r'"(?P<method>[A-Z]+) (?P<path>\S+) HTTP/(?P<version>\d(?:\.\d)?)" '
    r'(?P<status>\d{3}) (?P<size>\d+|-) '
    r'"(?P<referrer>[^"]*)" "(?P<ua>[^"]*)"'
    r'(?: (?P<response_time>\d+))?$'
)

def test_all_modes_emit_contract_compatible_lines():
    rng = random.Random(42)

    for mode in ["normal", "4xx-spike", "5xx-spike", "slow-response", "mixed"]:
        for _ in range(100):
            event = build_event(
                mode=mode,
                rng=rng,
                dash_size_rate=0.20,
                dash_referrer_rate=0.30,
                omit_response_time_rate=0.10,
            )
            line = format_event(event)
            match = LOG_RE.match(line)
            assert match, line

            # Validate timestamp shape and English month abbreviation.
            datetime.strptime(match.group("ts"), "%d/%b/%Y:%H:%M:%S %z")

            # Values are synthetic documentation ranges only.
            assert match.group("ip").startswith(("192.0.2.", "198.51.100.", "203.0.113."))

def test_dash_cases_exist():
    rng = random.Random(1)
    lines = []
    for _ in range(100):
        event = build_event(
            mode="mixed",
            rng=rng,
            dash_size_rate=0.50,
            dash_referrer_rate=0.50,
            omit_response_time_rate=0.00,
        )
        lines.append(format_event(event))

    assert any(re.search(r' \d{3} - "', line) for line in lines)
    assert any('" - "' in line or '"-"' in line for line in lines)
