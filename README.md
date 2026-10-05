# Battery80 NLYA · 便携运行版

面向 **THUNDEROBOT NLYA / BIOS TP181 / IT5570 rev07 / EC C009A0** 的原厂固定80%电池维护面板。营销型号或同模具不足以证明兼容。

普通使用者从 GitHub Releases 下载 `Battery80-NLYA-v0.2.1-Windows-x64.zip`，完整解压后双击 `BatteryPanel.exe`。**不需要安装 Python、PowerShell7，不需要首次导入 ROM。** exe需要同目录 `_internal` 与 `drivers`，不要只复制exe。

首次确认部署目录及临时签名驱动登记，然后点击“打开真实面板”并接受UAC。面板启动只读取状态；开启80%需要单独点击。只想看外观可选择“查看模拟演示”，不加载驱动。

高于80%时原厂策略可能主动放电，低于80%允许充电。成功开启后关闭窗口继续保持；恢复正常充电需重新打开点击“取消维护”。不是75/80双阈值，不保证睡眠、重启或掉电保持。

运行包保留实际身份、驱动签名/哈希、固定协议、故障日志与恢复检查。内置分析记录只记录逆向来源及结论，**不能证明运行EC镜像全哈希一致**。不包含BIOS/EC固件字节。

本机旧版本已有设置、回读、取消与约一分钟80%保持证据；本发布包做离线测试和模拟启动，不继承新路径实机验收。完整低电量充至80%、30分钟、两轮、睡眠/重启测试尚未完成。

- [运行与取消](docs/USAGE.md)、[部署与目录绑定](docs/DEPLOYMENT.md)
- [兼容范围](docs/COMPATIBILITY.md)、[故障处理](docs/TROUBLESHOOTING.md)
- [协议](docs/PROTOCOL.md)、[架构](docs/ARCHITECTURE.md)、[可复用逆向教程](docs/TUTORIAL.md)
- [构建](docs/DEVELOPMENT.md)、[验证](docs/VALIDATION.md)、[GitHub发布](docs/GITHUB_UPLOAD.md)
- [许可状态](LICENSE_STATUS.md)、[第三方许可](THIRD_PARTY_NOTICES.md)

源码入口 `portable_entry.py`。旧模块保留复用的协议和生命周期代码，不直接运行历史trial/query脚本。开发测试：`python -B -m unittest discover -s tests`。默认无参数只显示启动确认页。

## 0.2.1 · 黑金面板

本版把本机最新的黑金外观同步到便携exe：深黑背景、金色目标/电量环、切角卡片与诊断详情。充电协议、身份/签名/哈希、故障锁和恢复逻辑保持。

[项目目录](docs/PROJECT_LAYOUT.md)、[发布说明](RELEASE_NOTES.md)、[外观说明](docs/APPEARANCE.md)。GitHub Download ZIP是源码；下载Release运行附件才有exe。

![黑金面板模拟预览，非实时状态](assets/preview-holding.png)
