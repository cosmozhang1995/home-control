# Quick start

## 服务端部署

直接运行安装脚本：

```
sudo ./install_server.py
```

## PC端部署

第一步：复制`pc_config.example.json`，修改对应的配置信息。

第二步：设置开机运行：
1. Win + R → `shell:startup`，打开`Startup`文件夹；
2. 新建快捷方式`HomeControlPC`，**项目**位置填入`pythonw.exe D:\path\to\home-control\pc_client.py`
