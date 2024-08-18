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

app = FastAPI()
router = APIRouter(prefix="/v1")

# Accounts
@router.post("/accounts/", dependencies=[Depends(get_api_key)], tags=["Accounts"], response_model=AccountResponseModel, status_code=status.HTTP_201_CREATED)
async def create_account(account: AccountCreate):
    try:
        result = await mongodb.db["accounts"].insert_one(account.dict())
        created_account = await mongodb.db["accounts"].find_one({"_id": result.inserted_id})
        if not created_account:
            raise HTTPException(status_code=404, detail="Account creation failed")
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
    return AccountResponseModel.from_mongo(created_account)


@router.get("/accounts/", dependencies=[Depends(get_api_key)], tags=["Accounts"], response_model=GetAccountsResponseModel)
async def get_accounts():
    accounts = []
    try:
        async for account in mongodb.db["accounts"].find():
            account['_id'] = str(account['_id'])  # Convert _id to str
            accounts.append(AccountResponseModel.from_mongo(account))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
    return GetAccountsResponseModel(accounts=accounts)


@router.get("/accounts/{account_id}", dependencies=[Depends(get_api_key)], tags=["Accounts"], response_model=AccountResponseModel)
async def get_account(account_id: str):
    if not ObjectId.is_valid(account_id):
        raise HTTPException(status_code=400, detail="Invalid ObjectId")
    try:
        account = await mongodb.db["accounts"].find_one({"_id": ObjectId(account_id)})
        if account is None:
            raise HTTPException(status_code=404, detail="Account not found")
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
    return AccountResponseModel.from_mongo(account)


@router.put("/accounts/{account_id}", dependencies=[Depends(get_api_key)], tags=["Accounts"], response_model=AccountResponseModel)
async def update_account(account_id: str, account: AccountCreate):
    if not ObjectId.is_valid(account_id):
        raise HTTPException(status_code=400, detail="Invalid ObjectId")
    try:
        result = await mongodb.db["accounts"].update_one({"_id": ObjectId(account_id)}, {"$set": account.dict()})
        if result.matched_count == 0:
            raise HTTPException(status_code=404, detail="Account not found")
        updated_account = await mongodb.db["accounts"].find_one({"_id": ObjectId(account_id)})
        if updated_account is None:
            raise HTTPException(status_code=404, detail="Account not found")
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
    return AccountResponseModel.from_mongo(updated_account)


@router.delete("/accounts/{account_id}", dependencies=[Depends(get_api_key)], tags=["Accounts"], response_model=ResponseModel)
async def delete_account(account_id: str):
    if not ObjectId.is_valid(account_id):
        raise HTTPException(status_code=400, detail="Invalid ObjectId")
    try:
        result = await mongodb.db["accounts"].delete_one({"_id": ObjectId(account_id)})
        if result.deleted_count == 0:
            raise HTTPException(status_code=404, detail="Account not found")
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
    return ResponseModel(success=True, message="Account deleted")


# Transactions

@router.post("/transactions/", dependencies=[Depends(get_api_key)], tags=["Transactions"], response_model=TransactionResponseModel)
async def create_transaction(transaction: TransactionCreate):
    try:
        transaction.serialNumber = await TransactionCreate._generate_serial_number()
        result = await mongodb.db["transactions"].insert_one(transaction.dict())
        if not result.inserted_id:
            raise HTTPException(status_code=500, detail="Transaction creation failed")
            
        # Retrieve the created transaction from the database
        created_transaction = await mongodb.db["transactions"].find_one({"_id": result.inserted_id})
        if not created_transaction:
            raise HTTPException(status_code=404, detail="Failed to retrieve created transaction")

        return TransactionResponseModel(**created_transaction)
    
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("/transactions/", dependencies=[Depends(get_api_key)], tags=["Transactions"], response_model=TransactionsResponseModel)
async def get_transactions():
    try:
        transactions = await mongodb.db["transactions"].find().to_list(length=None)
        if not transactions:
            raise HTTPException(status_code=404, detail="No transactions found")

        # Convert _id to str and create TransactionResponseModel instances
        transactions_response = [TransactionResponseModel(**{**transaction, '_id': str(transaction['_id'])}) for transaction in transactions]

        return TransactionsResponseModel(transactions=transactions_response)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("/transactions/{serial_number}", dependencies=[Depends(get_api_key)], tags=["Transactions"], response_model=TransactionResponseModel)
async def get_transaction(serial_number: int):
    try:
        transaction = await mongodb.db["transactions"].find_one({"serialNumber": serial_number})
        if transaction is None:
            raise HTTPException(status_code=404, detail="Transaction not found")
        return TransactionResponseModel(**transaction)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.delete("/transactions/{serial_number}", dependencies=[Depends(get_api_key)], tags=["Transactions"], response_model=ResponseModel)
async def delete_transaction(serial_number: int):
    try:
        result = await mongodb.db["transactions"].delete_one({"serialNumber": serial_number})
        if result.deleted_count == 0:
            raise HTTPException(status_code=404, detail="Transaction not found")
        return ResponseModel(success=True, message="Transaction deleted")
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
    

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

