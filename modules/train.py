from __future__ import annotations

import csv
import pickle
import random
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_PATH = ROOT_DIR / "model" / "data.csv"
MODEL_PATH = ROOT_DIR / "model" / "temp_model.pkl"


def _solve_3x3(a: list[list[float]], b: list[float]) -> list[float]:
    """Gaussian elimination for a 3x3 linear system."""
    m = [row[:] + [rhs] for row, rhs in zip(a, b)]
    size = 3

    for pivot in range(size):
        max_row = max(range(pivot, size), key=lambda r: abs(m[r][pivot]))
        m[pivot], m[max_row] = m[max_row], m[pivot]

        pivot_val = m[pivot][pivot]
        if abs(pivot_val) < 1e-12:
            raise ValueError("Singular matrix while solving linear regression.")

        for col in range(pivot, size + 1):
            m[pivot][col] /= pivot_val

        for row in range(size):
            if row == pivot:
                continue
            factor = m[row][pivot]
            for col in range(pivot, size + 1):
                m[row][col] -= factor * m[pivot][col]

    return [m[i][size] for i in range(size)]


def generate_fake_dataset(rows: int = 250) -> list[dict[str, float]]:
    """
    Build synthetic chicken yield training data.
    yield_kg is daily yield estimate driven by temperature and humidity.
    """
    random.seed(42)
    dataset: list[dict[str, float]] = []
    for _ in range(rows):
        temperature = round(random.uniform(20.0, 40.0), 2)
        humidity = round(random.uniform(35.0, 90.0), 2)

        base_yield = 92.0 - 1.8 * abs(temperature - 28.0) - 0.9 * abs(humidity - 60.0)
        noisy_yield = base_yield + random.uniform(-2.0, 2.0)
        yield_kg = round(min(95.0, max(35.0, noisy_yield)), 2)

        dataset.append(
            {
                "temperature_c": temperature,
                "humidity_pct": humidity,
                "yield_kg": yield_kg,
            }
        )

    return dataset


def _fit_linear_regression(dataset: list[dict[str, float]]) -> dict[str, float]:
    # Normal equation for y = b0 + b1*T + b2*H
    n = float(len(dataset))
    sum_t = sum(row["temperature_c"] for row in dataset)
    sum_h = sum(row["humidity_pct"] for row in dataset)
    sum_y = sum(row["yield_kg"] for row in dataset)
    sum_tt = sum(row["temperature_c"] ** 2 for row in dataset)
    sum_hh = sum(row["humidity_pct"] ** 2 for row in dataset)
    sum_th = sum(row["temperature_c"] * row["humidity_pct"] for row in dataset)
    sum_ty = sum(row["temperature_c"] * row["yield_kg"] for row in dataset)
    sum_hy = sum(row["humidity_pct"] * row["yield_kg"] for row in dataset)

    a = [
        [n, sum_t, sum_h],
        [sum_t, sum_tt, sum_th],
        [sum_h, sum_th, sum_hh],
    ]
    b = [sum_y, sum_ty, sum_hy]
    intercept, coef_temp, coef_humidity = _solve_3x3(a, b)
    return {
        "intercept": intercept,
        "coef_temperature_c": coef_temp,
        "coef_humidity_pct": coef_humidity,
    }


def train_and_save_model() -> None:
    DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    dataset = generate_fake_dataset()
    with DATA_PATH.open("w", newline="", encoding="utf-8") as fp:
        writer = csv.DictWriter(fp, fieldnames=["temperature_c", "humidity_pct", "yield_kg"])
        writer.writeheader()
        writer.writerows(dataset)

    model = _fit_linear_regression(dataset)
    with MODEL_PATH.open("wb") as fp:
        pickle.dump(model, fp)

    print(f"Dataset created: {DATA_PATH}")
    print(f"Model saved: {MODEL_PATH}")
    print("Model weights:")
    print(f"  intercept: {model['intercept']:.4f}")
    print(f"  temperature_c coef: {model['coef_temperature_c']:.4f}")
    print(f"  humidity_pct coef: {model['coef_humidity_pct']:.4f}")


if __name__ == "__main__":
    train_and_save_model()