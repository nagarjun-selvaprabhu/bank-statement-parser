import math
import sqlite3

import pandas as pd
import plotly.express as px
import streamlit as st


DB_FILE = "expenses.db"
MONTH_ORDER = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def format_inr(amount):
    """Format a number into the Indian numbering system."""
    if pd.isna(amount):
        amount = 0

    is_negative = amount < 0
    amount = abs(float(amount))
    int_part, dec_part = f"{amount:.2f}".split(".")

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

    result = f"Rs. {formatted_int}.{dec_part}"
    return f"-{result}" if is_negative else result


def format_inr_tick(amount):
    return format_inr(amount).split(".")[0]


def numeric_values(values):
    series = pd.Series(values if hasattr(values, "__iter__") and not isinstance(values, str) else [values])
    return pd.to_numeric(series, errors="coerce").dropna()


def inr_ticks(values):
    series = numeric_values(values)
    if series.empty:
        return None, None

    min_val = float(series.min())
    max_val = float(series.max())
    if min_val == 0 and max_val == 0:
        return None, None

    if min_val > 0:
        min_val = 0
    if max_val < 0:
        max_val = 0

    max_abs = max(abs(min_val), abs(max_val))
    digits = int(math.floor(math.log10(max_abs)))
    step = 10 ** digits
    if max_abs / step < 2:
        step = step / 5
    elif max_abs / step < 5:
        step = step / 2

    tick_min = math.floor(min_val / step) * step
    tick_max = math.ceil(max_val / step) * step
    tick_count = int(round((tick_max - tick_min) / step)) + 1

    while tick_count > 9:
        step *= 2
        tick_min = math.floor(min_val / step) * step
        tick_max = math.ceil(max_val / step) * step
        tick_count = int(round((tick_max - tick_min) / step)) + 1

    tickvals = [tick_min + (i * step) for i in range(tick_count)]
    ticktext = [format_inr_tick(val) for val in tickvals]
    return tickvals, ticktext


def apply_inr_axis(fig, values, axis="y"):
    """Use full INR labels instead of abbreviated 200k-style labels."""
    tickvals, ticktext = inr_ticks(values)
    if not tickvals:
        return fig

    if axis == "y":
        fig.update_yaxes(tickmode="array", tickvals=tickvals, ticktext=ticktext)
    elif axis == "x":
        fig.update_xaxes(tickmode="array", tickvals=tickvals, ticktext=ticktext)

    return fig


def apply_inr_colorbar(fig, values):
    """Use full INR labels on continuous color legends."""
    tickvals, ticktext = inr_ticks(values)
    if not tickvals:
        return fig

    fig.update_layout(
        coloraxis_colorbar=dict(
            tickmode="array",
            tickvals=tickvals,
            ticktext=ticktext,
        )
    )
    return fig


def apply_inr_heatmap(fig, pivot, label="Spend"):
    """Use INR labels for heatmap hover text and colorbar ticks."""
    fig.update_traces(
        customdata=pivot.apply(lambda column: column.map(format_inr)).to_numpy(),
        hovertemplate=f"%{{y}}<br>%{{x}}<br>{label}: %{{customdata}}<extra></extra>",
    )
    fig = apply_inr_colorbar(fig, pivot.to_numpy().ravel())

    return fig


def polish_chart(fig, height=None):
    fig.update_layout(
        margin=dict(l=10, r=10, t=35, b=10),
        hovermode="closest",
        legend_title_text="",
        font=dict(size=12),
    )
    if height:
        fig.update_layout(height=height)
    return fig


def debit_rows(frame):
    return frame[frame["txn_type"] == "DEBIT"].copy()


def credit_rows(frame):
    return frame[frame["txn_type"] == "CREDIT"].copy()


def group_amount(frame, group_cols):
    data = frame.groupby(group_cols, dropna=False)["amount"].sum().reset_index()
    data["inr_text"] = data["amount"].apply(format_inr)
    return data


