# 13-Asset Universe Benchmark Results

| Asset    | Model                  |   Return (%) |   Sharpe |   Sortino |   Max DD (%) |   Trades |   Win Rate (%) |   Profit Factor |
|:---------|:-----------------------|-------------:|---------:|----------:|-------------:|---------:|---------------:|----------------:|
| BTCUSDT  | Buy & Hold             |         0.13 |     0.22 |      0.3  |         6.45 |        1 |          100   |           99    |
| BTCUSDT  | Moving Average (20/50) |        -3.27 |    -2.55 |     -2.32 |         7.57 |        6 |           50   |            0.53 |
| BTCUSDT  | Random Forest          |        -0.51 |    -4.16 |     -0.71 |         0.75 |        2 |           50   |            0.53 |
| BTCUSDT  | LightGBM               |        -2.12 |    -6.29 |     -1.6  |         2.67 |        9 |           55.6 |            0.57 |
| ETHUSDT  | Buy & Hold             |         1.92 |     0.97 |      1.33 |         6.69 |        1 |          100   |           99    |
| ETHUSDT  | Moving Average (20/50) |         1.23 |     0.81 |      0.8  |         8.86 |        8 |           37.5 |            1.62 |
| ETHUSDT  | Random Forest          |         0    |     0    |      0    |         0    |        0 |            0   |            0    |
| ETHUSDT  | LightGBM               |        -1.86 |    -2.43 |     -0.77 |         4    |       22 |           72.7 |            1.17 |
| SOLUSDT  | Buy & Hold             |        -4.64 |    -1.88 |     -2.56 |         9.64 |        1 |            0   |            0    |
| SOLUSDT  | Moving Average (20/50) |        -1.1  |    -0.54 |     -0.55 |         7.49 |        5 |           60   |            0.88 |
| SOLUSDT  | Random Forest          |         0.05 |     0.55 |      0.22 |         0.31 |        3 |           66.7 |            7.1  |
| SOLUSDT  | LightGBM               |        -1.22 |    -1.49 |     -0.84 |         3.89 |       32 |           62.5 |            1.64 |
| BNBUSDT  | Buy & Hold             |         2.08 |     1.41 |      2.02 |         4.23 |        1 |          100   |           99    |
| BNBUSDT  | Moving Average (20/50) |         2.2  |     1.95 |      2.01 |         2.98 |        5 |           40   |            2.97 |
| BNBUSDT  | Random Forest          |         0    |     0    |      0    |         0    |        0 |            0   |            0    |
| BNBUSDT  | LightGBM               |        -3.17 |    -8.01 |     -2.04 |         3.29 |        9 |           22.2 |            0.2  |
| XRPUSDT  | Buy & Hold             |        -4.49 |    -2.01 |     -2.87 |         9.89 |        1 |            0   |            0    |
| XRPUSDT  | Moving Average (20/50) |        -3.66 |    -2.42 |     -2.41 |         7.88 |        8 |           12.5 |            0.6  |
| XRPUSDT  | Random Forest          |        -1.61 |    -6.6  |     -1.01 |         1.61 |        4 |           50   |            0.13 |
| XRPUSDT  | LightGBM               |        -0.8  |    -2.31 |     -1.23 |         2.22 |       20 |           55   |            1.95 |
| DOGEUSDT | Buy & Hold             |        13.56 |     3.88 |      5.42 |         9.33 |        1 |          100   |           99    |
| DOGEUSDT | Moving Average (20/50) |         7.15 |     2.54 |      3.07 |         8.41 |        7 |           57.1 |            3.07 |
| DOGEUSDT | Random Forest          |         3.55 |     3.69 |      2.87 |         0.65 |        2 |           50   |            8.98 |
| DOGEUSDT | LightGBM               |         7.46 |     5.35 |      6.89 |         2.25 |       23 |           52.2 |            6.26 |
| ADAUSDT  | Buy & Hold             |       -21.48 |    -4.55 |     -6.2  |        26.17 |        1 |            0   |            0    |
| ADAUSDT  | Moving Average (20/50) |        -0.49 |    -0.06 |     -0.06 |         9.26 |        4 |           50   |            1.03 |
| ADAUSDT  | Random Forest          |         1.6  |     0.84 |      0.45 |        10.07 |       18 |           72.2 |            1.47 |
| ADAUSDT  | LightGBM               |         0.39 |     0.36 |      0.23 |        12.97 |       48 |           68.8 |            1.3  |
| AVAXUSDT | Buy & Hold             |         0.38 |     0.39 |      0.52 |        11.5  |        1 |          100   |           99    |
| AVAXUSDT | Moving Average (20/50) |        -3.34 |    -1.3  |     -1.11 |         7.69 |        7 |           42.9 |            0.76 |
| AVAXUSDT | Random Forest          |         4.18 |     3.47 |      1.32 |         2.96 |       21 |           71.4 |            3.18 |
| AVAXUSDT | LightGBM               |        12.55 |     7.57 |      6.45 |         2.92 |       54 |           75.9 |            3.21 |
| LINKUSDT | Buy & Hold             |       -30.05 |    -5.36 |     -6.98 |        32.94 |        1 |            0   |            0    |
| LINKUSDT | Moving Average (20/50) |       -29.53 |   -10.82 |     -7.56 |        30.84 |        8 |            0   |            0    |
| LINKUSDT | Random Forest          |        -9.69 |    -3.47 |     -2.03 |        11.18 |       39 |           53.8 |            0.79 |
| LINKUSDT | LightGBM               |        -8.82 |    -2.53 |     -2.17 |        18.1  |       76 |           50   |            1.02 |
| NEARUSDT | Buy & Hold             |        40.64 |     5.28 |      8.89 |        14.53 |        1 |          100   |           99    |
| NEARUSDT | Moving Average (20/50) |        -0.24 |     0.44 |      0.54 |        18.18 |        8 |           37.5 |            1.14 |
| NEARUSDT | Random Forest          |         2.65 |     1.24 |      0.81 |         9.46 |       25 |           52   |            1.43 |
| NEARUSDT | LightGBM               |        33.67 |     8.17 |      9.25 |        12.22 |       57 |           70.2 |            2.61 |
| LTCUSDT  | Buy & Hold             |        -7.81 |    -1.22 |     -1.54 |        21.28 |        1 |            0   |            0    |
| LTCUSDT  | Moving Average (20/50) |        -2.33 |    -0.5  |     -0.53 |        13.88 |        6 |           33.3 |            0.73 |
| LTCUSDT  | Random Forest          |       -10.92 |    -4.04 |     -1.94 |        10.92 |       30 |           53.3 |            0.6  |
| LTCUSDT  | LightGBM               |        -3.96 |    -1.02 |     -0.78 |         9.2  |       60 |           56.7 |            1.14 |
| DOTUSDT  | Buy & Hold             |        15.57 |     2.9  |      4.62 |        24.62 |        1 |          100   |           99    |
| DOTUSDT  | Moving Average (20/50) |        -2.49 |    -0.13 |     -0.14 |        19.75 |        8 |           12.5 |            1.03 |
| DOTUSDT  | Random Forest          |        -2.34 |    -1.53 |     -1.19 |         5.5  |       21 |           42.9 |            1.04 |
| DOTUSDT  | LightGBM               |        -1.89 |    -0.72 |     -0.58 |         7.27 |       31 |           51.6 |            1.19 |
| SUIUSDT  | Buy & Hold             |        -8.82 |    -1.56 |     -2.21 |        19.24 |        1 |            0   |            0    |
| SUIUSDT  | Moving Average (20/50) |       -16.99 |    -5.46 |     -4.7  |        17.45 |        7 |           42.9 |            0.08 |
| SUIUSDT  | Random Forest          |         5.34 |     7.39 |      2.88 |         1.14 |       10 |           90   |           42.46 |
| SUIUSDT  | LightGBM               |         9.46 |     5.11 |      3.55 |         4.06 |       36 |           77.8 |            2.81 |

## Aggregated Portfolio Metrics

| Model                  |   Return (%) |   Sharpe |   Max DD (%) |   Trades |   Win Rate (%) |   Profit Factor |
|:-----------------------|-------------:|---------:|-------------:|---------:|---------------:|----------------:|
| LightGBM               |         3.05 |     0.14 |         6.54 |      477 |          59.32 |            1.93 |
| Buy & Hold             |        -0.23 |    -0.12 |        15.12 |       13 |          53.85 |           53.31 |
| Random Forest          |        -0.59 |    -0.2  |         4.2  |      175 |          50.18 |            5.21 |
| Moving Average (20/50) |        -4.07 |    -1.39 |        12.33 |       87 |          36.63 |            1.11 |