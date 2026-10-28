# OmniBattery 架构设计与协议详解规范

## 1. 项目背景与痛点

在 Windows 平台上，外设驱动（尤其是 Logitech G HUB、Razer Synapse 等）已经成为玩家和效率工作者的“公害”：
- **资源严重冗余**：Logitech G HUB 启动后常驻 4~5 个子进程，常态内存消耗 **400MB ~ 800MB**，偶发性高 CPU 占用或自动更新无限转圈。
- **功能强加与侵入**：很多用户习惯使用鼠标板载内存（On-Board Memory）固化 DPI、回报率与按键，日常根本不需要软件去改写设置。
- **多设备割裂**：用户桌面上通常混合使用**罗技无线鼠标**、**蓝牙无线耳机**、**国产 2.4G 键盘或备用鼠标（如 VXE / ATK / 蜻蜓 / 黑爵）**。为了看眼电量，不得不安好几个驱动。

**OmniBattery 的核心目标**：
1. **0 侵入**：绝不发送任何修改 DPI、宏、RGB 的写指令，只做电量与充电状态只读探测。
2. **低资源**：纯 Windows 原生 API（GDI / HID / SetupAPI），后台探测路径不依赖 Electron / 浏览器内核；Dashboard 使用 WebView2 时由系统共享运行时承担渲染开销。
3. **多协议聚合**：单一界面同时显示罗技 2.4G Lightspeed、微软标准蓝牙、常见国产 2.4G 接收器电量。

---

## 2. 核心架构设计