@st.cache_data
def load_data():
    conn = sqlite3.connect(DB_FILE)
    df = pd.read_sql_query("SELECT * FROM transactions", conn)
    conn.close()

    df["txn_datetime"] = pd.to_datetime(df["txn_datetime"])
    df["Year"] = df["txn_datetime"].dt.year.astype(str)
    df["Month"] = df["txn_datetime"].dt.month
    df["Month_Name"] = df["txn_datetime"].dt.strftime("%b")
    df["Year-Month"] = df["txn_datetime"].dt.to_period("M").astype(str)
    df["Day"] = df["txn_datetime"].dt.day
    df["Weekday"] = df["txn_datetime"].dt.day_name()
    df["Weekday_Num"] = df["txn_datetime"].dt.weekday
    df["Signed_Amount"] = df.apply(
        lambda row: row["amount"] if row["txn_type"] == "DEBIT" else -row["amount"],
        axis=1,
    )
    return df


st.set_page_config(page_title="Personal Finance Dashboard", page_icon="💳", layout="wide")
st.title("Personal Finance Dashboard")

df = load_data()

st.sidebar.header("Filters")

txn_types = sorted(df["txn_type"].dropna().unique().tolist())
selected_types = st.sidebar.multiselect("Transaction Type", txn_types, default=txn_types)

banks = sorted(df["bank_name"].dropna().unique().tolist())
selected_banks = st.sidebar.multiselect("Bank", banks, default=banks)

available_cards = sorted(df[df["bank_name"].isin(selected_banks)]["card_name"].dropna().unique().tolist())
selected_cards = st.sidebar.multiselect("Credit Card", available_cards, default=available_cards)

available_categories = sorted(
    df[
        df["bank_name"].isin(selected_banks)
        & df["card_name"].isin(selected_cards)
    ]["category"].dropna().unique().tolist()
)
selected_categories = st.sidebar.multiselect("Category", available_categories, default=available_categories)

month_options = sorted(df["Year-Month"].dropna().unique().tolist(), reverse=True)
selected_month = st.sidebar.selectbox("Focus Month", month_options, index=0)

year_options = sorted(df["Year"].dropna().unique().tolist(), reverse=True)
selected_year = st.sidebar.selectbox("Focus Year", year_options, index=0)

date_min = df["txn_datetime"].min().date()
date_max = df["txn_datetime"].max().date()
selected_date_range = st.sidebar.date_input(
    "Date Range",
    value=(date_min, date_max),
    min_value=date_min,
    max_value=date_max,
)

if isinstance(selected_date_range, tuple) and len(selected_date_range) == 2:
    range_start, range_end = selected_date_range
else:
    range_start, range_end = date_min, date_max

filtered_df = df[
    df["txn_type"].isin(selected_types)
    & df["bank_name"].isin(selected_banks)
    & df["card_name"].isin(selected_cards)
    & df["category"].isin(selected_categories)
    & (df["txn_datetime"].dt.date >= range_start)
    & (df["txn_datetime"].dt.date <= range_end)
].copy()

spend_df = debit_rows(filtered_df)
credit_df = credit_rows(filtered_df)
month_df = filtered_df[filtered_df["Year-Month"] == selected_month].copy()
month_spend_df = debit_rows(month_df)
month_credit_df = credit_rows(month_df)
year_df = filtered_df[filtered_df["Year"] == selected_year].copy()
year_spend_df = debit_rows(year_df)
year_credit_df = credit_rows(year_df)

total_spend = spend_df["amount"].sum()
total_credits = credit_df["amount"].sum()
net_outflow = total_spend - total_credits

month_spend = month_spend_df["amount"].sum()
month_credits = month_credit_df["amount"].sum()
month_net = month_spend - month_credits
year_spend = year_spend_df["amount"].sum()
year_credits = year_credit_df["amount"].sum()
year_net = year_spend - year_credits

previous_month = (pd.Period(selected_month) - 1).strftime("%Y-%m")
prev_spend = debit_rows(filtered_df[filtered_df["Year-Month"] == previous_month])["amount"].sum()
spend_delta = month_spend - prev_spend
previous_year = str(int(selected_year) - 1)
prev_year_spend = debit_rows(filtered_df[filtered_df["Year"] == previous_year])["amount"].sum()
year_spend_delta = year_spend - prev_year_spend

st.subheader("Selected Scope")
m1, m2, m3, m4 = st.columns(4)
m1.metric("Total Spend", format_inr(total_spend))
m2.metric("Payments and Credits", format_inr(total_credits))
m3.metric("Net Outflow", format_inr(net_outflow))
m4.metric("Transactions", f"{len(filtered_df):,}")

st.divider()

