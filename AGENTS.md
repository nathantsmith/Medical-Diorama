# Repository Guidelines

## Project Structure & Module Organization
`main.py` is the entry point that starts the monitor, X-ray viewer, and web portal processes. Runtime configuration lives in `config.py` and secrets are loaded from `.env`.

Core modules are split by subsystem:
- `monitor/`: SPI display driver, renderer, process loop, and waveform generation.
- `xray/`: HDMI slideshow, gestures, and per-display process logic.
- `web/`: Flask app, auth, and route modules for monitor, status, and X-ray controls.
- `shared/`: multiprocessing state creation and shared helpers.
- `tests/`: pytest coverage for shared state, waveforms, and web routes.
- `data/xrays/`: image content used by the X-ray viewer.

## Build, Test, and Development Commands
- `python -m venv .venv && source .venv/bin/activate`: create and activate a local virtualenv.
- `pip install -r requirements.txt`: install runtime and test dependencies.
- `python main.py --mock-hardware`: run the full app without Raspberry Pi hardware.
- `python main.py --no-monitor` or `--no-xray`: isolate one subsystem during development.
- `python -m pytest tests`: run the full test suite.

If you use the checked-in virtualenv, prefer `.venv/bin/python main.py --mock-hardware` and `.venv/bin/python -m pytest tests`.

## Coding Style & Naming Conventions
Target Python 3.11+ and follow existing PEP 8-style conventions: 4-space indentation, `snake_case` for functions and variables, `CapWords` for classes, and uppercase module constants such as `XRAY_DISPLAYS`. Keep modules aligned to one subsystem and preserve the current pattern of short docstrings on public classes and functions.

No formatter or linter is configured in `pyproject.toml`; match the surrounding style and keep imports simple and explicit.

## Testing Guidelines
Tests use `pytest` and follow the `tests/test_<area>.py` naming pattern. Add or update tests whenever you touch shared state, waveform math, or Flask routes. There is no explicit coverage gate, so focus on behavior that could regress: state defaults, API validation, image discovery, and display timing logic.

## Commit & Pull Request Guidelines
Recent commits use concise, imperative summaries such as `Fix web UI alarms being overridden by auto-threshold check` and `Rewrite SPI driver for Seengreat 2" LCD`. Follow that format: start with a verb, name the subsystem, and keep the subject specific.

Pull requests should describe the user-visible change, list hardware or mock-mode validation performed, and include screenshots for web or display-facing changes when relevant. Link any related issue and call out config or environment changes explicitly.
