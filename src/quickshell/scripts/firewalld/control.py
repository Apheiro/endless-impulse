#!/usr/bin/env python3
"""Bounded Firewalld CLI bridge. No shell, sudo, files in /etc, or daemon control.

Single requests and a serialized JSON-lines worker share the same implementation.
Importing this module performs no I/O.
"""
import contextlib
import datetime
import io
import importlib
import ipaddress
import hashlib
import json
import os
import re
import runpy
import shlex
import signal
import select
import shutil
import subprocess
import sys
import time
import tempfile
import xml.etree.ElementTree as ET


class CliDeadlineExpired(BaseException):
    """Escape firewall.client's broad Exception handlers without retrying."""


class Failure(Exception):
    def __init__(self, state, message):
        super().__init__(message)
        self.state = state


def parse_objects(output):
    """Preserve all CLI fields, including multiline rich rules and unknown fields."""
    objects = []
    current = None
    field = None
    for line in output.splitlines():
        if not line.strip():
            continue
        if not line[0].isspace():
            name = line.split()[0]
            current = {"name": name, "active": "(active)" in line, "fields": {}}
            objects.append(current)
            field = None
        elif current is not None:
            match = re.match(r"^  ([a-z][a-z -]*):\s*(.*)$", line)
            if match:
                field, value = match.groups()
                current["fields"][field] = value
            elif field:
                current["fields"][field] += "\n" + line.strip()
            else:
                raise Failure("communication-error", "Unrecognized Firewalld response")
        else:
            raise Failure("communication-error", "Unrecognized Firewalld response")
    return objects


def revision(state):
    data = {k: state.get(k) for k in ("defaultZone", "scopes", "services", "catalogs", "connections", "capabilities")}
    return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()


def valid_port(value):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9]{1,5}(-[0-9]{1,5})?/(tcp|udp)", value):
        raise ValueError("Use a port or range with TCP/UDP")
    bounds = [int(n) for n in value.split("/")[0].split("-")]
    if not all(1 <= n <= 65535 for n in bounds) or bounds[0] > bounds[-1]:
        raise ValueError("Ports must be ordered within 1..65535")
    port = str(bounds[0]) if bounds[0] == bounds[-1] else "%s-%s" % tuple(bounds)
    return port + "/" + value.split("/")[1]


