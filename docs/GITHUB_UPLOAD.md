# 上传GitHub

1. 创建仓库，上传源码ZIP解压后battery80-nlya-source目录内的全部文件。不要上传本机battery或releases整个目录，不上传制作缓存、验证原日志和私人材料。
2. 仓库主页显示README；Actions只运行模拟测试，不访问硬件。云端结果需上传后自行查看。
3. 新建Release，tag建议v0.2.1，标记Pre-release，标题“Battery80 NLYA Windows x64 便携运行版”。
4. 附件上传Battery80-NLYA-v0.2.1-Windows-x64.zip与对应SHA256SUMS。别人下载附件完整解压，双击exe。不要单发exe。
5. 发布说明引用CHANGELOG，写明首次免导入、固定身份、高于80%可能主动放电、成功关闭保留、完整充电验收尚未完成、打包版本未做实机控制。

原厂固件、OEM更新包不能跟随公开；本包驱动使用独立许可且保持原签名。原创源码授权待指定，公开托管不自动授予开源许可。

## 本次交付目录

本机最新准备目录名为github-ready-20261005-r3。repository目录内文件用于仓库主页；release-assets目录内ZIP与SHA清单用于Release附件。该准备目录自己的总说明和制作验证不是运行程序。

在GitHub创建仓库后上传repository的内容（包括.github），再创建v0.2.1预发布，复制RELEASE_NOTES内容。不要只上传源码ZIP而期待显示源码主页，也不要把源码ZIP当运行包。这里仅准备材料，尚未创建或更新远端仓库。
