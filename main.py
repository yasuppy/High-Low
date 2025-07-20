import pandas as pd
import yfinance as yf
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import os
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from webdriver_manager.core.driver_cache import DriverCacheManager

def generate_shin_ne_ashi_data(daily_df, length=5):
    """
    日足データから新値足のOHLCデータ、トレンド転換点、経過本数を生成します。
    戻り値: (新値足データフレーム, 転換点データフレーム)
    """
    new_price_bars = []
    reversal_points = []
    last_trend = None
    since_turn_counter = 0

    if len(daily_df) < 1:
        return pd.DataFrame(), pd.DataFrame()

    # 最初の足
    first_bar_data = daily_df.iloc[0]
    new_price_bars.append({
        'Date': daily_df.index[0],
        'Open': first_bar_data['Open'], 'High': first_bar_data['High'],
        'Low': first_bar_data['Low'], 'Close': first_bar_data['Close'],
        'since_turn': 1 # 最初の足は1本目
    })
    last_trend = 'up' # 仮の初期トレンド
    since_turn_counter = 1

    for i in range(1, len(daily_df)):
        current_daily_bar = daily_df.iloc[i]
        current_date = daily_df.index[i]

        lookback_period = min(length, len(new_price_bars))
        recent_new_price_bars = new_price_bars[-lookback_period:]

        reference_high = max(bar['High'] for bar in recent_new_price_bars)
        reference_low = min(bar['Low'] for bar in recent_new_price_bars)
        last_new_price_close = new_price_bars[-1]['Close']

        is_new_high = current_daily_bar['High'] > reference_high
        is_new_low = current_daily_bar['Low'] < reference_low

        new_bar = None
        current_trend = last_trend

        if is_new_high:
            current_trend = 'up'
            if current_trend != last_trend:
                since_turn_counter = 1
                reversal_points.append({
                    'Date': current_date, 'High': current_daily_bar['High'],
                    'Trend': 'up'
                })
            else:
                since_turn_counter += 1

            new_bar = {
                'Date': current_date, 'Open': last_new_price_close,
                'High': current_daily_bar['High'], 'Low': last_new_price_close,
                'Close': current_daily_bar['High'], 'since_turn': since_turn_counter
            }
            last_trend = 'up'

        elif is_new_low:
            current_trend = 'down'
            if current_trend != last_trend:
                since_turn_counter = 1
                reversal_points.append({
                    'Date': current_date, 'Low': current_daily_bar['Low'],
                    'Trend': 'down'
                })
            else:
                since_turn_counter += 1

            new_bar = {
                'Date': current_date, 'Open': last_new_price_close,
                'High': last_new_price_close, 'Low': current_daily_bar['Low'],
                'Close': current_daily_bar['Low'], 'since_turn': since_turn_counter
            }
            last_trend = 'down'

        if new_bar:
            new_price_bars.append(new_bar)

    df_new_price = pd.DataFrame(new_price_bars).set_index('Date') if new_price_bars else pd.DataFrame()
    df_reversals = pd.DataFrame(reversal_points).set_index('Date') if reversal_points else pd.DataFrame()
    return df_new_price, df_reversals

