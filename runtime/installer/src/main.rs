mod tui;

use endless_setup::{Action, Engine, doctor};
use std::ffi::{OsStr, OsString};
use std::path::PathBuf;

const HELP: &str = "endless-setup — EXPERIMENTAL SANDBOX ONLY

Usage:
  endless-setup plan --sandbox DIR --manifest FILE [--action install|update|repair|uninstall]
  endless-setup install|update|repair --sandbox DIR --manifest FILE [--yes]
  endless-setup uninstall --sandbox DIR [--yes]
  endless-setup recover --sandbox DIR --yes
  endless-setup doctor [--manifest FILE] [--sandbox DIR]
  endless-setup tui --sandbox DIR [--manifest FILE]

Options:
  --sandbox, --root DIR  Existing private sandbox directory under canonical /tmp.
  --manifest FILE       Declarative subset bundle manifest (relative payload sources).
  --action ACTION       Action to preview with plan (default: install).
  --allow-replace       Permit explicitly planned backups of preexisting managed files.
                        Never overrides files modified after this engine installed them.
  --dry-run             Print the exact plan; never creates destination or state files.
  --json                Machine-readable JSON output (errors go to stderr as JSON).
  --yes                 Explicitly confirm a mutating CLI operation in the sandbox.
  -h, --help            Print this help without requiring a terminal or sandbox.
  -V, --version         Print version.

This MVP installs a representative SUBSET only, not a usable desktop.
Complete installation, integration with an existing Hyprland session, dependency
installation and service changes are NOT IMPLEMENTED. Real host targets are denied.
No sudo, package-manager invocation, shell commands or session restart is performed.
";

#[derive(Debug)]
pub(crate) struct Options {
    pub command: String,
    pub sandbox: Option<PathBuf>,
    pub manifest: Option<PathBuf>,
    pub action: Action,
    pub allow_replace: bool,
    pub dry_run: bool,
    pub json: bool,
    pub yes: bool,
}

fn parse_action(text: &str) -> Result<Action, String> {
    match text {
        "install" => Ok(Action::Install),
        "update" => Ok(Action::Update),
        "repair" => Ok(Action::Repair),
        "uninstall" => Ok(Action::Uninstall),
        _ => Err(format!("Unknown action: {text}")),
    }
}

fn parse(args: Vec<OsString>) -> Result<Options, String> {
    let mut args = args.into_iter();
    let command = args
        .next()
        .ok_or("A subcommand is required. Use --help.")?
        .into_string()
        .map_err(|_| "The subcommand must be UTF-8.")?;
    if ![
        "plan",
        "install",
        "update",
        "repair",
        "uninstall",
        "recover",
        "doctor",
        "tui",
    ]
    .contains(&command.as_str())
    {
        return Err(format!("Unknown subcommand: {command}. Use --help."));
    }
    let mut options = Options {
        command,
        sandbox: None,
        manifest: None,
        action: Action::Install,
        allow_replace: false,
        dry_run: false,
        json: false,
        yes: false,
    };
    let mut action_set = false;
    while let Some(arg) = args.next() {
        match arg.to_str().ok_or("Option names must be UTF-8.")? {
            "--sandbox" | "--root" => {
                if options.sandbox.is_some() {
                    return Err("Specify the sandbox only once.".into());
                }
                options.sandbox = Some(PathBuf::from(args.next().ok_or("Missing sandbox path.")?));
            }
            "--manifest" => {
                if options.manifest.is_some() {
                    return Err("Specify the manifest only once.".into());
                }
                options.manifest =
                    Some(PathBuf::from(args.next().ok_or("Missing manifest path.")?));
            }
            "--action" => {
                if options.command != "plan" || action_set {
                    return Err("--action is allowed once, with plan only.".into());
                }
                options.action = parse_action(
                    args.next()
                        .ok_or("Missing action.")?
                        .to_str()
                        .ok_or("Action must be UTF-8.")?,
                )?;
                action_set = true;
            }
            "--allow-replace" => options.allow_replace = true,
            "--dry-run" => options.dry_run = true,
            "--json" => options.json = true,
            "--yes" => options.yes = true,
            _ => return Err(format!("Unknown option: {}", arg.to_string_lossy())),
        }
    }
    Ok(options)
}

pub(crate) fn pretty(value: &impl serde::Serialize) -> Result<String, String> {
    serde_json::to_string_pretty(value).map_err(|e| e.to_string())
}

