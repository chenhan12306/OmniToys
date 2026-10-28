# 如何为 OmniToys 扩展新功能模块（像 PowerToys 一样）

OmniToys 采用了与微软 **Microsoft PowerToys** 完全一致的**宿主 + 独立插件模块**架构。每个小工具（Toy）都是一个自包含、可单独启用的对象。

---

## 3 步快速集成一个新工具

### 步骤 1：创建模块目录与类文件
在 `src/modules/` 下新建一个文件夹，例如 `quick_dns/`，并在其中创建 `module.py`：

```python
# src/modules/quick_dns/module.py
from typing import Dict, Any
from ..base_module import ToyModule

class QuickDnsModule(ToyModule):
    def __init__(self):
        super().__init__(
            module_id="quick_dns",
            name="DNS 快速切换 (Quick DNS)",
            description="一键在公共 DNS（114 / 阿里 / 谷歌 / Cloudflare）之间快速切换，无需打开网络控制面板。",
            icon="network" # 图标标识
        )

    def default_config(self) -> Dict[str, Any]:
        """定义此模块的默认设置项"""
        return {
            "enabled": True,
            "current_dns": "AliDNS (223.5.5.5)"
        }

    def start(self):
        """当模块被启用或软件启动时触发"""
        print(f"[{self.name}] 模块已启动")

    def stop(self):
        """当模块被用户在界面上关闭时触发"""
        print(f"[{self.name}] 模块已停止")

    def get_state(self) -> Dict[str, Any]:
        """向前端 Fluent UI 传递当前动态运行时数据"""
        return {
            "current_dns": self.config.get("current_dns"),
            "ping_ms": 12
        }

    def handle_action(self, action: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """处理来自前端按钮点击或下拉框的事件"""
        if action == "switch_dns":
            target = payload.get("target_dns")
            self.config["current_dns"] = target
            # 这里调用系统网络命令修改 DNS ...
            return {"status": "ok", "new_dns": target}
        return {"status": "unknown"}
```

---

### 步骤 2：在 AppHost 中注册你的新模块
打开 `src/core/app_host.py`，导入并注册它：

```python
# 在 src/core/app_host.py 中
from ..modules.quick_dns.module import QuickDnsModule # 导入

def _register_default_modules(self):
    default_list = [
        OmniBatteryModule(enable_mock=self.enable_mock),
        AwakeModule(),
        WindowPinnerModule(),
        QuickDnsModule()  # <-- 添加这一行！
    ]
    for mod in default_list:
        self.register_module(mod)
```

`AppHost.register_module()` 会自动注入配置保存回调。如果你的模块在后台线程里修改了 `self.config`（例如定时更新设置），调用 `self.save_config()` 即可持久化，无需自己保存 JSON。

---

### 步骤 3：在前端添加导航与视图（可选）
如果你的工具需要专属的设置卡片页面，只需在 `src/gui/web/index.html` 中的导航栏和内容区添加对应项即可。如果不加专属页面，OmniToys 会自动将其渲染在**主页概览（Dashboard）**卡片中，并附带开/关切换滑块！

> 前端所有写请求都通过 `apiCall()` 自动携带 `X-OmniToys-Token`，不要绕过它直接 `fetch` POST，否则会被本地 API 拒绝（403）。

---

## 现已内置的 PowerToys 风格模块
1. **外设电量监控 (`omni_battery`)**：替代 G HUB，直连罗技 HID++ 2.0、Windows 蓝牙与国产 2.4G 接收器。
2. **批量重命名 (`power_rename`)**：正则替换、大小写转换、自动编号、撤销。
3. **保持清醒 (`awake`)**：对应 PowerToys Awake，长时任务不黑屏、不休眠。
4. **窗口置顶 (`window_pinner`)**：对应 PowerToys Always on Top，`Ctrl+Win+T` 全局热键。