class Firewall:
    def __init__(self, binary=None):
        # Host tool is optional. Nix does not need the host's Python dbus bindings.
        self.binary = binary or shutil.which("firewall-cmd")
        if binary is None and not self.binary and os.path.isfile("/usr/bin/firewall-cmd"):
            self.binary = "/usr/bin/firewall-cmd"
        self.deadline = None
        self.allow_interaction = False
        self.authorization_started = False
        self.copy_directory = None
        self.request_id = None

    @contextlib.contextmanager
    def cli_environment(self):
        """Isolate upstream CLI globals and bus receivers between worker calls.

        The CLI's authorizeAll is an optional blanket preflight, not an operation's
        permission check. Skip it: call() checks the narrow permissions first and
        the actual D-Bus methods still enforce the host policy themselves.
        """
        try:
            client = importlib.import_module("firewall.client")
            dbus = importlib.import_module("dbus")
            network = importlib.import_module("firewall.core.fw_nm")
        except ImportError:
            # run_cli reports missing host dependencies if the CLI needs them.
            yield
            return
        original_bus = dbus.SystemBus
        original_authorize = client.FirewallClient.authorizeAll
        original_handler, original_loop = client.exception_handler, client.not_authorized_loop
        original_nm_write = network.nm_set_zone_of_connection
        buses = []

        def private_bus(*args, **kwargs):
            # FirewallClient initializes its GLib mainloop before opening the bus.
            kwargs["private"] = True
            bus = original_bus(*args, **kwargs)
            buses.append(bus)
            return bus

        def refuse_profile_write(*args, **kwargs):
            raise Failure("conflict", "NetworkManager owns this connection; change its zone in the owning network manager")

        dbus.SystemBus = private_bus
        client.FirewallClient.authorizeAll = lambda self: None
        client.exception_handler, client.not_authorized_loop = None, False
        # Permanent --change-interface otherwise silently delegates to NM. Even
        # if ownership changes after inventory, never write an NM profile here.
        network.nm_set_zone_of_connection = refuse_profile_write
        try:
            yield
        finally:
            dbus.SystemBus = original_bus
            client.FirewallClient.authorizeAll = original_authorize
            client.exception_handler, client.not_authorized_loop = original_handler, original_loop
            network.nm_set_zone_of_connection = original_nm_write
            for bus in buses:
                bus.close()

    def host_result(self, argv):
        try:
            if self.deadline and time.monotonic() >= self.deadline:
                return None
            return subprocess.run(argv, capture_output=True, text=True, timeout=3,
                                  env=dict(os.environ, LC_ALL="C"))
        except (OSError, subprocess.TimeoutExpired):
            return None

    def host_read(self, argv):
        """Optional, bounded inventory. These tools only read network metadata."""
        result = self.host_result(argv)
        return result.stdout if result is not None and result.returncode == 0 else ""

    def connections(self, state):
        # No guessing from interface names or connection types. Unknown NM status
        # disables assignment because firewall-cmd can otherwise change NM profiles.
        try:
            links = json.loads(self.host_read(["ip", "-j", "address", "show"]) or "[]")
            routes = json.loads(self.host_read(["ip", "-j", "route", "show", "default"]) or "[]")
            if not routes:
                routes = json.loads(self.host_read(["ip", "-j", "-6", "route", "show", "default"]) or "[]")
        except (ValueError, TypeError):
            links, routes = [], []
        nm = {}
        raw = self.host_read(["nmcli", "--terse", "--escape", "yes", "--fields",
                              "GENERAL.DEVICE,GENERAL.TYPE,GENERAL.STATE,GENERAL.CONNECTION,GENERAL.NM-MANAGED",
                              "device", "show"])
        device = None
        for line in raw.splitlines():
            key, sep, value = line.partition(":")
            if not sep:
                continue
            value = re.sub(r"\\(.)", r"\1", value)
            if key == "GENERAL.DEVICE":
                device = value
                nm[device] = {}
            elif device:
                nm[device][key] = value
        primary = min((r for r in routes if r.get("dev")), key=lambda r: r.get("metric", 0), default={}).get("dev")
        zones = state["scopes"]["runtime"]["zones"]
        bindings = {interface: z["name"] for z in zones for interface in z["fields"].get("interfaces", "").split()}
        permanent = {interface: z["name"] for z in state["scopes"]["permanent"]["zones"]
                     for interface in z["fields"].get("interfaces", "").split()}
        # Retain Firewalld interfaces even when the kernel inventory is unavailable.
        known = {link.get("ifname"): link for link in links if isinstance(link, dict)}
        for interface in bindings.keys() | nm.keys():
            known.setdefault(interface, {})
        result = []
        for interface, link in sorted(known.items()):
            if not interface or interface == "lo":
                continue
            info = nm.get(interface, {})
            kind = info.get("GENERAL.TYPE") or link.get("linkinfo", {}).get("info_kind") or "Unknown"
            unmanaged = info.get("GENERAL.NM-MANAGED") == "no"
            # Even an NM-unmanaged virtual interface can belong to another tool.
            safe = unmanaged and kind in ("ethernet", "wifi")
            name = info.get("GENERAL.CONNECTION", "")
            result.append(dict(interface=interface, name=name if name and name != "--" else interface,
                               type=kind, status=info.get("GENERAL.STATE") or link.get("operstate", "Unknown"),
                               zone=bindings.get(interface, state["defaultZone"]),
                               binding="explicit" if interface in bindings else "default",
                               permanentZone=permanent.get(interface, ""), primary=interface == primary,
                               manager="NetworkManager" if info.get("GENERAL.NM-MANAGED") == "yes" else "Unknown (NetworkManager reports unmanaged)" if unmanaged else "Unknown",
                               canAssign=safe,
                               assignmentReason="NetworkManager reports this physical device unmanaged. Other ownership is unknown; another network manager may overwrite this Firewalld binding." if safe else "Zone assignment is unavailable here: ownership is external or cannot be established safely. Use the owning network manager."))
        return result

    def capabilities(self):
        # --help never contacts D-Bus and does not require authorization.
        try:
            result = self.run_cli(["--help"], 3)
        except (OSError, subprocess.TimeoutExpired):
            return []
        output = result.stdout if result.returncode == 0 else ""
        return sorted(set(re.findall(r"--([a-z][a-z-]+)", output)))

    def definition(self, request):
        kind, name, scope = request.get("kind"), request.get("name"), request.get("scope")
        if kind not in ("service", "ipset", "zone") or scope not in ("runtime", "permanent"):
            raise ValueError("Select a definition and scope")
        if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}", name):
            raise ValueError("Invalid definition name")
        prefix = ["--permanent"] if scope == "permanent" else []
        objects = parse_objects(self.call(prefix + ["--info-" + kind + "=" + name]))
        if len(objects) != 1 or objects[0]["name"] != name:
            raise Failure("communication-error", "Incomplete definition response")
        objects[0]["revision"] = hashlib.sha256(json.dumps(objects[0], sort_keys=True).encode()).hexdigest()
        if kind == "zone" and scope == "permanent":
            # XML is used only for a lossless duplicate, never rewritten in place.
            try:
                document, origin = self.zone_document(name)
                objects[0].update(origin=origin, documentRevision=hashlib.sha256(document).hexdigest())
            except (Failure, ValueError) as exc:
                objects[0]["unavailableReason"] = str(exc)
        return objects[0]

    def zone_document(self, name):
        path = self.call(["--permanent", "--path-zone=" + name])
        allowed = {"/etc/firewalld/zones/" + name + ".xml": "custom",
                   "/usr/lib/firewalld/zones/" + name + ".xml": "vendor",
                   "/usr/share/firewalld/zones/" + name + ".xml": "vendor"}
        if path not in allowed:
            raise ValueError("Zone origin is unavailable; duplicate and delete are disabled")
        try:
            with os.fdopen(os.open(path, os.O_RDONLY | os.O_NOFOLLOW), "rb") as stream:
                document = stream.read(1024 * 1024 + 1)
            if len(document) > 1024 * 1024 or b"<!DOCTYPE" in document or b"<!ENTITY" in document:
                raise ValueError("Unsupported zone document")
            if ET.fromstring(document).tag != "zone":
                raise ValueError("Unsupported zone document")
        except (OSError, ET.ParseError):
            raise ValueError("Zone document cannot be read safely; duplicate and delete are disabled") from None
        origin = allowed[path]
        if origin == "custom" and any(os.path.exists(root + name + ".xml") for root in ("/usr/lib/firewalld/zones/", "/usr/share/firewalld/zones/")):
            origin = "override"
        return document, origin

    def check_zone_dependencies(self, name, state):
        if name == state["defaultZone"]:
            raise ValueError("The default zone cannot be deleted")
        for configuration in state["scopes"].values():
            for zone in configuration["zones"]:
                if zone["name"] == name and any(zone["fields"].get(field) for field in ("interfaces", "sources")):
                    raise ValueError("Remove zone interface and source bindings before deletion")
            for policy in configuration["policies"]:
                if any(name in policy["fields"].get(field, "").split() for field in ("ingress-zones", "egress-zones")):
                    raise ValueError("Resolve policy dependencies before deleting this zone")
        # Include inactive NM profiles, not just connected interfaces. Failure to
        # enumerate them is an unresolved dependency, never permission to delete.
        profiles = self.host_result(["nmcli", "--get-values", "UUID", "connection", "show"])
        if profiles is None or profiles.returncode != 0:
            raise ValueError("NetworkManager profile dependencies cannot be verified; deletion is unavailable")
        identifiers = profiles.stdout.split()
        if len(identifiers) > 128:
            raise ValueError("Too many external profiles to verify safely; deletion is unavailable")
        for identifier in identifiers:
            if not re.fullmatch(r"[a-fA-F0-9-]{36}", identifier):
                raise ValueError("Unrecognized external profile; deletion is unavailable")
            profile = self.host_result(["nmcli", "--get-values", "connection.zone", "connection", "show", "uuid", identifier])
            if profile is None or profile.returncode != 0:
                raise ValueError("External profile dependencies cannot be verified; deletion is unavailable")
            if profile.stdout.strip() == name:
                raise ValueError("A NetworkManager profile references this zone; update it in Network settings first")

    def check_owner(self):
        """Ask the bus itself, without activating or authorizing Firewalld."""
        busctl = shutil.which("busctl") or "/usr/bin/busctl"
        try:
            result = subprocess.run([busctl, "--system", "--auto-start=no", "--timeout=3",
                                     "call", "org.freedesktop.DBus", "/org/freedesktop/DBus",
                                     "org.freedesktop.DBus", "GetNameOwner", "s",
                                     "org.fedoraproject.FirewallD1"],
                                    capture_output=True, text=True, timeout=4,
                                    env=dict(os.environ, LC_ALL="C"))
        except subprocess.TimeoutExpired:
            raise Failure("timeout", "System D-Bus request timed out") from None
        except OSError:
            raise Failure("communication-error", "Could not query system D-Bus with busctl") from None
        if result.returncode:
            if any(word in result.stderr.lower() for word in ("no owner", "no such name", "not provided", "namehasnoowner")):
                raise Failure("unavailable", "Firewalld is stopped or unavailable on the system bus")
            raise Failure("communication-error", "Could not reach Firewalld on system D-Bus")

    def permissions(self):
        """Never invoke the CLI unless its Polkit actions are already allowed.

        Firewalld permits interaction server-side even for read methods. The CLI
        also reads config objects whose default action is *config*, not info.
        pkcheck without --allow-user-interaction cannot open a password prompt.
        """
        checker = shutil.which("pkcheck")
        if not checker and os.path.isfile("/usr/bin/pkcheck"):
            checker = "/usr/bin/pkcheck"
        if not checker:
            raise Failure("authorization-unavailable", "pkcheck is required for non-interactive Firewall reads")
        # Grants belong to this PID + start time + UID, not all session clients.
        with open("/proc/self/stat") as stream:
            start_time = stream.read().rsplit(")", 1)[1].split()[19]
        subject = f"{os.getpid()},{start_time},{os.getuid()}"
        for action in ("config", "info", "config.info"):
            if not self.check_permission(checker, subject, action):
                return False
        return True

    def check_permission(self, checker, subject, action, interactive=False):
        argv = [checker, "--process", subject, "--action-id",
                "org.fedoraproject.FirewallD1." + action]
        if interactive:
            argv.append("--allow-user-interaction")
        try:
            result = subprocess.run(argv, capture_output=True, text=True,
                                    timeout=60 if interactive else 3,
                                    env=dict(os.environ, LC_ALL="C"))
        except subprocess.TimeoutExpired:
            raise Failure("timeout", "Polkit permission check timed out") from None
        except OSError:
            raise Failure("authorization-unavailable", "Could not execute pkcheck") from None
        diagnostic = result.stderr.lower()
        # pkcheck(1): 1 denied, 2 needs interaction OR has no suitable agent,
        # 3 dismissed, 126 invalid invocation, 127 authorization check error.
        # Do not infer an absent agent from rc=2 on a silent check.
        if result.returncode == 0:
            return True
        if result.returncode in (1, 3):
            if interactive:
                raise Failure("access-denied", "Firewall authorization was denied or cancelled; retry manually")
            return False
        if result.returncode == 2:
            if interactive or "no authentication agent" in diagnostic or "no suitable authentication agent" in diagnostic:
                raise Failure("agent-unavailable", "No suitable session Polkit agent is available; start it and retry manually")
            return False
        if any(word in diagnostic for word in ("bus", "could not connect", "connection refused")):
            raise Failure("communication-error", "Could not reach Polkit on system D-Bus")
        raise Failure("authorization-unavailable", "Polkit permission check failed")

    def authorize(self):
        self.begin_authorization()
        checker = shutil.which("pkcheck") or "/usr/bin/pkcheck"
        with open("/proc/self/stat") as stream:
            start_time = stream.read().rsplit(")", 1)[1].split()[19]
        subject = f"{os.getpid()},{start_time},{os.getuid()}"
        # config is required by Firewalld's config object enumeration and implies
        # config.info. Never request all/direct/policies or a second challenge.
        self.check_permission(checker, subject, "config", interactive=True)

    def begin_authorization(self):
        if self.authorization_started:
            return
        # The UI acknowledges only after releasing its focus grab, before any
        # potentially interactive CLI starts. Fail closed if the UI disappears.
        event = {"event": "authorization-required"}
        if self.request_id is not None:
            event["requestId"] = self.request_id
        print(json.dumps(event), flush=True)
        if not select.select([sys.stdin], [], [], 3)[0]:
            raise Failure("timeout", "Settings did not acknowledge the authorization request")
        acknowledgement = sys.stdin.readline().strip()
        expected = {"event": "authorize", "requestId": self.request_id}
        if (self.request_id is None and acknowledgement != "authorize") or (self.request_id is not None and json.loads(acknowledgement) != expected):
            raise Failure("timeout", "Settings did not acknowledge the authorization request")
        self.authorization_started = True

    def run_cli(self, args, timeout):
        """Run the host Python CLI in the authorized process, never a child PID.

        main() selects the CLI's interpreter first (host dbus/GI dependencies).
        Each run gets fresh CLI globals; SystemExit is the CLI's normal result.
        The bridge owns stdout/stdin, argv and the bounded request deadline.
        """
        output, errors = io.StringIO(), io.StringIO()
        previous_argv, previous_stdin, previous_hook = sys.argv, sys.stdin, sys.excepthook
        def expired(signum, frame):
            raise CliDeadlineExpired()
        previous_handler = signal.signal(signal.SIGALRM, expired)
        code = 0
        try:
            sys.argv = [self.binary, *args]
            with open(os.devnull) as empty, contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors), self.cli_environment():
                sys.stdin = empty
                signal.setitimer(signal.ITIMER_REAL, timeout)
                try:
                    runpy.run_path(self.binary, run_name="__main__")
                except SystemExit as exc:
                    code = exc.code if isinstance(exc.code, int) else (0 if exc.code is None else 1)
        except CliDeadlineExpired:
            raise subprocess.TimeoutExpired(self.binary, timeout) from None
        except (ImportError, SyntaxError):
            raise Failure("communication-error", "The host firewall-cmd Python dependencies could not be loaded") from None
        finally:
            signal.setitimer(signal.ITIMER_REAL, 0)
            signal.signal(signal.SIGALRM, previous_handler)
            sys.argv, sys.stdin = previous_argv, previous_stdin
            sys.excepthook = previous_hook
        return subprocess.CompletedProcess([self.binary, *args], code, output.getvalue(), errors.getvalue())

    def call(self, args):
        if not self.binary:
            raise Failure("not-installed", "firewall-cmd is not available on this host")
        if not self.permissions():
            if not self.allow_interaction:
                raise Failure("access-denied", "Firewalld permission expired or is unavailable. Refresh to retry native authorization")
            if self.authorization_started:
                raise Failure("access-denied", "Firewall permissions are incomplete; retry manually")
            self.authorize()
            if not self.permissions():
                raise Failure("access-denied", "Firewall permissions are incomplete after authorization; retry manually")
        remaining = self.deadline - time.monotonic() if self.deadline else 5
        if remaining <= 0:
            raise Failure("timeout", "Firewalld snapshot timed out")
        try:
            result = self.run_cli(args, timeout=min(60 if self.authorization_started else 5, remaining))
        except FileNotFoundError:
            raise Failure("not-installed", "firewall-cmd is not available on this host") from None
        except subprocess.TimeoutExpired:
            raise Failure("timeout", "Firewalld request timed out; the operation may have taken effect") from None
        except OSError:
            raise Failure("communication-error", "Could not execute firewall-cmd") from None
        if result.returncode:
            diagnostic = (result.stderr + result.stdout).lower()
            if any(x in diagnostic for x in ("not_authorized", "notauthorizedexception", "not authorized(polkit)", "accessdenied", "access denied", "not authorized", "authorization failed", "authentication failed", "operation not permitted", "permission denied")):
                raise Failure("access-denied", "Firewalld denied this request; check the session Polkit agent and permissions")
            if result.returncode == 252 or "not running" in diagnostic or "serviceunknown" in diagnostic:
                raise Failure("unavailable", "Firewalld is stopped or unavailable on the system bus")
            raise Failure("communication-error", "Firewalld rejected the request; refresh and check its journal")
        return result.stdout.strip()

    def snapshot(self):
        self.deadline = time.monotonic() + (180 if self.allow_interaction else 22)
        state = {"installed": bool(self.binary), "connected": False, "state": "connecting",
                 "complete": False, "defaultZone": "", "activeZones": [], "scopes": {},
                 "services": [], "differences": [], "error": "", "lastUpdated": None, "revision": ""}
        try:
            if not self.binary:
                raise Failure("not-installed", "firewall-cmd is not available on this host")
            self.check_owner()
            # Real D-Bus round trip, not process/package/systemctl inference.
            state["defaultZone"] = self.call(["--get-default-zone"])
            state.update(connected=True, state="connected")
            for scope in ("runtime", "permanent"):
                prefix = ["--permanent"] if scope == "permanent" else []
                zones = parse_objects(self.call(prefix + ["--list-all-zones"]))
                if not zones or state["defaultZone"] not in [z["name"] for z in zones]:
                    raise Failure("communication-error", "Incomplete Firewalld zone response")
                policies = parse_objects(self.call(prefix + ["--list-all-policies"]))
                state["scopes"][scope] = {"zones": zones, "policies": policies}
            state["services"] = self.call(["--get-services"]).split()
            state["capabilities"] = self.capabilities()
            state["catalogs"] = {}
            for scope in ("runtime", "permanent"):
                prefix = ["--permanent"] if scope == "permanent" else []
                state["catalogs"][scope] = {
                    "services": state["services"] if scope == "runtime" else self.call(prefix + ["--get-services"]).split(),
                    "ipsets": self.call(prefix + ["--get-ipsets"]).split() if "get-ipsets" in state["capabilities"] else None,
                    "icmptypes": self.call(prefix + ["--get-icmptypes"]).split() if "get-icmptypes" in state["capabilities"] else None}
            state["connections"] = self.connections(state)
            # Check liveness again after collecting data. Never publish a partial snapshot as editable.
            if self.call(["--get-default-zone"]) != state["defaultZone"]:
                raise Failure("conflict", "Firewalld changed during the read; retry")
            state["activeZones"] = [z for z in state["scopes"]["runtime"]["zones"] if z["active"]]
            runtime = {z["name"]: z["fields"] for z in state["scopes"]["runtime"]["zones"]}
            permanent = {z["name"]: z["fields"] for z in state["scopes"]["permanent"]["zones"]}
            state["differences"] = sorted(k for k in runtime.keys() | permanent.keys() if runtime.get(k) != permanent.get(k))
            state.update(complete=True, lastUpdated=datetime.datetime.now(datetime.timezone.utc).isoformat())
            state["revision"] = revision(state)
        except Failure as exc:
            # A denied optional/config query is distinct from a stopped daemon.
            state.update(state=exc.state, error=str(exc), complete=False)
            if exc.state == "not-installed":
                state["installed"] = False
            state["connected"] = state["connected"] and exc.state not in ("unavailable", "not-installed", "communication-error", "timeout", "authorization-unavailable", "agent-unavailable")
            state.update(scopes={}, activeZones=[], services=[], catalogs={}, connections=[], revision="")
        return state

    def command(self, request, state):
        if not state["connected"] or not state["complete"]:
            raise Failure("unavailable", "A complete current snapshot is required")
        if request.get("revision") != state["revision"]:
            raise Failure("conflict", "Configuration changed externally. Review a fresh snapshot before applying")
        if request.get("confirmed") is not True:
            raise ValueError("Explicit review confirmation is required")
        scope = request.get("scope")
        if scope not in ("runtime", "permanent"):
            raise ValueError("Select runtime or permanent")
        action, value = request.get("action"), request.get("value")
        capabilities = state.get("capabilities", [])
        prefix = ["--permanent"] if scope == "permanent" else []
        if action in ("duplicate-zone", "delete-zone"):
            required = "new-zone-from-file" if action == "duplicate-zone" else "delete-zone"
            zone = request.get("zone")
            if scope != "permanent" or required not in capabilities or "path-zone" not in capabilities:
                raise ValueError("This zone operation is unavailable in this scope or host client")
            if zone not in [z["name"] for z in state["scopes"][scope]["zones"]] or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", zone):
                raise ValueError("Select an existing permanent zone")
            document, origin = self.zone_document(zone)
            if request.get("documentRevision") != hashlib.sha256(document).hexdigest():
                raise Failure("conflict", "Zone document changed. Read its metadata before reviewing again")
            if action == "delete-zone":
                if origin != "custom":
                    raise ValueError("Vendor zones cannot be deleted here")
                self.check_zone_dependencies(zone, state)
                return ["--permanent", "--delete-zone=" + zone]
            if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_-]{0,16}", value):
                raise ValueError("Use a new zone ID of 1–17 letters, digits, underscores or hyphens")
            if value in [z["name"] for z in state["scopes"][scope]["zones"]]:
                raise ValueError("Destination zone already exists")
            tree = ET.fromstring(document, parser=ET.XMLParser(target=ET.TreeBuilder(insert_comments=True, insert_pis=True)))
            # Duplicating bindings would reassign traffic. Copy all metadata and
            # rules losslessly while leaving the new zone explicitly unassigned.
            for child in list(tree):
                if child.tag in ("interface", "source"):
                    tree.remove(child)
            self.copy_directory = tempfile.TemporaryDirectory(prefix="firewalld-zone-copy-")
            path = os.path.join(self.copy_directory.name, "zone.xml")
            ET.ElementTree(tree).write(path, encoding="utf-8", xml_declaration=True)
            return ["--permanent", "--new-zone-from-file=" + path, "--name=" + value]
        if action in ("new-zone", "new-service", "new-ipset"):
            if scope != "permanent" or action not in capabilities:
                raise ValueError("Definition creation is available only in permanent configuration on supported hosts")
            if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_-]{0,16}", value):
                raise ValueError("Use 1–17 letters, digits, underscores or hyphens, starting with a letter, digit or underscore")
            kind = action[4:]
            existing = ([z["name"] for z in state["scopes"][scope]["zones"]] if kind == "zone"
                        else state.get("catalogs", {}).get(scope, {}).get(kind + "s"))
            if existing is None or value in existing:
                raise ValueError("The definition already exists or its catalog is unavailable")
            return prefix + ["--" + action + "=" + value] + (["--type=hash:ip", "--option=family=inet"] if kind == "ipset" else [])
        if action in ("definition-add-port", "definition-remove-port", "definition-add-entry", "definition-remove-entry"):
            kind = "service" if action.endswith("port") else "ipset"
            name = request.get("name")
            if scope != "permanent" or name not in (state.get("catalogs", {}).get(scope, {}).get(kind + "s") or []):
                raise ValueError("Select an existing permanent definition")
            operation = action.removeprefix("definition-")
            if operation not in capabilities:
                raise ValueError("This operation is unavailable on this host")
            definition = self.definition(dict(kind=kind, name=name, scope=scope))
            if request.get("definitionRevision") != definition["revision"]:
                raise Failure("conflict", "Definition changed externally. Read it again before reviewing")
            detail = definition["fields"]
            if kind == "service":
                value = valid_port(value)
                exists = value in detail.get("ports", "").split()
            else:
                if detail.get("type") != "hash:ip" or "timeout=" in detail.get("options", "") or "family=inet6" in detail.get("options", "").split():
                    raise ValueError("Only IPv4 hash:ip sets without timeouts can be edited here")
                value = str(ipaddress.IPv4Address(value))
                exists = value in detail.get("entries", "").split()
            if operation.startswith("add-") == exists:
                raise Failure("conflict", "Definition already has the requested state")
            return prefix + ["--" + kind + "=" + name, "--" + operation + "=" + value]
        zone = request.get("zone")
        zones = state["scopes"][scope]["zones"]
        selected = next((z for z in zones if z["name"] == zone), None)
        if not selected or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", zone):
            raise ValueError("Unknown zone")
        prefix += ["--zone=" + zone]
        if action == "change-interface":
            connection = next((c for c in state.get("connections", []) if c["interface"] == value), None)
            if action not in capabilities or not connection or not connection["canAssign"]:
                raise ValueError("Interface ownership does not permit safe assignment here")
            if not re.fullmatch(r"[A-Za-z0-9_.:-]{1,15}", value):
                raise ValueError("Unsupported interface identifier")
            current = connection["zone"] if scope == "runtime" else connection["permanentZone"]
            if current == zone:
                raise Failure("conflict", "Interface already has the requested zone")
            return prefix + ["--change-interface=" + value]
        if action in ("add-service", "remove-service"):
            services = state.get("catalogs", {}).get(scope, {}).get("services", state["services"])
            if not isinstance(value, str) or value not in services or not re.fullmatch(r"[A-Za-z0-9_.-]{1,128}", value):
                raise ValueError("Select a known service")
            exists = value in selected["fields"].get("services", "").split()
        elif action in ("add-port", "remove-port"):
            value = valid_port(value)
            exists = value in selected["fields"].get("ports", "").split()
        elif action in ("add-protocol", "remove-protocol", "add-source-port", "remove-source-port", "add-icmp-block", "remove-icmp-block", "add-rich-rule", "remove-rich-rule", "add-source", "remove-source"):
            if action not in capabilities or not isinstance(value, str):
                raise ValueError("This operation is unavailable on this host")
            field = action.split("-", 1)[1]
            if field == "source-port":
                value = valid_port(value)
            elif field == "protocol":
                if not re.fullmatch(r"[a-z][a-z0-9-]{0,31}|[0-9]{1,3}", value) or (value.isdigit() and int(value) > 255):
                    raise ValueError("Use a protocol name or number within 0–255")
            elif field == "icmp-block":
                if value not in (state.get("catalogs", {}).get(scope, {}).get("icmptypes") or []):
                    raise ValueError("Select a known ICMP type")
            elif field == "rich-rule":
                if not value.startswith("rule ") or len(value) > 4096 or any(ord(c) < 32 for c in value):
                    raise ValueError("Enter one complete Firewalld rich rule on a single line")
            elif field == "source":
                if value.startswith("ipset:"):
                    if value[6:] not in (state.get("catalogs", {}).get(scope, {}).get("ipsets") or []):
                        raise ValueError("Select an IP set in this scope")
                else:
                    value = str(ipaddress.ip_network(value, strict=False) if "/" in value else ipaddress.ip_address(value))
            key = {"source-port": "source-ports", "icmp-block": "icmp-blocks", "rich-rule": "rich rules"}.get(field, field + "s")
            entries = selected["fields"].get(key, "")
            exists = value in (entries.splitlines() if field == "rich-rule" else entries.split())
        elif action in ("add-forward", "remove-forward", "add-masquerade", "remove-masquerade"):
            if value is not None:
                raise ValueError("Unexpected flag value")
            field = "forward" if action.endswith("forward") else "masquerade"
            exists = selected["fields"].get(field) == "yes"
        else:
            raise ValueError("Unsupported operation")
        adding = action.startswith("add-")
        if adding == exists:
            raise Failure("conflict", "Rule already has the requested state; refresh")
        return prefix + ["--" + action + ("=" + value if value is not None else "")]

    def handle(self, request):
        try:
            return self.handle_request(request)
        finally:
            if self.copy_directory:
                self.copy_directory.cleanup()
                self.copy_directory = None

    def handle_request(self, request):
        if not isinstance(request, dict):
            raise ValueError("Expected an object")
        self.request_id = request.get("requestId")
        # One challenge at most per explicit request, even in a persistent worker.
        self.authorization_started = False
        self.allow_interaction = request.get("allowInteraction") is True
        self.deadline = time.monotonic() + (180 if self.allow_interaction else 22)
        if request.get("action") == "inspect":
            try:
                detail = self.definition(request)
                if request.get("kind") == "zone" and request.get("scope") == "permanent":
                    detail["deletionAllowed"] = False
                    current = self.snapshot()
                    if not current["complete"]:
                        raise Failure(current["state"], current["error"])
                    detail["deletionRevision"] = current["revision"]
                    try:
                        if detail.get("origin") != "custom":
                            raise ValueError("Only verified custom zones can be deleted here")
                        self.check_zone_dependencies(request["name"], current)
                        detail["deletionAllowed"] = True
                    except ValueError as exc:
                        detail["deletionReason"] = str(exc)
                return {"ok": True, "definition": detail}
            except (Failure, ValueError) as exc:
                return {"ok": False, "error": str(exc), "operationState": getattr(exc, "state", "invalid")}
        if request.get("action") == "snapshot":
            return {"ok": True, "snapshot": self.snapshot()}
        before = self.snapshot()
        attempted = False
        try:
            command = self.command(request, before)
            self.deadline = time.monotonic() + (60 if self.allow_interaction else 5)
            attempted = True
            self.call(command)
        except (Failure, ValueError) as exc:
            self.allow_interaction = False  # cancellation/denial never triggers another prompt
            return {"ok": False, "error": str(exc), "operationState": getattr(exc, "state", "invalid"), "snapshot": self.snapshot() if attempted else before}
        self.allow_interaction = False
        after = self.snapshot()
        verified = False
        if after["complete"]:
            action, scope = request["action"], request["scope"]
            zone = next((z for z in after["scopes"][scope]["zones"] if z["name"] == request.get("zone")), None)
            if action.startswith("new-"):
                kind = action[4:]
                verified = request["value"] in ([z["name"] for z in after["scopes"][scope]["zones"]] if kind == "zone" else after["catalogs"][scope].get(kind + "s", []))
            elif action in ("duplicate-zone", "delete-zone"):
                names = [z["name"] for z in after["scopes"][scope]["zones"]]
                verified = request["value"] in names if action == "duplicate-zone" else request["zone"] not in names
                if verified and action == "duplicate-zone":
                    try:
                        copied, _ = self.zone_document(request["value"])
                        with open(os.path.join(self.copy_directory.name, "zone.xml"), encoding="utf-8") as stream:
                            expected = ET.canonicalize(stream.read(), strip_text=True)
                        verified = ET.canonicalize(copied.decode("utf-8"), strip_text=True) == expected
                    except (Failure, ValueError, OSError, ET.ParseError, UnicodeError):
                        verified = False
            elif action.startswith("definition-"):
                try:
                    kind = "service" if action.endswith("port") else "ipset"
                    detail = self.definition(dict(kind=kind, name=request["name"], scope=scope))["fields"]
                    present = command[-1].split("=", 1)[1] in detail.get("ports" if kind == "service" else "entries", "").split()
                    verified = present == action.startswith("definition-add-")
                except Failure:
                    pass
            elif action == "change-interface":
                connection = next((c for c in after.get("connections", []) if c["interface"] == request["value"]), None)
                verified = bool(connection and (connection["zone"] if scope == "runtime" else connection["permanentZone"]) == request["zone"])
            elif zone:
                field = request["action"].split("-", 1)[1]
                if field not in ("forward", "masquerade"):
                    key = {"source-port": "source-ports", "icmp-block": "icmp-blocks", "rich-rule": "rich rules"}.get(field, field + "s")
                    entries = zone["fields"].get(key, "")
                    present = command[-1].split("=", 1)[1] in (entries.splitlines() if field == "rich-rule" else entries.split())
                else:
                    present = zone["fields"].get(field) == "yes"
                verified = present == request["action"].startswith("add-")
        return {"ok": True, "error": "", "operationState": "applied" if verified else "applied-unverified", "snapshot": after}


