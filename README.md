# Glutz eAccess — Home Assistant Integration

A [Home Assistant](https://www.home-assistant.io/) integration for the [Glutz eAccess](https://www.glutz.com/) cloud-based access control system. Control and monitor your Glutz eAccess doors directly from Home Assistant.

> **Status:** this integration is being submitted for inclusion in Home Assistant core. Once merged, it will be available out of the box and this repository will be archived. In the meantime, it can be installed manually as a custom component (see below).

## Manual installation (until available in HA core)

1. Download or clone this repository.
2. Copy the `homeassistant/components/glutz_eaccess/` folder into the `custom_components/` directory of your Home Assistant configuration:
   ```
   <config>/custom_components/glutz_eaccess/
   ```
3. Open `custom_components/glutz_eaccess/manifest.json` and add a `version` field — Home Assistant requires it for custom components:
   ```json
   "version": "0.1.0"
   ```
4. Restart Home Assistant.
5. Go to **Settings → Devices & Services → Add Integration**, search for **Glutz eAccess** and follow the setup wizard.

> **Note:** the `pyglutz-eaccess` Python dependency is installed automatically by Home Assistant on first start after installation.

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