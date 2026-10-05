# 开发与构建

开发使用Windows x64 Python3.12（含Tk），模块仅用标准库。测试命令：

```powershell
python -B -m unittest discover -s tests
python -B portable_entry.py --preview
```

测试使用模拟EC，不加载驱动、不查询真实电池。无参数只显示部署确认页；真实控制另需确认、UAC和全部预检。不要直接运行保留的历史trial/query入口。

构建：`python -B scripts/build_runtime.py`。依赖由build-requirements.txt锁版本及wheel哈希，pip仅安装到源码目录.build/deps；缓存、临时文件、spec、产物均在.build，不能覆盖已有构建。只在Windows x64 Python3.12执行，不全局安装PyInstaller。

输出.build/dist/BatteryPanel：完整文件夹运行，不能只提取exe。脚本只构建与复制许可，不运行实机控制；自行打包后需独立解压、模拟和硬件验收。Python/Tk版本来自构建解释器，重建二进制哈希不保证一致。

项目发布采用PyInstaller6.22.3 onedir/windowed，无UPX；未修改bootloader。冻结子进程设置PYINSTALLER_RESET_ENVIRONMENT=1并调用同一exe，源码模式调用portable_entry.py；不把python参数-B传给exe。

原协议、Backend控制/故障日志、监督恢复和服务生命周期保留。便携适配在portable_runtime.py、portable_entry.py、预检候选校验、PowerShell路径/UTF8和子进程启动。

参考：[构建参数](https://pyinstaller.org/en/stable/usage.html)、[运行路径](https://pyinstaller.org/en/stable/runtime-information.html)、[独立子进程](https://pyinstaller.org/en/stable/advanced-topics.html#independent-subprocesses-and-process-restarting)。

构建脚本会生成产物SHA256清单和标记“本地重建尚未验证”的RELEASE_VALIDATION.json，避免将旧发布验收误用于新二进制。当前源码VERSION是0.2.1-portable，PACKAGING_REVISION标记r3黑金发布修订。
