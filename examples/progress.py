"""A slow tool that reports progress and stops when the client cancels it.

Ask Claude: "count to 20 slowly", then press Esc (Claude Code) or Stop.
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mimimalmcp import Context, Server  # noqa: E402

server = Server("progress-demo")


@server.tool()
def slow_count(to: int, ctx: Context, seconds_per_step: float = 0.5) -> str:
    """Count from 1 to `to`, one step at a time, reporting progress."""
    for i in range(1, to + 1):
        if ctx.cancelled:           # or ctx.check_cancelled(), which raises
            ctx.log(f"stopped at {i}")
            return f"Stopped at {i}."
        ctx.progress(i, total=to, message=f"counted {i} of {to}")
        time.sleep(seconds_per_step)
    return f"Counted to {to}."


if __name__ == "__main__":
    server.run()
