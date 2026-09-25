import asyncio
import sys
from vartalap.session import run_one_time_login

if __name__ == "__main__":
    state_path = sys.argv[1] if len(sys.argv) > 1 else None
    asyncio.run(run_one_time_login(storage_state_path=state_path))
