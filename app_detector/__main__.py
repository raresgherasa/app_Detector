"""Entry point: ``python -m app_detector`` → CLI."""

from app_detector.cli import cli


def main() -> None:
    cli(prog_name="appdetect")


if __name__ == "__main__":
    main()
