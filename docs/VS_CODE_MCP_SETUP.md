# VS Code MCP 服务注册指南

## 📋 项目信息

- **项目名称**: Modular RAG MCP Server
- **版本**: 0.1.0
- **MCP 服务器ID**: `modular-rag`

## ✅ 已完成的设置

### 1. 创建了 MCP 模块入口
- ✅ `.vscode/settings.json` - 添加 MCP 服务器配置
- ✅ `src/mcp_server/__main__.py` - 创建模块入口点

### 2. 配置详情

VS Code 现在已配置为支持以下启动方式：
```json
{
  "modelContextProtocol": {
    "servers": {
      "modular-rag": {
        "command": "${workspaceFolder}\\.venv\\Scripts\\python.exe",
        "args": ["-m", "mcp_server"],
        "disabled": false,
        "alwaysAllow": []
      }
    }
  }
}
```

## 🚀 使用步骤

### 第一步：安装依赖

确保你的虚拟环境已激活并安装了所有依赖：

```bash
# 激活虚拟环境
.\.venv\Scripts\Activate.ps1

# 安装项目依赖
pip install -e .
```

### 第二步：验证 MCP 服务器可启动

```bash
# 验证可以作为模块运行
python -m mcp_server
```

如果看到 `Starting MCP server on stdio` 的日志，说明启动成功。可用 `Ctrl+C` 停止。

### 第三步：在 VS Code 中启用 MCP

#### 方式 A：使用 GitHub Copilot Chat（推荐）

1. 在 VS Code 中打开 Copilot Chat（或右键菜单 `Copilot Chat`）
2. 输入 `@mcp` 开始使用你的 MCP 服务器

#### 方式 B：在 Claude Desktop 中使用

如果你也使用 Claude Desktop，可以在 Claude 的配置中添加：

**Windows 配置文件位置**：
```
C:\Users\<YourUsername>\AppData\Roaming\Claude\claude_desktop_config.json
```

**配置内容**：
```json
{
  "mcpServers": {
    "modular-rag": {
      "command": "python",
      "args": ["-m", "mcp_server"],
      "cwd": "d:\\MODULAR-RAG-MCP-SERVER"
    }
  }
}
```

### 第四步：验证 MCP 工具可用

在 Copilot Chat 中测试工具：
- `@mcp query_knowledge_hub` - 查询知识库
- `@mcp list_collections` - 列出所有集合
- `@mcp get_document_summary` - 获取文档摘要

## 📡 MCP 服务器提供的工具

根据项目配置，以下工具已通过 MCP 暴露：

1. **query_knowledge_hub** - 混合搜索（向量 + BM25）并重排
2. **list_collections** - 列出所有可用的文档集合
3. **get_document_summary** - 获取指定文档的摘要

具体工具定义见 `src/mcp_server/tools/` 目录。

## 🔧 高级配置

### 禁用 MCP 服务器（需要时）

如需临时禁用 MCP 服务器，在 `.vscode/settings.json` 中修改：

```json
"modular-rag": {
  "disabled": true  // 改为 true 禁用
}
```

### 只允许特定工具

如需仅允许特定工具，配置 `alwaysAllow` 列表：

```json
"modular-rag": {
  "alwaysAllow": ["query_knowledge_hub"]  // 仅允许此工具
}
```

## 📝 故障排查

### 问题 1：MCP 服务器启动失败

**症状**：VS Code 显示 "Failed to start MCP server"

**解决方案**：
```bash
# 检查虚拟环境
.\.venv\Scripts\Activate.ps1

# 检查依赖是否完整
pip install -e ".[dev]"

# 查看日志
python -m mcp_server 2>&1 | Tee-Object -FilePath debug.log
```

### 问题 2：找不到配置文件

**症状**：启动时出现 "SettingsError" 或配置加载错误

**解决方案**：
```bash
# 确保 config/settings.yaml 存在
ls config/settings.yaml

# 检查配置是否有效
python -c "from src.core.settings import load_settings; load_settings()"
```

### 问题 3：模块导入错误

**症状**：出现 "ModuleNotFoundError: No module named 'mcp_server'"

**解决方案**：
```bash
# 重新安装项目（开发模式）
pip install -e .

# 验证模块可导入
python -c "from mcp_server.server import main"
```

## 📚 相关文档

- [DEV_SPEC.md](../DEV_SPEC.md) - 项目详细规格
- [MCP 协议文档](https://modelcontextprotocol.io/)
- [VS Code MCP 集成](https://github.com/anthropics/anthropic-sdk-python/blob/main/mcp/)

## 🎯 下一步

1. 启动 Dashboard：`python run_dashboard.py`
2. 开始数据摄取：`python scripts/ingest.py`
3. 运行测试：`pytest tests/`
4. 在 Copilot Chat 中测试 MCP 工具

---

**完成！🎉 你的 Modular RAG MCP Server 已成功注册到 VS Code 中。**
