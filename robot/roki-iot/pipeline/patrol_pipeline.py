"""순찰 AI 파이프라인 프로세스 관리."""

from __future__ import annotations

import os
import shlex
import signal
import subprocess
import time
from pathlib import Path


DEFAULT_PIPELINE_DIR = Path(
    "/home/e103/yolo-pipeline/yolo_pipeline"
)
DEFAULT_PYTHON = Path(
    "/home/e103/yolo-pipeline/venv/bin/python"
)


class PatrolPipelineRunner:
    """
    yolo-pipeline main.py를 subprocess로
    기동/중지한다.
    """

    def __init__(
        self,
        *,
        pipeline_dir: Path | None = None,
        python_path: Path | None = None,
        source_a: str = "0",
        source_b: str = "1",
        extra_args: str = "--no-ocr",
        start_grace_seconds: float = 8.0,
        stop_timeout_seconds: float = 60.0,
    ) -> None:
        self._pipeline_dir = (
            pipeline_dir or DEFAULT_PIPELINE_DIR
        )
        self._python_path = (
            python_path or DEFAULT_PYTHON
        )
        self._source_a = source_a
        self._source_b = source_b
        self._extra_args = extra_args
        self._start_grace_seconds = (
            start_grace_seconds
        )
        self._stop_timeout_seconds = (
            stop_timeout_seconds
        )
        self._process: subprocess.Popen[str] | None = (
            None
        )

    def is_running(self) -> bool:
        """파이프라인 프로세스가 살아 있는지 반환한다."""

        if self._process is None:
            return False

        return self._process.poll() is None

    def start(self) -> None:
        """파이프라인을 백그라운드로 시작한다."""

        if self.is_running():
            raise RuntimeError(
                "파이프라인이 이미 실행 중입니다."
            )

        if not self._python_path.exists():
            raise FileNotFoundError(
                "파이프라인 Python을 찾을 수 없습니다: "
                f"{self._python_path}"
            )

        main_py = self._pipeline_dir / "main.py"

        if not main_py.exists():
            raise FileNotFoundError(
                "main.py를 찾을 수 없습니다: "
                f"{main_py}"
            )

        video_devices = sorted(
            Path("/dev").glob("video*")
        )

        if not video_devices:
            raise RuntimeError(
                "카메라를 찾을 수 없습니다. "
                "/dev/video* 가 없습니다. "
                "USB 카메라 연결 후 다시 시도하세요."
            )

        command = [
            str(self._python_path),
            str(main_py),
            "--source-a",
            self._source_a,
            "--source-b",
            self._source_b,
        ]

        if self._extra_args.strip():
            command.extend(
                shlex.split(self._extra_args)
            )

        env = os.environ.copy()

        # Jetson 데스크톱에서 cv2.imshow 쓰려면 DISPLAY 필요
        if not env.get("DISPLAY"):
            env["DISPLAY"] = ":0"

        token_path = (
            Path(__file__).resolve().parents[1]
            / "runtime"
            / "robot_service_token"
        )

        if token_path.exists():
            env["ROBOT_SERVICE_TOKEN"] = (
                token_path.read_text(
                    encoding="utf-8"
                ).strip()
            )

        log_path = (
            self._pipeline_dir
            / "logs"
            / "patrol_pipeline_runner.log"
        )
        log_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )
        log_file = open(
            log_path,
            "a",
            encoding="utf-8",
        )

        print(
            "[PIPELINE] 실행 명령: "
            + " ".join(command)
        )
        print(
            "[PIPELINE] 감지된 카메라: "
            + ", ".join(
                str(device) for device in video_devices
            )
        )

        self._process = subprocess.Popen(
            command,
            cwd=str(self._pipeline_dir),
            env=env,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            text=True,
            start_new_session=True,
        )
        log_file.close()

        # TRT 로딩 + 카메라 open까지 기다린다.
        deadline = (
            time.monotonic()
            + self._start_grace_seconds
        )

        while time.monotonic() < deadline:
            if self._process.poll() is not None:
                exit_code = self._process.poll()
                self._process = None
                raise RuntimeError(
                    "파이프라인이 기동 직후 종료되었습니다: "
                    f"exit_code={exit_code}, "
                    f"log={log_path}"
                )

            time.sleep(0.2)

        if self._process.poll() is not None:
            exit_code = self._process.poll()
            self._process = None
            raise RuntimeError(
                "파이프라인이 기동 직후 종료되었습니다: "
                f"exit_code={exit_code}, log={log_path}"
            )

        print(
            "[PIPELINE] 시작: "
            f"pid={self._process.pid}, "
            f"log={log_path}"
        )

    def stop(self) -> None:
        """
        파이프라인에 SIGINT를 보내 정상 종료시킨다.

        main.py가 KeyboardInterrupt를 처리하면
        flush_all 경로를 탈 수 있다.
        """

        if not self.is_running():
            print("[PIPELINE] 이미 중지된 상태입니다.")
            self._process = None
            return

        assert self._process is not None

        pid = self._process.pid
        print(f"[PIPELINE] 중지 요청: pid={pid}")

        try:
            os.killpg(pid, signal.SIGINT)
        except ProcessLookupError:
            self._process = None
            return

        try:
            self._process.wait(
                timeout=self._stop_timeout_seconds
            )
        except subprocess.TimeoutExpired:
            print(
                "[PIPELINE] 정상 종료 시간 초과, "
                "SIGTERM 전송"
            )
            try:
                os.killpg(pid, signal.SIGTERM)
            except ProcessLookupError:
                pass

            try:
                self._process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                print(
                    "[PIPELINE] SIGKILL 강제 종료"
                )
                try:
                    os.killpg(pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                self._process.wait(timeout=5)

        exit_code = self._process.poll()
        self._process = None

        print(
            "[PIPELINE] 종료 완료: "
            f"exit_code={exit_code}"
        )
