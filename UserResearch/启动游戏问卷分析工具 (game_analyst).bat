@echo off
:: 1. 切换到 D 盘
d:
:: 2. 进入你的项目文件夹
cd "d:/SUN用研运营/Python分析工具/问卷数表"
:: 3. 运行 Streamlit (使用 python -m 模式最稳)
python -m streamlit run game_analyst.py
:: 如果程序意外退出，保持窗口不关闭以便查看报错
pause