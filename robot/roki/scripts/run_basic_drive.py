#!/usr/bin/env python3
"""이전 실행 경로 호환용. 운영 Runtime을 실행한다."""

from run_runtime import main


if __name__ == "__main__":
    raise SystemExit(main())