```
                         ┌────────────────────────────────────┐
                         │      User Interface Layer          │
                         │  - Win32 Native Tray (数字电量徽标) │
                         │  - Context Menu / Balloon Toast    │
                         │  - CLI / Rainmeter JSON Bridge     │
                         └─────────────────┬──────────────────┘
                                           │
                         ┌─────────────────┴──────────────────┐
                         │       Central Device Manager       │
                         │  - Device Cache & State Diff       │
                         │  - Non-blocking Periodic Timer     │
                         │  - Low Battery Threshold Alerter   │
                         └─────────────────┬──────────────────┘
                                           │
         ┌─────────────────────────────────┼─────────────────────────────────┐
         │                                 │                                 │
┌────────┴────────┐               ┌────────┴────────┐               ┌────────┴────────┐
│ Logitech HID++  │               │ Windows BLE/BT  │               │ Vendor 2.4G     │
│ Driver          │               │ Driver          │               │ Driver          │
│ (0x1004/0x1000) │               │ (PKEY_Battery)  │               │ (VXE/ATK/Razer) │
└────────┬────────┘               └────────┬────────┘               └────────┬────────┘
         │                                 │                                 │
┌────────┴─────────────────────────────────┴─────────────────────────────────┴────────┐
│                       Windows Native Kernel / Subsystems                            │
│  - hid.dll / setupapi.dll (Vendor Usage Page 0xFF00/0xFF43 Bypass)                 │
│  - cfgmgr32.dll / PnP Property System ({104EA319-6EE2-4701-BD47-8DDBF425BBE5}, 2)   │
└─────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. 设备协议深度解析

### 3.1 罗技 HID++ 2.0 / 1.0 原理与实现
罗技无线外设通过 Lightspeed / Unifying 接收器通信。在 Windows 操作系统中，若直接尝试打开鼠标的默认输入接口（Usage Page `0x01` 鼠标），Windows 会返回 `ERROR_ACCESS_DENIED`（防止恶意软件劫持指针）。
- **破局点**：罗技接收器公开了专有的 **Vendor-Defined Usage Page**（`0xFF00` 或 `0xFF43`），专用于驱动管理。该接口可以通过 `CreateFileW` 正常获取读写权限。
- **协议握手**：
  1. **动态 Feature 寻址（IRoot `0x0000`）**：
     构造 20 字节 Long Report：
     `[0x11, slot, 0x00, 0x00, 0x10, 0x04, 0x00, ...]`
     向 slot（`0x01` 对应配对的无线鼠标）查询 Feature `0x1004` (Unified Battery) 的动态索引号。
  2. **读取统一电量（Unified Battery `0x1004`）**：
     调用函数 0（`getBatteryLevelStatus`）：
     `[0x11, slot, feature_idx, 0x00, 0x00, ...]`
     响应中：
     - Byte 4：原生电量百分比（`0~100`）。
     - Byte 6：充电状态（`1`: 充电中, `2`: 已充满, `0`: 放电中）。
  3. **降级电压估算（Battery Voltage `0x1000`）**：
     若不支持 `0x1004`，动态查找 `0x1000`，读取毫伏电压（如 `3980mV`），并使用典型单节锂电池放电曲线换算为电量百分比。
  4. **老设备降级（HID++ 1.0 Register `0x0D`）**：
     发送 7 字节 Short Report `[0x10, slot, 0x8D, 0x00, 0x00, 0x00, 0x00]` 查询电量寄存器。

### 3.2 微软标准蓝牙（Bluetooth & BLE）
Windows 10/11 系统在内核驱动层对实现了 Bluetooth GATT Battery Service（UUID `0x180F`）或 Hands-Free 协议的外设维护了电量。
- **属性键**：`DEVPKEY_Device_BatteryLevel`
  - GUID：`{104EA319-6EE2-4701-BD47-8DDBF425BBE5}`
  - PID：`2`
- **读取机制**：通过查询 Windows PnP 设备实体，只要是处于连接态（Status OK）的蓝牙外设，系统均直接返回 `0~100` 的单字节数值。无需与设备建立 RF 交互，**完全不增加设备额外的蓝牙发射功耗**。

### 3.3 国产 2.4G 接收器（Nordic / 杰理 / 雷蛇方案）
参考 `yszyszysz233/2.4G-battery-viewer`：
- **Nordic 方案（VXE / ATK 蜻蜓等）**：接收器 VID 为 `0x373B`，通常向特定 Feature Report 发送查询字节，在响应的特定字节偏移读取电量。
- **雷蛇 2.4G（Razer Hyperspeed）**：通过 90 字节标准 Razer 报文（Command Class `0x07` Power，Command ID `0x80` Get Battery Level）读取。
- **动态扩展**：通过 `custom_devices.json`，任何玩家逆向出的 2.4G 设备只需填入 VID、PID 和响应偏移即可自动支持。

---

## 4. 系统托盘与界面设计

- **任务栏动态徽标**：
  利用 Windows GDI 内存绘图（`CreateCompatibleBitmap` + `DrawTextW`），将鼠标主电量数值（例如 `78`）以 32x32 清晰抗锯齿位图直接合成任务栏托盘图标。
  - 电量 ≥ 45%：清爽荧光绿
  - 电量 20% ~ 44%：琥珀黄
  - 电量 < 20%：警示红色
  - 充电中：青色并带有 `⚡` 标识
- **右键上下文菜单**：
  直接罗列当前在线的所有设备名称、电量及充电状态，提供“立即刷新”和“退出”。
- **低电量原生通知**：
  当鼠标电量跌破 20% / 10% 阈值且未连接充电线时，触发 Windows 系统级气泡 / Toast 通知，避免在激烈游戏时突然断电。

---

## 5. 线程与安全约束（实现要点）

- **Win32 窗口线程亲和**：托盘隐藏窗口、置顶热键窗口都在各自专用的消息线程中创建/销毁；HTTP 线程只通过 `PostThreadMessageW` 投递命令，绝不在请求线程里直接调用 `CreateWindowExW` / `DestroyWindow`。
- **HID 读取必须有界**：`ReadFile` 使用 `FILE_FLAG_OVERLAPPED` + 事件等待 + `CancelIoEx`，单次读取有毫秒级超时；设备不应答时扫描线程、托盘和 Web UI 都不会被永久阻塞。
- **Awake 线程绑定**：`SetThreadExecutionState` 是线程级的，因此由一条常驻 worker 线程持有并释放执行状态，而不是在短命的 HTTP 请求线程里调用。
- **本地 API 鉴权**：HTTP 服务只绑定 `127.0.0.1`；`index.html` 注入每次启动随机生成的 Token，所有 `POST` 都必须携带 `X-OmniToys-Token`，并校验 `Origin`，防止任意网页对 localhost 发起 CSRF 重命名/模块开关。
- **配置隔离**：配置默认写入 `%APPDATA%\OmniToys\omnitoys_config.json`，原子替换；默认字典全部深拷贝，模块不会污染全局默认值。
