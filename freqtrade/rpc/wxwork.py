import json

# 企业微信接口调试工具
# 开发者在调用时，可能会在请求url上加上debug=1参数以开启debug模式，该模式的频率限制很小，每分钟只有5次，开发者在正式上线前请务必去掉debug=1参数。
# https://open.work.weixin.qq.com/devtool/query?e=40058
import logging
import time
from datetime import timezone, timedelta, datetime
from typing import Any, Dict

from requests import RequestException, post

from freqtrade.constants import Config
from freqtrade.enums import RPCMessageType
from freqtrade.rpc import RPC, RPCHandler

logger = logging.getLogger(__name__)

logger.debug("加载模块: 企业微信 ...")

# 颜色标签
LABEL_RED = '<font color="red">'
LABEL_GREEN = '<font color="green">'
LABEL_ORANGE = '<font color="orange">'
LABEL_YELLOW = '<font color="yellow">'
LABEL_BLUE = '<font color="blue">'
LABEL_PURPLE = '<font color="purple">'
LABEL_GREY = '<font color="grey">'
# 标签结束
LABEL_END = "</font>"
# 时区


# 企业微信消息体长度限制
# https://developer.work.weixin.qq.com/document/path/91770#markdown%E7%B1%BB%E5%9E%8B
MAX_CONTENT_LENGTH = 4096
# 重试次数
RETRIES = 3
# 重试延时
RETRY_DELAY = 3
# 交易通知模板 - 文本通知卡片
TRADE_MESSAGE = {
    "msgtype": "template_card",
    "template_card": {},
}
TRADE_MESSAGE_CONTENT = {
    "card_type": "text_notice",
    "source": {
        "icon_url": "https://wework.qpic.cn/wwpic/252813_jOfDHtcISzuodLa_1629280209/0",
        "desc": "交易通知",
        "desc_color": 0,
    },
    # 主标题
    "main_title": {"title": "", "desc": ""},
    # 关键数据栏
    "emphasis_content": {"title": "", "desc": "开仓价格"},
    # 二级普通文本 (14字*8行)
    "sub_title_text": "下载企业微信还能抢红包！",
    # 二级列表
    "horizontal_content_list": [
        {"keyname": "邀请人", "value": "张三"},
        {
            "keyname": "企微官网",
            "value": "点击访问",
            "type": 1,
            "url": "https://work.weixin.qq.com/?from=openApi",
        },
        {
            "keyname": "企微下载",
            "value": "企业微信.apk",
            "type": 2,
            "media_id": "MEDIAID",
        },
    ],
    # 点击整体卡片的跳转地址
    "card_action": {
        "type": 0,
        "url": "",
    },
}

# test
TEST_SRC_EXIT = {
    "type": "exit",
    "trade_id": 54,
    "exchange": "Okx",
    "pair": "LTC/USDT:USDT",
    "leverage": 18.18,
    "direction": "Long",
    "gain": "loss",
    "limit": 88.17,
    "order_rate": 88.17,
    "order_type": "limit",
    "amount": 297.0,
    "open_rate": 88.3,
    "close_rate": 88.17,
    "current_rate": 88.17,
    "profit_amount": -49.092318,
    "profit_ratio": -0.03402541,
    "buy_tag": None,
    "enter_tag": None,
    "sell_reason": "exit_signal",
    "exit_reason": "exit_signal",
    "open_date": datetime(2023, 1, 15, 15, 47, 2, 70489),
    "close_date": datetime(2023, 1, 15, 15, 55, 2, 791666),
    "stake_amount": 1442.5247524752474,
    "stake_currency": "USDT",
    "fiat_currency": "USD",
    "sub_trade": False,
    "cumulative_profit": 0.0,
    "base_currency": "LTC",
}
TEST_SRC_ENTRY = {
    "trade_id": 54,
    "type": "entry",
    "buy_tag": None,
    "enter_tag": None,
    "exchange": "Okx",
    "pair": "LTC/USDT:USDT",
    "leverage": 18.18,
    "direction": "Long",
    "limit": 88.3,
    "open_rate": 88.3,
    "order_type": "limit",
    "stake_amount": 1442.9105159435996,
    "stake_currency": "USDT",
    "fiat_currency": "USD",
    "amount": 297.0,
    "open_date": datetime(2023, 1, 15, 15, 47, 2, 70489),
    "current_rate": 88.3,
    "sub_trade": False,
    "base_currency": "LTC",
}

