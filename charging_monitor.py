import urllib.request
import urllib.parse
import time
import json
import os
import sys
from urllib.error import URLError, HTTPError
from datetime import datetime, timedelta

# 请求URL
REQUEST_URL = "https://wx.jwnzn.com/mini_jwnzn/miniapp/mp_getChargingData.action"

# 全局变量存储历史功率数据
history_power_data = []

# 重试配置
MAX_RETRIES = 10  # 最大重试次数
RETRY_INTERVAL = 10  # 重试间隔（秒）


def clear_screen():
    # 清屏函数，兼容不同操作系统
    os.system('cls' if os.name == 'nt' else 'clear')

def get_user_cid():
    # 获取并验证用户输入的订单号，同时重置历史功率数据
    global history_power_data
    history_power_data = []
    while True:
        cid = input("请输入订单号：").strip()
        if cid.isdigit():
            return cid
        print("错误：订单号必须为纯数字，请重新输入！")

def get_power_threshold():
    # 获取并验证用户输入的功率阈值
    while True:
        threshold_str = input("请输入最低功率阈值（W，设为0W时将检测充电完成/拔出状态）：").strip()
        threshold_str = threshold_str.replace('W', '').replace('w', '').strip()
        
        if threshold_str.replace('.', '', 1).isdigit():
            threshold = float(threshold_str)
            if threshold >= 0:
                return threshold
            else:
                print("错误：阈值不能为负数！")
        else:
            print("错误：请输入有效的数字（如0、10、20.5、30W等）！")

def parse_time(time_str):
    # 解析时间字符串为datetime对象
    try:
        for fmt in ['%Y-%m-%d %H:%M:%S', '%Y/%m/%d %H:%M:%S', '%Y-%m-%d %H:%M']:
            return datetime.strptime(time_str, fmt)
    except ValueError:
        return None

def play_warning_sound(warning_type):
    # 根据警告类型播放对应声音提示
    if sys.platform.startswith('win32'):
        import winsound
        if warning_type == "low_power":
            winsound.Beep(5000, 500)
            winsound.Beep(4000, 500)
            winsound.Beep(3000, 500)
            winsound.Beep(2000, 500)
            winsound.Beep(1000, 500)
        elif warning_type == "sudden_increase":
            winsound.Beep(1000, 500)
            winsound.Beep(2000, 500)
            winsound.Beep(3000, 500)
            winsound.Beep(4000, 500)
            winsound.Beep(5000, 500)
        elif warning_type == "zero_power":
            winsound.Beep(2000, 800)
            time.sleep(0.2)
            winsound.Beep(2000, 800)
    else:
        if warning_type == "low_power":
            print("🔔 警告：当前充电功率低于设定阈值！")
        elif warning_type == "sudden_increase":
            print("🔔 警告：当前充电功率突然增大，可能更换了充电设备！")
        elif warning_type == "zero_power":
            print("🔔 提示：当前充电功率为0W，充电可能已完成或设备已拔出！")

