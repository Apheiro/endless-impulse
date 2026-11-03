#!/usr/bin/env python3
"""Native Tailscale panel bridge: read-only snapshots and explicit CLI operations."""
from concurrent.futures import ThreadPoolExecutor
import getpass
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import signal
import subprocess
import sys
import threading


def executable():
    override = os.environ.get("DOTS_TAILSCALE_BINARY")
    return override or ("/usr/bin/tailscale" if Path("/usr/bin/tailscale").is_file() else shutil.which("tailscale"))


def parse_help(text, path):
    sections, section = {}, "description"
    for line in text.splitlines():
        if re.fullmatch(r"[A-Z][A-Z ]+", line.strip()):
            section = line.strip()
        else:
            sections.setdefault(section, []).append(line)
    children = []
    for line in sections.get("SUBCOMMANDS", []):
        match = re.match(r"^\s{2,}([a-z0-9][a-z0-9-]*)\s{2,}(.+)", line)
        if match: children.append(dict(name=match[1], description=match[2].strip()))
    usage = "\n".join(sections.get("USAGE", [])).strip()
    prefix = "tailscale" + (" " + " ".join(path) if path else "")
    # Some commands (serve/funnel) document children only in their usage.
    for line in usage.splitlines():
        if line.strip().startswith(prefix + " "):
            remainder = line.strip()[len(prefix):].strip()
            first = remainder.split()[0] if remainder else ""
            if re.fullmatch(r"[a-z][a-z-]*", first) and not any(item["name"] == first for item in children):
                children.append(dict(name=first, description=""))
    flags, current = [], None
    for line in sections.get("FLAGS", []):
        match = re.match(r"^\s{2}--([a-z][a-z0-9-]*)(.*)", line)
        if match:
            boolean = "--" + match[1] + "=false" in match[2] or "--" + match[1] + "=true" in match[2]
            current = dict(name=match[1], type="bool" if boolean else "text", description="",
                           secret=bool(re.search(r"auth.?key|secret|token|password", match[1])))
            if not boolean and match[1] in ("c", "size", "http", "https", "tcp", "tls-terminated-tcp", "port"):
                port = match[1] in ("http", "https", "tcp", "tls-terminated-tcp", "port")
                current.update(input="number", minimum=1 if port else 0, maximum=65535 if port else 2147483647)
            flags.append(current)
        elif current and line.strip():
            current["description"] += (" " if current["description"] else "") + line.strip()
    first_usage = usage.splitlines()[0] if usage else ""
    positionals = [value for value in re.findall(r"<([^>]+)>", first_usage) if value not in ("subcommand", "command flags")]
    return dict(path=path, description="\n".join(sections.get("description", [])).strip(),
                usage=usage, children=children, flags=flags, positionals=positionals)


