# 雷神猎刃16 / THUNDEROBOT LieRen 16 Battery80 v0.2.1


新外观同步到独立exe：黑金配色、切角卡片、电量圆环、80%刻度、功率/容量/供电显示和诊断详情。控制协议、读回、身份白名单、签名/哈希、故障锁和监督恢复不变。

- 运行附件：Battery80-NLYA-v0.2.1-Windows-x64.zip，完整解压后双击BatteryPanel.exe，保留_internal与drivers。
- 源码附件：Battery80-NLYA-v0.2.1-Source.zip，解压后目录内容用于GitHub仓库。
- 两个附件的校验值见SHA256SUMS.txt。

免Python/PowerShell7安装、免ROM导入。首次确认部署与临时签名驱动，真实打开需UAC；面板启动不自动开启80%。仅支持THUNDEROBOT NLYA / TP181 / IT5570 rev07 / C009A0。高于80%可能主动放电；正常成功关闭保持策略，取消需重新打开。

升级建议完整解压到新目录，保留并先审查旧部署日志。新版本不继承旧目录绑定，不自动重绑、搬移故障日志或取消策略；不得借新目录绕过未解决的硬件故障。原本机生产程序不被发布包覆盖。

软件测试、独立运行包自检与模拟UI验证见 [RELEASE_VALIDATION.json](RELEASE_VALIDATION.json)。本次不读取真实电池、不加载驱动或发送EC控制。完整充电、30分钟保持、睡眠/重启仍需独立验收。内置分析记录不是运行固件全哈希证明；原创开源许可证待指定。

## 项目命名与实测参考更新

仓库改名为Thunderobot-LieRen16-Battery80，加入[实测型号](docs/TESTED_MODEL.md)与脱敏采样。运行附件仍为原0.2.1字节/哈希/文件名；本次只更新文档和仓库信息，没有新硬件调用。Release源码附件是原发布快照，最新文档见main分支。