TEST_SRC_PROTECTION_TRIGGER_GLOBAL = {
    "type": "protection_trigger_global",
    "id": 58,
    "pair": "*",
    "lock_time": "2023-01-16 00:33:11",
    "lock_timestamp": 1673829191528,
    "lock_end_time": "2023-01-16 02:34:00",
    "lock_end_timestamp": 1673836440000,
    "reason": "1 stoplosses in 6 min, locking for 120 min.",
    "side": "*",
    "active": True,
    "base_currency": "",
}


class WxWork(RPCHandler):
    def __init__(self, rpc: RPC, config: Config) -> None:
        super().__init__(rpc, config)
        # 机器人webhook地址
        self._url = self._config["wxwork"]["url"]
        # 请求最大重试次数
        self._retries = self._config["wxwork"].get("retries", 0)
        # 重试间隔时间
        self._retry_delay = self._config["wxwork"].get("retry_delay", 0.1)
        # 请求超时时间
        self._timeout = self._config["wxwork"].get("timeout", 10)

        # 交易通知的类型(markdown,card)
        self._format = self._config["wxwork"].get("format", "markdown")
        # markdown 交易通知是否显示网址链接
        self._markdown_action = self._config["wxwork"].get("markdown_action", False)
        if self._markdown_action:
            self._markdown_url = self._config["wxwork"].get("_markdown_url", "http://stoat.co0.cc")

        # 模板通知卡片是否支持点击操作
        self._card_action = self._config["wxwork"].get("card_action", False)
        if self._card_action:
            # 点击跳转的url
            self._card_url = self._config["wxwork"].get("card_url", "http://stoat.co0.cc")
        # 是否@用户
        self._at = self._config["wxwork"].get("at", False)
        if self._at:
            self._at_user = self._config["wxwork"].get("at_user", "LiuYin")
        # 消息是否使用中国时区
        self._cn_timezone = self._config["wxwork"].get("cn_timezone", False)
        # 不发送的消息类型列表
        self._ignore_message_type = self._config["wxwork"].get("ignore_message_type", [])
        # 推送消息测试
        # self.send_msg(TEST_SRC_ENTRY)
        # self.send_msg(TEST_SRC_EXIT)
        # return

    def send_msg(self, msg: Dict[str, Any]) -> None:
        try:
            # 不发送的消息类型
            if msg["type"] in self._ignore_message_type:
                return
            logger.info("原始消息: %s", msg)
            message = self.format(msg)
            logger.info("格式化后消息: %s", json.dumps(message))
            if message != None:
                self._send_msg(message)
        except KeyError as exc:
            logger.exception("发送企业微信通知失败: %s", exc)

    # 格式化消息内容(默认均使用markdown类型)
    def format(self, msg: Dict[str, Any]):
        data = ""
        if msg["type"] == "status":
            data = self._format_status(msg)
        elif msg["type"] == RPCMessageType.WARNING:
            title = '<font color="warning">*警告:*</font>\n'
            data = title + msg["status"]
        elif msg["type"] == RPCMessageType.STARTUP:
            title = '<font color="info">*状态通知:*</font>\n'
            data = title + msg["status"]
        # 交易通知
        elif msg["type"] in [RPCMessageType.ENTRY, RPCMessageType.EXIT]:
            if self._format == "card":
                data = self._format_trade_card(msg)
                # 生成企业微信markdown标准请求格式
                message = {
                    "msgtype": "template_card",
                    "template_card": data,
                }
                return message

            else:
                data = self._format_trade_markdown(msg)
        # 平仓
        elif msg["type"] == RPCMessageType.EXIT:
            data = self._format_trade(msg, "exit")
            return data
        # ANALYZED_DF
        elif msg["type"] == RPCMessageType.ANALYZED_DF:
            title = "数据分析:\n"
            data = title + ">" + str(msg) + "\n"
        else:
            title = "其他通知:\n"
            data = title + ">" + str(msg) + "\n"

        # 生成企业微信markdown标准请求格式
        message = {"msgtype": "markdown", "markdown": {"content": data}}
        return message

    # status类型格式化
    def _format_status(self, msg: Dict[str, Any]):
        data = "通知:\n"
        if "running" in msg["status"]:
            data += "{}机器人启动成功{}".format(LABEL_GREEN, LABEL_END)
        elif "process died" in msg["status"]:
            data += "{}机器人进程已停止{}".format(LABEL_RED, LABEL_END)
            if self._at:
                data += "\t<@{}>\n".format(self._at_user)
        else:
            data += "{}".format(msg["status"])
        return data

    # 交易类型格式化: markdown
    def _format_trade_markdown(self, msg: Dict[str, Any]):
        direction = "空" if msg["direction"] == "short" else "多"
        action = "开" if msg["type"] == "entry" else "平"
        data = "*交易通知:*\n"
        data += "## {}{}{}{}:\t\t\t{}{}{}\n".format(
            LABEL_GREEN if msg["type"] == "entry" else LABEL_RED,
            action,
            direction,
            LABEL_END,
            LABEL_YELLOW,
            msg["pair"],
            LABEL_END,
        )

        data += "> 开仓价格:\t{}\n".format(msg["open_rate"])
        if msg["type"] == "exit":
            data += "> 平仓价格:\t{}\n".format(msg["close_rate"])
        data += "\n{}*仓位详情:*{}\n".format(LABEL_GREY, LABEL_END)
        data += ">持仓数量:\t{:.2f} {}\n".format(msg["amount"], msg["base_currency"])
        data += ">仓位价值:\t{:.2f}\n".format(msg["open_rate"] * msg["amount"])
        data += ">杠杆倍数:\t{}\n".format(msg["leverage"])
        data += ">保证金:\t\t{:.2f}\n".format(msg["stake_amount"])

        if msg["type"] == "exit":
            # 收益详情
            data += "\n{}*盈亏分析:*{}\n".format(LABEL_GREY, LABEL_END)
            data += ">收益额:\t\t{}{:.2f}{}\n".format(
                LABEL_RED if msg["gain"] == "loss" else LABEL_GREEN,
                msg["profit_amount"],
                LABEL_END,
            )
            data += ">收益率:\t\t{}{:.2f}%{}\n".format(
                LABEL_RED if msg["gain"] == "loss" else LABEL_GREEN,
                msg["profit_ratio"] * 100,
                LABEL_END,
            )
            data += ">平仓原因:\t{}\n".format(self.format_exit_reason(msg["exit_reason"]))

        # 详情
        data += "\n{}*基本信息:*{}\n".format(LABEL_GREY, LABEL_END)
        data += ">交易ID:\t\t{}\n".format(msg["trade_id"])
        data += ">交易所:\t\t{}\n".format(msg["exchange"])
        data += ">交易对:\t\t{}\n".format(msg["pair"])
        data += ">开仓时间:\t{}\n".format(self._format_datetime(msg["open_date"]))

        if msg["type"] == "exit":
            data += ">平仓时间:\t{}\n".format(self._format_datetime(msg["close_date"]))
        if msg["enter_tag"] != None:
            data += ">备注:\t{}\n".format(msg["enter_tag"])
        if self._markdown_action:
            data += "[详细信息]({})".format(self._markdown_url)

        return data

    # 格式化平仓原因内容
    def format_exit_reason(self, src):
        if src == "exit_signal":
            return "平仓信号"
        elif src == "stop_loss":
            return "止损"
        elif src == "liquidation":
            return "强平"
        else:
            return src

    # 实际调用函数
    def _send_msg(self, message: dict) -> None:
        success = False
        attempts = 0
        while not success and attempts <= self._retries:
            if attempts:
                if self._retry_delay:
                    time.sleep(self._retry_delay)
                logger.info("企业微信通知发送失败,第 %d 次重试...", attempts)
            attempts += 1
            try:

                response = post(
                    self._url,
                    data=json.dumps(message),
                    headers={"Content-Type": "application/json;charset=UTF-8"},
                    timeout=self._timeout,
                )
                # 检查http状态码
                response.raise_for_status()
                # 检查企业微信返回码
                res = json.loads(response.text)
                if "errcode" in res:
                    if res["errcode"] == 0:
                        success = True
                        logger.info("企业微信通知发送成功:%s", res)
                    else:
                        logger.error("发送企业微信通知失败: %s", res)

            except RequestException as exc:
                logger.error("发送企业微信通知失败: %s", exc)

    # 公共函数
    @staticmethod
    def send_balance(rpc: RPC, config: Config):
        result = rpc._rpc_balance(config["stake_currency"], config.get("fiat_display_currency", ""))
        logger.info("result:{}".format(result))
        data = '<font color="info">定时通知:</font>\n'
        if config["dry_run"]:
            data += "\t*模拟资产*\n"
        for curr in result["currencies"]:
            curr_output = ""
            if curr["is_position"]:
                curr_output += "*{}*:\n".format(curr["currency"])
                curr_output += "\t\t *{}*: \t{}\n".format(curr["side"], curr["position"])
                curr_output += "\t\t *杠杆*:\t{}x\n".format(curr["leverage"])
            else:
                curr_output += "*{}*:\n".format(curr["currency"])
                curr_output += "\t\t *可用*: \t{:.3f}\n".format(curr["free"])
                curr_output += "\t\t *已用*:\t{:.3f}\n".format(curr["used"])
                curr_output += "\t\t *合计*: \t{:.3f}\n".format(curr["balance"])
            data += curr_output
        # total
        data += "\n*合计*:\t\t\t{:.3f}{}\n".format(result["value"], result["stake"])
        data += "\n*初始资金*:\t{}\n".format(result["starting_capital"], result["stake"])
        data += "\n*收益率*:\t\t{}{}%{}\n".format(
            LABEL_RED if result["starting_capital_pct"] <= 0 else LABEL_GREEN,
            result["starting_capital_pct"],
            LABEL_END,
        )
        data += "\n*交易次数*:\t{}\n".format(result["trade_count"])

        # if len(output + curr_output) >= MAX_CONTENT_LENGTH:
        message = {"msgtype": "markdown", "markdown": {"content": data}}
        logger.info("资产信息: {}".format(message))
        WxWork.notification(config["wxwork"]["url"], message)

    @staticmethod
    def notification(url, message) -> None:
        success = False
        attempts = 0
        while not success and attempts <= RETRIES:
            if attempts:
                if RETRY_DELAY:
                    time.sleep(RETRY_DELAY)
                logger.info("企业微信通知发送失败,第 %d 次重试...", attempts)
            attempts += 1
            try:
                # json 数据格式转换不使用默认编码，再进行 utf-8编码转换
                data = json.dumps(message)
                response = post(
                    url,
                    data=data,
                    headers={"Content-Type": "application/json;charset=UTF-8"},
                )
                # 检查http状态码
                response.raise_for_status()
                # 检查企业微信返回码
                res = json.loads(response.text)
                if "errcode" in res:
                    if res["errcode"] == 0:
                        success = True
                        logger.info("企业微信通知发送成功:%s", res)
                    else:
                        logger.error("发送企业微信通知失败: %s", res)

            except RequestException as exc:
                logger.error("发送企业微信通知失败: %s", exc)

    # https://developer.work.weixin.qq.com/document/path/91770#%E6%96%87%E6%9C%AC%E9%80%9A%E7%9F%A5%E6%A8%A1%E7%89%88%E5%8D%A1%E7%89%87
    # 开仓通知模板 -- 文本通知卡片类型
    # TODO: 展示效果待优化
    def _format_trade_card(self, msg: Dict[str, Any], action: str):
        message = TRADE_MESSAGE
        # dst = TRADE_MESSAGE_CONTENT
        dst = {
            "card_type": "text_notice",
            "source": {
                "icon_url": "https://wework.qpic.cn/wwpic/252813_jOfDHtcISzuodLa_1629280209/0",
                "desc": "交易通知",
                "desc_color": 0,
            },
        }

        direction = "空" if msg["direction"] == "short" else "多"
        action_str = "开" if action == "entry" else "平"
        # 主标题
        dst["main_title"] = {}
        dst["main_title"]["title"] = "{}{}: \t {}".format(action_str, direction, msg["pair"])
        dst["main_title"]["desc"] = "仓位: \t{:.2f} ({:.2f}x) ".format(
            msg["stake_amount"],
            msg["leverage"],
        )
        # 关键数据栏
        dst["emphasis_content"] = {}
        dst["emphasis_content"]["title"] = "{}".format(
            msg["open_rate"] if action == "entry" else msg["close_rate"]
        )
        dst["emphasis_content"]["desc"] = action_str + "仓价"

        # 详情 (最多8行)
        dst["sub_title_text"] = "详情:\n"
        dst["sub_title_text"] += "ID: \t\t\t\t{}\n".format(msg["trade_id"])
        dst["sub_title_text"] += "交易对: \t\t\t{}\n".format(msg["pair"])
        dst["sub_title_text"] += "仓位: \t\t\t{:.2f} {}\n".format(
            msg["stake_amount"], msg["stake_currency"]
        )
        dst["sub_title_text"] += "交易所: \t\t\t{}\n".format(msg["exchange"])
        dst["sub_title_text"] += "杠杆: \t\t\t{:.2f}x\n".format(msg["leverage"])
        # 盈亏分析 (quote_text最多3行)
        if action == "exit":
            dst["quote_area"] = {}
            gain = "亏损" if msg["gain"] == "loss" else "盈利"
            dst["quote_area"]["title"] = "收益详情:\t\t{}".format(gain)
            # dst['quote_area']['quote_text'] = ">盈亏: <font color=\"{}\">{}%</font>\n".format(
            #     "warning" if msg['gain'] == 'loss' else "success",  gain)
            dst["quote_area"]["quote_text"] = "收益: \t\t\t{:.2f}\n".format(
                msg["profit_amount"],
            )
            dst["quote_area"]["quote_text"] += "收益率: \t\t\t{:.2f}%\n".format(
                msg["profit_ratio"] * 100,
            )
            dst["quote_area"]["quote_text"] += "平仓原因: \t\t{}\n".format(msg["exit_reason"])
        # 二级列表 (最多六个)
        # dst['horizontal_content_list'] = []
        data = []
        data.append({"keyname": "开仓价格:", "value": "\t\t{}".format(msg["open_rate"])})
        if action == "exit":
            data.append({"keyname": "平仓价格:", "value": "\t\t{}".format(msg["close_rate"])})
        data.append(
            {
                "keyname": "开仓时间:",
                "value": "{}".format(self._format_datetime(msg["open_date"])),
            }
        )
        if action == "exit":
            data.append(
                {
                    "keyname": "平仓时间:",
                    "value": "{}".format(self._format_datetime(msg["close_date"])),
                }
            )

        if msg["enter_tag"] is not None:
            data.append({"keyname": "备注", "value": "\t{}".format(msg["enter_tag"])})
        dst["horizontal_content_list"] = data
        # 卡片跳转
        if self._card_action:
            dst["card_action"] = {"type": 1, "url": self._card_url}
        message["template_card"] = dst
        logger.info("dst formatted: {}", message)

        logger.info("message formatted: {}", message)
        return message

    # 时区转换
    def _format_datetime(self, src):
        if self._cn_timezone:
            utc_time = src.replace(tzinfo=timezone.utc)
            cn_tz = timezone(timedelta(hours=8))
            src = utc_time.astimezone(cn_tz)
        dst = src.strftime("%Y-%m-%d %H:%M:%S")
        return dst

    def _format_trade(self, msg, param):
        pass
