"""Simple Streamlit entry point for the MediKiosk prototype."""


def run() -> None:
    import streamlit as st

    st.set_page_config(page_title="MediKiosk")
    st.title("MediKiosk")
    st.caption("Adaptive clinical-questioning prototype")
    st.text_input("What brings you in today?")