st.subheader(f"Month Snapshot: {selected_month}")
mm1, mm2, mm3, mm4, mm5 = st.columns(5)
mm1.metric("Month Spend", format_inr(month_spend), delta=format_inr(spend_delta))
mm2.metric("Month Credits", format_inr(month_credits))
mm3.metric("Month Net", format_inr(month_net))
mm4.metric("Active Cards", f"{month_df['card_name'].nunique():,}")
mm5.metric("Transactions", f"{len(month_df):,}")

tab_overview, tab_month, tab_yearly, tab_trends, tab_mix, tab_merchants, tab_transactions = st.tabs(
    [
        "Overview",
        "Month Drilldown",
        "Yearly",
        "Trends",
        "Category and Card Mix",
        "Merchants",
        "Transactions",
    ]
)

with tab_overview:
    col1, col2 = st.columns([2, 1])

    with col1:
        st.subheader("Overall Volume Over Time")
        trend_data = filtered_df.groupby(["Year-Month", "txn_type"])["amount"].sum().reset_index()
        trend_data["inr_text"] = trend_data["amount"].apply(format_inr)
        if trend_data.empty:
            st.info("No transactions for the selected filters.")
        else:
            fig = px.bar(
                trend_data,
                x="Year-Month",
                y="amount",
                color="txn_type",
                barmode="group",
                color_discrete_map={"DEBIT": "#D95F02", "CREDIT": "#1B9E77"},
                custom_data=["inr_text"],
                labels={"amount": "Amount", "Year-Month": "Month"},
            )
            fig.update_traces(hovertemplate="Month: %{x}<br>Amount: %{customdata[0]}<extra></extra>")
            fig = apply_inr_axis(fig, trend_data["amount"].max(), "y")
            st.plotly_chart(polish_chart(fig, 430), width="stretch")

    with col2:
        st.subheader("Card-Wise Breakdown")
        card_data = group_amount(filtered_df, ["card_name"]).sort_values("amount", ascending=False)
        if card_data.empty:
            st.info("No card data for the selected filters.")
        else:
            fig = px.pie(
                card_data,
                names="card_name",
                values="amount",
                hole=0.42,
                custom_data=["inr_text"],
            )
            fig.update_traces(
                textposition="inside",
                textinfo="percent+label",
                hovertemplate="Card: %{label}<br>Amount: %{customdata[0]}<br>Share: %{percent}<extra></extra>",
            )
            st.plotly_chart(polish_chart(fig, 430), width="stretch")

    col3, col4 = st.columns([1, 1])

    with col3:
        st.subheader("Monthly Spend Comparison by Year")
        yoy_data = spend_df.groupby(["Year", "Month", "Month_Name"])["amount"].sum().reset_index()
        yoy_data = yoy_data.sort_values("Month")
        yoy_data["inr_text"] = yoy_data["amount"].apply(format_inr)
        if yoy_data.empty:
            st.info("No debit transactions for the selected filters.")
        else:
            fig = px.line(
                yoy_data,
                x="Month_Name",
                y="amount",
                color="Year",
                markers=True,
                custom_data=["inr_text"],
                labels={"Month_Name": "Month", "amount": "Spend"},
            )
            fig.update_xaxes(categoryorder="array", categoryarray=MONTH_ORDER)
            fig.update_traces(hovertemplate="Month: %{x}<br>Spend: %{customdata[0]}<extra></extra>")
            fig = apply_inr_axis(fig, yoy_data["amount"].max(), "y")
            st.plotly_chart(polish_chart(fig, 420), width="stretch")

    with col4:
        st.subheader("Category-Wise Spend")
        cat_data = group_amount(spend_df, ["category"]).sort_values("amount", ascending=True)
        if cat_data.empty:
            st.info("No debit transactions for the selected filters.")
        else:
            fig = px.bar(
                cat_data,
                x="amount",
                y="category",
                orientation="h",
                color="category",
                custom_data=["inr_text"],
                labels={"amount": "Spend", "category": "Category"},
            )
            fig.update_traces(hovertemplate="Category: %{y}<br>Spend: %{customdata[0]}<extra></extra>")
            fig.update_layout(showlegend=False)
            fig = apply_inr_axis(fig, cat_data["amount"].max(), "x")
            st.plotly_chart(polish_chart(fig, 420), width="stretch")

    st.subheader("Raw Transaction Data")
    overview_table = filtered_df.sort_values("txn_datetime", ascending=False).copy()
    overview_table["amount"] = overview_table["amount"].apply(format_inr)
    overview_table["txn_datetime"] = overview_table["txn_datetime"].dt.strftime("%Y-%m-%d")
    st.dataframe(
        overview_table[["txn_datetime", "bank_name", "card_name", "description", "amount", "txn_type", "category"]],
        hide_index=True,
        height=420,
    )

