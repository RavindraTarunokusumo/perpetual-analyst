"""typer CLI app. Installed as `analyst` script via pyproject.toml. See SPEC §3."""

# TODO (Task 1/5): Implement
# Commands:
#   analyst topic add NAME --brief TEXT
#   analyst topic list
#   analyst source add --topic SLUG --type rss --url URL [--name NAME]
#   analyst source list --topic SLUG
#   analyst run [--topic SLUG] [--dry-run]
#   analyst report show [--date YYYY-MM-DD]
#
# Use typer. Load .env on startup with python-dotenv.

import typer

app = typer.Typer(help="Perpetual Analyst CLI")

topic_app = typer.Typer()
source_app = typer.Typer()
report_app = typer.Typer()

app.add_typer(topic_app, name="topic")
app.add_typer(source_app, name="source")
app.add_typer(report_app, name="report")


@app.command()
def run(
    topic: str = typer.Option(None, help="Topic slug to run (default: all active)"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Print prompt, skip API calls"),
) -> None:
    """Run the daily analyst pipeline."""
    raise NotImplementedError("TODO Task 10")


if __name__ == "__main__":
    app()