@router.get("/tefas/BindComparisonFundReturns", tags=["Tefas"])
async def bind_comparison_fund_returns(
    bastarih: str = Query(None, description="Start date in format DD.MM.YYYY"),
    bittarih: str = Query(None, description="End date in format DD.MM.YYYY")
):
    # Default dates: past month
    if not bastarih:
        bastarih = (datetime.now() - timedelta(days=30)).strftime('%d.%m.%Y')
    if not bittarih:
        bittarih = datetime.now().strftime('%d.%m.%Y')
        
    payload = ComparisonFundReturnsRequest(
        bastarih=bastarih,
        bittarih=bittarih
    )

    url = 'https://www.tefas.gov.tr/api/DB/BindComparisonFundReturns'

    try:
        response = requests.post(url, data=payload.dict())
        response.raise_for_status()
        data = response.json()

        # 使用列表解析来过滤掉含有“Serbest”的项
        data['data'] = [item for item in data['data'] if 'Serbest' not in item['FONTURACIKLAMA']]
        # 更新 recordsTotal 和 recordsFiltered
        data['recordsTotal'] = len(data['data'])
        data['recordsFiltered'] = len(data['data'])

        # 使用列表解析来过滤掉含有“Serbest”的项
        data['data'] = [item for item in data['data'] if 'Para' not in item['FONTURACIKLAMA']]
        # 更新 recordsTotal 和 recordsFiltered
        data['recordsTotal'] = len(data['data'])
        data['recordsFiltered'] = len(data['data'])

        # 使用列表解析来过滤掉含有“Serbest”的项
        data['data'] = [item for item in data['data'] if 'Katılım' not in item['FONTURACIKLAMA']]
        # 更新 recordsTotal 和 recordsFiltered
        data['recordsTotal'] = len(data['data'])
        data['recordsFiltered'] = len(data['data'])

        # 使用列表解析来过滤掉含有“Serbest”的项
        data['data'] = [item for item in data['data'] if 'Borçlanma' not in item['FONTURACIKLAMA']]
        # 更新 recordsTotal 和 recordsFiltered
        data['recordsTotal'] = len(data['data'])
        data['recordsFiltered'] = len(data['data'])

        # 使用列表解析来过滤掉含有“Serbest”的项
        data['data'] = [item for item in data['data'] if 'Kira' not in item['FONTURACIKLAMA']]
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

        return data
    except requests.exceptions.HTTPError as http_err:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"HTTP error occurred: {http_err}")
    except requests.exceptions.ConnectionError as conn_err:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Connection error occurred: {conn_err}")
    except requests.exceptions.Timeout as timeout_err:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Timeout error occurred: {timeout_err}")
    except requests.exceptions.RequestException as req_err:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"An error occurred: {req_err}")

class BindHistoryInfo(BaseModel):
    fontip: str = "YAT"
    sfontur: str = ""
    fonkod: str
    fongrup: str = ""
    bastarih: str
    bittarih: str
    fonturkod: str = ""
    fonunvantip: str = ""

@router.get("/tefas/BindHistoryInfo/{fonkod}", tags=["Tefas"])
async def bind_history_info(
    fonkod: str = Path(..., description="Fund code"),
    bastarih: str = Query(None, description="Start date in format DD.MM.YYYY"),
    bittarih: str = Query(None, description="End date in format DD.MM.YYYY")
):
    # Default dates: past month
    if not bastarih:
        bastarih = (datetime.now() - timedelta(days=30)).strftime('%d.%m.%Y')
    if not bittarih:
        bittarih = datetime.now().strftime('%d.%m.%Y')
        
    payload = BindHistoryInfo(
        fonkod=fonkod,
        bastarih=bastarih,
        bittarih=bittarih
    )

    url = 'https://www.tefas.gov.tr/api/DB/BindHistoryInfo'

    try:
        response = requests.post(url, data=payload.dict())
        response.raise_for_status()
        data = response.json()
        return data
    except requests.exceptions.HTTPError as http_err:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"HTTP error occurred: {http_err}")
    except requests.exceptions.ConnectionError as conn_err:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Connection error occurred: {conn_err}")
    except requests.exceptions.Timeout as timeout_err:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Timeout error occurred: {timeout_err}")
    except requests.exceptions.RequestException as req_err:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"An error occurred: {req_err}")


@router.get("/tefas/BindComparisonFundSizes", tags=["Tefas"])
async def bind_comparison_fund_sizes(
    bastarih: str = Query(None, description="Start date in format DD.MM.YYYY"),
    bittarih: str = Query(None, description="End date in format DD.MM.YYYY")
):
    # Default dates: past month
    if not bastarih:
        bastarih = (datetime.now() - timedelta(days=30)).strftime('%d.%m.%Y')
    if not bittarih:
        bittarih = datetime.now().strftime('%d.%m.%Y')
        
    payload = ComparisonFundReturnsRequest(
        bastarih=bastarih,
        bittarih=bittarih
    )

    url = 'https://www.tefas.gov.tr/api/DB/BindComparisonFundSizes'

    try:
        response = requests.post(url, data=payload.dict())
        response.raise_for_status()
        data = response.json()

        # 使用列表解析来过滤掉含有“Serbest”的项
        data['data'] = [item for item in data['data'] if 'Serbest' not in item['FONTURACIKLAMA']]
        # 更新 recordsTotal 和 recordsFiltered
        data['recordsTotal'] = len(data['data'])
        data['recordsFiltered'] = len(data['data'])

        # 使用列表解析来过滤掉含有“Serbest”的项
        data['data'] = [item for item in data['data'] if 'Para' not in item['FONTURACIKLAMA']]
        # 更新 recordsTotal 和 recordsFiltered
        data['recordsTotal'] = len(data['data'])
        data['recordsFiltered'] = len(data['data'])

        # 使用列表解析来过滤掉含有“Serbest”的项
        data['data'] = [item for item in data['data'] if 'Katılım' not in item['FONTURACIKLAMA']]
        # 更新 recordsTotal 和 recordsFiltered
        data['recordsTotal'] = len(data['data'])
        data['recordsFiltered'] = len(data['data'])

        # 使用列表解析来过滤掉含有“Serbest”的项
        data['data'] = [item for item in data['data'] if 'Borçlanma' not in item['FONTURACIKLAMA']]
        # 更新 recordsTotal 和 recordsFiltered
        data['recordsTotal'] = len(data['data'])
        data['recordsFiltered'] = len(data['data'])

        # 使用列表解析来过滤掉含有“Serbest”的项
        data['data'] = [item for item in data['data'] if 'Kira' not in item['FONTURACIKLAMA']]
        # 更新 recordsTotal 和 recordsFiltered
        data['recordsTotal'] = len(data['data'])
        data['recordsFiltered'] = len(data['data'])

        # 处理 GETIRIORANI 为 None 的情况，将 None 替换为一个最小的值（如负无穷）
        for item in data['data']:
            if item['SONPORTFOYDEGERI'] is None:
                item['SONPORTFOYDEGERI'] = -1e10

        # 按照 GETIRIORANI 从大到小排序
        sorted_data = sorted(data['data'], key=lambda x: x['SONPORTFOYDEGERI'], reverse=True)

        # 更新原数据
        data['data'] = sorted_data

        return data
    except requests.exceptions.HTTPError as http_err:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"HTTP error occurred: {http_err}")
    except requests.exceptions.ConnectionError as conn_err:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Connection error occurred: {conn_err}")
    except requests.exceptions.Timeout as timeout_err:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Timeout error occurred: {timeout_err}")
    except requests.exceptions.RequestException as req_err:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"An error occurred: {req_err}")

