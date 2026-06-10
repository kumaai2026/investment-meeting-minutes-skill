#!/usr/bin/env python3
"""Check public-domain readiness for the Kuma frontend entry."""

from __future__ import annotations

import argparse
import json
import socket
import subprocess
from typing import Any

DOMAIN = "kuma.d91.global"
LOCAL_IP = "127.0.0.1"


def run_curl(args: list[str], timeout: int = 10) -> dict[str, Any]:
    result = subprocess.run(["curl", *args], text=True, capture_output=True, timeout=timeout)
    stdout_sample = result.stdout[:4000] + ("\n...\n" + result.stdout[-4000:] if len(result.stdout) > 8000 else "")
    return {
        "ok": result.returncode == 0,
        "returncode": result.returncode,
        "stdout": stdout_sample,
        "stderr": result.stderr[-2000:],
    }


def parse_http_response(stdout: str) -> dict[str, Any]:
    header_text = stdout.split("\r\n\r\n", 1)[0]
    lines = header_text.replace("\r\n", "\n").splitlines()
    status_code = 0
    headers: dict[str, str] = {}
    if lines:
        parts = lines[0].split()
        if len(parts) >= 2 and parts[1].isdigit():
            status_code = int(parts[1])
    for line in lines[1:]:
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        headers[key.strip().lower()] = value.strip()
    return {"status_code": status_code, "headers": headers}


def probe_forced_https(domain: str, path: str) -> dict[str, Any]:
    result = run_curl(
        ["-k", "-sS", "-i", "--max-time", "5", "--resolve", f"{domain}:443:{LOCAL_IP}", f"https://{domain}{path}"]
    )
    parsed = parse_http_response(result["stdout"])
    return {**result, **parsed, "path": path}


def protected_path_checks(domain: str) -> list[dict[str, Any]]:
    checks = []
    for path, expected_status, expected_text in [
        ("/latest", 302, "/access-login"),
        ("/drafts", 302, "/access-login"),
        ("/access-users", 302, "/access-login"),
        ("/api/drafts", 401, "authentication_required"),
        ("/api/access-users", 401, "authentication_required"),
    ]:
        probe = probe_forced_https(domain, path)
        location = str((probe.get("headers") or {}).get("location") or "")
        stdout = str(probe.get("stdout") or "")
        ok = bool(probe.get("ok")) and int(probe.get("status_code") or 0) == expected_status
        if expected_status in {301, 302, 303, 307, 308}:
            ok = ok and expected_text in location
        else:
            ok = ok and expected_text in stdout
        checks.append(
            {
                "path": path,
                "ok": ok,
                "status_code": probe.get("status_code"),
                "location": location,
                "expected_status": expected_status,
            }
        )
    return checks


def dns_records(domain: str) -> list[str]:
    try:
        return sorted(set(socket.gethostbyname_ex(domain)[2]))
    except OSError:
        return []


def build_report(domain: str = DOMAIN) -> dict[str, Any]:
    records = dns_records(domain)
    check_path = "/access-login"
    local_http = run_curl(["-sS", "--max-time", "5", "-H", f"Host: {domain}", f"http://{LOCAL_IP}:81{check_path}"])
    forced_https = run_curl(
        ["-k", "-sS", "--max-time", "5", "--resolve", f"{domain}:443:{LOCAL_IP}", f"https://{domain}{check_path}"]
    )
    public_https = run_curl(["-k", "-sS", "--max-time", "8", f"https://{domain}{check_path}"])
    def login_page_ok(probe: dict[str, Any]) -> bool:
        stdout = str(probe.get("stdout") or "")
        return bool(probe.get("ok")) and ("<title>访问登录</title>" in stdout or "访问登录" in stdout)

    public_https_ok = login_page_ok(public_https)
    protected_checks = protected_path_checks(domain)
    protected_ok = all(item.get("ok") for item in protected_checks)
    return {
        "ok": bool(local_http["ok"] and forced_https["ok"] and public_https_ok and protected_ok),
        "domain": domain,
        "dns_records": records,
        "expected_local_test_ip": LOCAL_IP,
        "check_path": check_path,
        "local_http_host_header_ok": login_page_ok(local_http),
        "forced_local_https_ok": login_page_ok(forced_https),
        "public_https_ok": public_https_ok,
        "protected_paths_ok": protected_ok,
        "protected_path_checks": protected_checks,
        "public_https_error": public_https["stderr"].strip(),
        "message": (
            "公网入口可用"
            if public_https_ok and protected_ok
            else f"本机 nginx 可服务 {domain}，但公网 DNS/HTTPS 尚未打通、未指向本机入口，或返回的不是访问登录页"
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="检查 Kuma 前台公网访问就绪状态")
    parser.add_argument("--json", action="store_true", help="输出 JSON")
    parser.add_argument("--domain", default=DOMAIN, help="要检查的域名")
    args = parser.parse_args()
    report = build_report(args.domain)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(report["message"])
        print(f"DNS: {', '.join(report['dns_records']) or '-'}")
        print(f"local http host header: {report['local_http_host_header_ok']}")
        print(f"forced local https: {report['forced_local_https_ok']}")
        print(f"public https: {report['public_https_ok']}")
        print(f"protected paths: {report['protected_paths_ok']}")
        if report["public_https_error"]:
            print(report["public_https_error"])
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
