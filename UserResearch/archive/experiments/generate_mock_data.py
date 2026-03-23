import pandas as pd
import numpy as np

# Create mock data
n_samples = 100
np.random.seed(42)

data = {
    '序号': range(1, n_samples + 1),
    'Q1.性别': np.random.choice(['男', '女'], n_samples),
    'Q2.年龄段': np.random.choice(['18岁以下', '18-24岁', '25-30岁', '31岁以上'], n_samples),
    'Q3.游戏类型:RPG': np.random.choice([0, 1], n_samples, p=[0.4, 0.6]),
    'Q3.游戏类型:FPS': np.random.choice([0, 1], n_samples, p=[0.3, 0.7]),
    'Q3.游戏类型:MOBA': np.random.choice([0, 1], n_samples, p=[0.2, 0.8]),
    'Q4.满意度:画面': np.random.choice(['非常满意', '满意', '一般', '不满意', '非常不满意'], n_samples),
    'Q4.满意度:玩法': np.random.choice(['非常满意', '满意', '一般', '不满意', '非常不满意'], n_samples),
    'Q5.NPS打分': np.random.randint(0, 11, n_samples)
}

df = pd.DataFrame(data)

# Save to Excel
file_path = 'd:\\SUN用研运营\\Python分析工具\\问卷数表\\mock_survey_data.xlsx'
df.to_excel(file_path, index=False)
print(f"Mock data generated at {file_path}")
