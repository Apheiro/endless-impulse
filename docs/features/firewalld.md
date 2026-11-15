# Native Firewall settings

Open **Settings → System → Firewall** (deep links `firewall` and
`security-network`). Firewall occupies the existing Settings content workspace,
uses native QML and shared Settings primitives, and loads on demand. Opening,
navigating, filtering and refreshing never change the firewall. Opening Firewall
immediately allows a native Polkit prompt when permission is missing; there is no
login, password setup or separate authorization button.

## Task navigation

The prototype supplies distribution, grouping and visual hierarchy. QML adapts
those relationships to the available workspace and font sizes using native
components and theme tokens; it does not reproduce fixed CSS dimensions.
The Settings window supplies the home title. Effective zones are inline links in
connection summaries. Shared SettingsCard primary/secondary tones distinguish the
primary connection and status/context cards with matching theme foreground colors.
The first two cards use half the normal surface opacity to blend into Settings;
text and controls remain fully opaque and theme transparency still applies. Other Settings cards retain their default
surface unless they opt into a tone.

- **Firewall home:** service status, at most one discovered primary connection
  with its effective runtime zone, Change zone, View all connections, and four
  task entries. A missing default route produces an explicit unavailable primary
  state; another connection is not arbitrarily called primary.
- **Network connections:** discovered kernel interfaces, reported type and
  connectivity state, effective runtime zone, reported/inherited binding,
  permanent binding and ownership information. Zone buttons open the editor.
- **Zones and rules:** all actual zones in the selected scope, bindings, services
  and ports. No zone identifiers are treated as connection categories.
- **Zone editor:** the explicit zone ID, interfaces, sources and selected scope
  persist on nested pages. Services and Ports appear first as full-width menu
  rows, each opening a focused editor. Advanced expands to
  exactly Protocols, Source ports, Masquerading, Port forwarding, ICMP filter,
  Rich rules, Interfaces and Sources. Missing zones never silently select a
  different zone. Scope is chosen on the zone list and remains read-only inside
  editors; there is no nested zone selector. One Back action restores the previous
  page and its exact zone, scope and section. Details and management open a separate
  nested page, preserving the compact rule menu. All raw fields remain inspectable, including unknown fields.
- **Services and IP sets:** global definitions, scoped inspection and separate
  usage information. Creating a service does not allow traffic. Creating an IP
  set does nothing until a source or rule references it.
- **Policies and diagnostics:** complete global policy fields, default zone and
  runtime/permanent differences, separately from per-zone rules.

All displayed rules and identifiers are plain text. Counts and descriptions are
not invented. Zone metadata can be read explicitly from the host. Usage reports
inspect zone/policy services, source references and recognizable rich-rule
references; they are not a complete dependency graph or security audit.

## Host integration and authentication

The optional host **firewalld** package supplies the daemon and Python
`firewall-cmd`. A system bus and session Polkit agent are required for protected
operations. `ip` and `nmcli` provide optional read-only interface, route and
ownership inventory. Missing inventory does not imply an interface is safe to
modify. The panel does not install packages, start services or manage credentials.
No external firewall GUI, shell, sudo or direct nftables commands are used.

`FirewalldControl.qml` keeps one idle JSON-lines bridge worker for the lifetime
of Settings and serializes one bounded request at a time. Navigating away from
Firewall does not replace the worker. The Python bridge re-execs under
`firewall-cmd`'s host Python interpreter, preserving its PID, start time and UID
across authorization, later refreshes, inspections and writes. It executes the
CLI with `runpy` in **that same process**, with fresh globals, captured output,
isolated argv/stdin and bounded SIGALRM. Each CLI invocation uses private D-Bus
connections that close afterwards; exception handlers and `sys.excepthook` are
restored so signal receivers and CLI state do not accumulate in the worker.
It never authorizes PID A and launches firewall-cmd as PID B. Host D-Bus bindings
are not added to the independent Nix runtime.

