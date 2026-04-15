# Home Control

可以用来控制家里的电脑。

分为 Server端 和 PC端。

在 Server端 上部署后，通过`http://server:80000/pc_launch?mode=xxx`远程启动PC端。

PC端上安装了松果电子远程启动模块，Server端通过松果电子提供的API完成远程启动。同时需要配置本项目中的`pc_client.py`开机自启，以便在开机后自动做一些配置。

mode的可选项有：
- `default`：默认模式，启动后会切换到主显示器。
- `game`：游戏模式，启动后会切换到副显示器（大屏/电视），并且启动UU加速器和Steam。

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