with tab_month:
    col1, col2 = st.columns([1, 1])

    with col1:
        st.subheader("Spend by Category")
        if month_spend_df.empty:
            st.info("No debit transactions for the selected month and filters.")
        else:
            cat_data = group_amount(month_spend_df, ["category"]).sort_values("amount", ascending=True)
            fig = px.bar(
                cat_data,
                x="amount",
                y="category",
                orientation="h",
                color="category",
                custom_data=["inr_text"],
                labels={"amount": "Spend", "category": "Category"},
            )
            fig.update_traces(hovertemplate="Category: %{y}<br>Spend: %{customdata[0]}<extra></extra>")
            fig.update_layout(showlegend=False)
            fig = apply_inr_axis(fig, cat_data["amount"].max(), "x")
            st.plotly_chart(polish_chart(fig, 460), width="stretch")

    with col2:
        st.subheader("Spend by Credit Card")
        if month_spend_df.empty:
            st.info("No debit transactions for the selected month and filters.")
        else:
            card_data = group_amount(month_spend_df, ["card_name"]).sort_values("amount", ascending=True)
            fig = px.bar(
                card_data,
                x="amount",
                y="card_name",
                orientation="h",
                color="card_name",
                custom_data=["inr_text"],
                labels={"amount": "Spend", "card_name": "Credit Card"},
            )
            fig.update_traces(hovertemplate="Card: %{y}<br>Spend: %{customdata[0]}<extra></extra>")
            fig.update_layout(showlegend=False)
            fig = apply_inr_axis(fig, card_data["amount"].max(), "x")
            st.plotly_chart(polish_chart(fig, 460), width="stretch")

    col3, col4 = st.columns([2, 1])

    with col3:
        st.subheader("Daily Spend in Month")
        if month_spend_df.empty:
            st.info("No daily spend to plot.")
        else:
            daily = group_amount(month_spend_df, ["txn_datetime"]).sort_values("txn_datetime")
            fig = px.line(
                daily,
                x="txn_datetime",
                y="amount",
                markers=True,
                custom_data=["inr_text"],
                labels={"txn_datetime": "Date", "amount": "Spend"},
            )
            fig.update_traces(hovertemplate="Date: %{x|%d %b %Y}<br>Spend: %{customdata[0]}<extra></extra>")
            fig = apply_inr_axis(fig, daily["amount"].max(), "y")
            st.plotly_chart(polish_chart(fig, 360), width="stretch")

    with col4:
        st.subheader("Month Category Share")
        if month_spend_df.empty:
            st.info("No category share to show.")
        else:
            share_data = group_amount(month_spend_df, ["category"]).sort_values("amount", ascending=False)
            fig = px.pie(
                share_data,
                names="category",
                values="amount",
                hole=0.45,
                custom_data=["inr_text"],
            )
            fig.update_traces(
                textinfo="percent+label",
                hovertemplate="Category: %{label}<br>Spend: %{customdata[0]}<br>Share: %{percent}<extra></extra>",
            )
            st.plotly_chart(polish_chart(fig, 360), width="stretch")