On first entry, protected reads immediately allow one contextual native Polkit
challenge, without a separate authorization button. Manual Refresh and confirmed
writes also allow one challenge when needed. Background polling and definition
inspection stay silent. A cancelled, denied or timed-out request stops polling
and suppresses automatic challenges on re-entry. Only a manual Refresh or confirmed
operation retries. The panel never collects or sets a password.

Before an interactive check, the bridge emits `authorization-required`, waits for
Settings to release its focus grab and acknowledge, then runs graphical pkcheck.
Worker requests, responses and authorization acknowledgements carry the same
request ID. Late or duplicate replies cannot resolve another request. Startup
errors, malformed replies, unexpected exit (including while hidden), protected
inspection failures and the five-minute request watchdog disable editing and
discard old rule data. The last complete-read timestamp remains historical.
Recovery requires an explicit manual action; no write is automatically retried.
The existing native authentication focus gate remains active through the panel's
exit animation. No credentials are handled by the Firewall page. Silent checks
and CLI calls retain the same subject; only `config` is requested interactively,
never broad `all`, `direct` or `policies` authorization. The small race between a
silent permission check and the server's own check remains subject to host policy.
The upstream CLI's blanket `authorizeAll()` preflight is suppressed only inside
the bridge process. The actual D-Bus methods retain their normal host permission
checks. The bridge also refuses the CLI's implicit NetworkManager profile-write
path if ownership changes after inventory; no NetworkManager profile is edited.

Connected requires a real default-zone D-Bus round trip. Editable requires full
runtime/permanent zone and policy reads, service catalogs and final liveness.
Failures hide old rules and disable changes; the last complete-read timestamp is
historical. Optional client capabilities are discovered from `--help`, which
never contacts D-Bus. Unsupported operations are explicitly unavailable.

## Supported changes and safety

Every write requires a review and explicit confirmation. Review captures the
operation, exact zone or global definition, requested scope, affected interface
bindings and revision. Connection review includes previous and destination zones.
Runtime takes effect immediately; permanent is saved for a future reload/start.
**The panel never reloads, restarts or copies runtime configuration to permanent.**
There is no timed test or automatic rollback.

Supported paths, subject to installed CLI capabilities:

- Allow/remove zone services and TCP/UDP ports or ordered ranges within 1–65535.
- Add/remove protocols, source ports, known ICMP filter types and complete
  single-line rich rules. ICMP block inversion is displayed explicitly and never
  changed by these controls. Removing a rich rule preserves its full text.
- Toggle masquerading and the separate intra-zone forwarding flag.
- Add/remove IP/network or existing IP-set source bindings. Adding a source
  changes zone classification, rather than merely permitting that source.
- Change an eligible interface's Firewalld binding in exactly one scope.
- Create empty permanent zones and service definitions, or permanent IPv4
  `hash:ip` sets without timeouts.
- Edit individual permanent service ports and IPv4 entries in compatible
  `hash:ip` sets, preserving other definition fields. Definition edits compare a
  separate detail revision so external definition edits cannot pass a mere
  catalog-name check.
- Duplicate a permanent zone's complete XML rules and metadata into a new zone,
  **without interface or source bindings**. The host-reported source path must
  match a supported zone configuration directory, be readable without following
  a final symlink, and have the exact reviewed digest. Unknown XML elements and
  comments are preserved in the import. A canonical post-read comparison must
  match before duplication is reported verified; host normalization can leave
  it accepted-but-unverified. The private temporary copy is removed on success or
  failure; existing configuration files are never directly rewritten.
- Delete a verified custom permanent zone only after default-zone, runtime and
  permanent binding, policy and inactive NetworkManager-profile checks. Vendor
  zones and overrides of vendor zones cannot be deleted here. Unknown origins,
  unreadable XML, unavailable profile enumeration and unresolved dependencies
  refuse deletion. A fresh XML digest is required. Runtime remains separate.
  Reading permanent zone metadata runs the dependency preflight before enabling
  deletion, tied to the current snapshot revision. Confirmation repeats all checks.

