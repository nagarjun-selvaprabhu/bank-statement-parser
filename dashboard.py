import streamlit as st
import sqlite3
import pandas as pd
import plotly.express as px
import math

def format_inr(amount):
    """Formats a number into the Indian numbering system (e.g., ₹69,00,778.48)"""
    is_negative = amount < 0
    amount = abs(amount)
    
    int_part, dec_part = f"{amount:.2f}".split('.')
    
    if len(int_part) <= 3:
        formatted_int = int_part
    else:
        last_three = int_part[-3:]
        remaining = int_part[:-3]
        
        groups = []
        while remaining:
            groups.append(remaining[-2:])
            remaining = remaining[:-2]
        
        groups.reverse()
        formatted_int = ",".join(groups) + "," + last_three
        
    result = f"₹{formatted_int}.{dec_part}"
    return f"-{result}" if is_negative else result

def apply_inr_axis(fig, max_val, axis='y'):
    """Dynamically calculates chart axes to override '200k' with '₹2,00,000'"""
    if pd.isna(max_val) or max_val <= 0:
        return fig
        
    digits = int(math.log10(max_val))
    step = 10 ** digits
    
    # Adjust step size for perfectly spaced chart lines
    if max_val / step < 2:
        step = step / 5
    elif max_val / step < 5:
        step = step / 2
        
    tickvals = [i * step for i in range(int(max_val / step) + 2)]
    # Drop decimals for clean axis labels
    ticktext = [format_inr(val).split('.')[0] for val in tickvals] 
    
    if axis == 'y':
        fig.update_layout(yaxis=dict(tickmode='array', tickvals=tickvals, ticktext=ticktext))
    elif axis == 'x':
        fig.update_layout(xaxis=dict(tickmode='array', tickvals=tickvals, ticktext=ticktext))
        
    return fig

# --- PAGE CONFIG ---
st.set_page_config(page_title="Personal Finance Engine", page_icon="💳", layout="wide")
st.title("💳  Personal Finance Dashboard")

# --- LOAD DATA ---
@st.cache_data
def load_data():
    conn = sqlite3.connect("expenses.db")
    df = pd.read_sql_query("SELECT * FROM transactions", conn)
    conn.close()
    
    df['txn_datetime'] = pd.to_datetime(df['txn_datetime'])
    
    df['Year'] = df['txn_datetime'].dt.year.astype(str)
    df['Month'] = df['txn_datetime'].dt.month
    df['Month_Name'] = df['txn_datetime'].dt.strftime('%b')
    df['Year-Month'] = df['txn_datetime'].dt.to_period('M').astype(str)
    
    return df

df = load_data()

# --- SIDEBAR FILTERS ---
st.sidebar.header("🔍 Filter Your Data")
txn_types = df['txn_type'].unique().tolist()
selected_types = st.sidebar.multiselect("Transaction Type", txn_types, default=["DEBIT"])

banks = df['bank_name'].unique().tolist()
selected_banks = st.sidebar.multiselect("Select Bank", banks, default=banks)

available_cards = df[df['bank_name'].isin(selected_banks)]['card_name'].unique().tolist()
selected_cards = st.sidebar.multiselect("Select Card", available_cards, default=available_cards)

# APPLY FILTERS
filtered_df = df[
    (df['txn_type'].isin(selected_types)) &
    (df['bank_name'].isin(selected_banks)) &
    (df['card_name'].isin(selected_cards))
].copy() # Copy prevents warning when we format the raw data table later

# --- TOP METRICS ROW ---
total_debit = df[(df['txn_type'] == 'DEBIT') & (df['card_name'].isin(selected_cards))]['amount'].sum()
total_credit = df[(df['txn_type'] == 'CREDIT') & (df['card_name'].isin(selected_cards))]['amount'].sum()

m1, m2, m3 = st.columns(3)
m1.metric("🔴 Total Filtered Spends (Debit)", format_inr(total_debit))
m2.metric("🟢 Total Filtered Payments/Refunds (Credit)", format_inr(total_credit))
m3.metric("📊 Filtered Transactions", len(filtered_df))

