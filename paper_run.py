import argparse
import os


def build_argument_parser():
    parser = argparse.ArgumentParser(
        description="Run the Binance Futures bot in safe dry-run mode for a fixed number of cycles."
    )
    parser.add_argument("--cycles", type=int, default=3, help="Number of bot cycles to run.")
    parser.add_argument("--sleep-seconds", type=int, default=5, help="Seconds to wait between cycles.")
    parser.add_argument("--symbol-allowlist", default="", help="Comma-separated symbols to scan.")
    parser.add_argument("--max-symbol-scan", type=int, default=3, help="Maximum symbols to scan each cycle.")
    parser.add_argument(
        "--journal-file",
        default="runtime/paper-run.jsonl",
        help="Where to write JSONL journal entries.",
    )
    parser.add_argument(
        "--state-file",
        default="runtime/paper-run-state.json",
        help="Where to store runtime state for the paper run.",
    )
    return parser


def build_env_updates(args):
    return {
        "DRY_RUN": "true",
        "USE_TESTNET": "true",
        "RUN_ONCE": "false",
        "SYMBOL_ALLOWLIST": args.symbol_allowlist,
        "MAX_SYMBOL_SCAN": str(args.max_symbol_scan),
        "JOURNAL_FILE": args.journal_file,
        "STATE_FILE": args.state_file,
    }


def apply_env_updates(env_updates):
    for key, value in env_updates.items():
        os.environ[key] = value


def main():
    parser = build_argument_parser()
    args = parser.parse_args()
    apply_env_updates(build_env_updates(args))

    from bot import main as run_bot
    from journal import append_journal_entry

    append_journal_entry(
        "paper_run_started",
        {
            "cycles": args.cycles,
            "sleep_seconds": args.sleep_seconds,
            "symbol_allowlist": args.symbol_allowlist,
            "max_symbol_scan": args.max_symbol_scan,
        },
    )
    run_bot(max_cycles=args.cycles, sleep_seconds=args.sleep_seconds)
    append_journal_entry(
        "paper_run_completed",
        {
            "cycles": args.cycles,
            "sleep_seconds": args.sleep_seconds,
            "symbol_allowlist": args.symbol_allowlist,
            "max_symbol_scan": args.max_symbol_scan,
        },
    )


if __name__ == "__main__":
    main()
