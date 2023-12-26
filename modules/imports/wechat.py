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
from tqdm import tqdm

Account_WeChat = 'Assets:MobilePayment:WeChat'

account_map = {
    "招商银行\(3007\)":"Assets:Bank:CMB:3007"
}

account_map_res = dict([(key, re.compile(key)) for key in account_map])

def get_account_by_map(description):
    if description != '':
        for key, value in account_map.items():
            if account_map_res[key].findall(description):
                return value
    
    return Account_WeChat

# 需要跳过的交易

# 对于线上交易，跳过退款的支出和收入部分
skip_transaction_map = [
    "退款"
]

skip_transaction_res = [re.compile(key) for key in skip_transaction_map]


def skip_transaction(amount_type):
    if amount_type != '':
        for value in skip_transaction_res:
            if value.findall(amount_type):
                return True
    
    return False

class WeChat(Base):

    def __init__(self, filename, byte_content, entries, option_map):
        if not re.search(r'微信支付账单.*\.csv$', filename.name):
            raise Exception("not WeChat ,skip")
     
        content = byte_content.decode('utf-8')
        lines = content.split("\n")

        # 去除注释行，无效行
        start_lines = 0
        end_lines = 0
        for idx,line in enumerate(lines):
            if line.startswith("交易时间"):
                start_lines = idx
            
            if line != '':
                end_lines = idx


        # print('Import WeChat: ' + lines[1])
        content = "\n".join(lines[start_lines:end_lines + 1])
        self.content = content
        self.filename = filename.name
        self.line_num = end_lines - start_lines  #不再加1是为了排除标题行

        # 去重复
        self.deduplicate = Deduplicate(entries, option_map)

    def parse(self):
        content = self.content
        f = StringIO(content)
        reader = DictReaderStrip(f, delimiter=',')
        # 交易时间,交易类型,交易对方,商品,收/支,金额(元),支付方式,当前状态,交易单号,商户单号,备注
        # 2023-12-03 17:39:16,商户消费,龙头寺茶园,"74107437-1币-ID30101016",支出,¥1.00,零钱,支付成功,4200001997202312038921813515	,9001034128723337	,"/"
         #进度展示
        with tqdm(total=self.line_num) as pbar:
            pbar.set_description(f'{self.filename}:')
            
            transactions = []
            for row in reader:

                amount_status = row["当前状态"]
                if skip_transaction(amount_status):
                    # 跳过数据
                    pbar.update(1)
                    continue

                # 准备元数据

                amount_time = row['交易时间']
                amount_datetime = datetime.strptime(amount_time,"%Y-%m-%d %H:%M:%S")

                meta = {}
                meta['trade_time'] = str(amount_datetime)
                meta['timestamp'] = str(amount_datetime.timestamp()).replace('.0', '')

                meta['shop_trade_no']  = row["商户单号"].strip("\t")
                meta['wechat_trade_no'] = row["交易单号"].strip("\t")

                
                amount_type = row['交易类型']
                counterparty = row['交易对方']
                goods = row["商品"]
                amount_note = row['备注']
                description = f"{amount_type},{counterparty},{goods},{amount_note}"
                meta['note'] = description

                # print(description)


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
                        row['交易对方'],
                        description,
                        data.EMPTY_SET,
                        data.EMPTY_SET, []
                    )

                # 银行账户，支出/收入都会是银行的账户
                account2 = get_account_by_map(row['支付方式'])
                price = row['金额(元)'].strip("¥")

                #支出
                if row['收/支'] in ('支出'):
                    account = get_account_by_guess(counterparty, description, amount_datetime)
                    if account == "Expenses:Unknown":
                        entry = entry._replace(flag='!')

                    # 金额为正，写入到支出的账户中
                    data.create_simple_posting(entry, account, price, 'CNY')
                    data.create_simple_posting(entry, account2, f"-{price}",'CNY')

                #收入
                elif row['收/支'] in ('收入'):
                    income = get_income_account_by_guess(counterparty, description, amount_datetime)
                    if income == 'Income:Unknown':
                        entry = entry._replace(flag='!')

                    # 金额为正，写入到微信的账户中
                    data.create_simple_posting(entry, account2, price,'CNY')
                    data.create_simple_posting(entry, income, f"-{price}", 'CNY')

                else:
                    print("非收入/支出")
                    pass

            
                #去重
                amount = float(price)
                if not self.deduplicate.find_duplicate(entry, amount,"wechat_trade_no"):
                    transactions.append(entry)
                pbar.update(1)
        # self.deduplicate.apply_beans()
        return transactions
