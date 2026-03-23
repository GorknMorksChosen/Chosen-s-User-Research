import pandas as pd
import seaborn as sns
import matplotlib.pyplot as plt

# 1. 配置区域
FILE_PATH = r'D:\SUN用研运营\主角设计问卷数据\survey_data_ranking.xlsx' #Windows 用户： 找到文件，按住 Shift 键并右键点击文件，选择“复制文件路径”。注意： Windows 路径需要加一个 r 在引号前面，防止反斜杠报错。比如r'D:\SUN用研运营\主角设计问卷数据\survey_data.xlsx'
COL_LABEL = '用户标签'  # 第一列名称
# 根据你的描述，列名可能是“排序第1位”、“排序第2位”等，请据实修改
RANK_COLUMNS = ['排序第1位', '排序第2位', '排序第3位', '排序第4位', '排序第5位']

# 设置中文字体
plt.rcParams['font.sans-serif'] = ['SimHei'] 
plt.rcParams['axes.unicode_minus'] = False

def analyze_advanced_ranking(path):
    # 2. 读取并清洗
    df = pd.read_excel(path)
    # 获取所有选项的名称清单
    all_options = pd.unique(df[RANK_COLUMNS].values.ravel())
    all_options = [x for x in all_options if str(x) != 'nan']
    
    # 获取每个标签的人数样本量，用于后续计算百分比
    tag_counts = df[COL_LABEL].value_counts()

    # 3. 数据处理逻辑
    # a) 计算平均得分 (Weighted Score)
    extracted_data = []
    weights = {RANK_COLUMNS[i]: 5-i for i in range(5)} # 1名5分...5名1分
    
    for _, row in df.iterrows():
        for col in RANK_COLUMNS:
            extracted_data.append({
                'Tag': row[COL_LABEL],
                'Option': row[col],
                'Score': weights[col],
                'is_top1': 1 if col == RANK_COLUMNS[0] else 0,
                'is_top2': 1 if col in RANK_COLUMNS[:2] else 0
            })
    
    long_df = pd.DataFrame(extracted_data).dropna()

    # --- 计算三个核心指标 ---
    
    # 指标 1: 平均分
    avg_score = long_df.groupby(['Tag', 'Option'])['Score'].mean().unstack(fill_value=0)

    # 指标 2: Top 1 率 (第一名人数 / 该标签总人数)
    top1_count = long_df[long_df['is_top1'] == 1].groupby(['Tag', 'Option']).size().unstack(fill_value=0)
    top1_rate = top1_count.div(tag_counts, axis=0) * 100

    # 指标 3: Top 2 率 (前两名总人数 / 该标签总人数)
    top2_count = long_df[long_df['is_top2'] == 1].groupby(['Tag', 'Option']).size().unstack(fill_value=0)
    top2_rate = top2_count.div(tag_counts, axis=0) * 100

    # 4. 绘图：三合一画布
    fig, axes = plt.subplots(3, 1, figsize=(12, 18))

    # 热力图 1: 平均得分
    sns.heatmap(avg_score, annot=True, fmt='.2f', cmap='YlGnBu', ax=axes[0])
    axes[0].set_title('1. 角色类型：平均加权得分 (综合好感度)', fontsize=14)

    # 热力图 2: Top 1 Rate
    sns.heatmap(top1_rate, annot=True, fmt='.1f', cmap='OrRd', ax=axes[1])
    axes[1].set_title('2. 角色类型：第一提及率 Top 1 % (核心死忠偏好)', fontsize=14)

    # 热力图 3: Top 2 Rate
    sns.heatmap(top2_rate, annot=True, fmt='.1f', cmap='Purples', ax=axes[2])
    axes[2].set_title('3. 角色类型：前两名胜出率 Top 2 % (大众接受度)', fontsize=14)

    for ax in axes:
        ax.set_xlabel('主角类型选项')
        ax.set_ylabel('用户标签')

    plt.tight_layout()
    plt.show()

if __name__ == "__main__":
    analyze_advanced_ranking(FILE_PATH)
