import pandas as pd
import seaborn as sns
import matplotlib.pyplot as plt

# 1. 配置区域
FILE_PATH = r'D:\SUN用研运营\主角设计问卷数据\survey_data_ranking.xlsx' #Windows 用户： 找到文件，按住 Shift 键并右键点击文件，选择“复制文件路径”。注意： Windows 路径需要加一个 r 在引号前面，防止反斜杠报错。比如r'D:\SUN用研运营\主角设计问卷数据\survey_data.xlsx'
COL_LABEL = '用户标签'  
RANK_COLUMNS = ['排序第1位', '排序第2位', '排序第3位', '排序第4位', '排序第5位']

# 设置中文字体
plt.rcParams['font.sans-serif'] = ['SimHei']  
plt.rcParams['axes.unicode_minus'] = False

def analyze_advanced_ranking(path):
    # 2. 读取并清洗
    df = pd.read_excel(path)
    tag_counts = df[COL_LABEL].value_counts()

    # 3. 数据转换与指标计算
    extracted_data = []
    weights = {RANK_COLUMNS[i]: 5-i for i in range(5)} 
    
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

    # --- 计算三个核心指标矩阵 ---
    avg_score = long_df.groupby(['Tag', 'Option'])['Score'].mean().unstack(fill_value=0)
    top1_rate = (long_df[long_df['is_top1'] == 1].groupby(['Tag', 'Option']).size().unstack(fill_value=0)).div(tag_counts, axis=0) * 100
    top2_rate = (long_df[long_df['is_top2'] == 1].groupby(['Tag', 'Option']).size().unstack(fill_value=0)).div(tag_counts, axis=0) * 100

    # 4. --- 核心功能：基于启发式标准的自动化分类决策 ---
    # 定义分类函数
    def get_category(row):
        s = row['平均分']
        r1 = row['Top1率']
        r2 = row['Top2率']
        
        if r1 > 30 and r2 > 55 and s > 3.5:
            return "众望所归型"
        elif r1 > 30 and r2 <= 55:
            return "小众狂热型"
        elif r1 <= 30 and r2 > 55 and s > 3.0:
            return "安全备胎型"
        elif r1 > 25 and s <= 3.0:
            return "两极分化型"
        else:
            return "表现平平/待定"

    # 将三个矩阵合并为一个长表进行判定
    summary_list = []
    for tag in avg_score.index:
        for option in avg_score.columns:
            summary_list.append({
                '用户标签': tag,
                '主角类型': option,
                '平均分': avg_score.loc[tag, option],
                'Top1率': top1_rate.loc[tag, option],
                'Top2率': top2_rate.loc[tag, option]
            })
    
    analysis_df = pd.DataFrame(summary_list)
    analysis_df['需求分类结论'] = analysis_df.apply(get_category, axis=1)

    # 5. 输出结论表格
    print("\n" + "="*80)
    print("【自动化调研结论：主角类型需求分类报告】")
    print("="*80)
    # 按标签排序打印，方便阅读
    pd.set_option('display.max_rows', None) # 确保显示所有行
    display_df = analysis_df.sort_values(by=['用户标签', '平均分'], ascending=[True, False])
    print(display_df[['用户标签', '主角类型', '需求分类结论', '平均分', 'Top1率', 'Top2率']].to_string(index=False))
    print("="*80)

    # 6. 绘图（保留你原来的热力图展示）
    fig, axes = plt.subplots(3, 1, figsize=(12, 18))
    sns.heatmap(avg_score, annot=True, fmt='.2f', cmap='YlGnBu', ax=axes[0])
    axes[0].set_title('1. 角色类型：平均加权得分', fontsize=14)
    sns.heatmap(top1_rate, annot=True, fmt='.1f', cmap='OrRd', ax=axes[1])
    axes[1].set_title('2. 角色类型：第一提及率 Top 1 %', fontsize=14)
    sns.heatmap(top2_rate, annot=True, fmt='.1f', cmap='Purples', ax=axes[2])
    axes[2].set_title('3. 角色类型：前两名胜出率 Top 2 %', fontsize=14)
    plt.tight_layout()
    plt.show()

if __name__ == "__main__":
    analyze_advanced_ranking(FILE_PATH)