@router.get("/tefas/BindComparisonManagementFees", tags=["Tefas"])
async def bind_comparison_management_fees(
):
        
    payload = {
        "fontip": "YAT",
        "sfontur": "",
        "kurucukod": "",
        "fongrup": "",
        "fonturkod": "",
        "fonunvantip": "",
        "islemdurum": "1"
    }

    url = 'https://www.tefas.gov.tr/api/DB/BindComparisonManagementFees'

    try:
        response = requests.post(url, data=payload)
        response.raise_for_status()
        data = response.json()

        # 使用列表解析来过滤掉含有“Serbest”的项
        data['data'] = [item for item in data['data'] if 'Serbest' not in item['FONTURACIKLAMA']]
        # 更新 recordsTotal 和 recordsFiltered
        data['recordsTotal'] = len(data['data'])
        data['recordsFiltered'] = len(data['data'])

        # 使用列表解析来过滤掉含有“Serbest”的项
        data['data'] = [item for item in data['data'] if 'Para' not in item['FONTURACIKLAMA']]
        # 更新 recordsTotal 和 recordsFiltered
        data['recordsTotal'] = len(data['data'])
        data['recordsFiltered'] = len(data['data'])

        # 使用列表解析来过滤掉含有“Serbest”的项
        data['data'] = [item for item in data['data'] if 'Katılım' not in item['FONTURACIKLAMA']]
        # 更新 recordsTotal 和 recordsFiltered
        data['recordsTotal'] = len(data['data'])
        data['recordsFiltered'] = len(data['data'])

        # 使用列表解析来过滤掉含有“Serbest”的项
        data['data'] = [item for item in data['data'] if 'Borçlanma' not in item['FONTURACIKLAMA']]
        # 更新 recordsTotal 和 recordsFiltered
        data['recordsTotal'] = len(data['data'])
        data['recordsFiltered'] = len(data['data'])

        # 使用列表解析来过滤掉含有“Serbest”的项
        data['data'] = [item for item in data['data'] if 'Kira' not in item['FONTURACIKLAMA']]
        # 更新 recordsTotal 和 recordsFiltered
        data['recordsTotal'] = len(data['data'])
        data['recordsFiltered'] = len(data['data'])

        return data
    except requests.exceptions.HTTPError as http_err:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"HTTP error occurred: {http_err}")
    except requests.exceptions.ConnectionError as conn_err:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Connection error occurred: {conn_err}")
    except requests.exceptions.Timeout as timeout_err:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Timeout error occurred: {timeout_err}")
    except requests.exceptions.RequestException as req_err:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"An error occurred: {req_err}")


@router.get("/tefas/ParaGirisi", tags=["Tefas"])
async def bind_comparison_fund_sizes(
    bastarih: str = Query(None, description="Start date in format DD.MM.YYYY"),
    bittarih: str = Query(None, description="End date in format DD.MM.YYYY")
):
    # Default dates: past month
    if not bastarih:
        bastarih = (datetime.now() - timedelta(days=30)).strftime('%d.%m.%Y')
    if not bittarih:
        bittarih = datetime.now().strftime('%d.%m.%Y')
        
    payload = ComparisonFundReturnsRequest(
        bastarih=bastarih,
        bittarih=bittarih
    )

    url = 'https://www.tefas.gov.tr/api/DB/BindComparisonFundSizes'

    try:
        response = requests.post(url, data=payload.dict())
        response.raise_for_status()
        data = response.json()

        # 使用列表解析来过滤掉含有“Serbest”的项
        data['data'] = [item for item in data['data'] if 'Serbest' not in item['FONTURACIKLAMA']]
        # 更新 recordsTotal 和 recordsFiltered
        data['recordsTotal'] = len(data['data'])
        data['recordsFiltered'] = len(data['data'])

        # 计算并添加新字段
        total_delta = 0
        for item in data['data']:
            item['PORTFOYDEGERIDELTA'] = round(item['SONPORTFOYDEGERI'] - item['ILKPORTFOYDEGERI'],2)
            total_delta += item['PORTFOYDEGERIDELTA']

        # 将总和添加到原始数据中
        data['TOTALPORTFOYDEGERIDELTA'] = round(total_delta,2)

        # 处理 GETIRIORANI 为 None 的情况，将 None 替换为一个最小的值（如负无穷）
        for item in data['data']:
            if item['PORTFOYDEGERIDELTA'] is None:
                item['PORTFOYDEGERIDELTA'] = -1e10

        # 按照 GETIRIORANI 从大到小排序
        sorted_data = sorted(data['data'], key=lambda x: x['PORTFOYDEGERIDELTA'], reverse=True)

        # 更新原数据
        data['data'] = sorted_data

        # 获取前20条数据，中的data['FONTURACIKLAMA']
        data_frist_20 = data['data'][:30]

        # print(data_frist_20)

        # Get all FONTURACIKLAMA values
        fonturaciklama_list = [item['FONTURACIKLAMA'] for item in data_frist_20]

        # Count the occurrences of each value
        fonturaciklama_counts = Counter(fonturaciklama_list)

        # Get the most common value
        most_common_fonturaciklama = fonturaciklama_counts.most_common(1)[0]

        print(f"En Fazla Para Girisi olan: {most_common_fonturaciklama[0]}, Count: {most_common_fonturaciklama[1]}")



        return data_frist_20
    except requests.exceptions.HTTPError as http_err:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"HTTP error occurred: {http_err}")
    except requests.exceptions.ConnectionError as conn_err:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Connection error occurred: {conn_err}")
    except requests.exceptions.Timeout as timeout_err:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Timeout error occurred: {timeout_err}")
    except requests.exceptions.RequestException as req_err:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"An error occurred: {req_err}")

