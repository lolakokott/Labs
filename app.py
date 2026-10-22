
import streamlit as st
import pandas as pd

from portfolio import (
    assets,
    correlations,
    objective_return,
    reserve_eligible,
    find_lowest_risk_mix,
    estimate_from_csv
)

st.set_page_config(page_title="Portfolio Stability Decision")

st.title("Portfolio Stability Decision")
st.caption(
    "Built with AI help, a learning demonstration, "
    "not investment advice."
)

# Sidebar controls
st.sidebar.header("Portfolio Settings")

objective = st.sidebar.number_input(
    "Expected return objective (%)",
    value=6.5,
    step=0.1
) / 100

reserve_minimum = st.sidebar.number_input(
    "Minimum reserve weight (%)",
    value=3.0,
    min_value=0.0,
    max_value=100.0,
    step=1.0
) / 100

uploaded_file = st.sidebar.file_uploader(
    "Upload prices.csv",
    type="csv"
)

last_36 = st.sidebar.checkbox("Use last 36 months")

# Select inputs
if uploaded_file is not None:
    try:
        full_assets, full_corr = estimate_from_csv(
            uploaded_file, last_36=False
        )
        uploaded_file.seek(0)
        if last_36:
            current_assets, current_corr = estimate_from_csv(
                uploaded_file, last_36=True
            )
        else:
            current_assets, current_corr = full_assets, full_corr
    except Exception as error:
        st.error(f"Unable to read CSV: {error}")
        st.stop()

    st.subheader("Your Project 2 Universe")
    st.caption("Historical returns are estimates, not forecasts.")
    default_eligible = {"BIL", "IEF"}
else:
    current_assets = {
        name: values.copy() for name, values in assets.items()
    }
    current_corr = correlations
    full_assets = {
        name: values.copy() for name, values in assets.items()
    }
    full_corr = correlations

    st.subheader("Meridian Training Universe")
    default_eligible = set(reserve_eligible)

# Asset input controls
st.write("### Expected Return Estimates")

edited_assets = {
    name: values.copy()
    for name, values in current_assets.items()
}

eligible = []

for name in current_assets:
    col1, col2 = st.columns([2, 1])

    with col1:
        edited_return = st.number_input(
            f"{name} expected return (%)",
            value=round(current_assets[name]["return"] * 100, 3),
            step=0.1,
            key=f"return_{name}_{last_36}_{uploaded_file is not None}"
        )
        edited_assets[name]["return"] = edited_return / 100

    with col2:
        checked = st.checkbox(
            f"{name} reserve-eligible",
            value=name in default_eligible,
            key=f"reserve_{name}_{uploaded_file is not None}"
        )
        if checked:
            eligible.append(name)

# Calculate original and edited solutions
baseline = find_lowest_risk_mix(
    full_assets,
    full_corr,
    objective,
    reserve_minimum,
    eligible
)

current = find_lowest_risk_mix(
    edited_assets,
    current_corr,
    objective,
    reserve_minimum,
    eligible
)

def display_solution(solution, asset_names):
    if solution is None:
        st.warning("No mix meets the objective")
        return

    weights = pd.DataFrame({
        "Asset": asset_names,
        "Weight (%)": [
            round(w * 100, 2) for w in solution["weights"]
        ]
    })

    st.dataframe(weights, hide_index=True)

    st.metric(
        "Expected return",
        f'{solution["return"] * 100:.2f}%'
    )
    st.metric(
        "Volatility",
        f'{solution["volatility"] * 100:.2f}%'
    )
    st.metric(
        "Reserve-eligible weight",
        f'{solution["reserve"] * 100:.2f}%'
    )

st.divider()

left, right = st.columns(2)

with left:
    st.subheader("As Loaded")
    display_solution(baseline, list(full_assets))

with right:
    st.subheader("Current Scenario")
    display_solution(current, list(edited_assets))

if baseline is not None and current is not None:
    changes = [
        abs(a - b) * 100
        for a, b in zip(
            baseline["weights"], current["weights"]
        )
    ]

    st.metric(
        "Largest weight change",
        f"{max(changes):.0f} percentage points"
    )
else:
    st.info(
        "Weight changes cannot be calculated "
        "when a scenario has no feasible mix."
    )
