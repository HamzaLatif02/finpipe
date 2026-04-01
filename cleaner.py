import logging
from pathlib import Path

import pandas as pd

import fetcher
from config import CLEAN_DIR as _CLEAN_DIR

logging.basicConfig(level=logging.INFO, format="%(levelname)s — %(message)s")
logger = logging.getLogger(__name__)

CLEAN_DIR = Path(_CLEAN_DIR)


def clean_data(config: dict) -> pd.DataFrame:
    """Load raw prices, apply cleaning and derived columns, save to data/clean/.

    Returns the cleaned DataFrame.
    """
    symbol = config["symbol"]
    df = fetcher.load_raw(symbol)["prices"].copy()

    # --- Date column: parse, strip timezone, sort ascending ---
    df["Date"] = pd.to_datetime(df["Date"], utc=True).dt.tz_convert(None)
    df.sort_values("Date", inplace=True)

    # --- Remove bad rows ---
    df = df[df["Close"].notna() & (df["Close"] != 0)]

    # --- Remove duplicate dates (keep last) ---
    df = df.drop_duplicates(subset="Date", keep="last")

    df.reset_index(drop=True, inplace=True)

    # --- Derived columns ---
    df["daily_return"] = df["Close"].pct_change() * 100

    first_close = df["Close"].iloc[0]
    df["cumulative_return"] = (df["Close"] / first_close - 1) * 100

    df["typical_price"] = (df["High"] + df["Low"] + df["Close"]) / 3
    df["price_range"] = df["High"] - df["Low"]

    volume_total = df["Volume"].sum() if "Volume" in df.columns else 0
    if volume_total > 0:
        cum_tp_vol = (df["typical_price"] * df["Volume"]).cumsum()
        cum_vol = df["Volume"].cumsum()
        df["vwap"] = cum_tp_vol / cum_vol
    else:
        logger.info("Volume is zero for %s — skipping VWAP.", symbol)

    # --- Round all float columns ---
    float_cols = df.select_dtypes(include="float").columns
    df[float_cols] = df[float_cols].round(6)

    # --- Save ---
    CLEAN_DIR.mkdir(parents=True, exist_ok=True)
    out_path = CLEAN_DIR / f"{symbol}_clean.csv"
    df.to_csv(out_path, index=False)
    logger.info(
        "Cleaned %s: %d rows from %s to %s → %s",
        symbol, len(df),
        df["Date"].iloc[0].date(), df["Date"].iloc[-1].date(),
        out_path,
    )

    return df


def load_clean(symbol: str) -> pd.DataFrame:
    """Load the cleaned CSV for a symbol and return it with Date as the index."""
    path = CLEAN_DIR / f"{symbol}_clean.csv"
    if not path.exists():
        raise FileNotFoundError(f"No cleaned data for '{symbol}': {path}")
    df = pd.read_csv(path, parse_dates=["Date"])
    df.set_index("Date", inplace=True)
    return df


if __name__ == "__main__":
    import explorer
    config = explorer.interactive_select()
    fetcher.fetch_data(config)
    df = clean_data(config)

    print(f"\nSymbol:     {config['symbol']}")
    print(f"Rows:       {len(df)}")
    print(f"Date range: {df['Date'].iloc[0].date()} → {df['Date'].iloc[-1].date()}")

    derived = ["Date", "Close", "daily_return", "cumulative_return", "typical_price", "price_range", "vwap"]
    cols = [c for c in derived if c in df.columns]
    print(f"\nFirst 5 rows:\n{df[cols].head().to_string(index=False)}")