fn run(options: Options) -> Result<(), String> {
    if options.command == "doctor" {
        let sandbox = options
            .sandbox
            .as_ref()
            .map(|root| {
                Engine::open(root)
                    .and_then(|engine| engine.inspect())
                    .map_err(|e| e.to_string())
            })
            .transpose()?;
        let report = doctor(options.manifest.as_deref()).map_err(|e| e.to_string())?;
        if !options.json {
            println!("EXPERIMENTAL SANDBOX ONLY — read-only diagnostics");
        }
        println!(
            "{}",
            pretty(&serde_json::json!({"host": report, "sandbox": sandbox}))?
        );
        return Ok(());
    }
    if options.command == "tui" {
        if options.json || options.dry_run || options.yes {
            return Err(
                "tui uses its own plan and confirmation; omit --json/--dry-run/--yes.".into(),
            );
        }
        return tui::run(&options);
    }
    let sandbox = options
        .sandbox
        .as_deref()
        .ok_or("--sandbox DIR is mandatory. Real host installation is disabled.")?;
    let engine = Engine::open(sandbox).map_err(|e| e.to_string())?;
    if options.command == "recover" {
        if options.dry_run {
            return Err("Recovery is mutating. Use plan/doctor for read-only inspection; omit --dry-run and add --yes to recover.".into());
        }
        if !options.yes {
            return Err("Recovery requires explicit --yes inside the sandbox.".into());
        }
        let report = engine.recover().map_err(|e| e.to_string())?;
        println!("{}", pretty(&report)?);
        return Ok(());
    }
    let action = if options.command == "plan" {
        options.action
    } else {
        parse_action(&options.command)?
    };
    let plan = engine
        .plan(action, options.manifest.as_deref(), options.allow_replace)
        .map_err(|e| e.to_string())?;
    if !options.json {
        println!(
            "EXPERIMENTAL SANDBOX ONLY — representative subset; desktop installation incomplete"
        );
    }
    if options.command == "plan" || options.dry_run {
        println!("{}", pretty(&plan)?);
        return if plan.blocked.is_empty() {
            Ok(())
        } else {
            Err("Plan blocked; no changes applied.".into())
        };
    }
    if !options.yes {
        println!("{}", pretty(&plan)?);
        return Err("No changes applied. Review the plan and explicitly pass --yes to apply it inside the sandbox.".into());
    }
    let report = engine.execute(&plan).map_err(|e| e.to_string())?;
    println!("{}", pretty(&report)?);
    Ok(())
}

fn main() {
    let args: Vec<OsString> = std::env::args_os().skip(1).collect();
    if args.iter().any(|arg| arg == "--help" || arg == "-h") {
        print!("{HELP}");
        return;
    }
    if args.len() == 1 && [OsStr::new("--version"), OsStr::new("-V")].contains(&args[0].as_os_str())
    {
        println!(
            "endless-setup {} (experimental sandbox subset)",
            env!("CARGO_PKG_VERSION")
        );
        return;
    }
    let json = args.iter().any(|arg| arg == "--json");
    if let Err(error) = parse(args).and_then(run) {
        if json {
            eprintln!("{}", serde_json::json!({"ok": false, "error": error}));
        } else {
            eprintln!("endless-setup: {error}");
        }
        std::process::exit(1);
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn options(arguments: &[&str]) -> Result<Options, String> {
        parse(arguments.iter().map(OsString::from).collect())
    }

    #[test]
    fn preview_has_no_implicit_confirmation_or_replacement() {
        let options = options(&[
            "plan",
            "--sandbox",
            "/tmp/example",
            "--manifest",
            "bundle.json",
        ])
        .expect("valid preview arguments");
        assert!(!options.yes);
        assert!(!options.allow_replace);
        assert!(matches!(options.action, Action::Install));
    }

    #[test]
    fn unknown_duplicate_and_misplaced_options_fail() {
        assert!(options(&["install", "--action", "uninstall"]).is_err());
        assert!(options(&["plan", "--sandbox", "/tmp/a", "--root", "/tmp/b"]).is_err());
        assert!(options(&["plan", "--manifest", "a", "--manifest", "b"]).is_err());
        assert!(options(&["plan", "--host"]).is_err());
        assert!(options(&["install-complete"]).is_err());
        assert!(options(&["integrate-hyprland-existing"]).is_err());
    }

    #[test]
    fn destructive_flags_are_explicit() {
        let options = options(&[
            "update",
            "--root",
            "/tmp/example",
            "--allow-replace",
            "--dry-run",
            "--yes",
            "--json",
        ])
        .expect("valid explicit flags");
        assert!(options.yes && options.allow_replace && options.dry_run && options.json);
    }

    #[test]
    fn non_utf8_sandbox_argument_does_not_panic() {
        use std::os::unix::ffi::OsStringExt;
        let path = OsString::from_vec(b"/tmp/sandbox-\xff".to_vec());
        let options = parse(vec!["plan".into(), "--sandbox".into(), path.clone()])
            .expect("paths do not require UTF-8");
        assert_eq!(options.sandbox, Some(PathBuf::from(path)));
    }
}