@router.get("/tefas/ParaGirisi_V2", tags=["Tefas"])
async def bind_comparison_fund_sizes(
    bastarih: str = Query(None, description="Start date in format DD.MM.YYYY"),
    bittarih: str = Query(None, description="End date in format DD.MM.YYYY")
):
    # Default dates: past month
    if not bastarih:
        bastarih = (datetime.now() - timedelta(days=30)).strftime('%d.%m.%Y')
    if not bittarih:
        bittarih = datetime.now().strftime('%d.%m.%Y')
        
    payload = ComparisonFundReturnsRequest(
        bastarih=bastarih,
        bittarih=bittarih
    )

    url = 'https://www.tefas.gov.tr/api/DB/BindComparisonFundSizes'

    try:
        response = requests.post(url, data=payload.dict())
        response.raise_for_status()
        data = response.json()

        # 使用列表解析来过滤掉含有“Serbest”的项
        data['data'] = [item for item in data['data'] if 'Serbest' not in item['FONTURACIKLAMA']]
        # 更新 recordsTotal 和 recordsFiltered
        data['recordsTotal'] = len(data['data'])
        data['recordsFiltered'] = len(data['data'])

        # 使用列表解析来过滤掉含有“Serbest”的项
        data['data'] = [item for item in data['data'] if 'Para' not in item['FONTURACIKLAMA']]
        # 更新 recordsTotal 和 recordsFiltered
        data['recordsTotal'] = len(data['data'])
        data['recordsFiltered'] = len(data['data'])

        # 使用列表解析来过滤掉含有“Serbest”的项
        data['data'] = [item for item in data['data'] if 'Katılım' not in item['FONTURACIKLAMA']]
        # 更新 recordsTotal 和 recordsFiltered
        data['recordsTotal'] = len(data['data'])
        data['recordsFiltered'] = len(data['data'])

        # 使用列表解析来过滤掉含有“Serbest”的项
        data['data'] = [item for item in data['data'] if 'Borçlanma' not in item['FONTURACIKLAMA']]
        # 更新 recordsTotal 和 recordsFiltered
        data['recordsTotal'] = len(data['data'])
        data['recordsFiltered'] = len(data['data'])

        # 使用列表解析来过滤掉含有“Serbest”的项
        data['data'] = [item for item in data['data'] if 'Kira' not in item['FONTURACIKLAMA']]
        # 更新 recordsTotal 和 recordsFiltered
        data['recordsTotal'] = len(data['data'])
        data['recordsFiltered'] = len(data['data'])

        # 计算并添加新字段
        total_delta = 0
        for item in data['data']:
            item['PORTFOYDEGERIDELTA'] = round(item['SONPORTFOYDEGERI'] - item['ILKPORTFOYDEGERI'],2)
            total_delta += item['PORTFOYDEGERIDELTA']

        # 将总和添加到原始数据中
        data['TOTALPORTFOYDEGERIDELTA'] = round(total_delta,2)

        # 处理 GETIRIORANI 为 None 的情况，将 None 替换为一个最小的值（如负无穷）
        for item in data['data']:
            if item['PORTFOYDEGERIDELTA'] is None:
                item['PORTFOYDEGERIDELTA'] = -1e10

        # 按照 GETIRIORANI 从大到小排序
        sorted_data = sorted(data['data'], key=lambda x: x['PORTFOYDEGERIDELTA'], reverse=True)

        # 更新原数据
        data['data'] = sorted_data

        # 获取前20条数据，中的data['FONTURACIKLAMA']
        data_frist_20 = data['data'][:30]

        # print(data_frist_20)

        # Get all FONTURACIKLAMA values
        fonturaciklama_list = [item['FONTURACIKLAMA'] for item in data_frist_20]

        # Count the occurrences of each value
        fonturaciklama_counts = Counter(fonturaciklama_list)

        # Get the most common value
        most_common_fonturaciklama = fonturaciklama_counts.most_common(1)[0]

        print(f"En Fazla Para Girisi olan: {most_common_fonturaciklama[0]}, Count: {most_common_fonturaciklama[1]}")



        return data_frist_20
    except requests.exceptions.HTTPError as http_err:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"HTTP error occurred: {http_err}")
    except requests.exceptions.ConnectionError as conn_err:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Connection error occurred: {conn_err}")
    except requests.exceptions.Timeout as timeout_err:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Timeout error occurred: {timeout_err}")
    except requests.exceptions.RequestException as req_err:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"An error occurred: {req_err}")