Connection type never determines zone. The effective zone is the runtime
Firewalld interface binding, or the default fallback when no binding is reported;
source classification and policies can further affect traffic. A reported
runtime binding does not prove a NetworkManager profile has an explicit zone.
The primary interface is selected from lowest-metric default routes (IPv4 first,
IPv6 fallback); this is not an Internet reachability check or full policy-routing
analysis.

Assignment is conservatively limited to physical wifi/ethernet interfaces reported
unmanaged by NetworkManager. Known NM-managed devices and virtual/unknown
ownership have an explicit unavailable explanation and must use their owning
manager. Even an NM-unmanaged physical interface can be configured by another
tool; review warns that external managers can override changes. No NetworkManager
profile is changed by this panel. Each attempted binding write is followed by a
new inventory and separate runtime/permanent observed binding checks.

Before every mutation, a fresh snapshot must match the reviewed revision. Catalog,
connection/ownership and rule changes invalidate review. External tools can still
race the final check: these are not atomic transactions. After every attempted
write, including failure or timeout, the bridge reads again. It reports verified
success only when the requested state is observed; otherwise it reports
accepted-but-unverified. A failed operation may have taken effect and must not be
blindly retried.

## Explicitly unavailable

Structured forward-port destination editing, changing ICMP inversion, targets,
default zones and global policies are read-only. Service/IP-set definition
deletion and duplication are unavailable because full indirect definition/direct
rule/external dependencies are not yet validated. Complex service fields,
non-`hash:ip` IP sets, IPv6 set creation and timed sets are inspected without being
rewritten. This is a functional limit, not a promise made by an inert button.

## Isolated verification and live validation

```sh
python3 -m unittest discover -s tests -p 'test_firewalld*.py' -v
./dev check -p 'test_firewalld*.py'
```

Tests mock host reads, CLI calls and authorization. Disposable-process identity
fixtures use fake firewall-cmd, pkcheck, busctl, ip and nmcli. Offscreen tests load
the real page/shared controls at 360/620/1100 px, light/dark themes, and the real
service/focus components with disposable bridges. Optional
`DOTS_FIREWALL_TEST_IMAGES=/tmp/firewall-images` saves rendered fixtures.

The user is the live tester. Still required: rendering in actual Settings and
Matugen themes, native Polkit focus/cancel/credentials, real host CLI compatibility,
connection inventory (including IPv6, VPN/container and unmanaged devices),
runtime/permanent assignments and postconditions, external override/conflict,
custom-zone dependency failures, and changes followed by an externally performed
reload. Agent tests do not claim any real firewall or user-session validation.

Manual Settings handoff:

1. Open Settings → System → Firewall. If permission is missing, expect the native
   authentication panel immediately. There must be no login/password setup button.
   Cancel it: changes must stay disabled and re-entry must not reopen it in a loop.
2. Select Refresh to retry if needed. After authorizing, navigate
   away and back, refresh and inspect a definition. Expect the same process
   subject and no new prompt while the host retains its grant. Expired grants
   must return to the explicit permission state rather than repeatedly prompting.
3. Cancel an authorization request and check that Settings stays open, focus
   returns, changes stay disabled, and only a manual action retries.
4. Check the primary connection and every discovered interface against the host's
   actual assignments. Open a zone from its label; verify that nested pages and
   scope changes retain that exact zone ID. Managed/unknown connections must
   explain why assignment is unavailable. An open assignment form must reflect
   refreshed ownership and zone information.
5. If choosing to test writes, use a disposable unused permanent zone/definition.
   Cancel its review first, then confirm separately. Check scope and observed
   postconditions. Duplicate must omit bindings. Delete must stay disabled until
   metadata/dependency checks pass; bindings, policies or NM profile references
   must prevent it. No panel action reloads the firewall.
6. While a review is open, change the relevant configuration externally. Confirm
   must refuse a stale revision and require fresh review. After a bridge failure,
   previous rules must disappear and manual Refresh must recover without retrying
   the write. Validate runtime/permanent behavior across an external reload only
   when independently safe to do so.
7. Check actual Matugen light/dark themes and narrow Settings widths. Structured
   forwarding, policy/default-zone editing and definition deletion/duplication
   must be clearly unavailable, with no inert success controls.