def respond(client, payload):
    request_id = None
    try:
        request = json.loads(payload)
        if isinstance(request, dict):
            request_id = request.get("requestId")
        result = client.handle(request)
    except Failure as exc:
        result = {"ok": False, "error": str(exc), "operationState": exc.state}
    except OSError:
        result = {"ok": False, "error": "Could not load the host firewall-cmd client", "operationState": "communication-error"}
    except (ValueError, TypeError) as exc:
        result = {"ok": False, "error": str(exc), "operationState": "invalid"}
    if request_id is not None:
        result["requestId"] = request_id
    return result


def main():
    try:
        # Re-exec once under firewall-cmd's own Python interpreter. This keeps
        # host bindings available even when Quickshell uses a Nix/venv Python.
        # exec preserves PID/start time/UID for the whole authorization subject.
        if sys.argv[1] == "--host-cli":
            binary, payload = sys.argv[2:4]
        else:
            payload = sys.argv[1]
            binary = Firewall().binary
            if binary:
                with open(binary) as stream:
                    shebang = stream.readline().strip()
                interpreter = shlex.split(shebang[2:]) if shebang.startswith("#!") else []
                if not interpreter or not any("python" in os.path.basename(part) for part in interpreter):
                    raise Failure("communication-error", "firewall-cmd must be the host Python client")
                os.environ["LC_ALL"] = "C"
                os.execv(interpreter[0], [*interpreter, os.path.abspath(__file__), "--host-cli", binary, payload])
        client = Firewall(binary)
        if payload == "--serve":
            print(json.dumps({"event": "ready"}), flush=True)
            for line in sys.stdin:
                print(json.dumps(respond(client, line), ensure_ascii=True), flush=True)
            return
        result = respond(client, payload)
    except Failure as exc:
        result = {"ok": False, "error": str(exc), "operationState": exc.state}
    except OSError:
        result = {"ok": False, "error": "Could not load the host firewall-cmd client", "operationState": "communication-error"}
    except (ValueError, IndexError, TypeError) as exc:
        result = {"ok": False, "error": str(exc), "operationState": "invalid"}
    print(json.dumps(result, ensure_ascii=True))


if __name__ == "__main__":
    main()
