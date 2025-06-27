import calendar
import csv
import re
from zipfile import ZipFile
from datetime import datetime,date
from io import StringIO, BytesIO

# import dateparser
from dateutil import parser
from beancount.core import data
from beancount.core.data import Note, Transaction

from . import (DictReaderStrip, get_account_by_guess,
               get_income_account_by_guess)
from .base import Base
from .deduplicate import Deduplicate
import logging
from tqdm import tqdm

Account招商 = 'Assets:Bank:CMB:3007'

account_map = {
    "招商":"Assets:Bank:CMB:3007"
}

account_map_res = dict([(key, re.compile(key)) for key in account_map])

def get_account_by_map(description):
    if description != '':
        for key, value in account_map.items():
            if account_map_res[key].findall(description):
                return value
    
    return Account招商

# 需要跳过的交易

# 对于支付宝等线上交易，通过支付宝，微信拉取交易信息
skip_transaction_map = [
    "(网联|银联在线支付|银联快捷支付)",  #支付宝支付，退款使用的网联/银联快捷支付，拼多多使用的银联在线支付
    "冲补账处理"            #拼多多退款使用的冲补账处理
]

skip_transaction_res = [re.compile(key) for key in skip_transaction_map]


def skip_transaction(amount_type):
    if amount_type != '':
        for value in skip_transaction_res:
            if value.findall(amount_type):
                return True
    
    return False

class CMB(Base):

    def __init__(self, filename, byte_content, entries, option_map):
        if not re.search(r'CMB.*\.csv$', filename.name):
            raise Exception("not 招商 ,skip")
     
        content = byte_content.decode('utf-8')
        lines = content.split("\n")

        # 去除注释行，无效行
        start_lines = 0
        end_lines = 0
        for idx,line in enumerate(lines):
            if line.startswith("交易日期"):
                start_lines = idx
            
            if (not line.startswith("#")) and (line != '') and (line != '\r'):
                end_lines = idx
            

        # print('Import CMB: ' + lines[0])
        content = "\n".join(lines[start_lines:end_lines+1])
        # logging.error(f"{lines[end_lines+1]}")
        self.content = content
        self.line_num = end_lines - start_lines
        self.filename = filename.name

        # 去重复
        self.deduplicate = Deduplicate(entries, option_map)

    def check_none(self,row):
        # 检查字典中值是不是都存在
        one_is_present = False
        for key, value in row.items():
            if key in ["交易日期","交易时间"]:
                if value is None or value == '':  # 添加对空列表和空字典的判断
                    return False
            elif key in ["收入","支出"]:
                if value != '':
                    one_is_present = True

        return one_is_present  
                

    def parse(self):
        content = self.content
        f = StringIO(content)
        reader = DictReaderStrip(f, delimiter=',')
        # 交易日期,交易时间,收入,支出,余额,交易类型,交易备注
        # "	20231203","	12:56:16","","64.91","221455.46","	银联在线支付","	银联在线支付，（特约）拼多多"
        
                #进度展示
        with tqdm(total=self.line_num) as pbar:
            pbar.set_description(f'{self.filename}')

            transactions = []
            for row in reader:

                if not self.check_none(row):
                    pbar.update(1)
                    continue
                
                amount_type = row['交易类型'].strip("\t")
                # 跳过数据
                # if skip_transaction(amount_type):
                #     pbar.update(1)
                #     continue

                # 准备元数据

                amount_date = row['交易日期'].strip("\t")
                amount_time = row['交易时间'].strip("\t")
                amount_datetime = parser.parse(f"{amount_date} {amount_time}")

                meta = {}
                meta['trade_time'] = str(amount_datetime)
                meta['timestamp'] = str(amount_datetime.timestamp()).replace('.0', '')

                # meta['shop_trade_no']  #无
                # meta['alipay_trade_no'] #无

                
                amount_note = row['交易备注'].strip("\t")
                description = f"{amount_type},{amount_note}"
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
                account2 = Account招商

                amount_out  = True if row["支出"] != "" else False
                price = row['支出'] if amount_out else row['收入']
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

                #银行账单不去重
                amount = float(price)
                transactions.append(entry)

                pbar.update(1)
        # self.deduplicate.apply_beans()
        return transactions
