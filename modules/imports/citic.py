import calendar
import csv
import re
from zipfile import ZipFile
from datetime import datetime,date
from io import StringIO, BytesIO

import dateparser
from beancount.core import data
from beancount.core.data import Note, Transaction

from . import (DictReaderStrip, get_account_by_guess,
               get_income_account_by_guess)
from .base import Base
from .deduplicate import Deduplicate
import logging
import pandas as pd
from io import StringIO
from tqdm import tqdm

Account中信 = 'Assets:Bank:CITIC:5999'

account_map = {
    # "招商":"Assets:Bank:CMB:3007"
}

account_map_res = dict([(key, re.compile(key)) for key in account_map])

def get_account_by_map(description):
    if description != '':
        for key, value in account_map.items():
            if account_map_res[key].findall(description):
                return value
    
    return Account中信

# 需要跳过的交易

# 对于支付宝等线上交易，通过支付宝，微信拉取交易信息
skip_transaction_map = [
    "(财付通)",  #微信支付
]

skip_transaction_res = [re.compile(key) for key in skip_transaction_map]


def skip_transaction(amount_type):
    if amount_type != '':
        for value in skip_transaction_res:
            if value.findall(amount_type):
                return True
    
    return False

class CITICC(Base):

    def __init__(self, filename, byte_content, entries, option_map):
        if not re.search(r'中信.*\.xls$', filename.name):
            raise Exception("not 中信 ,skip")

        xls_buffer = BytesIO(byte_content)
        # 使用 pandas 读取 XLS 数据
        xls_df = pd.read_excel(xls_buffer)
        # 创建一个 StringIO 对象来保存 CSV 数据
        csv_buffer = StringIO()
        # 使用 pandas 将内存中的 XLS 数据转换为 CSV 数据并保存在 csv_buffer 中
        xls_df.to_csv(csv_buffer, index=False)
        # 获取 CSV 数据字符串
        content = csv_buffer.getvalue()
        lines = content.split("\n")

        # 去除注释行，无效行
        start_lines = 0
        end_lines = 0
        for idx,line in enumerate(lines):
            if line.startswith("交易"):
                start_lines = idx
            
            if (line != ''):
                end_lines = idx
            

        content = "\n".join(lines[start_lines:end_lines+1])
        self.content = content
        self.line_num = end_lines - start_lines
        self.filename = filename.name

        # 去重复
        self.deduplicate = Deduplicate(entries, option_map)

    def parse(self):
        content = self.content
        f = StringIO(content)
        reader = DictReaderStrip(f, delimiter=',')
        # 交易日期   ,收入金额,支出金额 ,账户余额    ,对方名称,对方账号         ,受理机构,摘要                            ,交易流水号                          ,交易卡号,状态
        # 2024-01-05,__      ,10.00   ,"46,813.85",        ,2433********0133,       ,财付通快捷支付-重庆高科集团有限公司,WL142024010521795329851802110111306,--     ,完成
        
        with tqdm(total=self.line_num) as pbar:
            pbar.set_description(f'{self.filename}')
            transactions = []
            for row in reader:

                amount_note = row['摘要']
                # 跳过数据
                if skip_transaction(amount_note):
                    pbar.update(1)
                    continue

                # 准备元数据
                amount_datetime = datetime.strptime(f"{row['交易日期']}","%Y-%m-%d %H:%M:%S")

                meta = {}
                meta['trade_time'] = str(amount_datetime)
                meta['timestamp'] = str(amount_datetime.timestamp()).replace('.0', '')

                meta['shop_trade_no'] = row['交易流水号'] 
                # meta['alipay_trade_no'] #无

            
                description = f"{row['对方名称']},{row['受理机构']},{amount_note}"
                meta['note'] = description

                meta = data.new_metadata(
                    'beancount/core/testing.beancount',
                    12345,
                    meta
                )
                
                # 构造交易
                entry = Transaction(
                        meta,
                        date(amount_datetime.year, amount_datetime.month, amount_datetime.day),
                        "*",
                        "", #无交易对方
                        description,
                        data.EMPTY_SET,
                        data.EMPTY_SET, []
                    )

                # 银行账户，支出/收入都会是银行的账户
                account2 = Account中信

                amount_out  = True if row["收入金额"] in ["__","--"] else False
                price = row['支出金额'] if amount_out else row['收入金额']
                #支出
                if amount_out:
                    # 靠支付宝获取其他信息
                    account = get_account_by_guess('', description, amount_datetime)
                    if account == "Expenses:Unknown":
                        entry = entry._replace(flag='!')

                    # 支出，金额写到Expenses账户
                    data.create_simple_posting(entry, account2, f"-{price}",'CNY')
                    data.create_simple_posting(entry, account, price, 'CNY')

                #收入
                else:
                    income = get_income_account_by_guess('', description, amount_datetime)
                    if income == 'Income:Unknown':
                        entry = entry._replace(flag='!')

                    # 收入，金额写到收入账户
                    data.create_simple_posting(entry, income, f"-{price}", 'CNY')
                    data.create_simple_posting(entry, account2, price,'CNY')

                #去重
                amount = float(price)
                if not self.deduplicate.find_duplicate(entry, amount):
                    transactions.append(entry)

                pbar.update(1)
        # self.deduplicate.apply_beans()
        return transactions