with tab_yearly:
    st.subheader(f"Year Snapshot: {selected_year}")
    yy1, yy2, yy3, yy4, yy5 = st.columns(5)
    yy1.metric("Year Spend", format_inr(year_spend), delta=format_inr(year_spend_delta))
    yy2.metric("Year Credits", format_inr(year_credits))
    yy3.metric("Year Net", format_inr(year_net))
    yy4.metric("Active Cards", f"{year_df['card_name'].nunique():,}")
    yy5.metric("Transactions", f"{len(year_df):,}")

    col1, col2 = st.columns([1, 1])

    with col1:
        st.subheader("Yearly Spend vs Credits")
        annual = filtered_df.groupby(["Year", "txn_type"])["amount"].sum().reset_index()
        annual["inr_text"] = annual["amount"].apply(format_inr)
        if annual.empty:
            st.info("No yearly data for the selected filters.")
        else:
            fig = px.bar(
                annual,
                x="Year",
                y="amount",
                color="txn_type",
                barmode="group",
                color_discrete_map={"DEBIT": "#D95F02", "CREDIT": "#1B9E77"},
                custom_data=["inr_text"],
                labels={"amount": "Amount"},
            )
            fig.update_traces(hovertemplate="Year: %{x}<br>Amount: %{customdata[0]}<extra></extra>")
            fig = apply_inr_axis(fig, annual["amount"].max(), "y")
            st.plotly_chart(polish_chart(fig, 430), width="stretch")

    with col2:
        st.subheader("Net Outflow by Year")
        annual_net = filtered_df.groupby("Year")["Signed_Amount"].sum().reset_index()
        annual_net["inr_text"] = annual_net["Signed_Amount"].apply(format_inr)
        if annual_net.empty:
            st.info("No yearly net data for the selected filters.")
        else:
            fig = px.bar(
                annual_net,
                x="Year",
                y="Signed_Amount",
                color="Signed_Amount",
                color_continuous_scale=["#1B9E77", "#F7F7F7", "#D95F02"],
                custom_data=["inr_text"],
                labels={"Signed_Amount": "Net Outflow"},
            )
            fig.update_traces(hovertemplate="Year: %{x}<br>Net: %{customdata[0]}<extra></extra>")
            fig = apply_inr_axis(fig, annual_net["Signed_Amount"], "y")
            fig = apply_inr_colorbar(fig, annual_net["Signed_Amount"])
            st.plotly_chart(polish_chart(fig, 430), width="stretch")

    col3, col4 = st.columns([1, 1])

    with col3:
        st.subheader(f"{selected_year} Spend by Category")
        year_cat = group_amount(year_spend_df, ["category"]).sort_values("amount", ascending=True)
        if year_cat.empty:
            st.info("No category spend for the selected year.")
        else:
            fig = px.bar(
                year_cat,
                x="amount",
                y="category",
                orientation="h",
                color="category",
                custom_data=["inr_text"],
                labels={"amount": "Spend", "category": "Category"},
            )
            fig.update_traces(hovertemplate="Category: %{y}<br>Spend: %{customdata[0]}<extra></extra>")
            fig.update_layout(showlegend=False)
            fig = apply_inr_axis(fig, year_cat["amount"].max(), "x")
            st.plotly_chart(polish_chart(fig, 500), width="stretch")

    with col4:
        st.subheader(f"{selected_year} Spend by Credit Card")
        year_card = group_amount(year_spend_df, ["card_name"]).sort_values("amount", ascending=True)
        if year_card.empty:
            st.info("No card spend for the selected year.")
        else:
            fig = px.bar(
                year_card,
                x="amount",
                y="card_name",
                orientation="h",
                color="card_name",
                custom_data=["inr_text"],
                labels={"amount": "Spend", "card_name": "Credit Card"},
            )
            fig.update_traces(hovertemplate="Card: %{y}<br>Spend: %{customdata[0]}<extra></extra>")
            fig.update_layout(showlegend=False)
            fig = apply_inr_axis(fig, year_card["amount"].max(), "x")
            st.plotly_chart(polish_chart(fig, 500), width="stretch")

    col5, col6 = st.columns([1, 1])

    with col5:
        st.subheader(f"{selected_year} Month-by-Month Spend")
        year_month = year_spend_df.groupby(["Month", "Month_Name"])["amount"].sum().reset_index()
        year_month = year_month.sort_values("Month")
        year_month["inr_text"] = year_month["amount"].apply(format_inr)
        if year_month.empty:
            st.info("No monthly spend for the selected year.")
        else:
            fig = px.bar(
                year_month,
                x="Month_Name",
                y="amount",
                color="Month_Name",
                custom_data=["inr_text"],
                labels={"Month_Name": "Month", "amount": "Spend"},
            )
            fig.update_xaxes(categoryorder="array", categoryarray=MONTH_ORDER)
            fig.update_traces(hovertemplate="Month: %{x}<br>Spend: %{customdata[0]}<extra></extra>")
            fig.update_layout(showlegend=False)
            fig = apply_inr_axis(fig, year_month["amount"].max(), "y")
            st.plotly_chart(polish_chart(fig, 430), width="stretch")

    with col6:
        st.subheader(f"{selected_year} Category x Month")
        top_year_categories = year_spend_df.groupby("category")["amount"].sum().nlargest(12).index.tolist()
        year_heat = year_spend_df[year_spend_df["category"].isin(top_year_categories)]
        year_heat = year_heat.groupby(["category", "Month_Name", "Month"])["amount"].sum().reset_index()
        if year_heat.empty:
            st.info("No category heatmap for the selected year.")
        else:
            year_heat["Month_Name"] = pd.Categorical(year_heat["Month_Name"], categories=MONTH_ORDER, ordered=True)
            pivot = year_heat.pivot(index="category", columns="Month_Name", values="amount").fillna(0)
            pivot = pivot.reindex(columns=MONTH_ORDER, fill_value=0)
            fig = px.imshow(
                pivot,
                aspect="auto",
                color_continuous_scale="YlOrRd",
                labels={"color": "Spend"},
            )
            fig = apply_inr_heatmap(fig, pivot)
            st.plotly_chart(polish_chart(fig, 430), width="stretch")

    st.subheader("Yearly Summary Table")
    annual_summary = filtered_df.pivot_table(
        index="Year",
        columns="txn_type",
        values="amount",
        aggfunc="sum",
        fill_value=0,
    ).reset_index()
    if "DEBIT" not in annual_summary:
        annual_summary["DEBIT"] = 0
    if "CREDIT" not in annual_summary:
        annual_summary["CREDIT"] = 0
    annual_summary["Net Outflow"] = annual_summary["DEBIT"] - annual_summary["CREDIT"]
    annual_summary["Transactions"] = filtered_df.groupby("Year")["id"].count().reindex(annual_summary["Year"]).values
    annual_summary = annual_summary.sort_values("Year", ascending=False)
    annual_summary["DEBIT"] = annual_summary["DEBIT"].apply(format_inr)
    annual_summary["CREDIT"] = annual_summary["CREDIT"].apply(format_inr)
    annual_summary["Net Outflow"] = annual_summary["Net Outflow"].apply(format_inr)
    st.dataframe(annual_summary, hide_index=True, height=260)

