# 亏损计算系统

跨境电商利润计算工具，支持 Wildberries店铺利润计算、佣金匹配、折扣推算等功能。

## 功能特性

- **利润计算**: 支持跨境电商多店铺（本地/跨境）模式下的利润计算
- **佣金匹配**: 两步匹配（SKU → 商品 → 品类）自动获取佣金
- **折扣推算**: 基于利润目标的折扣推荐
- **数据导入**: 支持 Excel 模板导入
- **数据库管理**: 内置 SQLite 数据库存储

## 项目结构

```
├── src/
│   ├── config.py          # 配置文件
│   ├── main.py            # 主入口
│   ├── models/           # 数据模型
│   ├── services/         # 业务服务
│   └── ui/               # 界面
├── scripts/              # 工具脚本
├── tests/               # 测试
├── dist/                # 打包输出
└── data/                # 数据目录
```

## 快速开始

### 安装依赖

```bash
pip install -r requirements.txt
```

### 运行

```bash
python src/main.py
```

或直接运行打包好的 exe：

```bash
dist/WB系统.exe
```

## 技术栈

- Python 3.10+
- PyQt5 / PySide6 (GUI)
- SQLite (数据库)

## 许可证

MIT License