@router.get("/tefas/ParaGirisi_V2_hafta", tags=["Tefas"])
async def bind_comparison_fund_sizes(
):
    # Default dates: past month
    if not bastarih:
        bastarih = (datetime.now() - timedelta(days=7)).strftime('%d.%m.%Y')
    if not bittarih:
        bittarih = datetime.now().strftime('%d.%m.%Y')
        
    payload = ComparisonFundReturnsRequest(
        bastarih=bastarih,
        bittarih=bittarih
    )

    url = 'https://www.tefas.gov.tr/api/DB/BindComparisonFundSizes'

    try:
        response = requests.post(url, data=payload.dict())
        response.raise_for_status()
        data = response.json()

        # 使用列表解析来过滤掉含有“Serbest”的项
        data['data'] = [item for item in data['data'] if 'Serbest' not in item['FONTURACIKLAMA']]
        # 更新 recordsTotal 和 recordsFiltered
        data['recordsTotal'] = len(data['data'])
        data['recordsFiltered'] = len(data['data'])

        # 使用列表解析来过滤掉含有“Serbest”的项
        data['data'] = [item for item in data['data'] if 'Para' not in item['FONTURACIKLAMA']]
        # 更新 recordsTotal 和 recordsFiltered
        data['recordsTotal'] = len(data['data'])
        data['recordsFiltered'] = len(data['data'])

        # 使用列表解析来过滤掉含有“Serbest”的项
        data['data'] = [item for item in data['data'] if 'Katılım' not in item['FONTURACIKLAMA']]
        # 更新 recordsTotal 和 recordsFiltered
        data['recordsTotal'] = len(data['data'])
        data['recordsFiltered'] = len(data['data'])

        # 使用列表解析来过滤掉含有“Serbest”的项
        data['data'] = [item for item in data['data'] if 'Borçlanma' not in item['FONTURACIKLAMA']]
        # 更新 recordsTotal 和 recordsFiltered
        data['recordsTotal'] = len(data['data'])
        data['recordsFiltered'] = len(data['data'])

        # 使用列表解析来过滤掉含有“Serbest”的项
        data['data'] = [item for item in data['data'] if 'Kira' not in item['FONTURACIKLAMA']]
        # 更新 recordsTotal 和 recordsFiltered
        data['recordsTotal'] = len(data['data'])
        data['recordsFiltered'] = len(data['data'])

        # 计算并添加新字段
        total_delta = 0
        for item in data['data']:
            item['PORTFOYDEGERIDELTA'] = round(item['SONPORTFOYDEGERI'] - item['ILKPORTFOYDEGERI'],2)
            total_delta += item['PORTFOYDEGERIDELTA']

        # 将总和添加到原始数据中
        data['TOTALPORTFOYDEGERIDELTA'] = round(total_delta,2)

        # 处理 GETIRIORANI 为 None 的情况，将 None 替换为一个最小的值（如负无穷）
        for item in data['data']:
            if item['PORTFOYDEGERIDELTA'] is None:
                item['PORTFOYDEGERIDELTA'] = -1e10

        # 按照 GETIRIORANI 从大到小排序
        sorted_data = sorted(data['data'], key=lambda x: x['PORTFOYDEGERIDELTA'], reverse=True)

        # 更新原数据
        data['data'] = sorted_data

        # 获取前20条数据，中的data['FONTURACIKLAMA']
        data_frist_20 = data['data'][:30]

        # print(data_frist_20)

        # Get all FONTURACIKLAMA values
        fonturaciklama_list = [item['FONTURACIKLAMA'] for item in data_frist_20]

        # Count the occurrences of each value
        fonturaciklama_counts = Counter(fonturaciklama_list)

        # Get the most common value
        most_common_fonturaciklama = fonturaciklama_counts.most_common(1)[0]

        print(f"En Fazla Para Girisi olan: {most_common_fonturaciklama[0]}, Count: {most_common_fonturaciklama[1]}")



        return data_frist_20
    except requests.exceptions.HTTPError as http_err:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"HTTP error occurred: {http_err}")
    except requests.exceptions.ConnectionError as conn_err:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Connection error occurred: {conn_err}")
    except requests.exceptions.Timeout as timeout_err:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Timeout error occurred: {timeout_err}")
    except requests.exceptions.RequestException as req_err:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"An error occurred: {req_err}")



@router.get("/tefas/ParaCikisi", tags=["Tefas"])
async def bind_comparison_fund_sizes(
    bastarih: str = Query(None, description="Start date in format DD.MM.YYYY"),
    bittarih: str = Query(None, description="End date in format DD.MM.YYYY")
):
    # Default dates: past month
    if not bastarih:
        bastarih = (datetime.now() - timedelta(days=30)).strftime('%d.%m.%Y')
    if not bittarih:
        bittarih = datetime.now().strftime('%d.%m.%Y')
        
    payload = ComparisonFundReturnsRequest(
        bastarih=bastarih,
        bittarih=bittarih
    )

    url = 'https://www.tefas.gov.tr/api/DB/BindComparisonFundSizes'

    try:
        response = requests.post(url, data=payload.dict())
        response.raise_for_status()
        data = response.json()

        # 使用列表解析来过滤掉含有“Serbest”的项
        data['data'] = [item for item in data['data'] if 'Serbest' not in item['FONTURACIKLAMA']]
        # 更新 recordsTotal 和 recordsFiltered
        data['recordsTotal'] = len(data['data'])
        data['recordsFiltered'] = len(data['data'])

        # 计算并添加新字段
        total_delta = 0
        for item in data['data']:
            item['PORTFOYDEGERIDELTA'] = round(item['SONPORTFOYDEGERI'] - item['ILKPORTFOYDEGERI'],2)
            total_delta += item['PORTFOYDEGERIDELTA']

        # 将总和添加到原始数据中
        data['TOTALPORTFOYDEGERIDELTA'] = round(total_delta,2)

        # 处理 GETIRIORANI 为 None 的情况，将 None 替换为一个最小的值（如负无穷）
        for item in data['data']:
            if item['PORTFOYDEGERIDELTA'] is None:
                item['PORTFOYDEGERIDELTA'] = -1e10

        # 按照 GETIRIORANI 从大到小排序
        sorted_data = sorted(data['data'], key=lambda x: x['PORTFOYDEGERIDELTA'])

        # 更新原数据
        data['data'] = sorted_data

        # 获取前20条数据，中的data['FONTURACIKLAMA']
        data_frist_20 = data['data'][:30]

        # print(data_frist_20)

        # Get all FONTURACIKLAMA values
        fonturaciklama_list = [item['FONTURACIKLAMA'] for item in data_frist_20]

        # Count the occurrences of each value
        fonturaciklama_counts = Counter(fonturaciklama_list)

        # Get the most common value
        most_common_fonturaciklama = fonturaciklama_counts.most_common(1)[0]

        print(f"En Fazla Para Cikisi olan: {most_common_fonturaciklama[0]}, Count: {most_common_fonturaciklama[1]}")



        return data_frist_20
    except requests.exceptions.HTTPError as http_err:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"HTTP error occurred: {http_err}")
    except requests.exceptions.ConnectionError as conn_err:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Connection error occurred: {conn_err}")
    except requests.exceptions.Timeout as timeout_err:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Timeout error occurred: {timeout_err}")
    except requests.exceptions.RequestException as req_err:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"An error occurred: {req_err}")
    

