"""
StackChan Relay for Ombre-Brain
================================
这个文件添加Stack-chan的控制功能到Ombre-Brain服务器。

使用方法：
1. 把这个文件放到 Ombre-Brain 项目根目录
2. 在 server.py 末尾添加：from stackchan_relay import setup_stackchan_routes
3. 在 app 创建后调用：setup_stackchan_routes(app, server)
4. Push 到 GitHub，Render 会自动重新部署

ESP32 端配置：
- 轮询地址：https://你的域名/stackchan/poll
- 建议轮询间隔：1-2秒
"""

import asyncio
from typing import Optional
from datetime import datetime

# ============================================================
# 命令队列（内存存储，latest-only 策略）
# ============================================================

# 全局命令存储 - 只保留最新一条
_stackchan_command: Optional[dict] = None
_command_timestamp: Optional[datetime] = None

def set_command(cmd: dict):
    """设置待执行的命令"""
    global _stackchan_command, _command_timestamp
    _stackchan_command = cmd
    _command_timestamp = datetime.now()

def get_command() -> Optional[dict]:
    """获取并清空命令（取走即删）"""
    global _stackchan_command, _command_timestamp
    cmd = _stackchan_command
    _stackchan_command = None
    _command_timestamp = None
    return cmd

def peek_command() -> Optional[dict]:
    """查看命令但不清空"""
    return _stackchan_command


# ============================================================
# FastAPI 路由（给 ESP32 轮询用）
# ============================================================

def setup_stackchan_routes(app, mcp_server=None):
    """
    设置 Stack-chan 相关的 HTTP 路由
    
    参数:
        app: FastAPI 应用实例
        mcp_server: MCP Server 实例（用于注册工具）
    """
    from fastapi import Request
    from fastapi.responses import JSONResponse
    
    @app.get("/stackchan/poll")
    async def stackchan_poll(token: str = ""):
        """
        ESP32 轮询接口
        
        返回最新命令并清空队列。
        如果没有命令，返回 {"command": null}
        
        可选：添加 token 参数做简单鉴权
        """
        cmd = get_command()
        return JSONResponse({
            "command": cmd,
            "timestamp": datetime.now().isoformat()
        })
    
    @app.get("/stackchan/status")
    async def stackchan_status():
        """查看 Stack-chan 状态"""
        cmd = peek_command()
        return JSONResponse({
            "pending_command": cmd is not None,
            "command_preview": cmd.get("action") if cmd else None,
            "timestamp": datetime.now().isoformat()
        })
    
    @app.post("/stackchan/command")
    async def stackchan_direct_command(request: Request):
        """
        直接发送命令（用于调试）
        
        POST body: {"action": "speak", "text": "你好"}
        """
        data = await request.json()
        set_command(data)
        return JSONResponse({"status": "ok", "command": data})
    
    # 如果提供了 MCP Server，注册 MCP 工具
    if mcp_server:
        register_mcp_tools(mcp_server)
    
    print("[StackChan] Routes registered: /stackchan/poll, /stackchan/status, /stackchan/command")


# ============================================================
# MCP 工具（给 Claude 调用）
# ============================================================