def main():
    currency_pairs = ['USDJPY=X', 'EURJPY=X', 'AUDJPY=X', 'AUDUSD=X', 'EURUSD=X']
    figs = []

    # 今日の日付でフォルダを作成
    today_str = datetime.now().strftime('%Y%m%d')
    output_dir = os.path.join(os.getcwd(), today_str)
    os.makedirs(output_dir, exist_ok=True)
    output_file_path = os.path.join(output_dir, 'forex_analysis.html')

    for pair in currency_pairs:
        data = yf.download(pair, period="1y", interval="1d")
        new_columns = []
        for col in data.columns:
            if isinstance(col, tuple):
                new_columns.append(col[0].capitalize())
            else:
                new_columns.append(col.capitalize())
        data.columns = new_columns

        df_new_price, df_reversals = generate_shin_ne_ashi_data(data)

        fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.05,
                          subplot_titles=(f'{pair} - Daily Candlestick w/ Reversals', f'{pair} - New Price Chart (5 bars) w/ Count'),
                          row_heights=[0.6, 0.4])

        # 1. 日足チャート
        fig.add_trace(go.Candlestick(x=data.index, open=data['Open'], high=data['High'],
                                     low=data['Low'], close=data['Close'], name='Daily'),
                      row=1, col=1)

        # 転換点マーカーを追加
        if not df_reversals.empty:
            up_reversals = df_reversals[df_reversals['Trend'] == 'up']
            down_reversals = df_reversals[df_reversals['Trend'] == 'down']
            if not up_reversals.empty:
                fig.add_trace(go.Scatter(x=up_reversals.index, y=up_reversals['High'] * 1.01, mode='markers',
                                         marker=dict(symbol='triangle-up', color='blue', size=10),
                                         name='Upward Reversal'), row=1, col=1)
            if not down_reversals.empty:
                fig.add_trace(go.Scatter(x=down_reversals.index, y=down_reversals['Low'] * 0.99, mode='markers',
                                         marker=dict(symbol='triangle-down', color='purple', size=10),
                                         name='Downward Reversal'), row=1, col=1)

        # 2. 新値足チャート
        if not df_new_price.empty:
            fig.add_trace(go.Candlestick(x=df_new_price.index, open=df_new_price['Open'], high=df_new_price['High'],
                                         low=df_new_price['Low'], close=df_new_price['Close'], name='New Price'),
                          row=2, col=1)
            # 経過本数をテキストで表示
            fig.add_trace(go.Scatter(x=df_new_price.index, y=df_new_price['High'] * 1.005, mode='text',
                                     text=df_new_price['since_turn'], textposition='top center',
                                     textfont=dict(size=10, color='rgba(128, 128, 128, 0.8)'),
                                     showlegend=False), row=2, col=1)

        # X軸の目盛りを日本語形式に設定
        fig.update_xaxes(
            tickformatstops = [
                dict(dtickrange=[None, "M1"], value="%m/%d"),          # 1ヶ月未満の範囲では「月/日」
                dict(dtickrange=["M1", "M12"], value="%Y年%m月"), # 1ヶ月〜1年の範囲では「年と月」
                dict(dtickrange=["M12", None], value="%Y年")         # 1年以上の範囲では「年」
            ]
        )

        fig.update_layout(title_text=f'{pair} Analysis', xaxis_rangeslider_visible=False, height=800)
        figs.append(fig)

    with open(output_file_path, 'w') as f:
        f.write("<html><head><title>Forex Analysis</title></head><body>")
        f.write("<h1 style=\"text-align: center;\">Shin-ne-ashi (New Price Bar) Analysis</h1>")
        for fig in figs:
            f.write(fig.to_html(full_html=False, include_plotlyjs='cdn'))
        f.write("</body></html>")

    print(f"Analysis complete. Check '{output_file_path}'")

    # webdriver-managerのキャッシュパスをプロジェクト内に設定
    cache_path = os.path.join(os.getcwd(), "webdriver_cache")
    os.makedirs(cache_path, exist_ok=True)
    cache_manager = DriverCacheManager(cache_path)

    # ヘッドレスモードでChromeをセットアップ
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox") # Recommended for running in restricted environments
    chrome_options.add_argument("--disable-dev-shm-usage") # Overcomes limited resource problems

    # webdriver-managerを使ってブラウザを起動し、生成したHTMLファイルを開く
    driver = webdriver.Chrome(service=Service(ChromeDriverManager(cache_manager=cache_manager).install()), options=chrome_options)
    driver.get(f"file://{output_file_path}")
    print(f"Successfully opened {output_file_path} in headless browser.")

    driver.quit()


if __name__ == '__main__':
    main()
