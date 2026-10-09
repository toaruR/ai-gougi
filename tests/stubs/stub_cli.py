"""受入テスト用 stub CLI。環境変数 STUB_MODE で挙動を切替える。

modes: echo_stdin / exit1 / sleep / bytes_ff / record_argv / print_cwd
STUB_SLEEP_SEC: sleep 秒数, STUB_ARGV_FILE: record_argv の出力先JSON。
未知の STUB_MODE は終了コード2。
"""
import json
import os
import sys
import time


def main() -> int:
    mode = os.environ.get("STUB_MODE", "echo_stdin")
    out = sys.stdout.buffer
    if mode == "echo_stdin":
        out.write(sys.stdin.buffer.read())
        out.flush()
        return 0
    if mode == "exit1":
        sys.stderr.write("stub failure\n")
        return 1
    if mode == "sleep":
        time.sleep(float(os.environ.get("STUB_SLEEP_SEC", "1")))
        return 0
    if mode == "bytes_ff":
        out.write(b"ok\xff\xfe\n")
        out.flush()
        return 0
    if mode == "record_argv":
        path = os.environ.get("STUB_ARGV_FILE")
        if path:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(sys.argv[1:], f, ensure_ascii=False)
        return 0
    if mode == "print_cwd":
        out.write(os.getcwd().encode("utf-8"))
        out.flush()
        return 0
    sys.stderr.write(f"unknown STUB_MODE: {mode}\n")
    return 2


if __name__ == "__main__":
    sys.exit(main())
