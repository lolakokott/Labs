
# LAB 14 — PORTFOLIO BASELINES
# FIN 43900

import math

# 1. Editable inputs
# Returns and volatility are written as decimals.

assets = {
    "Treasury bills": {
        "return": 0.035, "vol": 0.005
    },
    "Treasury 10-year note": {
        "return": 0.043, "vol": 0.070
    },
    "Investment-grade bond fund": {
        "return": 0.050, "vol": 0.060
    },
    "Global equity index fund": {
        "return": 0.080, "vol": 0.160
    }
}

correlations = [
    [1.00, 0.10, 0.05, 0.00],
    [0.10, 1.00, 0.80, -0.10],
    [0.05, 0.80, 1.00, 0.25],
    [0.00, -0.10, 0.25, 1.00]
]

objective_return = 0.065
reserve_eligible = ["Treasury bills", "Treasury 10-year note"]
names = list(assets)


# 2. Validate correlations
def validate_correlations(matrix):
    n = len(assets)

    if len(matrix) != n or any(len(row) != n for row in matrix):
        raise ValueError("Correlation table has the wrong dimensions.")

    for i in range(n):
        for j in range(n):
            value = matrix[i][j]

            if not -1 <= value <= 1:
                raise ValueError(
                    f"Invalid correlation: {value}. "
                    "Correlations must be between -1 and 1."
                )

            if not math.isclose(value, matrix[j][i],
                                abs_tol=1e-10):
                raise ValueError(
                    "Correlation table is not symmetric."
                )

        if not math.isclose(matrix[i][i], 1.0):
            raise ValueError(
                "An asset's correlation with itself must equal 1."
            )


# 3. Build covariance matrix
def build_covariance(matrix):
    return [
        [
            matrix[i][j]
            * assets[names[i]]["vol"]
            * assets[names[j]]["vol"]
            for j in range(len(names))
        ]
        for i in range(len(names))
    ]


# 4. Define portfolio weights
def benchmark_weights():
    return [0.0, 0.0, 0.4, 0.6]


def equal_weights():
    return [1 / len(names)] * len(names)


def inverse_volatility_weights():
    inverse = [1 / assets[name]["vol"] for name in names]
    total = sum(inverse)
    return [value / total for value in inverse]


# 5. Calculate expected portfolio return
def portfolio_return(weights):
    return sum(
        weights[i] * assets[names[i]]["return"]
        for i in range(len(names))
    )


# 6. Calculate portfolio volatility
def portfolio_volatility(weights, covariance):
    variance = sum(
        weights[i] * weights[j] * covariance[i][j]
        for i in range(len(names))
        for j in range(len(names))
    )
    return math.sqrt(variance)


# 7. Calculate reserve-eligible weight
def portfolio_reserve(weights):
    return sum(
        weights[i]
        for i, name in enumerate(names)
        if name in reserve_eligible
    )


# 8. Print portfolio results
def print_portfolio(label, weights, covariance):
    expected = portfolio_return(weights)
    volatility = portfolio_volatility(weights, covariance)
    reserve = portfolio_reserve(weights)
    meets_objective = expected >= objective_return

    print(f"\n{label}")
    print("Weights (bills / 10-year / IG / equity):")
    print(" / ".join(f"{w * 100:.1f}%" for w in weights))
    print(f"Expected return: {expected * 100:.2f}%")
    print(f"Volatility: {volatility * 100:.2f}%")
    print(f"Reserve-eligible: {reserve * 100:.1f}%")
    print(
        f"Meets {objective_return * 100:.1f}% objective: "
        f"{'YES' if meets_objective else 'NO'}"
    )


# 9. Run all three portfolios
def main():
    validate_correlations(correlations)
    covariance = build_covariance(correlations)

    portfolios = {
        "Benchmark": benchmark_weights(),
        "Equal weight": equal_weights(),
        "Inverse volatility": inverse_volatility_weights()
    }

    for label, weights in portfolios.items():
        print_portfolio(label, weights, covariance)


if __name__ == "__main__":
    main()
