# 测试框架指南

## 概述

本项目采用 **pytest** 作为测试框架，遵循**测试驱动开发（TDD）**范式。测试分为三层：

- **单元测试**（Unit Tests）：验证独立组件的内部逻辑
- **集成测试**（Integration Tests）：验证多组件协作与数据流转
- **端到端测试**（E2E Tests）：模拟真实用户场景，验证完整流程

## 目录结构

```
tests/
├── __init__.py                    # 测试包初始化
├── conftest.py                    # pytest 共享配置与 fixtures
├── unit/                          # 单元测试目录
│   ├── __init__.py
│   └── test_*.py                  # 单元测试文件
├── integration/                   # 集成测试目录
│   ├── __init__.py
│   └── test_*.py                  # 集成测试文件
└── e2e/                           # 端到端测试目录
    ├── __init__.py
    └── test_*.py                  # E2E 测试文件
```

## Pytest 配置

配置定义在 `pyproject.toml` 中的 `[tool.pytest.ini_options]` 部分：

- **testpaths**：指定测试目录为 `tests/`
- **python_files**：测试文件命名规范为 `test_*.py` 或 `*_test.py`
- **markers**：自定义标记用于测试分类
- **asyncio_mode**：支持异步测试

## Fixtures（测试夹具）

共享 fixtures 定义在 `tests/conftest.py` 中：

### 内置 Fixtures

| Fixture | 功能 | 用途 |
|---------|------|------|
| `project_root` | 返回项目根目录路径 | 获取项目基础路径 |
| `config_dir` | 返回配置目录路径 | 访问配置文件 |
| `temp_data_dir` | 创建临时数据目录 | 隔离测试数据 |
| `mock_settings` | 提供模拟配置字典 | 测试配置逻辑 |
| `test_data_dir` | 返回测试数据目录 | 存储测试数据 |

### 使用示例

```python
@pytest.mark.unit
def test_example(project_root, mock_settings):
    """使用多个 fixtures 的示例。"""
    config_path = project_root / "config" / "settings.yaml"
    assert config_path.exists()
    assert mock_settings["llm"]["provider"] == "openai"
```

## 测试标记（Markers）

使用标记对测试进行分类：

```python
@pytest.mark.unit
def test_component_logic():
    """单元测试。"""
    pass

@pytest.mark.integration
def test_component_interaction():
    """集成测试。"""
    pass

@pytest.mark.e2e
def test_full_workflow():
    """端到端测试。"""
    pass

@pytest.mark.slow
def test_real_api_call():
    """标记为慢速测试（如真实 API 调用）。"""
    pass
```

## 运行测试

### 运行所有测试

```bash
pytest tests/ -v
```

### 运行特定测试文件

```bash
pytest tests/unit/test_pytest_setup.py -v
```

### 运行特定测试类或函数

```bash
pytest tests/unit/test_pytest_setup.py::TestPytestSetup::test_pytest_installed -v
```

### 按标记运行测试

```bash
# 仅运行单元测试
pytest -m unit

# 仅运行集成测试
pytest -m integration

# 仅运行 E2E 测试
pytest -m e2e

# 排除慢速测试
pytest -m "not slow"
```

### 生成覆盖率报告（需要 pytest-cov）

```bash
pytest tests/ --cov=src --cov-report=html
```

## 编写测试的最佳实践

### 1. 单元测试

- 测试单个函数或类的逻辑
- Mock 所有外部依赖（LLM API、数据库等）
- 快速执行（通常 < 100ms）

```python
@pytest.mark.unit
def test_chunk_validation(mock_settings):
    """测试 Chunk 数据验证逻辑。"""
    from src.core.types import Chunk
    
    chunk = Chunk(
        content="Test content",
        metadata={"source": "test.pdf"}
    )
    assert chunk.content == "Test content"
    assert chunk.metadata["source"] == "test.pdf"
```

### 2. 集成测试

- 测试多组件的协作
- 可使用真实实现，但需隔离数据
- 验证接口兼容性

```python
@pytest.mark.integration
def test_pipeline_integration(temp_data_dir, mock_settings):
    """测试 Ingestion Pipeline 多个阶段的协作。"""
    # 准备数据
    # 执行流程
    # 验证结果
    pass
```

### 3. 端到端测试

- 模拟真实用户场景
- 测试完整流程（如从文档摄取到查询返回）
- 可以较慢，但应有超时保护

```python
@pytest.mark.e2e
@pytest.mark.slow
def test_ingestion_to_query_workflow(project_root):
    """测试从文档摄取到查询的完整工作流。"""
    # 1. 准备测试文档
    # 2. 执行摄取
    # 3. 执行查询
    # 4. 验证结果
    pass
```

## Mock 和 Fixtures 模式

### Mock 外部 API

```python
from unittest.mock import patch, MagicMock

@pytest.mark.unit
def test_llm_call_with_mock():
    """Mock LLM API 调用。"""
    with patch('src.libs.llm.openai_llm.OpenAI') as mock_llm:
        mock_llm.return_value.generate.return_value = "Mocked response"
        # 测试代码
```

### 使用 Fixture 提供测试数据

```python
@pytest.fixture
def sample_pdf_path(test_data_dir):
    """提供示例 PDF 文件路径。"""
    pdf_path = test_data_dir / "sample.pdf"
    if not pdf_path.exists():
        # 创建或下载示例 PDF
        pass
    return pdf_path

@pytest.mark.integration
def test_pdf_loader(sample_pdf_path):
    """测试 PDF 加载器。"""
    from src.ingestion.loaders import PDFLoader
    loader = PDFLoader()
    docs = loader.load(sample_pdf_path)
    assert len(docs) > 0
```

## 持续集成建议

### 本地开发工作流

```bash
# 快速验证（仅单元测试）
pytest -m unit -x

# 完整验证（单元 + 集成）
pytest -m "unit or integration" --tb=short

# 包含 E2E 测试
pytest
```

### CI/CD 流程（可选）

```bash
# 单元测试 + 覆盖率
pytest -m unit --cov=src

# 集成测试
pytest -m integration

# E2E 测试（可选，可能较慢）
pytest -m e2e --timeout=300
```

## 常见问题

### Q: 如何为现有代码补充测试？

A: 参考"编写测试的最佳实践"部分，从单元测试开始，逐步补充集成和 E2E 测试。

### Q: 如何处理需要真实外部服务的测试？

A: 
- 优先 Mock 外部服务
- 使用 `@pytest.mark.slow` 标记
- 可在 CI/CD 中选择性跳过

### Q: 如何共享测试数据？

A: 将数据放在 `tests/data/` 目录，通过 `test_data_dir` fixture 访问。

### Q: 如何调试失败的测试？

A: 
```bash
pytest tests/unit/test_file.py::test_function -vv --tb=long
```

## 参考资源

- [Pytest 官方文档](https://docs.pytest.org/)
- [Python unittest.mock 文档](https://docs.python.org/3/library/unittest.mock.html)
- 项目规范：`DEV_SPEC.md` - 第 4 章"测试方案"
