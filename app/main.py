from fastapi import APIRouter, FastAPI, Depends, HTTPException, Path, Body, Query

from .models import AccountCreate, AccountResponseModel, GetAccountsResponseModel, ResponseModel, TransactionCreate, TransactionResponseModel, TransactionsResponseModel
from .database import mongodb
from .auth import get_api_key
from bson import ObjectId

app = FastAPI()
router = APIRouter(prefix="/v1")

# Accounts
@router.post("/accounts/", dependencies=[Depends(get_api_key)], tags=["Accounts"], response_model=AccountResponseModel)
async def create_account(account: AccountCreate):
    result = await mongodb.db["accounts"].insert_one(account.dict())
    created_account = await mongodb.db["accounts"].find_one({"_id": result.inserted_id})
    if not created_account:
        raise HTTPException(status_code=404, detail="Account creation failed")
    return AccountResponseModel.from_mongo(created_account)


@router.get("/accounts/", dependencies=[Depends(get_api_key)], tags=["Accounts"], response_model=GetAccountsResponseModel)
async def get_accounts():
    accounts = []
    async for account in mongodb.db["accounts"].find():
        account['_id'] = str(account['_id'])  # Convert _id to str
        accounts.append(AccountResponseModel.from_mongo(account))
    return GetAccountsResponseModel(accounts=accounts)


@router.get("/accounts/{account_id}", dependencies=[Depends(get_api_key)], tags=["Accounts"], response_model=AccountResponseModel)
async def get_account(account_id: str):
    if not ObjectId.is_valid(account_id):
        raise HTTPException(status_code=400, detail="Invalid ObjectId")
    account = await mongodb.db["accounts"].find_one({"_id": ObjectId(account_id)})
    if account is None:
        raise HTTPException(status_code=404, detail="Account not found")
    return AccountResponseModel.from_mongo(account)


@router.put("/accounts/{account_id}", dependencies=[Depends(get_api_key)], tags=["Accounts"], response_model=AccountResponseModel)
async def update_account(account_id: str, account: AccountCreate):
    if not ObjectId.is_valid(account_id):
        raise HTTPException(status_code=400, detail="Invalid ObjectId")
    result = await mongodb.db["accounts"].update_one({"_id": ObjectId(account_id)}, {"$set": account.dict()})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Account not found")
    updated_account = await mongodb.db["accounts"].find_one({"_id": ObjectId(account_id)})
    if updated_account is None:
        raise HTTPException(status_code=404, detail="Account not found")
    return AccountResponseModel.from_mongo(updated_account)


@router.delete("/accounts/{account_id}", dependencies=[Depends(get_api_key)], tags=["Accounts"], response_model=ResponseModel)
async def delete_account(account_id: str):
    if not ObjectId.is_valid(account_id):
        raise HTTPException(status_code=400, detail="Invalid ObjectId")
    result = await mongodb.db["accounts"].delete_one({"_id": ObjectId(account_id)})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Account not found")
    return ResponseModel(success=True, message="Account deleted")


# Transactions

@router.post("/transactions/", dependencies=[Depends(get_api_key)], tags=["Transactions"], response_model=TransactionResponseModel)
async def create_transaction(transaction: TransactionCreate):
    transaction.serialNumber = await TransactionCreate._generate_serial_number()
    result = await mongodb.db["transactions"].insert_one(transaction.dict())
    if not result.inserted_id:
        raise HTTPException(status_code=500, detail="Transaction creation failed")
        
    # Retrieve the created transaction from the database
    created_transaction = await mongodb.db["transactions"].find_one({"_id": result.inserted_id})
    if not created_transaction:
        raise HTTPException(status_code=404, detail="Failed to retrieve created transaction")

    return TransactionResponseModel(**created_transaction)


@router.get("/transactions/", dependencies=[Depends(get_api_key)], tags=["Transactions"], response_model=TransactionsResponseModel)
async def get_transactions():
    transactions = await mongodb.db["transactions"].find().to_list(length=None)
    if not transactions:
        raise HTTPException(status_code=404, detail="No transactions found")

    # Convert _id to str and create TransactionResponseModel instances
    transactions_response = [TransactionResponseModel(**{**transaction, '_id': str(transaction['_id'])}) for transaction in transactions]

    return TransactionsResponseModel(transactions=transactions_response)


@router.get("/transactions/{serial_number}", dependencies=[Depends(get_api_key)], tags=["Transactions"], response_model=TransactionResponseModel)
async def get_transaction(serial_number: int):
    
    transaction = await mongodb.db["transactions"].find_one({"serialNumber": serial_number})
    if transaction is None:
        raise HTTPException(status_code=404, detail="Transaction not found")
    return TransactionResponseModel(**transaction)


@router.delete("/transactions/{serial_number}", dependencies=[Depends(get_api_key)], tags=["Transactions"], response_model=ResponseModel)
async def delete_transaction(serial_number: int):
    result = await mongodb.db["transactions"].delete_one({"serialNumber": serial_number})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Transaction not found")
    return ResponseModel(success=True, message="Transaction deleted")


app.include_router(router)