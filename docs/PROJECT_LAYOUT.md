# 项目目录与包的区别

| 位置 | 用途 |
|---|---|
| portable_entry.py | 首次确认、模拟、真实面板手动入口 |
| tools/ | 面板、协议、恢复、驱动生命周期和便携路径模块 |
| tests/ | 模拟EC/服务、故障与部署门控测试，不访问真实硬件 |
| assets/ | 分析校验记录和明确标记的模拟截图 |
| drivers/ | 固定哈希的原签名InpOut驱动 |
| licenses/ | 第三方许可原文 |
| docs/ | 使用、恢复、兼容、协议、逆向教程、构建、来源与验收 |
| scripts/ | 公开清单检查和项目内构建 |
| .github/ | 模拟测试工作流、Issue/PR模板 |
| evidence/ | 初始父目录；使用后生成的部署/会话日志不随源码上传 |
| .build/ | 本地构建生成物，可重建，不上传 |

运行ZIP里含exe、_internal、drivers、licenses和使用文档；不包含开发解释器或制作缓存。Github源码ZIP含可复用源码及文档，不包含exe。两个ZIP都不含BIOS/EC固件、原厂安装器、私人日志、凭据或Git历史。

使用中的deployment.json和session/driver日志仍有安全作用，不当成缓存删除。源码目录可用于新部署前的离线学习；实机授权和兼容证据不能从另一台机器继承。