@router.get("/tefas/ParaCikisi_V2", tags=["Tefas"])
async def bind_comparison_fund_sizes(
    bastarih: str = Query(None, description="Start date in format DD.MM.YYYY"),
    bittarih: str = Query(None, description="End date in format DD.MM.YYYY")
):
    # Default dates: past month
    if not bastarih:
        bastarih = (datetime.now() - timedelta(days=30)).strftime('%d.%m.%Y')
    if not bittarih:
        bittarih = datetime.now().strftime('%d.%m.%Y')
        
    payload = ComparisonFundReturnsRequest(
        bastarih=bastarih,
        bittarih=bittarih
    )

    url = 'https://www.tefas.gov.tr/api/DB/BindComparisonFundSizes'

    try:
        response = requests.post(url, data=payload.dict())
        response.raise_for_status()
        data = response.json()

        # 使用列表解析来过滤掉含有“Serbest”的项
        data['data'] = [item for item in data['data'] if 'Serbest' not in item['FONTURACIKLAMA']]
        # 更新 recordsTotal 和 recordsFiltered
        data['recordsTotal'] = len(data['data'])
        data['recordsFiltered'] = len(data['data'])

        # 使用列表解析来过滤掉含有“Serbest”的项
        data['data'] = [item for item in data['data'] if 'Para' not in item['FONTURACIKLAMA']]
        # 更新 recordsTotal 和 recordsFiltered
        data['recordsTotal'] = len(data['data'])
        data['recordsFiltered'] = len(data['data'])

        # 使用列表解析来过滤掉含有“Serbest”的项
        data['data'] = [item for item in data['data'] if 'Katılım' not in item['FONTURACIKLAMA']]
        # 更新 recordsTotal 和 recordsFiltered
        data['recordsTotal'] = len(data['data'])
        data['recordsFiltered'] = len(data['data'])

        # 使用列表解析来过滤掉含有“Serbest”的项
        data['data'] = [item for item in data['data'] if 'Borçlanma' not in item['FONTURACIKLAMA']]
        # 更新 recordsTotal 和 recordsFiltered
        data['recordsTotal'] = len(data['data'])
        data['recordsFiltered'] = len(data['data'])

        # 使用列表解析来过滤掉含有“Serbest”的项
        data['data'] = [item for item in data['data'] if 'Kira' not in item['FONTURACIKLAMA']]
        # 更新 recordsTotal 和 recordsFiltered
        data['recordsTotal'] = len(data['data'])
        data['recordsFiltered'] = len(data['data'])

        # 计算并添加新字段
        total_delta = 0
        for item in data['data']:
            item['PORTFOYDEGERIDELTA'] = round(item['SONPORTFOYDEGERI'] - item['ILKPORTFOYDEGERI'],2)
            total_delta += item['PORTFOYDEGERIDELTA']

        # 将总和添加到原始数据中
        data['TOTALPORTFOYDEGERIDELTA'] = round(total_delta,2)

        # 处理 GETIRIORANI 为 None 的情况，将 None 替换为一个最小的值（如负无穷）
        for item in data['data']:
            if item['PORTFOYDEGERIDELTA'] is None:
                item['PORTFOYDEGERIDELTA'] = -1e10

        # 按照 GETIRIORANI 从大到小排序
        sorted_data = sorted(data['data'], key=lambda x: x['PORTFOYDEGERIDELTA'])

        # 更新原数据
        data['data'] = sorted_data

        # 获取前20条数据，中的data['FONTURACIKLAMA']
        data_frist_20 = data['data'][:30]

        # print(data_frist_20)

        # Get all FONTURACIKLAMA values
        fonturaciklama_list = [item['FONTURACIKLAMA'] for item in data_frist_20]

        # Count the occurrences of each value
        fonturaciklama_counts = Counter(fonturaciklama_list)

        # Get the most common value
        most_common_fonturaciklama = fonturaciklama_counts.most_common(1)[0]

        print(f"En Fazla Para Cikisi olan: {most_common_fonturaciklama[0]}, Count: {most_common_fonturaciklama[1]}")



        return data_frist_20
    except requests.exceptions.HTTPError as http_err:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"HTTP error occurred: {http_err}")
    except requests.exceptions.ConnectionError as conn_err:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Connection error occurred: {conn_err}")
    except requests.exceptions.Timeout as timeout_err:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Timeout error occurred: {timeout_err}")
    except requests.exceptions.RequestException as req_err:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"An error occurred: {req_err}")
    

