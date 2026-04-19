# Glutz eAccess — Home Assistant Integration

A custom [Home Assistant](https://www.home-assistant.io/) integration for the [Glutz eAccess](https://www.glutz.com/) cloud-based access control system. Control and monitor your Glutz eAccess doors directly from Home Assistant.

## Development

### Running the tests

The test suite requires Python 3.12 and runs under Linux (or WSL on Windows — the native Windows interpreter is not supported due to a transitive `lru-dict` dependency that requires MSVC++ build tools on Windows).

**First-time setup** — create a virtual environment and install the dependencies:

```bash
python3.12 -m venv ~/venvs/glutz
source ~/venvs/glutz/bin/activate
pip install -r requirements_test.txt
```

**Run the suite:**

```bash
source ~/venvs/glutz/bin/activate
pytest tests/ -q
```

From a Windows terminal via WSL:

```bash
wsl -- bash -c "source ~/venvs/glutz/bin/activate && cd /mnt/c/Users/<user>/Workspace/hass-glutz-eaccess && pytest tests/ -q"
```