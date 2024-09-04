from datetime import datetime, timedelta
from fastapi import APIRouter, FastAPI, Depends, HTTPException, Path, Query, status
from pydantic import BaseModel

from .models import AccountCreate, AccountResponseModel, GetAccountsResponseModel, ResponseModel, TransactionCreate, TransactionResponseModel, TransactionsResponseModel
from .database import mongodb
from .auth import get_api_key
from bson import ObjectId
import requests
from collections import Counter
import time
import calendar
from collections import Counter

app = FastAPI()

router = APIRouter(prefix="/v2")

class ComparisonFundReturnsRequest(BaseModel):
    calismatipi: str = "1"
    fontip: str = "YAT"
    sfontur: str = ""
    kurucukod: str = ""
    fongrup: str = ""
    bastarih: str
    bittarih: str
    fonturkod: str = ""
    fonunvantip: str = ""
    strperiod: str = "1,1,1,1,1,1,1"
    islemdurum: str = "1"


# Binance API endpoint for ticker price
BINANCE_API_URL = "https://api.binance.com/api/v3/ticker/price"

@router.get("/usdttry/current", tags=["Binance"])
def get_usd_try_price():
    try:
        response = requests.get(BINANCE_API_URL, params={"symbol": "USDTTRY"})
        response.raise_for_status()  # Raise an HTTPError for bad responses
        data = response.json()
        return data
        # return {"symbol": data["symbol"], "price": data["price"]}
    except requests.RequestException as exc:
        raise HTTPException(status_code=500, detail=str(exc))

# Binance API endpoint for historical candlestick data
HISTORICAL_API_URL = "https://api.binance.com/api/v3/klines"

@router.get("/usdttry/historical", tags=["Binance"])
def get_historical_price(date: str):
    # Validate and parse the date
    try:
        dt = datetime.strptime(date, "%d.%m.%Y")
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use DD.MM.YYYY")
    
    # Set up the start and end times for the requested date
    start_time = int(dt.timestamp() * 1000)  # Convert to milliseconds
    end_time = int((dt + timedelta(days=1)).timestamp() * 1000)  # End of the day

    try:
        response = requests.get(HISTORICAL_API_URL, params={
            "symbol": "USDTTRY",
            "interval": "1d",
            "startTime": start_time,
            "endTime": end_time
        })
        response.raise_for_status()
        data = response.json()
        if not data:
            raise HTTPException(status_code=404, detail="No data found for the specified date.")
        # Extract relevant parts from the candlestick data
        price_data = {
            "open_time": data[0][0],
            "open": data[0][1],
            "high": data[0][2],
            "low": data[0][3],
            "close": data[0][4],
            "volume": data[0][5]
        }
        return price_data
    except requests.RequestException as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    
