# THUNDEROBOT LieRen 16 (雷神猎刃16 / R16) Battery80

[中文](README.md) · [Download Windows runtime](https://github.com/gndb/Thunderobot-LieRen16-Battery80/releases/tag/v0.2.1) · [Tested machine and evidence](docs/TESTED_MODEL.md)

For **雷神猎刃16 / THUNDEROBOT LieRen 16 (system model R16)**. LieRen is the pinyin spelling of the Chinese product name, not a claim of compatibility with another international product family.

Tested reference: **THUNDEROBOT R16 / NLYA / TP181 / IT5570 rev07 / C009A0**, Intel Core i9-13900HX. The full SKU and GPU configuration have not been confirmed from saved evidence. The original machine has setting, read-back, cancel and close/reopen persistence evidence. Later saved snapshots show Windows 79%, EC 80%, AC connected and 0 W charging/discharging. These sparse samples do not certify a continuous 30-minute test. See [tested model](docs/TESTED_MODEL.md).

Windows x64 native 80% battery maintenance panel for **THUNDEROBOT NLYA / TP181 / IT5570 rev07 / C009A0** only.

Download the runtime ZIP from GitHub Releases, extract the entire folder, and double-click `BatteryPanel.exe`. No Python installation, PowerShell7, or ROM import is required. Keep `_internal` and `drivers` next to the exe.

Confirm the deployment folder and temporary signed driver use; choose Open Panel and accept UAC. Launch reads state only; enabling is a separate action. Simulation preview requires no driver. Above 80% the OEM policy may actively discharge. Successful close keeps the policy; reopen and cancel maintenance to restore default charging.

The embedded analysis record is provenance, not cryptographic attestation of the running EC image. Hardware identity, driver signature/hash, fixed commands, fault journals and recovery gates remain. No BIOS/EC firmware bytes are distributed.

The packaged release has offline/simulation validation only. Prior machine-specific observations do not certify a new deployment, full charging cycles, sleep or reboot persistence. See [validation](docs/VALIDATION.md), [usage](docs/USAGE.md), [building](docs/DEVELOPMENT.md), [license status](LICENSE_STATUS.md) and [third-party notices](THIRD_PARTY_NOTICES.md).

Version 0.2.1 includes the current black-and-gold panel. Charging protocol, identity checks, fault locks and recovery behavior remain unchanged. The application was rebuilt and validated offline; no new live hardware acceptance is implied. See [release notes](RELEASE_NOTES.md).
