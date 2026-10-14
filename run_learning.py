"""One-command PowerShell entrypoint for the editable DeepReason learning assistant."""
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "workbench" / "deepreason" / "src"))

from reasoning_agent_template.learning import main  # noqa: E402


if __name__ == "__main__":
    arguments = sys.argv[1:]
    if not arguments:
        arguments = ["--interactive"]
    raise SystemExit(main(arguments))
