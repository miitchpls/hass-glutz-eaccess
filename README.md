# Glutz eAccess — Home Assistant Integration

A [Home Assistant](https://www.home-assistant.io/) integration for the [Glutz eAccess](https://www.glutz.com/) cloud-based access control system. Control and monitor your Glutz eAccess doors directly from Home Assistant.

![Dashboard](./assets/5-dashboard.jpg)
![Lock entity](./assets/6-lock.jpg)

> **Status:** this integration is being submitted for inclusion in Home Assistant core. Once merged, it will be available out of the box and this repository may be archived.

## Manual installation (until available in HA core)

Run the following command on your Home Assistant instance:

```sh
wget -O - https://raw.githubusercontent.com/miitchpls/hass-glutz-eaccess/main/install | bash -
```

### Configuration
<a href="https://my.home-assistant.io/redirect/config_flow_start/?domain=glutz_eaccess" target="_blank"><img src="https://my.home-assistant.io/badges/config_flow_start.svg" alt="Open your Home Assistant instance and start setting up a new integration." /></a>

![Choose a login method](./assets/2-choose_login.jpg)

![Sign in](./assets/3-sign_in.jpg)

![Devices created](./assets/4-devices_created.jpg)

> **Note:** the `pyglutz-eaccess` Python dependency is installed automatically by Home Assistant on first start after installation.

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

## Documentation

See the [full documentation](./documentation.markdown)

