"""
EMCT — CDP 交易执行器
通过 Chrome DevTools Protocol 连接 Windows Edge，执行东方财富下单
"""
import asyncio
import json
import os
import time
from datetime import datetime
from typing import Optional
from dataclasses import dataclass, field

import websockets

CDP_HOST = os.environ.get("CDP_HOST", "localhost")
CDP_PORT = int(os.environ.get("CDP_PORT", "9222"))
SCREENSHOT_DIR = os.path.join(os.path.dirname(__file__), "..", "screenshots")


@dataclass
class CDPSession:
    """CDP 会话状态"""
    ws_url: str = ""
    ws: Optional[websockets.WebSocketClientProtocol] = None
    msg_id: int = 0
    connected: bool = False
    target_id: str = ""

    async def connect(self) -> bool:
        """连接到 Edge CDP"""
        try:
            # 获取可用的 target
            import urllib.request
            resp = urllib.request.urlopen(f"http://{CDP_HOST}:{CDP_PORT}/json", timeout=5)
            targets = json.loads(resp.read())
            if not targets:
                print("❌ CDP: 没有可用的浏览器页面")
                return False

            # 优先选东方财富页面，否则选第一个
            target = None
            for t in targets:
                if "eastmoney" in t.get("url", "").lower() or "东方财富" in t.get("title", ""):
                    target = t
                    break
            if not target:
                target = targets[0]

            self.target_id = target["id"]
            self.ws_url = target["webSocketDebuggerUrl"]
            self.ws = await websockets.connect(self.ws_url, max_size=2**24)
            self.connected = True
            print(f"✅ CDP 已连接: {target.get('title', 'unknown')[:30]}")
            return True
        except Exception as e:
            print(f"❌ CDP 连接失败: {e}")
            self.connected = False
            return False

    async def send(self, method: str, params: dict = None) -> dict:
        """发送 CDP 命令，返回结果"""
        if not self.ws:
            raise RuntimeError("CDP 未连接")
        self.msg_id += 1
        msg = {"id": self.msg_id, "method": method, "params": params or {}}
        await self.ws.send(json.dumps(msg))
        # 等待响应（忽略事件类消息）
        while True:
            raw = await self.ws.recv()
            resp = json.loads(raw)
            if resp.get("id") == self.msg_id:
                return resp.get("result", {})

    async def navigate(self, url: str):
        """导航到指定URL"""
        await self.send("Page.enable")
        await self.send("Page.navigate", {"url": url})
        await asyncio.sleep(2)

    async def screenshot(self, name: str = "") -> str:
        """截图并保存"""
        os.makedirs(SCREENSHOT_DIR, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        fname = f"{ts}_{name}.png" if name else f"{ts}.png"
        fpath = os.path.join(SCREENSHOT_DIR, fname)

        result = await self.send("Page.captureScreenshot", {"format": "png"})
        import base64
        with open(fpath, "wb") as f:
            f.write(base64.b64decode(result["data"]))
        return fpath

    async def click(self, selector: str):
        """点击元素（通过 JS）"""
        await self.send("Runtime.evaluate", {
            "expression": f"""
            (function() {{
                const el = document.querySelector('{selector}');
                if (el) {{ el.click(); return 'clicked'; }}
                return 'not found: {selector}';
            }})()
            """
        })

    async def type_text(self, selector: str, text: str):
        """输入文本"""
        await self.send("Runtime.evaluate", {
            "expression": f"""
            (function() {{
                const el = document.querySelector('{selector}');
                if (el) {{
                    el.focus();
                    el.value = '{text}';
                    el.dispatchEvent(new Event('input', {{ bubbles: true }}));
                    el.dispatchEvent(new Event('change', {{ bubbles: true }}));
                    return 'typed';
                }}
                return 'not found';
            }})()
            """
        })

    async def disconnect(self):
        if self.ws:
            await self.ws.close()
            self.connected = False


# ── 全局会话 ──
_session: Optional[CDPSession] = None


async def get_session() -> CDPSession:
    global _session
    if _session is None or not _session.connected:
        _session = CDPSession()
        await _session.connect()
    return _session


async def execute_order(
    code: str,
    name: str,
    direction: str,
    price: float,
    volume: int,
) -> dict:
    """
    执行下单流程：
    1. 连接 Edge CDP
    2. 导航到东方财富交易页
    3. 填入股票代码/价格/数量
    4. 点击买入/卖出
    5. 截图确认
    """
    session = await get_session()
    if not session.connected:
        return {"ok": False, "error": "CDP 未连接，请确保 Edge 已启动并开启调试端口"}

    try:
        # 导航到东方财富交易页
        trade_url = os.environ.get(
            "TRADE_URL",
            "https://trade.eastmoney.com/"
        )
        await session.navigate(trade_url)
        await asyncio.sleep(2)

        # 截图：交易页初始状态
        await session.screenshot(f"trade_{code}_{direction}")

        # 填入股票代码
        await session.type_text("#stock-code, input[placeholder*='代码'], .stock-code-input input", code)
        await asyncio.sleep(0.5)

        # 填入价格
        await session.type_text("#price, input[placeholder*='价格'], .price-input input", str(price))
        await asyncio.sleep(0.3)

        # 填入数量
        await session.type_text("#volume, input[placeholder*='数量'], .volume-input input", str(volume))
        await asyncio.sleep(0.3)

        # 点击买入/卖出按钮
        btn_text = "买入" if direction == "buy" else "卖出"
        btn_selectors = [
            f"button:has-text('{btn_text}')",
            f".btn-{direction}",
            f"#{direction}-btn",
            f"[data-action='{direction}']",
        ]
        for sel in btn_selectors:
            await session.click(sel)
            await asyncio.sleep(1)

        # 截图：确认页面
        confirm_path = await session.screenshot(f"confirm_{code}_{direction}")

        return {
            "ok": True,
            "code": code,
            "name": name,
            "direction": direction,
            "price": price,
            "volume": volume,
            "amount": round(price * volume, 2),
            "screenshot": confirm_path,
            "message": f"已提交 {btn_text} {name}({code}) {volume}股 @{price}"
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}