@router.get("/tefas/ParaCikisi_V2_hafta", tags=["Tefas"])
async def bind_comparison_fund_sizes(
):
    # Default dates: past month
    if not bastarih:
        bastarih = (datetime.now() - timedelta(days=7)).strftime('%d.%m.%Y')
    if not bittarih:
        bittarih = datetime.now().strftime('%d.%m.%Y')
        
    payload = ComparisonFundReturnsRequest(
        bastarih=bastarih,
        bittarih=bittarih
    )

    url = 'https://www.tefas.gov.tr/api/DB/BindComparisonFundSizes'

    try:
        response = requests.post(url, data=payload.dict())
        response.raise_for_status()
        data = response.json()

        # 使用列表解析来过滤掉含有“Serbest”的项
        data['data'] = [item for item in data['data'] if 'Serbest' not in item['FONTURACIKLAMA']]
        # 更新 recordsTotal 和 recordsFiltered
        data['recordsTotal'] = len(data['data'])
        data['recordsFiltered'] = len(data['data'])

        # 使用列表解析来过滤掉含有“Serbest”的项
        data['data'] = [item for item in data['data'] if 'Para' not in item['FONTURACIKLAMA']]
        # 更新 recordsTotal 和 recordsFiltered
        data['recordsTotal'] = len(data['data'])
        data['recordsFiltered'] = len(data['data'])

        # 使用列表解析来过滤掉含有“Serbest”的项
        data['data'] = [item for item in data['data'] if 'Katılım' not in item['FONTURACIKLAMA']]
        # 更新 recordsTotal 和 recordsFiltered
        data['recordsTotal'] = len(data['data'])
        data['recordsFiltered'] = len(data['data'])

        # 使用列表解析来过滤掉含有“Serbest”的项
        data['data'] = [item for item in data['data'] if 'Borçlanma' not in item['FONTURACIKLAMA']]
        # 更新 recordsTotal 和 recordsFiltered
        data['recordsTotal'] = len(data['data'])
        data['recordsFiltered'] = len(data['data'])

        # 使用列表解析来过滤掉含有“Serbest”的项
        data['data'] = [item for item in data['data'] if 'Kira' not in item['FONTURACIKLAMA']]
        # 更新 recordsTotal 和 recordsFiltered
        data['recordsTotal'] = len(data['data'])
        data['recordsFiltered'] = len(data['data'])

        # 计算并添加新字段
        total_delta = 0
        for item in data['data']:
            item['PORTFOYDEGERIDELTA'] = round(item['SONPORTFOYDEGERI'] - item['ILKPORTFOYDEGERI'],2)
            total_delta += item['PORTFOYDEGERIDELTA']

        # 将总和添加到原始数据中
        data['TOTALPORTFOYDEGERIDELTA'] = round(total_delta,2)

        # 处理 GETIRIORANI 为 None 的情况，将 None 替换为一个最小的值（如负无穷）
        for item in data['data']:
            if item['PORTFOYDEGERIDELTA'] is None:
                item['PORTFOYDEGERIDELTA'] = -1e10

        # 按照 GETIRIORANI 从大到小排序
        sorted_data = sorted(data['data'], key=lambda x: x['PORTFOYDEGERIDELTA'])

        # 更新原数据
        data['data'] = sorted_data

        # 获取前20条数据，中的data['FONTURACIKLAMA']
        data_frist_20 = data['data'][:30]

        # print(data_frist_20)

        # Get all FONTURACIKLAMA values
        fonturaciklama_list = [item['FONTURACIKLAMA'] for item in data_frist_20]

        # Count the occurrences of each value
        fonturaciklama_counts = Counter(fonturaciklama_list)

        # Get the most common value
        most_common_fonturaciklama = fonturaciklama_counts.most_common(1)[0]

        print(f"En Fazla Para Cikisi olan: {most_common_fonturaciklama[0]}, Count: {most_common_fonturaciklama[1]}")



        return data_frist_20
    except requests.exceptions.HTTPError as http_err:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"HTTP error occurred: {http_err}")
    except requests.exceptions.ConnectionError as conn_err:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Connection error occurred: {conn_err}")
    except requests.exceptions.Timeout as timeout_err:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Timeout error occurred: {timeout_err}")
    except requests.exceptions.RequestException as req_err:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"An error occurred: {req_err}")
    



# haftalik, son 150 hafta eger haftada x yatirsam ne kadar olur du?
@router.get("/tefas/Haftada_KODa_500_yatirsam/{fonkod}", tags=["Tefas"])
async def find_returns(
    fonkod: str = Path(..., description="Fund code"),
    hafta_sayisi: int = Query(None, description="Kac hafta olsun?"),
):
    print("Running find_returns")

    today = datetime.today()
    start_of_week = today - timedelta(days=today.weekday())
    end_of_week = start_of_week + timedelta(days=6)

    rate_list = []

    for i in range(hafta_sayisi):
        print(f"Getting data for week {i+1}")
        # For each week, get Monday and Sunday
        monday = start_of_week - timedelta(weeks=i)
        sunday = end_of_week - timedelta(weeks=i)
        
        # Format the dates as DD.MM.YYYY
        monday_formatted = monday.strftime('%d.%m.%Y')
        sunday_formatted = sunday.strftime('%d.%m.%Y')
        print(f"{monday_formatted} : {sunday_formatted}")

        payload = ComparisonFundReturnsRequest(
            bastarih=monday_formatted,
            bittarih=sunday_formatted
        )

        url = 'https://www.tefas.gov.tr/api/DB/BindComparisonFundReturns'


        try:
            response = requests.post(url, data=payload.dict())
            response.raise_for_status()
            data = response.json()

            # 使用列表解析来过滤掉含有“Serbest”的项
            data['data'] = [item for item in data['data'] if 'Serbest' not in item['FONTURACIKLAMA']]
            # 更新 recordsTotal 和 recordsFiltered
            data['recordsTotal'] = len(data['data'])
            data['recordsFiltered'] = len(data['data'])

            for item in data["data"]:
                if item["FONKODU"] == fonkod:
                    rate_list.append(item["GETIRIORANI"])
                    break


        except requests.exceptions.HTTPError as http_err:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"HTTP error occurred: {http_err}")
        except requests.exceptions.ConnectionError as conn_err:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Connection error occurred: {conn_err}")
        except requests.exceptions.Timeout as timeout_err:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Timeout error occurred: {timeout_err}")
        except requests.exceptions.RequestException as req_err:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"An error occurred: {req_err}")

    # 倒序列表
    rate_list.reverse()
    return rate_list



