import streamlit as st
import yaml
import os

st.set_page_config(page_title="Modular RAG MCP Server", page_icon="🤖", layout="wide")

st.title("🤖 Modular RAG MCP Server Dashboard")

st.markdown("""
欢迎使用 Modular RAG MCP Server！

这个 dashboard 提供了完整的数据管理和链路追踪能力。

**当前配置：**
""")

# Load config
config_path = "config/settings.yaml"
if os.path.exists(config_path):
    with open(config_path) as f:
        config = yaml.safe_load(f)

    col1, col2, col3 = st.columns(3)

    with col1:
        st.subheader("LLM 配置")
        st.write(f"Provider: {config['llm']['provider']}")
        st.write(f"Model: {config['llm']['model']}")

    with col2:
        st.subheader("Embedding 配置")
        st.write(f"Provider: {config['embedding']['provider']}")
        st.write(f"Model: {config['embedding']['model']}")

    with col3:
        st.subheader("其他配置")
        st.write(f"Vision: {'启用' if config['vision_llm']['enabled'] else '禁用'}")
        st.write(f"Rerank: {config['rerank']['provider'] if config['rerank']['enabled'] else '禁用'}")

else:
    st.error("配置文件不存在，请先运行 setup")

st.markdown("""
---
### 功能模块

1. **系统总览** - 查看系统状态和配置
2. **数据浏览** - 浏览向量数据库中的文档
3. **Ingestion 管理** - 上传和管理文档
4. **摄取追踪** - 查看文档处理进度
5. **查询追踪** - 查看查询历史和性能
6. **评估面板** - 运行评估测试

*注意：完整功能需要安装所有依赖包。*
""")