@router.get("/tefas/fonlarin_getirisi_dolar", tags=["Tefas"])
async def fonlarin_getirisi_dolar(
    ay_sayisi: int = Query(None, description="Kac ay olsun? (1-59)"),
):
    print("Running find_returns")

    today = datetime.today()

    # fon list
    fon_list = []
        
    payload = ComparisonFundReturnsRequest(
        bastarih=(datetime.now() - timedelta(days=30)).strftime('%d.%m.%Y'),
        bittarih=datetime.now().strftime('%d.%m.%Y')
    )

    url = 'https://www.tefas.gov.tr/api/DB/BindComparisonFundReturns'

    
    response = requests.post(url, data=payload.dict())
    response.raise_for_status()
    data = response.json()

    # 使用列表解析来过滤掉含有“Serbest”的项
    data['data'] = [item for item in data['data'] if 'Serbest' not in item['FONTURACIKLAMA']]
    # 更新 recordsTotal 和 recordsFiltered
    data['recordsTotal'] = len(data['data'])
    data['recordsFiltered'] = len(data['data'])

    # 处理 GETIRIORANI 为 None 的情况，将 None 替换为一个最小的值（如负无穷）
    for item in data['data']:
        if item['GETIRIORANI'] is None:
            item['GETIRIORANI'] = -1e10

    # 按照 GETIRIORANI 从大到小排序
    sorted_data = sorted(data['data'], key=lambda x: x['GETIRIORANI'], reverse=True)

    # 更新原数据
    data['data'] = sorted_data

    for item in data['data']:
        fon_list.append(item['FONKODU'])

    # print(fon_list)

    # fon_list = ["YAS","MAC","IIH"]

    ##################################################

    dic_A = {}
    for i in range(ay_sayisi):

        print(f"Getting data for month {i+1}")
        month_offset = today.month - (i + 1)
        year = today.year + (month_offset // 12)
        month = month_offset % 12
        if month <= 0:
            month += 12
            year -= 1

        # 计算该月的第一天和最后一天
        first_day = datetime(year, month, 1)
        last_day = datetime(year, month, calendar.monthrange(year, month)[1])        

        # 格式化日期
        first_day_str = first_day.strftime('%d.%m.%Y')
        print(f"first_day_str: {first_day_str}")
        last_day_str = last_day.strftime('%d.%m.%Y')
        print(f"last_day_str: {last_day_str}")

        payload = ComparisonFundReturnsRequest(
            bastarih= first_day_str,
            bittarih= last_day_str
        )

        url = 'https://www.tefas.gov.tr/api/DB/BindComparisonFundReturns'

        try:
            response = requests.post(url, data=payload.dict())
            response.raise_for_status()
            data = response.json()

            # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # 
            # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # # 
            a = get_historical_price(first_day_str)
            data['first_day_usd'] = float(a['close'])
            b = get_historical_price(last_day_str)
            data['last_day_usd'] = float(b['close'])

            dic_A[i+1] = data

            # print("dic_A: ", dic_A)


        except requests.exceptions.HTTPError as http_err:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"HTTP error occurred: {http_err}")
        except requests.exceptions.ConnectionError as conn_err:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Connection error occurred: {conn_err}")
        except requests.exceptions.Timeout as timeout_err:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Timeout error occurred: {timeout_err}")
        except requests.exceptions.RequestException as req_err:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"An error occurred: {req_err}")

        

    # fon_list = ["YAS","MAC","IIH"]

    data_B = {}
    for fon in fon_list:
        print("fon: ", fon)

        list_b = []

        for key, value in dic_A.items():
            usd_price_begin = value['first_day_usd']
            usd_price_last = value['last_day_usd']
            # print(f"usd_price_begin: {usd_price_begin}, usd_price_last: {usd_price_last}")
            for item in value['data']:
                if item['FONKODU'] == fon:
                    # list_b.append(item['GETIRIORANI'])
                    # # # # # # # # # # # # # # # # # # # # # # # # # # 
                    # # # # # # # # # # # # # # # # # # # # # # # # # # 
                    delta = item['GETIRIORANI']

                    if delta is None:
                        delta = 0

                    price_begin = 1
                    price_last = 1 + delta/100

                    a = price_begin / usd_price_begin
                    b = price_last / usd_price_last
                    c = b / a
                    d = (c - 1) * 100
                    # print(f"a = {a}, b = {b}, c = {c}, d = {d}")
                    list_b.append(d)

                     

        data_B[fon] = list_b

    # print(f"data_B: {data_B}")

    data_C = {}
    for fonkod, list_c in data_B.items():
        list_d = []
        list_c.reverse()
        list_c = list(filter(None, list_c))

        period_profits = list_c
        # 每周投资金额
        investment_per_peroid = 100

        # 初始投资账户价值
        investment_value = 0

        # 总投资金额
        total_investment = 0

        # 遍历每周的利润率并更新投资账户价值
        for profit in period_profits:
            # 将当前投资金额加入账户
            investment_value += investment_per_peroid
            # 更新总投资金额
            total_investment += investment_per_peroid
            # 根据当前周的利润率更新账户价值
            investment_value += investment_value * (profit / 100)
            print(f"当前账户价值: {total_investment} - {investment_value:.2f} 元")

        # 计算最终利润
        final_profit = investment_value - total_investment

        print(f"总共投入: {total_investment:.2f} 元")
        print(f"最终利润: {final_profit:.2f} 元")

        # 避免除以零的错误
        if total_investment != 0:
            profit_rate = (final_profit / total_investment) * 100
            print(f"利润率: {profit_rate:.2f}%")
            print(f"period%: {profit_rate/len(period_profits):.2f}%")
        else:
            print("总投入为 0，无法计算利润率")

        list_d.append(total_investment)
        list_d.append(investment_value)
        list_d.append(profit_rate)
        try:
            list_d.append(profit_rate/len(period_profits))
        except ZeroDivisionError:
            list_d.append(0)

        data_C[fonkod] = list_d

    sorted_data = dict(sorted(data_C.items(), key=lambda item: item[1][3], reverse=True))
    # return sorted_data

    # 使用字典推导式删除不等于 ay_sayisi * 100 的键值对
    num = ay_sayisi * 100
    filtered_data = {key: value for key, value in sorted_data.items() if value[0] == num}
    # return filtered_data

    # 使用字典推导式删除第三项小于零的键值对
    filtered_data_2 = {key: value for key, value in filtered_data.items() if value[2] >= 0}

    # # 使用 keys() 方法将所有键保存到一个新的列表
    # keys_list = list(filtered_data_2.keys())

    return filtered_data_2




@router.get("/tefas/fonlarin_getirisi_dolar_her_3ay", tags=["Tefas"])
async def fonlarin_getirisi_dolar_her_3ay():

    list_ = []
    for i in range(5):
        data = await fonlarin_getirisi_dolar(3 * (i + 1))

        # 使用 keys() 方法将所有键保存到一个新的列表
        keys_list = list(data.keys())
        
        # 插入 keys_list 的每个元素到 list_ 中
        for idx, key in enumerate(keys_list):
            if idx < len(list_):
                list_.insert(idx, key)
            else:
                list_.append(key)


    # 使用 Counter 来计算出现频率
    frequency = Counter(list_)

    data = {}
    # 输出出现频率
    for item, count in frequency.items():
        data[item] = count
    
    # 按值从大到小排序字典
    sorted_data = dict(sorted(data.items(), key=lambda item: item[1], reverse=True))

    return sorted_data


app.include_router(router)