with tab_trends:
    col1, col2 = st.columns([2, 1])

    with col1:
        st.subheader("Monthly Spend and Credits")
        monthly = filtered_df.groupby(["Year-Month", "txn_type"])["amount"].sum().reset_index()
        monthly["inr_text"] = monthly["amount"].apply(format_inr)
        fig = px.bar(
            monthly,
            x="Year-Month",
            y="amount",
            color="txn_type",
            barmode="group",
            color_discrete_map={"DEBIT": "#D95F02", "CREDIT": "#1B9E77"},
            custom_data=["inr_text"],
            labels={"amount": "Amount", "Year-Month": "Month"},
        )
        fig.update_traces(hovertemplate="Month: %{x}<br>Amount: %{customdata[0]}<extra></extra>")
        fig = apply_inr_axis(fig, monthly["amount"].max(), "y")
        st.plotly_chart(polish_chart(fig, 440), width="stretch")

    with col2:
        st.subheader("Net Outflow by Month")
        net_monthly = filtered_df.groupby("Year-Month")["Signed_Amount"].sum().reset_index()
        net_monthly["inr_text"] = net_monthly["Signed_Amount"].apply(format_inr)
        fig = px.bar(
            net_monthly,
            x="Year-Month",
            y="Signed_Amount",
            color="Signed_Amount",
            color_continuous_scale=["#1B9E77", "#F7F7F7", "#D95F02"],
            custom_data=["inr_text"],
            labels={"Signed_Amount": "Net Outflow", "Year-Month": "Month"},
        )
        fig.update_traces(hovertemplate="Month: %{x}<br>Net: %{customdata[0]}<extra></extra>")
        fig = apply_inr_axis(fig, net_monthly["Signed_Amount"], "y")
        fig = apply_inr_colorbar(fig, net_monthly["Signed_Amount"])
        st.plotly_chart(polish_chart(fig, 440), width="stretch")

    col3, col4 = st.columns([1, 1])

    with col3:
        st.subheader("Year-over-Year Monthly Spend")
        yearly = spend_df.groupby(["Year", "Month", "Month_Name"])["amount"].sum().reset_index()
        yearly = yearly.sort_values("Month")
        yearly["inr_text"] = yearly["amount"].apply(format_inr)
        fig = px.line(
            yearly,
            x="Month_Name",
            y="amount",
            color="Year",
            markers=True,
            custom_data=["inr_text"],
            labels={"Month_Name": "Month", "amount": "Spend"},
        )
        fig.update_xaxes(categoryorder="array", categoryarray=MONTH_ORDER)
        fig.update_traces(hovertemplate="Month: %{x}<br>Spend: %{customdata[0]}<extra></extra>")
        fig = apply_inr_axis(fig, yearly["amount"].max(), "y")
        st.plotly_chart(polish_chart(fig, 400), width="stretch")

    with col4:
        st.subheader("Cumulative Spend by Year")
        cumulative = spend_df.groupby(["Year", "txn_datetime"])["amount"].sum().reset_index()
        cumulative["Day_Of_Year"] = cumulative["txn_datetime"].dt.dayofyear
        cumulative["Cumulative_Spend"] = cumulative.groupby("Year")["amount"].cumsum()
        cumulative["inr_text"] = cumulative["Cumulative_Spend"].apply(format_inr)
        fig = px.line(
            cumulative,
            x="Day_Of_Year",
            y="Cumulative_Spend",
            color="Year",
            custom_data=["inr_text"],
            labels={"Day_Of_Year": "Day of Year", "Cumulative_Spend": "Cumulative Spend"},
        )
        fig.update_traces(hovertemplate="Day: %{x}<br>Cumulative: %{customdata[0]}<extra></extra>")
        fig = apply_inr_axis(fig, cumulative["Cumulative_Spend"].max(), "y")
        st.plotly_chart(polish_chart(fig, 400), width="stretch")

