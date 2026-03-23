#终极一招：直接把文件“拖进”命令行
#如果你不确定路径或者文件名对不对，可以尝试这样做：
#在命令行里先输入：python -m streamlit run （注意末尾留一个空格）。
#用鼠标选中你的那个代码文件，直接拖进黑色命令行窗口里。
#命令行会自动填充该文件的完整路径（例如 "C:\Users\Desktop\my_analysis.py"）。
#按下回车键。

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

# 设置页面配置
st.set_page_config(page_title="满意度驱动力分析工具", layout="wide")

st.title("📊 满意度四分图分析 (IPA)")
st.markdown("""
通过计算细项得分的**均值**（表现）与整体满意度的**相关系数**（重要性），识别“拖累”项。
""")

# 1. 文件上传
uploaded_file = st.file_uploader("第一步：上传您的 Excel 数据文件", type=["xlsx", "xls"])

if uploaded_file:
    df = pd.read_excel(uploaded_file)
    st.write("数据预览：", df.head(5))
    
    columns = df.columns.tolist()
    
    # 2. 变量选择
    col1, col2 = st.columns(2)
    with col1:
        target_col = st.selectbox("第二步：选择【整体满意度】列", options=columns)
    with col2:
        feature_cols = st.multiselect("第三步：选择【细项满意度】列（支持20+项）", 
                                      options=[c for c in columns if c != target_col])

    if target_col and feature_cols:
        # 计算指标
        results = []
        for col in feature_cols:
            # 计算平均分（满意度现状）
            mean_score = df[col].mean()
            # 计算皮尔森相关系数（重要性/影响力）
            correlation = df[col].corr(df[target_col])
            results.append({
                "细项名称": col,
                "满意度评分": round(mean_score, 2),
                "对整体的影响力": round(correlation, 3)
            })
        
        res_df = pd.DataFrame(results)

        # 3. 设置象限分割线（默认取均值）
        st.divider()
        st.subheader("分析结果")
        
        x_mean = res_df["满意度评分"].mean()
        y_mean = res_df["对整体的影响力"].mean()

        # 4. 绘制交互式散点图
        fig = px.scatter(
            res_df, 
            x="满意度评分", 
            y="对整体的影响力", 
            text="细项名称",
            hover_name="细项名称",
            size_max=60,
            template="plotly_white",
            title="满意度 IPA 矩阵（四分图）"
        )

        # 添加象限参考线
        fig.add_hline(y=y_mean, line_dash="dash", line_color="red", annotation_text="平均影响力")
        fig.add_vline(x=x_mean, line_dash="dash", line_color="red", annotation_text="平均得分")

        # 优化视觉
        fig.update_traces(textposition='top center', marker=dict(size=12, color='royalblue', line=dict(width=2, color='DarkSlateGrey')))
        fig.update_layout(
            height=600,
            xaxis_title="满意度得分（表现）",
            yaxis_title="相关系数（重要性）",
            annotations=[
                dict(x=x_mean*1.1, y=y_mean*1.1, text="重点保持区", showarrow=False, opacity=0.3, font=dict(size=20)),
                dict(x=x_mean*0.9, y=y_mean*1.1, text="重点改进区（拖累项）", showarrow=False, opacity=0.3, font=dict(size=20, color="red")),
                dict(x=x_mean*0.9, y=y_mean*0.9, text="次要改进区", showarrow=False, opacity=0.3, font=dict(size=20)),
                dict(x=x_mean*1.1, y=y_mean*0.9, text="过度服务区", showarrow=False, opacity=0.3, font=dict(size=20))
            ]
        )

        st.plotly_chart(fig, use_container_width=True)

        # 5. 显示明细数据
        st.subheader("数据明细记录")
        st.dataframe(res_df.sort_values(by="对整体的影响力", ascending=False))
        
        # 识别拖累项
        draggers = res_df[(res_df["满意度评分"] < x_mean) & (res_df["对整体的影响力"] > y_mean)]
        if not draggers.empty:
            st.warning(f"🚨 **分析结论：** 发现以下 {len(draggers)} 个核心拖累项：{', '.join(draggers['细项名称'].tolist())}。这些项影响力大但得分低，应优先优化。")
        else:
            st.success("✅ 暂时没有发现处于‘重点改进区’的明显拖累项。")

else:
    st.info("💡 请在上方上传 Excel 文件（第一列通常为样本 ID，确保数据是纯数字评分）。")
