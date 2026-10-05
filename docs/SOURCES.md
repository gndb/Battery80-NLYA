# 来源、版本与归属

公开仓库保存源码及自主整理的摘要，没有包含上游仓库、厂商固件、反编译完整材料；运行包按原许可附带签名驱动。[SOURCES.json](SOURCES.json)列本地冻结仓库commit、镜像哈希及驱动来源；本页链接当前网站不代表本地快照会自动更新。

| 来源 | 借鉴范围 |
|---|---|
| [Mechrevo-Xingyao-14](https://github.com/YMGPwcca/Mechrevo-Xingyao-14) | Windows软件到EC的定位与回读验证；不复用其地址 |
| [excalibur](https://github.com/thekayrasari/excalibur) | 同协议族OEM WMI线索；同GUID不等于充电兼容 |
| [casper-wmi](https://github.com/Mustafa-eksi/casper-wmi) | Windows/OEM接口族对照 |
| [Lecoo-Control-Center](https://github.com/LaVashikk/Lecoo-Control-Center) | 平台配置与访问层研究 |
| [Highrez InpOut](https://www.highrez.co.uk/Downloads/InpOut32/default.htm) | 临时签名端口访问驱动来源；以实际下载许可证及哈希为准 |
| [微软DPI说明](https://learn.microsoft.com/windows/win32/hidpi/setting-the-default-dpi-awareness-for-a-process) | Python绘制进程初始化时机 |
| [SetProcessDpiAwarenessContext](https://learn.microsoft.com/windows/win32/api/winuser/nf-winuser-setprocessdpiawarenesscontext) | 原生DPI上下文API |

雷神、神舟、七彩虹控制中心离线对照用于识别NLYA家族与命令，但本发布不再分发这些安装包/DLL。固件及OEM软件归原权利人，原机合法导出的ROM不因本项目研究而获得公开再分发授权。

公开采样来自原机保存的一分钟只读Windows遥测；仅选择电量、供电、功率、容量和采样时间。原始JSON、路径、设备标识与完整会话留在本地。截图来自模拟界面。

感谢上游作者及驱动提供者。仓库许可证如后续选定只覆盖本项目原创源码和说明，不替换上游许可证。见 [第三方说明](../THIRD_PARTY_NOTICES.md)。