with tab_mix:
    col1, col2 = st.columns([1, 1])

    with col1:
        st.subheader("Category Mix Over Time")
        top_categories = spend_df.groupby("category")["amount"].sum().nlargest(10).index.tolist()
        category_trend = spend_df[spend_df["category"].isin(top_categories)]
        category_trend = category_trend.groupby(["Year-Month", "category"])["amount"].sum().reset_index()
        category_trend["inr_text"] = category_trend["amount"].apply(format_inr)
        fig = px.area(
            category_trend,
            x="Year-Month",
            y="amount",
            color="category",
            custom_data=["inr_text"],
            labels={"amount": "Spend", "Year-Month": "Month"},
        )
        fig.update_traces(hovertemplate="Month: %{x}<br>Spend: %{customdata[0]}<extra></extra>")
        fig = apply_inr_axis(fig, category_trend["amount"].max(), "y")
        st.plotly_chart(polish_chart(fig, 440), width="stretch")

    with col2:
        st.subheader("Credit Card Trend")
        card_trend = spend_df.groupby(["Year-Month", "card_name"])["amount"].sum().reset_index()
        card_trend["inr_text"] = card_trend["amount"].apply(format_inr)
        fig = px.line(
            card_trend,
            x="Year-Month",
            y="amount",
            color="card_name",
            custom_data=["inr_text"],
            labels={"amount": "Spend", "Year-Month": "Month"},
        )
        fig.update_traces(hovertemplate="Month: %{x}<br>Spend: %{customdata[0]}<extra></extra>")
        fig = apply_inr_axis(fig, card_trend["amount"].max(), "y")
        st.plotly_chart(polish_chart(fig, 440), width="stretch")

    col3, col4 = st.columns([1, 1])

    with col3:
        st.subheader("Category Heatmap by Month")
        heat = spend_df[spend_df["category"].isin(top_categories)]
        heat = heat.groupby(["category", "Year-Month"])["amount"].sum().reset_index()
        if heat.empty:
            st.info("No category heatmap data for the selected filters.")
        else:
            pivot = heat.pivot(index="category", columns="Year-Month", values="amount").fillna(0)
            fig = px.imshow(
                pivot,
                aspect="auto",
                color_continuous_scale="YlOrRd",
                labels={"color": "Spend"},
            )
            fig = apply_inr_heatmap(fig, pivot)
            st.plotly_chart(polish_chart(fig, 430), width="stretch")

    with col4:
        st.subheader("Bank and Card Treemap")
        tree = group_amount(spend_df, ["bank_name", "card_name", "category"])
        if tree.empty:
            st.info("No debit transactions for this treemap.")
        else:
            fig = px.treemap(
                tree,
                path=["bank_name", "card_name", "category"],
                values="amount",
                custom_data=["inr_text"],
            )
            fig.update_traces(hovertemplate="%{label}<br>Spend: %{customdata[0]}<extra></extra>")
            st.plotly_chart(polish_chart(fig, 430), width="stretch")