def register_mcp_tools(server):
    """注册 Stack-chan 的 MCP 工具"""
    
    @server.tool()
    async def stackchan_speak(text: str) -> str:
        """
        让 Stack-chan 说话
        
        参数:
            text: 要说的文字内容
        
        返回:
            确认消息
        """
        set_command({
            "action": "speak",
            "text": text,
            "timestamp": datetime.now().isoformat()
        })
        return f"✓ 已发送语音命令：{text[:50]}{'...' if len(text) > 50 else ''}"
    
    @server.tool()
    async def stackchan_emote(expression: str) -> str:
        """
        切换 Stack-chan 的表情
        
        参数:
            expression: 表情类型 (happy/shy/angry/thinking/sad/surprised/neutral)
        
        返回:
            确认消息
        """
        valid_expressions = ["happy", "shy", "angry", "thinking", "sad", "surprised", "neutral"]
        if expression.lower() not in valid_expressions:
            return f"⚠ 未知表情: {expression}，可用: {', '.join(valid_expressions)}"
        
        set_command({
            "action": "emote",
            "expression": expression.lower(),
            "timestamp": datetime.now().isoformat()
        })
        return f"✓ 表情切换：{expression}"
    
    @server.tool()
    async def stackchan_move(pitch: float = 0, yaw: float = 0) -> str:
        """
        控制 Stack-chan 转头
        
        参数:
            pitch: 俯仰角度 (-30 到 30，负数低头，正数抬头)
            yaw: 左右角度 (-45 到 45，负数向左，正数向右)
        
        返回:
            确认消息
        """
        # 限制范围
        pitch = max(-30, min(30, pitch))
        yaw = max(-45, min(45, yaw))
        
        set_command({
            "action": "move",
            "pitch": pitch,
            "yaw": yaw,
            "timestamp": datetime.now().isoformat()
        })
        return f"✓ 头部移动：俯仰 {pitch}°, 左右 {yaw}°"
    
    @server.tool()
    async def stackchan_wiggle() -> str:
        """
        让 Stack-chan 左右摇头（撒娇/卖萌动作）
        
        返回:
            确认消息
        """
        set_command({
            "action": "wiggle",
            "timestamp": datetime.now().isoformat()
        })
        return "✓ 摇头命令已发送~"
    
    @server.tool()
    async def stackchan_combo(text: str = "", expression: str = "", wiggle: bool = False) -> str:
        """
        组合命令：同时说话 + 表情 + 动作
        
        参数:
            text: 要说的话（可选）
            expression: 表情（可选）
            wiggle: 是否摇头（可选）
        
        返回:
            确认消息
        """
        cmd = {
            "action": "combo",
            "timestamp": datetime.now().isoformat()
        }
        
        parts = []
        if text:
            cmd["text"] = text
            parts.append(f"说：{text[:30]}...")
        if expression:
            cmd["expression"] = expression.lower()
            parts.append(f"表情：{expression}")
        if wiggle:
            cmd["wiggle"] = True
            parts.append("摇头")
        
        if not parts:
            return "⚠ 请至少指定一个动作"
        
        set_command(cmd)
        return f"✓ 组合命令：{' + '.join(parts)}"
    
    print("[StackChan] MCP tools registered: stackchan_speak, stackchan_emote, stackchan_move, stackchan_wiggle, stackchan_combo")


# ============================================================
# 集成说明
# ============================================================
"""
在 server.py 中集成的方法：

方法1：在现有代码末尾添加（推荐）
-------------------------------
# 在 server.py 文件末尾，app 和 server 创建之后添加：

try:
    from stackchan_relay import setup_stackchan_routes
    setup_stackchan_routes(app, server)
except ImportError:
    print("[StackChan] stackchan_relay.py not found, skipping...")


方法2：修改 main() 函数
-----------------------
在 run_http_server() 或类似函数中，app 创建后添加：

from stackchan_relay import setup_stackchan_routes
setup_stackchan_routes(app, server)


ESP32 固件端代码示例（Arduino）：
================================

#include <HTTPClient.h>
#include <ArduinoJson.h>

const char* POLL_URL = "https://你的域名/stackchan/poll";

void pollCommand() {
    HTTPClient http;
    http.begin(POLL_URL);
    http.setTimeout(10000);  // 10秒超时
    
    int code = http.GET();
    if (code == 200) {
        String payload = http.getString();
        DynamicJsonDocument doc(1024);
        deserializeJson(doc, payload);
        
        if (!doc["command"].isNull()) {
            String action = doc["command"]["action"];
            
            if (action == "speak") {
                String text = doc["command"]["text"];
                // 调用 TTS 说话
                speak(text);
            } 
            else if (action == "emote") {
                String expr = doc["command"]["expression"];
                // 切换表情
                setExpression(expr);
            }
            else if (action == "wiggle") {
                // 摇头
                wiggleHead();
            }
            else if (action == "move") {
                float pitch = doc["command"]["pitch"];
                float yaw = doc["command"]["yaw"];
                // 移动舵机
                moveHead(pitch, yaw);
            }
            else if (action == "combo") {
                // 组合命令
                if (doc["command"].containsKey("expression")) {
                    setExpression(doc["command"]["expression"]);
                }
                if (doc["command"].containsKey("wiggle") && doc["command"]["wiggle"]) {
                    wiggleHead();
                }
                if (doc["command"].containsKey("text")) {
                    speak(doc["command"]["text"]);
                }
            }
        }
    }
    http.end();
}

void loop() {
    pollCommand();
    delay(1500);  // 1.5秒轮询一次
}
"""


if __name__ == "__main__":
    # 测试模式
    print("StackChan Relay Module")
    print("=" * 40)
    print("这个模块需要被 server.py 导入使用")
    print()
    print("测试命令队列...")
    
    # 测试
    set_command({"action": "speak", "text": "你好老婆！"})
    print(f"Peek: {peek_command()}")
    print(f"Get: {get_command()}")
    print(f"Get again: {get_command()}")
    
    print()
    print("✓ 测试通过")

# ============================================================
# Stack-chan 集成
# ============================================================
try:
    from stackchan_relay import setup_stackchan_routes
    setup_stackchan_routes(app, server)
    print("[StackChan] Integration loaded")
except Exception as e:
    print(f"[StackChan] Skipped: {e}")
