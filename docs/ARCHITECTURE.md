# 面板、监督进程与EC的控制链

```mermaid
flowchart TD
  A[便携exe启动页与UAC] --> B[冻结exe监督进程]
  B --> C[临时签名InpOut驱动]
  B --> D[Tk界面子进程]
  D --> E[单线程队列与固定协议]
  E --> C
  C --> F[PMC2 0x6C / 0x68]
  F --> G[IT5570运行期RAM]
  G --> H[EC原厂主循环与充电管理]
  I[Windows电池遥测] --> D
  D --> J[已验证状态正常关闭]
  J --> B
  B --> K[停止并删除本次临时驱动登记]
```

设置参数后EC持续执行，窗口每15秒刷新，关闭后不再刷新。正常退出不取消成功设置的策略；驱动消失不等于策略消失。

tools/battery_panel.py负责UI、队列、日志和监督；battery_panel_core.py负责固定策略和完整状态验证；nlya_pmc2_query.py负责固定地址读取；nlya_policy_trial.py提供当前面板导入的传输、遥测与恢复判据；inpout_status_probe.py负责签名与服务生命周期。widgets与dpi模块只负责绘制。

控制意图在I/O前持久记录。完整事务之前置unsafe，完成后才置safe；未完成事务、读回异常和恢复故障跨启动形成门控。正常退出需要关闭标记、有效末次状态、没有未完成/故障及子进程exit0共同成立。日志失败时仍努力清理驱动，但不会声明正常退出通过。

冻结exe绘制进程在创建Tk前设置DPI上下文，以DPI/72设字体、DPI/96换算布局。每个绘制子进程独立初始化。当前仅启动时按显示器工作区初始化；运行中跨不同DPI显示器自动重排未实现/验收。

quanta_bridge_probe.py是原厂CCDRV1历史探测及模拟测试依赖，未使用的原厂二进制不随包发布；它不是生产入口。nlya_policy_trial.py的独立短时实验也不是日常入口，不批量执行tools脚本。
