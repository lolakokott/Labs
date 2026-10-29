"""Run with: python -m streamlit run asof_app.py."""

from datetime import date
from io import StringIO
import re

import pandas as pd
import requests
import streamlit as st


SERIES = {
    "BAA": "Moody's Baa corporate bond yield",
    "FEDFUNDS": "Federal funds rate",
    "DGS10": "10-year Treasury yield",
    "MORTGAGE30US": "30-year mortgage rate",
}


def parse_csv(text: str) -> pd.Series:
    """Both downloads have a date column followed by one series column."""
    frame = pd.read_csv(StringIO(text), na_values=["."])
    if len(frame.columns) != 2:
        raise ValueError("The download did not contain a single FRED series.")
    dates = pd.to_datetime(frame.iloc[:, 0], errors="raise")
    values = pd.to_numeric(frame.iloc[:, 1], errors="raise")
    result = pd.Series(values.to_numpy(), index=pd.DatetimeIndex(dates), name="Value")
    return result.dropna().sort_index().loc[lambda s: ~s.index.duplicated(keep="last")]


@st.cache_data(ttl=3600, show_spinner=False)
def download_today(series_id: str, downloaded_on: date) -> pd.Series:
    """One public CSV request; the date key prevents reuse across days."""
    response = requests.get(
        "https://fred.stlouisfed.org/graph/fredgraph.csv",
        params={"id": series_id}, timeout=30,
    )
    response.raise_for_status()
    return parse_csv(response.text)


@st.cache_data(ttl=3600, show_spinner=False)
def download_asof(series_id: str, vintage_date: date, downloaded_on: date) -> pd.Series:
    """One ALFRED request for the complete historical vintage."""
    response = requests.get(
        "https://alfred.stlouisfed.org/graph/alfredgraph.csv",
        params={"id": series_id, "vintage_date": vintage_date.isoformat()}, timeout=30,
    )
    response.raise_for_status()
    return parse_csv(response.text)


def last_observation(series: pd.Series) -> tuple:
    if series.empty:
        return None, None
    return series.index[-1].date(), float(series.iloc[-1])


def comparison(series_id: str, current: pd.Series, vintage: pd.Series) -> dict:
    then_date, then_value = last_observation(vintage)
    now_date, now_value = last_observation(current)
    shared = pd.concat([current.rename("today"), vintage.rename("then")], axis=1).dropna()
    return {
        "Series": f"https://fred.stlouisfed.org/series/{series_id}",
        "Last measured date, as known then": then_date,
        "Value as known then": then_value,
        "Last measured date, today": now_date,
        "Value today": now_value,
        "New values since then": int((current.index > pd.Timestamp(then_date)).sum()) if then_date else None,
        "Revised values on shared dates": int(shared["today"].ne(shared["then"]).sum()),
    }


def main() -> None:
    st.set_page_config(page_title="Interest rates — as known then", layout="wide")
    today = date.today()
    st.title("Interest rates — as known then")
    st.caption(
        f"Data from FRED and ALFRED, Federal Reserve Bank of St. Louis, downloaded today "
        f"({today.isoformat()}); built with AI help, a learning demonstration, not investment advice."
    )
    selected = st.sidebar.multiselect(
        "Interest rate series", list(SERIES), default=list(SERIES),
        format_func=lambda key: f"{key} — {SERIES[key]}",
    )
    extra = st.sidebar.text_input("Add another FRED series ID", placeholder="e.g. DGS2").strip().upper()
    start = st.sidebar.date_input("Start date", date(2020, 1, 1), min_value=date(1776, 1, 1), max_value=today)
    asof = st.sidebar.date_input("As known on", today, min_value=date(1776, 1, 1), max_value=today)
    if extra:
        if re.fullmatch(r"[A-Z0-9_]+", extra):
            if extra not in selected:
                selected.append(extra)
        else:
            st.sidebar.error("Enter a single FRED series ID using letters, numbers, or underscores.")
    if not selected:
        st.info("Select a series or enter a FRED series ID to begin.")
        return

    rows = []
    for series_id in selected:
        st.subheader(f"{series_id} — {SERIES[series_id]}" if series_id in SERIES else series_id)
        current = vintage = None
        with st.spinner(f"Loading {series_id}…"):
            try:
                current = download_today(series_id, today)
            except Exception as exc:
                st.error(f"{series_id}: could not download today's data. Check the ID or try again. ({exc})")
            try:
                vintage = download_asof(series_id, asof, today)
            except Exception as exc:
                st.error(f"{series_id}: could not download data as known on {asof}. ({exc})")
        if current is not None:
            chart = current.loc[pd.Timestamp(start):]
            if chart.empty:
                st.info("No measured values on or after the start date.")
            else:
                st.line_chart(chart, x_label="Observation date", y_label="Value (series units)")
        if vintage is not None:
            last_date, _ = last_observation(vintage)
            st.caption(f"Last measured date known on {asof}: {last_date if last_date else 'No measured values available'}. ")
        if current is not None and vintage is not None:
            rows.append(comparison(series_id, current, vintage))

    st.subheader("Then and today")
    st.caption("Comparisons use the complete downloads; the start date only filters charts. Missing days (.) are excluded. Revisions compare nonmissing values on shared dates.")
    if rows:
        st.dataframe(
            pd.DataFrame(rows), hide_index=True, width="stretch",
            column_config={"Series": st.column_config.LinkColumn("Series", display_text=r"https://fred\.stlouisfed\.org/series/(.*)")},
        )
    else:
        st.info("No series have both downloads available for comparison.")


if __name__ == "__main__":
    main()
