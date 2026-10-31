# KyDevTool-python
Python version of the KyDevTool flashing utility. A tool for writing to
`Ky X1` boards via `MaskROM`/`fastboot` mode.

This QT6 app has been made by just mimicking what the original tool does.

## Compatibility
This tool has been tested with the OrangePi `R2S`. 

It can practically work with the `RV2`/other boards as well but i can't guarantee that the `factory/` blobs
are compatible

Also, flashing custom OpenWRT builds may not be possible at the current state of `spacemit/ky` bringup

## How to use
1. Install `python` requirements
```shell
pip install -r requirements.txt
```

2. Run the app
```shell
python gui.py
```

## `Bootinfo`
This partition is used to set the boot order for the target board. The original tool always flashes `bootinfo_sd.bin` no matter the board,
but considering the `R2S` (for example) doesn't even have Micro SDCard slot, i set `bootinfo_emmc.bin` as the default.

## Sources
The original tool can be found in [this shared google drive](https://drive.google.com/drive/folders/1gYQgScW-yQKJDVb23ym3kDw8F4_afjbM) 
by the manufacturer.

[I have uploaded the original tool to archive.org for redundancy here](https://archive.org/details/orangepi-r2s-rv2-ky-dev-tool)

## Requirements
- Python 3.10 or newer
- Installed `PyQt6`, `pyqt6_sip` pip packages
- `fastboot` binary in system PATH

## Disclaimer
This project is not affiliated or associated with Orange Pi, Shenzhen Xunlong Software Co., Ltd., or SpacemiT
