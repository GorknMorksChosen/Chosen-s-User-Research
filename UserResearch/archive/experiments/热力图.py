import pandas as pd
import seaborn as sns
import matplotlib.pyplot as plt
import math

# 1. 配置区域
FILE_PATH = r'D:\SUN用研运营\主角设计问卷数据\survey_data.xlsx' #Windows 用户： 找到文件，按住 Shift 键并右键点击文件，选择“复制文件路径”。注意： Windows 路径需要加一个 r 在引号前面，防止反斜杠报错。
COL_LABEL = '用户标签'  # 替换为你Excel中标签列的实际名称
COL_Q6 = 'Q6'
COL_Q8 = 'Q8'

# 设置中文字体
plt.rcParams['font.sans-serif'] = ['SimHei'] 
plt.rcParams['axes.unicode_minus'] = False

def analyze_by_tags(path):
    # 2. 读取并清洗数据
    df = pd.read_excel(path)
    df = df[[COL_LABEL, COL_Q6, COL_Q8]].dropna()
    df[COL_Q6] = df[COL_Q6].astype(int)
    df[COL_Q8] = df[COL_Q8].astype(int)

    # 获取所有唯一的标签
    unique_labels = df[COL_LABEL].unique()
    num_labels = len(unique_labels)
    
    # 3. 动态计算布局（每行放2个图）
    cols_per_row = 2
    rows = math.ceil(num_labels / cols_per_row)
    
    fig, axes = plt.subplots(rows, cols_per_row, figsize=(12, 5 * rows))
    axes = axes.flatten() # 转为一维方便循环

    full_range = [1, 2, 3, 4, 5]

    # 4. 循环为每个标签绘图
    for i, label in enumerate(unique_labels):
        ax = axes[i]
        label_data = df[df[COL_LABEL] == label]
        
        # 计算交叉频数
        ct = pd.crosstab(label_data[COL_Q8], label_data[COL_Q6])
        ct = ct.reindex(index=full_range, columns=full_range, fill_value=0)
        
        # 转化为百分比（在该标签内部的占比），这样更有对比意义
        ct_percent = (ct / ct.sum().sum() * 100).round(1)
        
        # 绘制热力图
        sns.heatmap(ct_percent, annot=True, fmt='.1f', cmap='YlGnBu', ax=ax, cbar=False)
        
        ax.set_title(f'标签：{label} (样本数:{len(label_data)})', fontsize=13, pad=10)
        ax.set_xlabel('Q6 代入习惯' if i >= num_labels - cols_per_row else '')
        ax.set_ylabel('Q8 缺失感受' if i % cols_per_row == 0 else '')

    # 5. 移除多余的子图空白
    for j in range(i + 1, len(axes)):
        fig.delaxes(axes[j])

    plt.suptitle('不同用户群对“游戏主角”的需求交叉分析 (单位: %)', fontsize=16, y=1.02)
    plt.tight_layout()
    plt.show()

if __name__ == "__main__":
    analyze_by_tags(FILE_PATH)
