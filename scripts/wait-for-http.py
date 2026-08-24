#!/usr/bin/env python3
"""Wait until an HTTP readiness endpoint returns the expected status."""

import argparse
import time
import urllib.error
import urllib.request


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url", help="HTTP(S) endpoint to poll")
    parser.add_argument("--status", type=int, default=200, help="required HTTP status")
    parser.add_argument("--timeout", type=float, default=90, help="maximum seconds to wait")
    parser.add_argument("--interval", type=float, default=0.5, help="seconds between attempts")
    return parser.parse_args()


def wait_for_http(url, *, expected_status, timeout, interval):
    """Poll *url* until it returns *expected_status* or the deadline expires."""
    if timeout <= 0:
        raise ValueError("timeout must be greater than zero")
    if interval <= 0:
        raise ValueError("interval must be greater than zero")

    deadline = time.monotonic() + timeout
    last_failure = "no request attempted"
    request = urllib.request.Request(url, headers={"User-Agent": "MetroDrip-readiness/1"})

    while time.monotonic() < deadline:
        remaining = deadline - time.monotonic()
        try:
            with urllib.request.urlopen(request, timeout=max(0.1, min(2.0, remaining))) as response:
                if response.status == expected_status:
                    print(f"Ready: {url} returned HTTP {response.status}.")
                    return
                last_failure = f"HTTP {response.status}"
        except (OSError, urllib.error.URLError) as error:
            last_failure = str(error)
        time.sleep(min(interval, max(0, deadline - time.monotonic())))

    raise TimeoutError(
        f"Timed out after {timeout:g}s waiting for {url} to return "
        f"HTTP {expected_status}; last result: {last_failure}"
    )


def main():
    args = parse_args()
    try:
        wait_for_http(
            args.url,
            expected_status=args.status,
            timeout=args.timeout,
            interval=args.interval,
        )
    except (TimeoutError, ValueError) as error:
        raise SystemExit(str(error)) from error


if __name__ == "__main__":
    main()