class Tailscale:
    def __init__(self, binary=None):
        self.binary = binary or executable()
        self.schemas = {}

    def query(self, args, allow_failure=False):
        if not self.binary: raise ValueError("Tailscale is not installed.")
        result = subprocess.run([self.binary, *args], capture_output=True, text=True, timeout=12)
        if result.returncode and not allow_failure:
            raise ValueError(result.stderr.strip() or "Tailscale could not complete this request.")
        return result

    def json(self, args, fallback):
        result = self.query(args, allow_failure=True)
        try: return json.loads(result.stdout)
        except ValueError: return fallback

    def schema(self, path):
        if not isinstance(path, list) or len(path) > 8 or any(not re.fullmatch(r"[a-z0-9][a-z0-9-]*", part) for part in path):
            raise ValueError("Invalid Tailscale operation.")
        key = tuple(path)
        if key in self.schemas: return self.schemas[key]
        if path:
            parent = self.schema(path[:-1])
            allowed = [item["name"] for item in parent["children"]]
            if not path[:-1]: allowed.append("debug")
            if path[-1] not in allowed: raise ValueError("This operation is not supported by the installed Tailscale CLI.")
        result = self.query([*path, "--help"], allow_failure=True)
        schema = parse_help(result.stdout + result.stderr, path)
        if not path and not any(item["name"] == "debug" for item in schema["children"]):
            schema["children"].append(dict(name="debug", description="Diagnostics and troubleshooting"))
        self.schemas[key] = schema
        return schema

    def command(self, path, flags, args, admin=False):
        schema = self.schema(path)
        if not path: raise ValueError("Choose an operation first.")
        available = {item["name"]: item for item in schema["flags"]}
        if not isinstance(flags, dict) or not isinstance(args, list) or len(args) > 64:
            raise ValueError("Invalid operation options.")
        command = [self.binary, *path]
        for key, value in flags.items():
            if key not in available: raise ValueError("This option is not supported: " + key)
            if available[key]["type"] == "bool":
                if type(value) is not bool: raise ValueError("Expected a switch value for " + key)
                value = "true" if value else "false"
            elif not isinstance(value, str): raise ValueError("Expected text for " + key)
            if len(value) > 8192 or "\0" in value: raise ValueError("Invalid option value.")
            command.append("--" + key + "=" + value)
        if any(not isinstance(arg, str) or "\0" in arg or len(arg) > 8192 for arg in args):
            raise ValueError("Invalid operation arguments.")
        if args: command += ["--", *args]
        return (["pkexec"] if admin else []) + command

    def snapshot(self):
        if not self.binary: return dict(installed=False, running=False, profiles=[], peers=[], prefs={}, health=[])
        with ThreadPoolExecutor(max_workers=3) as pool:
            status_job = pool.submit(self.json, ["status", "--json"], {})
            profiles_job = pool.submit(self.json, ["switch", "--list", "--json"], [])
            prefs_job = pool.submit(self.json, ["debug", "prefs"], {})
            status, profiles, prefs = status_job.result(), profiles_job.result(), prefs_job.result()
        own = status.get("Self") or {}
        peers = [dict(id=peer.get("ID", ""), name=peer.get("HostName", ""), dns=peer.get("DNSName", ""),
                      ips=peer.get("TailscaleIPs") or [], online=bool(peer.get("Online")),
                      exitOption=bool(peer.get("ExitNodeOption")), exitNode=bool(peer.get("ExitNode")),
                      os=peer.get("OS", "")) for peer in (status.get("Peer") or {}).values()]
        # Never send private keys, Persist, Config, or raw debug prefs to QML.
        native_prefs = {"accept-dns": bool(prefs.get("CorpDNS")), "accept-routes": bool(prefs.get("RouteAll")),
                        "shields-up": bool(prefs.get("ShieldsUp")), "ssh": bool(prefs.get("RunSSH")),
                        "webclient": bool(prefs.get("RunWebClient")),
                        "exit-node-allow-lan-access": bool(prefs.get("ExitNodeAllowLANAccess")),
                        "hostname": prefs.get("Hostname", ""), "advertise-routes": ",".join([route for route in (prefs.get("AdvertiseRoutes") or []) if route not in ("0.0.0.0/0", "::/0")])}
        current_exit = next((peer["ips"][0] for peer in peers if peer["id"] == prefs.get("ExitNodeID") and peer["ips"]), "")
        native_prefs["exit-node"] = current_exit or prefs.get("ExitNodeIP", "")
        native_prefs["advertise-exit-node"] = any(route in (prefs.get("AdvertiseRoutes") or []) for route in ("0.0.0.0/0", "::/0"))
        set_flags = [item["name"] for item in self.schema(["set"])["flags"]]
        return dict(installed=True, backendState=status.get("BackendState", "Unavailable"),
                    running=status.get("BackendState") == "Running", hostname=own.get("HostName", ""),
                    ips=status.get("TailscaleIPs") or [], tailnet=(status.get("CurrentTailnet") or {}).get("Name", ""),
                    authURL=status.get("AuthURL", ""), health=status.get("Health") or [],
                    profiles=profiles if isinstance(profiles, list) else [], peers=sorted(peers, key=lambda peer: (not peer["online"], peer["name"])),
                    prefs=native_prefs, canOperate=prefs.get("OperatorUser") == getpass.getuser() or os.geteuid() == 0,
                    username=getpass.getuser(), setFlags=set_flags)


def redact(text, secrets=()):
    for secret in sorted((str(v) for v in secrets if v), key=len, reverse=True):
        text = text.replace(secret, "[redacted]")
    text = re.sub(r"(?i)(?:tskey-[a-z0-9_-]+|(?:privkey|nodekey|machinekey|disco|mkey):[a-z0-9]+)", "[redacted]", text)
    return re.sub(r'(?i)("?(?:Private[^"\s:]*|AuthKey|Password|Token|Secret)"?\s*[:=]\s*)("[^"\n]*"|[^\s,}]+)', r'\1"[redacted]"', text)