# aylik, son 36 ay eger ayda x yatirsam ne kadar olur du?
@router.get("/tefas/Ayda_KODa_500_yatirsam/{fonkod}", tags=["Tefas"])
async def find_returns(
    fonkod: str = Path(..., description="Fund code"),
    ay_sayisi: int = Query(None, description="Kac ay olsun?"),
):
    print("Running find_returns")

    today = datetime.today()

    rate_list = []

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
        last_day_str = last_day.strftime('%d.%m.%Y')

        payload = ComparisonFundReturnsRequest(
            bastarih= first_day_str,
            bittarih= last_day_str
        )

        url = 'https://www.tefas.gov.tr/api/DB/BindComparisonFundReturns'

        try:
            response = requests.post(url, data=payload.dict())
            response.raise_for_status()
            data = response.json()

            # 使用列表解析来过滤掉含有“Serbest”的项
            data['data'] = [item for item in data['data'] if 'Serbest' not in item['FONTURACIKLAMA']]
            # 更新 recordsTotal 和 recordsFiltered
            data['recordsTotal'] = len(data['data'])
            data['recordsFiltered'] = len(data['data'])

            for item in data["data"]:
                if item["FONKODU"] == fonkod:
                    rate_list.append(item["GETIRIORANI"])
                    break

        except requests.exceptions.HTTPError as http_err:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"HTTP error occurred: {http_err}")
        except requests.exceptions.ConnectionError as conn_err:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Connection error occurred: {conn_err}")
        except requests.exceptions.Timeout as timeout_err:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Timeout error occurred: {timeout_err}")
        except requests.exceptions.RequestException as req_err:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"An error occurred: {req_err}")

        

    # 倒序列表
    rate_list.reverse()
    return rate_list



@router.get("/tefas/tum_hisse_senedi_fonlari_getirisi_v2", tags=["Tefas"])
async def find_returns(
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

    # fon_list = ["IIH","MAC","YAS"]

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
        last_day_str = last_day.strftime('%d.%m.%Y')

        payload = ComparisonFundReturnsRequest(
            bastarih= first_day_str,
            bittarih= last_day_str
        )

        url = 'https://www.tefas.gov.tr/api/DB/BindComparisonFundReturns'

        try:
            response = requests.post(url, data=payload.dict())
            response.raise_for_status()
            data = response.json()

            dic_A[i+1] = data


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
            for item in value['data']:
                if item['FONKODU'] == fon:
                    list_b.append(item['GETIRIORANI'])

        data_B[fon] = list_b


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
    return sorted_data

# fon adet degisimi
@router.get("/tefas/FonAdetDegisimi/{fonkod}", tags=["Tefas"])
async def fon_adet_degisimi(
    fonkod: str = Path(..., description="Fund code"),
    gun : int = Query(None, description="Day"),
):
    print("Running fon_adet_degisimi")
    start_date = datetime.now()
    end_date = start_date - timedelta(days=gun)

    url = 'https://www.tefas.gov.tr/api/DB/BindHistoryInfo'

    FIYAT_LIST = []
    TEDPAYSAYISI_LIST = []
    KISISAYISI_LIST = []
    PORTFOYBUYUKLUK_LIST = []

    current_date = start_date
    while current_date > end_date:
        # 输出日期格式为 DD.MM.YYYY
        # print(current_date.strftime("%d.%m.%Y"))
        tarih = current_date.strftime("%d.%m.%Y")

        payload = BindHistoryInfo(
            fonkod=fonkod,
            bastarih=tarih,
            bittarih=tarih
        )

        try:
            response = requests.post(url, data=payload.dict())
            response.raise_for_status()
            data = response.json()

            # print(f"data: {data}")
            if data["recordsTotal"] == 0:
                pass

            else:
                FIYAT_LIST.append(data["data"][0]["FIYAT"])
                TEDPAYSAYISI_LIST.append(data["data"][0]["TEDPAYSAYISI"])
                KISISAYISI_LIST.append(data["data"][0]["KISISAYISI"])
                PORTFOYBUYUKLUK_LIST.append(data["data"][0]["PORTFOYBUYUKLUK"])
                


        except requests.exceptions.HTTPError as http_err:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"HTTP error occurred: {http_err}")
        except requests.exceptions.ConnectionError as conn_err:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Connection error occurred: {conn_err}")
        except requests.exceptions.Timeout as timeout_err:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Timeout error occurred: {timeout_err}")
        except requests.exceptions.RequestException as req_err:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"An error occurred: {req_err}")

        current_date -= timedelta(days=1)

    
    # 倒序列表
    TEDPAYSAYISI_LIST.reverse()
    KISISAYISI_LIST.reverse()
    PORTFOYBUYUKLUK_LIST.reverse()
    FIYAT_LIST.reverse()
    
    return FIYAT_LIST, TEDPAYSAYISI_LIST, KISISAYISI_LIST, PORTFOYBUYUKLUK_LIST

# return fons history price as long as possible and save to database, get USDTRY price

app.include_router(router)
