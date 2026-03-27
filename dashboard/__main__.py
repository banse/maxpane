"""Launch the MaxPane dashboard: python -m dashboard"""
import argparse
import logging

from dashboard.app import MaxPaneApp


def main():
    parser = argparse.ArgumentParser(description="MaxPane Dashboard")
    parser.add_argument(
        "--poll-interval",
        type=int,
        default=30,
        help="Poll interval in seconds (default: 30)",
    )
    parser.add_argument(
        "--theme",
        default="matrix",
        choices=["matrix", "minimal", "bloomberg", "htop", "retro", "bakery", "frenpet", "base"],
    )
    parser.add_argument(
        "--game",
        default="bakery",
        choices=["bakery", "frenpet", "base"],
        help="Which game dashboard to show first (default: bakery)",
    )
    parser.add_argument(
        "--wallet",
        default="0x030A3EECeB839031e8632B627BdDefEc50624A51",
        help="Wallet address for FrenPet pet view",
        # TODO: make configurable via settings screen or config file
    )
    parser.add_argument(
        "--log-level",
        default="WARNING",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging verbosity (default: WARNING)",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )

    app = MaxPaneApp(
        poll_interval=args.poll_interval,
        theme=args.theme,
        initial_game=args.game,
        wallet_address=args.wallet,
    )
    app.run()


if __name__ == "__main__":
    main()