class Controller:
    def __init__(self, client=None):
        self.client = client or Tailscale()
        self.output_lock = threading.Lock()
        self.process_lock = threading.Lock()
        self.process = None
        self.stopping = False
        self.input_secrets = []

    def emit(self, **data):
        with self.output_lock:
            print(json.dumps(data, ensure_ascii=False), flush=True)

    def refresh(self):
        self.emit(event="state", state=self.client.snapshot())

    def run(self, request):
        if self.stopping: raise ValueError("Tailscale integration is shutting down.")
        command = self.client.command(request.get("path", []), request.get("flags", {}), request.get("args", []), bool(request.get("admin")))
        if not self.process_lock.acquire(blocking=False): raise ValueError("Another Tailscale operation is still running.")
        try:
            self.input_secrets = []
            self.emit(event="running", value=True)
            schema = self.client.schema(request["path"])
            secrets = [value for key, value in request.get("flags", {}).items()
                       if any(flag["name"] == key and flag["secret"] for flag in schema["flags"])]
            sensitive = request["path"][0] in ("debug", "configure", "cert", "lock")
            # Interactive sessions need a terminal's TTY; configuration stays native.
            if request["path"][0] in ("ssh", "nc"):
                terminal = shlex.split(request.get("terminal") or "kitty")
                if not terminal: raise ValueError("Choose a terminal in Settings first.")
                subprocess.Popen([*terminal, "-e", *command], start_new_session=True,
                                 stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return
            self.process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                            stderr=subprocess.STDOUT, text=True, bufsize=1, start_new_session=True)
            if self.stopping: self.cancel()
            for line in self.process.stdout:
                # Diagnostic dumps can contain unknown credentials and multi-line keys.
                self.emit(event="output", text="[Diagnostic output hidden]\n" if sensitive else redact(line[:16384], secrets + request.get("args", []) + self.input_secrets))
            code = self.process.wait()
            if code: raise ValueError("Tailscale operation ended with code " + str(code) + ". See the operation output.")
        finally:
            process = self.process
            if process:
                if process.poll() is None: self.cancel()
                for stream in (process.stdin, process.stdout):
                    if stream: stream.close()
            self.process = None
            self.input_secrets = []
            self.process_lock.release()
            self.emit(event="running", value=False)
            if not self.stopping: self.refresh()

    def cancel(self):
        process = self.process
        if process and process.poll() is None:
            try: os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError: pass
            try: process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                try: os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError: pass

    def handle(self, request):
        identity = request.get("id", "")
        try:
            action = request.get("action")
            if action == "refresh": self.refresh()
            elif action == "schema":
                self.emit(event="schema", schema=self.client.schema(request.get("path", [])))
            elif action == "run": self.run(request)
            elif action == "cancel": self.cancel()
            elif action == "input":
                process = self.process
                if not process or process.poll() is not None: raise ValueError("No operation is accepting input.")
                response = str(request.get("text", ""))
                if len(response) > 8192: raise ValueError("Response is too long.")
                self.input_secrets.append(response)
                process.stdin.write(response + "\n")
                process.stdin.flush()
            else: raise ValueError("Unknown Tailscale action.")
            self.emit(event="result", id=identity, ok=True)
        except (ValueError, OSError, subprocess.SubprocessError) as error:
            self.emit(event="result", id=identity, ok=False, error=str(error))


def main():
    controller = Controller()
    pool = ThreadPoolExecutor(max_workers=4)
    def stop(signum, frame):
        controller.stopping = True
        controller.cancel()
        raise SystemExit(0)
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    try:
        for line in sys.stdin:
            try:
                request = json.loads(line)
                if not isinstance(request, dict): raise ValueError("Invalid request")
                if request.get("action") == "cancel": controller.handle(request)
                else: pool.submit(controller.handle, request)
            except (ValueError, TypeError): controller.emit(event="error", error="Invalid Tailscale request.")
    finally:
        controller.stopping = True
        controller.cancel()
        pool.shutdown(wait=True, cancel_futures=True)


if __name__ == "__main__": main()
