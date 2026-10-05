# 实测参考型号 / Tested reference machine

## 型号与身份

| 字段 | 参考机器 |
|---|---|
| 商品名（使用者提供） | 雷神猎刃16 / THUNDEROBOT LieRen 16 |
| 系统制造商 / 型号 | THUNDEROBOT / R16 |
| 主板 / BIOS | NLYA / TP181 |
| EC芯片 / 修订 | IT5570 / 07 |
| EC运行构建标识 | C009A0 |
| CPU | Intel Core i9-13900HX |
| 固定维护目标 | 80% |
| 完整商品SKU / 显卡配置 | 未确认；不按同系列产品参数推断 |

商品名由使用者确认；R16、主板和BIOS来自保存的系统诊断；CPU来自保存的设备清单；EC信息来自已保存的面板读取。LieRen是“猎刃”的拼音，方便英文检索，不声称其他海外型号等同本机。[雷神官方型号表](https://www.thunderobot.com/new_detail?article_id=581)将多个不同配置列入猎刃16/R16系列，这不能证明它们的EC接口都兼容。

不公开设备序列号、UUID、个人路径或完整原始日志。EC构建标识匹配不是运行固件全镜像哈希证明。兼容性仍以[现有完整白名单](COMPATIBILITY.md)和程序诊断为准。

## 已验证与观察

| 项目 | 本机结果 / 边界 |
|---|---|
| 设置与回读 | 原机生产版本已设置目标80%，三次回读D0 |
| 取消维护 | 已执行取消，Learn请求清除、恢复原厂默认管理；不保证接近满电时立刻充电 |
| 关闭窗口 | 成功开启后关闭、再打开仍目标80%；不推导重启保持 |
| 早期80%保持 | 五次Windows采样约一分钟，80%、0 W、容量50.682 Wh不变 |
| 后续采样1 | 2026-10-05 20:26:57 UTC：Windows79%、EC80%、AC在线、充电0 W、放电0 W、容量50425 mWh |
| 后续采样2 | 2026-10-05 20:49:30 UTC：Windows79%、EC80%、AC在线、充电0 W、放电0 W、容量50395 mWh |
| 后续两份日志 | 目标80、Learn未请求、读取有效、无传输故障；完整字段见脱敏JSON |
| 尚未验收 | 低电量完整充至80%、连续30分钟、两轮充电、睡眠/重启/掉电、新路径便携运行包真实控制 |

两份后续日志相隔约22.5分钟，仅是各会话保存的最后一次采样，不能据此声称全时段连续停充。小幅容量变化也不能单独推断主动放电；需要连续功率、容量及EC状态联合判断。高于80%时原厂策略可能主动放电。

[脱敏采样及原日志SHA256](TESTED_MODEL_SAMPLES.json) · [完整验收矩阵](VALIDATION.md)

## English reference

The user-tested machine is **THUNDEROBOT LieRen 16 (雷神猎刃16), Windows model R16**, motherboard NLYA, BIOS TP181, IT5570 revision 07, runtime build C009A0, Intel Core i9-13900HX. Full SKU/GPU is unconfirmed. Setting, read-back, cancel and close/reopen retention were verified on the original production installation. Saved snapshots show Windows 79%, EC 80%, AC connected and zero charging/discharging power. This is not continuous 30-minute evidence or new portable-package hardware acceptance. Other configurations require independent compatibility verification; do not bypass the guards.