st.divider()

# --- ROW 1: TIME SERIES & CARD DISTRIBUTION ---
col1, col2 = st.columns([2, 1])

with col1:
    st.subheader("Overall Volume Over Time")
    trend_data = filtered_df.groupby(['Year-Month', 'txn_type'])['amount'].sum().reset_index()
    trend_data['inr_text'] = trend_data['amount'].apply(format_inr)
    
    fig_trend = px.bar(trend_data, x='Year-Month', y='amount', color='txn_type', 
                       barmode='group', color_discrete_map={"DEBIT": "#EF553B", "CREDIT": "#00CC96"},
                       custom_data=['inr_text'])
    
    fig_trend.update_traces(hovertemplate='Month: %{x}<br>Amount: %{customdata[0]}')
    fig_trend = apply_inr_axis(fig_trend, trend_data['amount'].max(), 'y')
    st.plotly_chart(fig_trend, use_container_width=True)

with col2:
    st.subheader("Card-Wise Breakdown")
    card_data = filtered_df.groupby('card_name')['amount'].sum().reset_index()
    card_data['inr_text'] = card_data['amount'].apply(format_inr)
    
    fig_cards = px.pie(card_data, names='card_name', values='amount', hole=0.4, custom_data=['inr_text'])
    fig_cards.update_traces(textposition='inside', textinfo='percent+label', 
                            hovertemplate='%{label}<br>Amount: %{customdata[0]}<br>Share: %{percent}')
    st.plotly_chart(fig_cards, use_container_width=True)

st.divider()

# --- ROW 2: YEAR-OVER-YEAR MONTHLY COMPARISON ---
st.subheader("📅 Monthly Spend Comparison (Year-over-Year)")

spend_df = filtered_df[filtered_df['txn_type'] == 'DEBIT']

if not spend_df.empty:
    mom_data = spend_df.groupby(['Year', 'Month', 'Month_Name'])['amount'].sum().reset_index()
    mom_data = mom_data.sort_values('Month')
    mom_data['inr_text'] = mom_data['amount'].apply(format_inr)
    
    fig_mom = px.line(mom_data, x='Month_Name', y='amount', color='Year', markers=True,
                      labels={'Month_Name': 'Month', 'amount': 'Total Spend'}, custom_data=['inr_text'])
                      
    fig_mom.update_traces(hovertemplate='Month: %{x}<br>Amount: %{customdata[0]}')
    fig_mom.update_xaxes(categoryorder='array', categoryarray=['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'])
    fig_mom = apply_inr_axis(fig_mom, mom_data['amount'].max(), 'y')
    
    st.plotly_chart(fig_mom, use_container_width=True)
else:
    st.info("No debit transactions found for the selected filters.")

st.divider()

# --- ROW 3: CATEGORY & RAW DATA ---
col3, col4 = st.columns([1, 1])

with col3:
    st.subheader("Category-Wise Spend")
    cat_data = filtered_df.groupby('category')['amount'].sum().reset_index().sort_values('amount', ascending=True)
    cat_data['inr_text'] = cat_data['amount'].apply(format_inr)
    
    fig_cat = px.bar(cat_data, x='amount', y='category', orientation='h', color='category', custom_data=['inr_text'])
    fig_cat.update_traces(hovertemplate='Category: %{y}<br>Amount: %{customdata[0]}')
    fig_cat.update_layout(showlegend=False)
    fig_cat = apply_inr_axis(fig_cat, cat_data['amount'].max(), 'x')
    
    st.plotly_chart(fig_cat, use_container_width=True)

with col4:
    st.subheader("Raw Transaction Data")
    display_df = filtered_df[['txn_datetime', 'bank_name', 'description', 'amount', 'txn_type', 'category']].copy()
    display_df = display_df.sort_values('txn_datetime', ascending=False)
    
    # Format the amount column into strings for the table display
    display_df['amount'] = display_df['amount'].apply(format_inr)
    
    st.dataframe(display_df, hide_index=True, height=400)