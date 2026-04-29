# Glutz eAccess — Home Assistant Integration

A [Home Assistant](https://www.home-assistant.io/) integration for the [Glutz eAccess](https://www.glutz.com/) cloud-based access control system. Control and monitor your Glutz eAccess doors directly from Home Assistant.

> **Status:** this integration is being submitted for inclusion in Home Assistant core. Once merged, it will be available out of the box and this repository may be archived.  
> Until then, a dedicated `custom-component` branch is available for manual installation.

## Manual installation  (until available in HA core)

This repository includes a dedicated branch for custom installation:

1. Download or clone this repository.

    ```bash
    git clone --branch custom-component --single-branch https://github.com/miitchpls/hass-glutz-eaccess.git
    ```

2. Copy the `glutz_eaccess/` folder into the `custom_components/` directory of your Home Assistant configuration:
    ```
    <config>/custom_components/glutz_eaccess/
    ```
3. Restart Home Assistant. 
4. Go to **Settings → Devices & Services → Add Integration**, search for **Glutz eAccess** and follow the setup wizard.

> **Note:** the `pyglutz-eaccess` Python dependency is installed automatically by Home Assistant on first start after installation.

## Repository branches

- **main**  
  Development branch targeting inclusion in Home Assistant Core.

- **custom-component**  
  Standalone branch for manual installation as a custom integration.

### Running the tests

The test suite lives inside the [home-assistant/core](https://github.com/home-assistant/core) repository and must be run from there. The native Windows interpreter is not supported — use WSL on Windows.

**First-time setup** — clone HA core and create its development venv (Python 3.14):

```bash
git clone https://github.com/home-assistant/core.git
cd core
python3.14 -m venv ~/venvs/hass-core
source ~/venvs/hass-core/bin/activate
pip install -r requirements_test.txt
```

Copy (or symlink) the integration and its tests into the HA core tree:

```
homeassistant/components/glutz_eaccess/   ← integration source
tests/components/glutz_eaccess/           ← test suite
```

**Run the suite:**

```bash
source ~/venvs/hass-core/bin/activate
cd /path/to/core
pytest tests/components/glutz_eaccess -q
```

From a Windows terminal via WSL:

```bash
wsl bash -c "source ~/venvs/hass-core/bin/activate && cd /mnt/c/Users/<user>/Workspace/core && pytest tests/components/glutz_eaccess -q"
```

**Coverage report:**

```bash
pytest tests/components/glutz_eaccess \
    --cov=homeassistant.components.glutz_eaccess \
    --cov-report=term-missing -q
```

**Regenerate snapshots** (needed after changing entity attributes or diagnostics output):

```bash
pytest tests/components/glutz_eaccess --snapshot-update -q
```

Commit the generated `.ambr` files — they are the baseline for snapshot assertions.
