import re
from bson import ObjectId
from pydantic import BaseModel, Field, field_validator
from datetime import datetime
from typing import List
from .database import mongodb


class AccountCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100, description="Account holder's name")
    currency: str = Field(..., description="The currency code for the account, e.g., USD, EUR")
    balance: float
    type: int # check app/account_type.png
    create_date: datetime = Field(default_factory=datetime.utcnow, description="The date the account was created")
    last_update_date: datetime = Field(default_factory=datetime.utcnow, description="The date the account was last updated")

class AccountResponseModel(BaseModel):
    id: str
    name: str
    currency: str
    balance: float
    type: int
    create_date: datetime
    last_update_date: datetime

    @classmethod
    def from_mongo(cls, mongo_data: dict) -> "AccountResponseModel":
        id_str = str(mongo_data.pop("_id"))
        return cls(id=id_str, **mongo_data)
    

class GetAccountsResponseModel(BaseModel):
    accounts: List[AccountResponseModel]


class ResponseModel(BaseModel):
    success: bool
    message: str

# Transaction
class TransactionCreate(BaseModel):
    serialNumber: int | None = None
    account_id_High: str 
    amount_High: float
    rate: float
    amount_Low: float
    account_id_Low: str
    description: str | None = None
    create_date: datetime = Field(default_factory=datetime.utcnow)
    last_update_date: datetime = Field(default_factory=datetime.utcnow)

    @classmethod
    async def _generate_serial_number(cls) -> int:
        counter = await mongodb.counters_collection.find_one_and_update(
            {"_id": "transaction_serial"},
            {"$inc": {"sequence_value": 1}},
            upsert=True,
            return_document=True
        )
        return counter["sequence_value"]    
    
class TransactionResponseModel(BaseModel):
    serialNumber: int
    account_id_High: str 
    amount_High: float | int
    rate: float | int
    amount_Low: float | int
    account_id_Low: str
    description: str | None
    create_date: datetime
    last_update_date: datetime

class TransactionsResponseModel(BaseModel):
    transactions: List[TransactionResponseModel]
