from survey_tools.web.quant_app import main
import streamlit as st

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        st.error(f"应用启动失败: {e}")
