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
import pandas as pd
from io import StringIO
from tqdm import tqdm
from decimal import Decimal

Account中信信用卡 = 'Liabilities:CreditCard:CITIC:3995'

account_map = {
    # "招商":"Assets:Bank:CMB:3007"
}

account_map_res = dict([(key, re.compile(key)) for key in account_map])

def get_account_by_map(description):
    if description != '':
        for key, value in account_map.items():
            if account_map_res[key].findall(description):
                return value
    
    return Account中信信用卡

# 需要跳过的交易

# 还款使用的中信储蓄卡，会在储蓄卡和信用卡中记录两笔，信用卡的还款记录就需要跳过
skip_transaction_map = [
    "中信银行移动银行",
    "本行自动还款",
]

skip_transaction_res = [re.compile(key) for key in skip_transaction_map]


def skip_transaction(amount_type):
    if amount_type != '':
        for value in skip_transaction_res:
            if value.findall(amount_type):
                return True
    
    return False

class CITICCredit(Base):

    def __init__(self, filename, byte_content, entries, option_map):
        if not re.search(r'.*账单明细.*\.xls$', filename.name):
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
            if line.startswith("账号"):
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
        # 账号	                 交易日期	  记账日期	  交易描述	        参考编号	          交易币种	结算金额	交易代码	结算币种	交易金额
        # 622918 **** ** 3995	20240818	20240818	财付通－永辉生活		               人民币	   44.40	 1005	    人民币	   44.40
        # 622918 **** ** 3995	20240820	20240820	财付通－重庆兴红得聪餐饮管理有限公…		人民币	    19.88	   1005	      人民币	19.88
        # 622918 **** ** 3995	20240902	20240902	财付通－重庆医科大学附属儿童医院		人民币	    -15.00	   1006	      人民币	-15.00
        # 622918 **** ** 3995	20240905	20240905	本行自动还款	  99999999	          人民币	-113.00	     8600	    人民币	  -113.00

        with tqdm(total=self.line_num) as pbar:
            pbar.set_description(f'{self.filename}')
            transactions = []
            for row in reader:
                amount_note = row['交易描述']
                # 跳过数据
                if skip_transaction(amount_note):
                    pbar.update(1)
                    continue

                # 准备元数据
                amount_datetime = parser.parse(row['交易日期'])

                meta = {}
                meta['trade_time'] = str(amount_datetime)
                meta['timestamp'] = str(amount_datetime.timestamp()).replace('.0', '')

                meta['shop_trade_no'] = ''
                # meta['alipay_trade_no'] #无

            
                description = f"{amount_note}"
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
                account_citic_credit = Account中信信用卡

                price = Decimal(row["交易金额"])
                amount_out  = True if price >= 0 else False
                #支出
                if amount_out:
                    # 靠支付宝获取其他信息
                    account = get_account_by_guess('', description, amount_datetime)
                    if account == "Expenses:Unknown":
                        entry = entry._replace(flag='!')

                    # 支出，金额写到Expenses账户
                    data.create_simple_posting(entry, account_citic_credit, -price,'CNY')
                    data.create_simple_posting(entry, account, price, 'CNY')

                #收入
                else:
                    income = get_income_account_by_guess('', description, amount_datetime)
                    if income == 'Income:Unknown':
                        entry = entry._replace(flag='!')

                    # 收入，金额写到收入账户
                    data.create_simple_posting(entry, income, price, 'CNY')
                    data.create_simple_posting(entry, account_citic_credit, -price,'CNY')

                #银行卡不去重
                amount = float(price)
                transactions.append(entry)
                    

                pbar.update(1)
        # self.deduplicate.apply_beans()
        return transactions
