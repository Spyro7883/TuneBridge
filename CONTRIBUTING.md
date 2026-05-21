# Contributing to TuneBridge

Thanks for your interest in TuneBridge. Contributions, bug reports, and feature suggestions are welcome.

## Reporting bugs

Open an [issue](https://github.com/Spyro7883/TuneBridge/issues) and include:

- TuneBridge version (commit SHA or release tag)
- Operating system and Python version
- Steps to reproduce
- Expected vs. actual behavior
- Relevant error messages or stack traces (full text, not screenshots)
- Sample input URLs that trigger the bug, if applicable

Do **not** include your iBroadcast credentials or any private data in issues.

## Suggesting features

Open an issue with the `enhancement` label and describe:

- The use case you're trying to solve
- How it would integrate with the existing pipeline (Spotify URL → YouTube match → download → organize → upload)
- Any design ideas, but stay open to alternative implementations

## Development setup

```bash
git clone https://github.com/Spyro7883/TuneBridge.git
cd TuneBridge
pip install -r requirements.txt
pip install pytest pytest-asyncio pytest-mock
cp .env.example .env  # fill in iBroadcast credentials for upload tests
```

Run the test suite:

```bash
python -m pytest tests/ -v
```

Run the app:

```bash
python tunebridge.py
```

## Pull requests

- Branch from `master`
- Keep PRs focused on one change (bug fix, feature, refactor)
- Add or update tests for any behavioral change
- Ensure `python -m pytest tests/` passes locally before opening the PR
- Match the existing code style (no enforced formatter — just follow surrounding patterns)
- Reference any related issue in the PR description

## Code style

- Python 3.11+ features are fine (`list[int]`, `int | None`, etc.)
- Standard library `logging` for diagnostics — never `print()` in production paths
- No `requests` calls with `verify=False` (TLS verification must stay on)
- Subprocess calls always use argv lists, never `shell=True`
- Threading: prefer `ThreadPoolExecutor` over raw `Thread`; use `threading.Lock` for shared mutable state

## What's out of scope

- Spotify Web API integration (the public-page scraping approach is intentional)
- Sources other than Spotify and YouTube (Apple Music, SoundCloud, etc.)
- In-app playback / streaming
- Automatic background polling

If your idea falls in one of these areas, it's better suited to a fork.
