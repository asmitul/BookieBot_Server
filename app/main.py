from datetime import datetime, timedelta
from fastapi import APIRouter, FastAPI, Depends, HTTPException, Path, Query, status
from pydantic import BaseModel

from .models import AccountCreate, AccountResponseModel, GetAccountsResponseModel, ResponseModel, TransactionCreate, TransactionResponseModel, TransactionsResponseModel
from .database import mongodb
from .auth import get_api_key
from bson import ObjectId
import requests

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


app.include_router(router)
