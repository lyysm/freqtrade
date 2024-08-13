# 开发环境设置

# python 环境

```bash
conda create  -n freqtrade python=3.12
conda activate freqtrade
pip install --upgrade pip
```

### 安装依赖

```bash
bash build_helpers/install_ta-lib.sh
```

### 安装 freqtrade

```bash
pip install -e .
```

### 使用

- 创建用户目录和配置文件

```bash
freqtrade create-userdir --userdir bot-01
freqtrade new-config --config bot-01/config.json
```

> 在用户目录下执行 freqtrade 时无需指定配置文件,默认使用当前目录下的 config.json

- 下载数据

```bash
freqtrade download-data --exchange okx --pairs "ETH/USDT:USDT"
freqtrade download-data --exchange okx --pairs "ETH/USDT:USDT" --days 10
freqtrade download-data --exchange okx --pairs "ETH/USDT:USDT" --days 10 --timeframes 1m 5m 15m 1h 4h 1d
```

````

# 启动 webserver

```bash
freqtrade webserver --config bot-01/config.json
````

---

## 通知配置

### 企业微信

````json
    "wxwork": {
        "enabled": true,
        "url": "{bot-url}",
        "retries": 0,
        "retry_delay": 0.1,
        "timeout": 3,
        "format": "markdown",
        "markdown_action": true,
        "card_action": true,
        "at": true,
        "at_user": "Liuyin",
        "cn_timezone": true,
        "ignore_message_type": [
            "analyzed_df",
            "new_candle"
        ]
    }
    ```
````
