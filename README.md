# KyDevTool-python
Python version of the KyDevTool flashing utility. A tool for writing to
`Ky X1` boards via `MaskROM`/`fastboot` mode.

This QT6 app has been made by just mimicking what the original tool does.

## Compatibility
This tool has been tested with the OrangePi `R2S`. 

It can practically work with the `RV2`/other boards as well but i can't guarantee that the `factory/` blobs
are compatible

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
The original tool always flashes `bootinfo_sd.bin` no matter what board is connected. To me, that sounds kinda counter-productive 
(as the `R2S` board doesn't have Micro SD Card slot) so i made `bootinfo_emmc.bin` the default. If that causes problems switch back 
to `bootinfo_sd.bin`

## Original source
The original tool can be found in [this shared google drive](https://drive.google.com/drive/folders/1gYQgScW-yQKJDVb23ym3kDw8F4_afjbM) 
by the manufacturer. Archive the contents please

## Requirements
- Python 3.10 or newer
- Installed `PyQt6`, `pyqt6_sip` pip packages

## Disclaimer
This project is not affiliated or associated with Orange Pi, Shenzhen Xunlong Software Co., Ltd., or SpacemiT