with tab_merchants:
    col1, col2 = st.columns([1, 1])

    with col1:
        st.subheader("Top Merchants by Spend")
        merchants = group_amount(spend_df, ["description", "category"]).sort_values("amount", ascending=False).head(25)
        fig = px.bar(
            merchants.sort_values("amount", ascending=True),
            x="amount",
            y="description",
            color="category",
            orientation="h",
            custom_data=["inr_text"],
            labels={"amount": "Spend", "description": "Merchant"},
        )
        fig.update_traces(hovertemplate="Merchant: %{y}<br>Spend: %{customdata[0]}<extra></extra>")
        fig = apply_inr_axis(fig, merchants["amount"].max(), "x")
        st.plotly_chart(polish_chart(fig, 700), width="stretch")

    with col2:
        st.subheader("Frequent Merchants")
        frequency = spend_df.groupby(["description", "category"]).agg(
            Transactions=("id", "count"),
            Spend=("amount", "sum"),
            Avg_Ticket=("amount", "mean"),
        ).reset_index()
        frequency = frequency[frequency["Transactions"] >= 2].sort_values(["Transactions", "Spend"], ascending=False).head(30)
        frequency["Spend_Text"] = frequency["Spend"].apply(format_inr)
        fig = px.scatter(
            frequency,
            x="Transactions",
            y="Spend",
            size="Avg_Ticket",
            color="category",
            hover_name="description",
            custom_data=["Spend_Text"],
            labels={"Spend": "Total Spend"},
        )
        fig.update_traces(hovertemplate="%{hovertext}<br>Transactions: %{x}<br>Spend: %{customdata[0]}<extra></extra>")
        fig = apply_inr_axis(fig, frequency["Spend"].max(), "y")
        st.plotly_chart(polish_chart(fig, 700), width="stretch")

    col3, col4 = st.columns([1, 1])

    with col3:
        st.subheader("Weekday Spend Pattern")
        weekday = group_amount(spend_df, ["Weekday", "Weekday_Num"]).sort_values("Weekday_Num")
        fig = px.bar(
            weekday,
            x="Weekday",
            y="amount",
            color="Weekday",
            custom_data=["inr_text"],
            labels={"amount": "Spend"},
        )
        fig.update_traces(hovertemplate="Weekday: %{x}<br>Spend: %{customdata[0]}<extra></extra>")
        fig.update_layout(showlegend=False)
        fig = apply_inr_axis(fig, weekday["amount"].max(), "y")
        st.plotly_chart(polish_chart(fig, 380), width="stretch")

    with col4:
        st.subheader("Transaction Size Distribution")
        if spend_df.empty:
            st.info("No debit transactions for the histogram.")
        else:
            fig = px.histogram(
                spend_df,
                x="amount",
                nbins=40,
                color="category",
                labels={"amount": "Transaction Amount"},
            )
            fig = apply_inr_axis(fig, spend_df["amount"].max(), "x")
            st.plotly_chart(polish_chart(fig, 380), width="stretch")

with tab_transactions:
    col1, col2 = st.columns([1, 1])

    with col1:
        st.subheader("Largest Transactions")
        largest = filtered_df.sort_values("amount", ascending=False).head(50).copy()
        largest["amount"] = largest["amount"].apply(format_inr)
        largest["txn_datetime"] = largest["txn_datetime"].dt.strftime("%Y-%m-%d")
        st.dataframe(
            largest[["txn_datetime", "txn_type", "card_name", "category", "description", "amount"]],
            hide_index=True,
            height=520,
        )

    with col2:
        st.subheader(f"Transactions in {selected_month}")
        month_table = month_df.sort_values("txn_datetime", ascending=False).copy()
        month_table["amount"] = month_table["amount"].apply(format_inr)
        month_table["txn_datetime"] = month_table["txn_datetime"].dt.strftime("%Y-%m-%d")
        st.dataframe(
            month_table[["txn_datetime", "txn_type", "card_name", "category", "description", "amount"]],
            hide_index=True,
            height=520,
        )