def fetch_charging_data(cid, power_threshold):
    # 发送POST请求获取充电数据，并处理各类警告状态
    global history_power_data
    form_data = {"cid": cid}
    encoded_data = urllib.parse.urlencode(form_data).encode("utf-8")

    try:
        request = urllib.request.Request(
            url=REQUEST_URL,
            data=encoded_data,
            method="POST"
        )
        request.add_header("Content-Type", "application/x-www-form-urlencoded; charset=utf-8")
        request.add_header("User-Agent", "Mozilla/5.0")

        with urllib.request.urlopen(request, timeout=10) as response:
            response_content = response.read().decode("utf-8")
            response_json = json.loads(response_content)

        clear_screen()
        current_time = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())
        current_datetime = datetime.now()
        print("=== 充电数据实时监控 ===")
        print(f"监控时间: {current_time}")
        print(f"监控订单: {cid}")
        print(f"功率阈值: {power_threshold}W\n")
        
        if response_json.get("normal") == 1 and response_json.get("msg") == "获取成功":
            ele_data = response_json.get("eleChargingData", {})
            out_power = ele_data.get('outPower', '未获取到')
            
            charge_info = {
                "订单时间（startTime）": ele_data.get("startTime", "未获取到"),
                "充电站名称（snName）": ele_data.get("snName", "未获取到"),
                "充电桩编号（sn）": ele_data.get("sn", "未获取到"),
                "插座编号（sid）": ele_data.get("sid", "未获取到"),
                "充电时长（chargeTime）": ele_data.get("chargeTime", "未获取到"),
                "当前充电功率（outPower）": f"{out_power}W",
                "订单价格（payMoney）": f"¥{ele_data.get('payMoney', '未获取到')}",
                "安全服务费（safeServerMoney）": f"¥{ele_data.get('safeServerMoney', '未获取到')}",
                "时长服务费（timeServerMoney）": f"¥{ele_data.get('timeServerMoney', '未获取到')}"
            }
            for key, value in charge_info.items():
                print(f"{key}: {value}")
            
            low_power_warn = False
            sudden_increase_warn = False
            zero_power_warn = False
            order_time = ele_data.get("startTime", "")
            order_datetime = parse_time(order_time)
            
            if isinstance(out_power, (int, float)):
                # 检测0W状态
                if out_power == 0:
                    zero_power_warn = True
                # 检测低功率状态
                elif out_power < power_threshold and power_threshold > 0:
                    low_power_warn = True
                
                # 记录并检测功率突增
                history_power_data.append(out_power)
                if len(history_power_data) > 5:
                    history_power_data.pop(0)
                
                if len(history_power_data) >= 3 and order_datetime:
                    time_since_order = current_datetime - order_datetime
                    if time_since_order > timedelta(minutes=5):
                        avg_prev_power = sum(history_power_data[:-1]) / len(history_power_data[:-1])
                        if out_power - avg_prev_power > 10:
                            sudden_increase_warn = True
            
            # 按优先级触发警告
            print("\n" + "="*40)
            if zero_power_warn:
                print("⚠️  重要提示：当前充电功率为0W")
                print("   可能原因：充电已完成 / 充电设备已拔出 / 充电中断")
                play_warning_sound("zero_power")
            elif sudden_increase_warn:
                print("⚠️  警告：充电功率突然增大超过10W")
                print("   可能原因：充电设备被更换 / 充电桩异常")
                play_warning_sound("sudden_increase")
            elif low_power_warn:
                print(f"⚠️  警告：当前充电功率（{out_power}W）低于设定阈值（{power_threshold}W）")
                play_warning_sound("low_power")
            else:
                print("✅  当前充电状态正常，功率稳定")
            print("="*40)
            print("\n(按Ctrl+C停止监控)")
            return False  # 订单状态正常
        
        else:
            error_msg = response_json.get("msg", "未知错误")
            print(f"获取数据失败：{error_msg}")
            print("\n(按Ctrl+C停止监控)")
            return True  # 订单状态异常

    # 异常处理
    except HTTPError as e:
        clear_screen()
        print("=== 充电数据实时监控 ===")
        print(f"监控时间: {time.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"监控订单: {cid}\n")
        print(f"❌ HTTP错误：状态码 {e.code}（可能是服务器异常或接口失效）")
        print("\n(按Ctrl+C停止监控)")
        return True
    except URLError as e:
        clear_screen()
        print("=== 充电数据实时监控 ===")
        print(f"监控时间: {time.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"监控订单: {cid}\n")
        print(f"❌ 网络错误：{str(e.reason)}（请检查网络连接或URL是否正确）")
        print("\n(按Ctrl+C停止监控)")
        return True
    except json.JSONDecodeError:
        clear_screen()
        print("=== 充电数据实时监控 ===")
        print(f"监控时间: {time.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"监控订单: {cid}\n")
        print("❌ 解析错误：服务器返回数据格式异常（非JSON）")
        print("\n(按Ctrl+C停止监控)")
        return True
    except Exception as e:
        clear_screen()
        print("=== 充电数据实时监控 ===")
        print(f"监控时间: {time.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"监控订单: {cid}\n")
        print(f"❌ 未知错误：{str(e)}")
        print("\n(按Ctrl+C停止监控)")
        return True

def main():
    # 主函数：初始化并执行监控逻辑
    print("=== 中网充订单数据实时监控工具 ===")
    print("功能说明：")
    print("1. 监控充电功率，当低于设定阈值时发出警告")
    print("2. 当功率设为0W时，自动检测充电完成/设备拔出状态")
    print("3. 订单开始5分钟后，检测功率突增（>10W），预警设备更换风险")
    print("4. 支持异常自动重试，提高监控稳定性")
    print("-"*50)
    
    cid = get_user_cid()
    power_threshold = get_power_threshold()
    
    print(f"\n📌 监控配置完成：")
    print(f"   - 目标订单：{cid}")
    print(f"   - 功率阈值：{power_threshold}W")
    print(f"   - 刷新频率：每5秒更新一次数据")
    print(f"   - 重试机制：异常时自动重试{MAX_RETRIES}次，每次间隔{RETRY_INTERVAL}秒")
    print(f"   - 停止方式：按Ctrl+C终止监控")
    print("\n倒计时2秒后开始监控...")
    time.sleep(2)
    
    try:
        while True:
            retry_count = 0
            order_abnormal = True
            
            # 异常时自动重试机制
            while retry_count <= MAX_RETRIES and order_abnormal:
                order_abnormal = fetch_charging_data(cid, power_threshold)
                
                # 如果正常获取数据，退出重试循环
                if not order_abnormal:
                    break
                
                # 如果还有重试次数，进行重试
                if retry_count < MAX_RETRIES:
                    retry_count += 1
                    print(f"\n🔄 异常自动重试（{retry_count}/{MAX_RETRIES}）...")
                    time.sleep(RETRY_INTERVAL)
                else:
                    # 重试次数用完，要求用户重新输入订单号
                    print(f"\n🔄 已连续重试{MAX_RETRIES}次仍失败，将重新获取订单号...")
                    time.sleep(2)
                    cid = get_user_cid()
                    print(f"\n已切换监控订单：{cid}，继续监控...")
            
            # 正常监控间隔
            if not order_abnormal:
                time.sleep(5)
    
    except KeyboardInterrupt:
        clear_screen()
        print("=== 监控工具已停止 ===")
        print(f"停止时间：{time.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"本次监控订单：{cid}")
        print("感谢使用，再见！")
        sys.exit(0)

if __name__ == "__main__":
    main()