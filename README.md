# OmniToys (全能外设与效率工具箱)
> **告别臃肿的罗技 G HUB 与各类流氓驱动！** 专为 Windows 打造的微软 **PowerToys 风格**现代化效率工具箱。不仅能精准监控罗技 2.4G / 蓝牙 / 国产 2.4G 外设电量，还可以像 PowerToys 一样无限扩展各种实用小工具，并能直接编译为单个独立的 `.exe` 文件。

---

## 🌟 核心特性

1. **类似微软 PowerToys 的现代化架构**：
   - **Windows 11 Fluent Design (Mica 质感)**：原生深色主题、Fluent 卡片、流畅过渡动画，告别传统老旧丑陋的 WinForms 界面。
   - **工具箱（Toolbox）插件式架构**：核心宿主 + 独立模块，每个小工具均有独立的开关、独立后台 Worker 与专属卡片，可按需任意开启/禁用。
2. **多协议外设电量监控（OmniBattery）**：
   - **罗技 Lightspeed & Unifying (HID++ 2.0 / 1.0)**：直接与硬件接口通信，读取原生百分比与充电状态，**无需安装和运行几百兆内存的罗技 G HUB**。
   - **Windows 标准蓝牙外设**：直连 Windows 内核设备属性 `DEVPKEY_Device_BatteryLevel`，支持所有蓝牙鼠标、键盘、AirPods/蓝牙耳机、无线手柄。
   - **国产与主流 2.4G 接收器**：支持 ATK、VXE 蜻蜓、雷蛇 Hyperspeed、杰理等 2.4G 方案，并支持通过 JSON 配置文件自由扩充逆向报文。
   - **任务栏动态电量数字徽标**：在 Windows 任务栏直接显示当前主鼠标电量数字（如 `78`，绿/黄/红分级变色，充电带 `⚡` 标识）。
3. **已内置的 PowerToys 风格小工具**：
   - 🔋 **外设电量监控 (OmniBattery)**：替代 G HUB，多设备电量统一看。
   - 🏷️ **批量重命名 (PowerRename)**：对标 PowerToys PowerRename，支持高级正则替换、大小写格式转换、自动递增编号、实时表格更名预览与安全一键撤销。
   - ☕ **保持清醒 (Awake)**：对应 PowerToys Awake，长时下载、渲染或挂机时阻止电脑休眠或显示器黑屏。
   - 📌 **窗口置顶 (Always on Top)**：对应 PowerToys Always on Top，快捷键让任何计算器、记事本或视频窗口悬浮在顶层。
4. **编译为单文件 EXE**：
   - 提供开箱即用的 `build.bat` 与 `OmniToys.spec`，一键生成无黑框控制台的单文件 `OmniToys.exe`，启动即用，方便分享与随身携带。

---

## 🚀 快速上手与运行

### 方式 A：源码直接运行 (推荐调试)
```powershell
# 1. 安装界面与打包依赖 (核心硬件通信模块零依赖)
pip install -r requirements.txt

# 2. 启动现代 Fluent UI 仪表盘 (默认模式)
python main.py

# 3. 仅在后台系统托盘运行 (极致节能，内存仅约 12MB)
python main.py --tray

# 4. 终端单次查看电量并退出
python main.py --once
```

### 方式 B：一键编译为单个 `.exe` 文件
在 Windows 电脑上直接双击根目录下的 **[build.bat](file:///Users/han/Documents/2.4G-device-controller/build.bat)**，或者执行：
```powershell
pyinstaller OmniToys.spec --clean
```
编译完成后，在 `dist/` 目录下将生成 **`OmniToys.exe`**：
- 单个独立 EXE，无需携带任何杂乱的 DLL。
- 无黑色 CMD 终端窗口闪烁。
- 启动后自动载入现代 Fluent UI 窗口，可自由最小化到右下角托盘。

---

## 🛠️ 如何添加更多新工具？

参考详尽文档：**[HOW_TO_ADD_A_TOOL.md](file:///Users/han/Documents/2.4G-device-controller/HOW_TO_ADD_A_TOOL.md)**。
只需在 `src/modules/` 中新建一个继承自 `ToyModule` 的类，并在 `app_host.py` 中注册，新工具就会自动出现在工具箱中，拥有自己的开关与状态面板！
