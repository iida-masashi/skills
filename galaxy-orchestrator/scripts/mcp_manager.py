import json
import logging
import os
from contextlib import AsyncExitStack
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

# `google.genai.types` depends on the environment
try:
    from google.genai import types
except ImportError:
    types = None

logger = logging.getLogger(__name__)

class MCPManager:
    def __init__(self, config_path: str):
        self.config_path = config_path
        self.servers: dict[str, dict] = {}
        self.sessions: dict[str, ClientSession] = {}
        self.exit_stack = AsyncExitStack()

        self.tool_to_server_map: dict[str, str] = {}
        self.gemini_tool_map: dict[str, str] = {} # gemini safe name -> original name
        self.available_tools: list[Any] = [] # Stores original mcp.types.Tool objects

    async def initialize(self):
        """設定ファイルからサーバーを読み込み、サブプロセスを起動して接続を確立する"""
        if not os.path.exists(self.config_path):
            print(f"MCP Config not found at {self.config_path}. Skipping MCP initialization.")
            return

        with open(self.config_path, encoding="utf-8") as f:
            config = json.load(f)

        self.servers = config.get("mcpServers", {})

        for name, server_config in self.servers.items():
            print(f"🔌 Connecting to MCP Server: {name}...")
            command = server_config.get("command")
            args = server_config.get("args", [])
            env = server_config.get("env", None)

            # Windows では npm/npx などは .cmd 拡張子がないとエラーになる場合があるための対応
            if os.name == "nt" and command in ["npx", "npm", "uvx"]:
                command += ".cmd" if command != "uvx" else ".exe"

            # Merge with system env if env is provided
            final_env = os.environ.copy()
            if env:
                final_env.update(env)

            server_params = StdioServerParameters(
                command=command,
                args=args,
                env=final_env
            )

            try:
                stdio_transport = await self.exit_stack.enter_async_context(stdio_client(server_params))
                read, write = stdio_transport
                session = await self.exit_stack.enter_async_context(ClientSession(read, write))

                await session.initialize()
                self.sessions[name] = session
                print(f"✅ Connected to {name}")

            except Exception as e:
                print(f"❌ Failed to connect to MCP Server {name}: {e}")

        # Fetch tools and map them
        await self._discover_tools()

    async def _discover_tools(self):
        """全サーバーのツールを取得し、Geminiで利用可能な名前とマッピングする"""
        self.tool_to_server_map.clear()
        self.gemini_tool_map.clear()
        self.available_tools.clear()

        for server_name, session in self.sessions.items():
            try:
                tools_response = await session.list_tools()
                for tool in tools_response.tools:
                    safe_name = tool.name.replace("-", "_").replace(".", "_")
                    self.tool_to_server_map[tool.name] = server_name
                    self.gemini_tool_map[safe_name] = tool.name
                    self.available_tools.append(tool)
            except Exception as e:
                print(f"⚠️ Failed to list tools from {server_name}: {e}")

    def _clean_schema(self, schema: dict) -> dict:
        """Gemini の API スキーマに合わせて不要なフィールドを削除する"""
        cleaned = {}
        for k, v in schema.items():
            if k in ["$schema", "additionalProperties", "additional_properties", "exclusiveMaximum", "exclusiveMinimum", "propertyNames"]:
                continue
            if isinstance(v, dict):
                cleaned[k] = self._clean_schema(v)
            elif isinstance(v, list):
                cleaned[k] = [self._clean_schema(i) if isinstance(i, dict) else i for i in v]
            else:
                cleaned[k] = v
        return cleaned

    def get_gemini_tools(self) -> list[Any]:
        """Geminiの GenerateContentConfig(tools=...) に渡す形式でツールリストを返す"""
        if not types or not self.available_tools:
            return []

        func_decls = []
        for tool in self.available_tools:
            safe_name = tool.name.replace("-", "_").replace(".", "_")

            schema = dict(tool.inputSchema) if tool.inputSchema else {}
            schema = self._clean_schema(schema)

            # Convert JSON schema to Gemini Schema if possible, or pass dict directly
            # google-genai accepts dict for parameters
            func_decls.append(
                types.FunctionDeclaration(
                    name=safe_name,
                    description=tool.description or "",
                    parameters=schema
                )
            )

        if not func_decls:
            return []

        return [{"function_declarations": func_decls}]

    async def call_tool(self, safe_name: str, arguments: dict) -> str:
        """Geminiから指定されたツールを実行する"""
        original_name = self.gemini_tool_map.get(safe_name)
        if not original_name:
            return f"Error: Tool {safe_name} not found."

        server_name = self.tool_to_server_map.get(original_name)
        session = self.sessions.get(server_name)
        if not session:
            return f"Error: Session for {server_name} not found."

        print(f"🛠️  Calling MCP Tool: {original_name} (Server: {server_name})...")
        try:
            result = await session.call_tool(original_name, arguments)
            # result is an object with content list
            output_texts = []
            for content in result.content:
                if content.type == "text":
                    output_texts.append(content.text)
                elif content.type == "resource":
                    output_texts.append(str(content.resource))
            return "\n".join(output_texts) if output_texts else "Tool executed successfully but returned no text."
        except Exception as e:
            print(f"❌ Error executing tool {original_name}: {e}")
            return f"Error executing tool: {e}"

    async def close(self):
        await self.exit_stack.aclose()
