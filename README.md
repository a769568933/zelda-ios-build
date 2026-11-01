# iPhone touch-controls build

Build support for two floating sticks with locked touch-down origins, limited knobs and axes, and return to neutral on release. This repository contains open-source controls and build tools only. Game files, keys, existing app binaries and shader libraries are not uploaded.

本项目默认使用 **Mac 本地 Xcode 编译**。GitHub 仅保存源码，自动编译已关闭，保留手动工作流备用。需要完整 Xcode、iPhoneOS SDK 和 Python 3.11+。

在 Mac 上双击 `Build-Local.command`，或在项目目录执行：

```sh
bash tools/build_local.sh --check
bash tools/build_local.sh
```

每次编译生成独立的 `build/local.XXXXXX/` 目录，包含两个未签名模块和编译信息。给脚本传入当前兼容的未签名 IPA，可在编译后自动加入独立 16:9 外接屏支持：

```sh
bash tools/build_local.sh "/path/Current-Unsigned.ipa" "/path/TV16x9-Unsigned.ipa"
```

此打包步骤保留输入 IPA 已有的触控模块，不自动替换它。输出 IPA 不签名、不安装；画面、完整游戏运行和持续 60 FPS 仍需设备测试。当前源码包不包含游戏 IPA。详见 [BUILD.md](BUILD.md)。

Optional independent 16:9 TV output is built as `DmExternalDisplay.dylib`.
See [external display setup and validation scope](docs/EXTERNAL_DISPLAY.md).

