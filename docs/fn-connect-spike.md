# FN Connect 匿名客户访问 Spike

状态：已完成局域网 NAS 部署和 100 张闭环，外部匿名访问尚未通过验收。本地 FN Connect 入口发生内网优化跳转，NAS 设置中未确认匿名 Docker 网站映射，因此不能用文件分享能力推断 PicPeak 画廊也允许匿名访问。仍需未登录飞牛账号的外部蜂窝网络验证。

先完成局域网部署，创建只有合成照片的测试画廊。将同一画廊的分享入口映射到 FN Connect，并在未登录飞牛账号的手机上关闭 Wi-Fi、通过蜂窝网络打开。使用无痕窗口分别检查：打开分享链接、密码页、缩略图、原图、标记精修、评论、下载、链接转发给第二位客户。记录是否要求飞牛账号、首次加载耗时、100/1000 张画廊滚动耗时、10MB 下载速度、断线恢复和有效期。不要将 Bridge 管理端口映射出去。

验收条件：外部客户无需飞牛账号，PicPeak 自身分享密码有效，所有反馈和下载请求成功，服务重启后原链接继续有效。任一条件失败则 FN Connect 不能作为正式客户入口。

替代方案：有域名和 VPS 时可用 FRP HTTPS 反向代理，仅暴露 PicPeak；也可评估提供匿名 HTTPS 网站入口的托管隧道，并现场核实服务条款、图片下载限额和所在地区性能。Tailscale 适合摄影师进入私有网络读取 SMB，不适合要求客户安装软件的匿名选片。

参考：[飞牛访问说明](https://help.fnnas.com/articles/v1/access/how-access)、[飞牛文件分享](https://help.fnnas.com/articles/v1/file/create-share-link)、[FRP HTTP 示例](https://gofrp.org/en/docs/examples/vhost-http/)、[FRP HTTPS](https://gofrp.org/en/docs/features/http-https/)。这些资料并不能替代上述真实匿名访问测试。

现场记录表：NAS/fnOS 版本、入口形式、网络/运营商、浏览器、是否登录飞牛、成功项/失败项、耗时、下载速度、日期。照片和访问凭证不要放进公开仓库。
